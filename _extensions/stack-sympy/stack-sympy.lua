-- Quarto HTML filter for trusted, authored STACK question XML.
-- stack-sympy is a part of CTM Assessment: its library ctm-libs (the Python
-- runtime, AI feedback) is found by the canonical bootstrap, which stops the
-- render with the install command when CTM Assessment is missing. The STACK
-- engine is ctm-checkers' (ctm_checkers.stack), which ctm-libs finds
-- (ctm.checkers): its wheels at build time, its page scripts in the browser.
local ctm = dofile(quarto.utils.resolve_path('ctm-bootstrap.lua'))('stack-sympy')
local installed = false
local sequence = 0
local feedbackRequested = false
local feedback = nil
local documentLanguage = 'en'

local function fail(message)
  -- Quarto replaces the global error() with a logger that lets the render
  -- continue; an unsupported question must stop the render rather than ship
  -- as an empty card, so fail through assert.
  assert(false, message)
end

local function escape(s)
  return tostring(s):gsub('&', '&amp;'):gsub('<', '&lt;'):gsub('>', '&gt;'):gsub('"', '&quot;')
end

-- This extension's version (its _extension.yml), for its HTML dependency.
local function extensionVersion()
  local f = io.open(quarto.utils.resolve_path('_extension.yml'), 'r')
  local version = f and f:read('*a'):match('\nversion:%s*[\'"]?([%w%.%-]+)')
  if f then f:close() end
  return version or '0'
end

-- ctm-checkers with its STACK engine, once per page: an older ctm-libs has
-- no ctm.checkers, and ctm.checkers.require stops the render when
-- ctm-checkers is missing or has another API level, each with the command
-- that fixes it.
local INSTALL = 'quarto add https://erasmus-ctm.github.io/ctm-assessment/ctm-assessment.tar.gz'
local checkersReady = false
local function requireCheckers()
  if checkersReady then return end
  if not ctm.checkers then
    fail('stack-sympy ' .. extensionVersion() .. ' needs ctm-checkers, which the ctm-libs in ' .. ctm.dir
      .. ' does not provide. Update CTM Assessment: ' .. INSTALL)
  end
  ctm.checkers.require('stack-sympy', 1)
  checkersReady = true
end

local function readFile(path)
  local file, reason = io.open(path, 'rb')
  if not file then fail('stack-sympy: could not read source ' .. path .. ': ' .. tostring(reason)) end
  local contents = file:read('*a')
  file:close()
  return contents
end

local function authoredSource(block)
  -- Pandoc provides the authored body and attributes, but normalizes the
  -- outer fence. Choose a fence that cannot close within the body.
  local longest = 0
  for ticks in block.text:gmatch('`+') do longest = math.max(longest, #ticks) end
  local fence = string.rep('`', math.max(3, longest + 1))
  local attributes = {'.stack-question'}
  if block.identifier ~= '' then table.insert(attributes, '#' .. block.identifier) end
  for _, class in ipairs(block.classes) do
    if class ~= 'stack-question' then table.insert(attributes, '.' .. class) end
  end
  for key, value in pairs(block.attributes) do
    if not key:match('^data%-ai%-feedback%-') then
      table.insert(attributes, key .. '="' .. value:gsub('\\', '\\\\'):gsub('"', '\\"') .. '"')
    end
  end
  return fence .. '{' .. table.concat(attributes, ' ') .. '}\n' .. block.text .. '\n' .. fence
end

local function sourcePanel(label, language, source)
  return '<details class="stack-source"><summary>' .. label .. '</summary>' ..
    '<pre><code class="language-' .. language .. '">' .. escape(source) .. '</code></pre></details>'
end

-- Scripts and styles as cacheable HTML dependencies, once per page: ctm-libs'
-- Python runtime (MathExerciseRuntime) and ctm-checkers' page scripts with
-- the STACK engine in the head (the grading worker loads them by their
-- URLs), then this extension's styles and scripts.
local function setup()
  if installed then return end
  installed = true
  requireCheckers()
  ctm.runtime.use()
  ctm.checkers.use('stack')
  quarto.doc.add_html_dependency({
    name = 'stack-sympy', version = extensionVersion(),
    scripts = {{path = 'vendor/matrix-input.js', afterBody = true}, {path = 'stack-sympy.js', afterBody = true}},
    stylesheets = {'vendor/matrix-input.css', 'stack-sympy.css'},
    resources = {
      {name = 'worker.js', path = 'worker.js'}
    }
  })
end

local function options(text)
  local opts = {}
  for line in (text .. '\n'):gmatch('([^\r\n]*)\n') do
    local key, value = line:match('^#|%s*([%w_-]+):%s*(.-)%s*$')
    if key then opts[key] = value
    elseif line:match('%S') then fail('stack-sympy: only #| key: value lines are allowed in a stack-question block') end
  end
  return opts
end

local function booleanOption(opts, name)
  local v = opts[name]
  if v == nil or v == 'false' then return false end
  if v == 'true' then return true end
  fail('stack-sympy: ' .. name .. ' must be true or false')
end

local function integerOption(opts, name, default, minimum, maximum)
  local value = opts[name] or tostring(default)
  local n = tonumber(value)
  if not n or n ~= math.floor(n) or n < minimum or n > maximum then
    fail('stack-sympy: ' .. name .. ' must be an integer from ' .. minimum .. ' to ' .. maximum)
  end
  return n
end

local function render(block)
  if not block.classes:includes('stack-question') then return nil end
  if not quarto.doc.is_format('html:js') then
    fail('stack-sympy: interactive questions require HTML output')
  end
  local opts = options(block.text)
  if not opts.file or opts.file == '' then fail('stack-sympy: #| file: is required') end
  if not opts.question or opts.question == '' then fail('stack-sympy: #| question: is required') end
  local variants = integerOption(opts, 'variants', 1, 1, 20)
  local seed = integerOption(opts, 'seed', 1, -2147483648, 2147483647)
  local review = booleanOption(opts, 'review')
  local diagnostics = booleanOption(opts, 'diagnostics')
  -- AI feedback when the card asks for it and the build has it (S-15).
  local useFeedback = feedbackRequested and booleanOption(opts, 'feedback')
  sequence = sequence + 1
  local identifier = block.identifier ~= '' and block.identifier or ('stack-sympy-' .. sequence)
  requireCheckers()
  -- Author paths are relative to the QMD, unlike extension asset paths.
  local inputPath = pandoc.path.is_absolute(opts.file) and opts.file
    or pandoc.path.normalize(pandoc.path.join({pandoc.path.directory(quarto.doc.input_file), opts.file}))
  local python = os.getenv('STACK_SYMPY_PYTHON') or 'python3'
  local args = {'-m', 'ctm_checkers.stack.cli', 'render', '--errors-to-stdout', '--file', inputPath,
    '--question', opts.question, '--id', identifier,
    '--variants', tostring(variants), '--seed', tostring(seed)}
  if opts['python-checkers'] then
    local checkerPath = pandoc.path.is_absolute(opts['python-checkers']) and opts['python-checkers']
      or pandoc.path.normalize(pandoc.path.join({pandoc.path.directory(quarto.doc.input_file), opts['python-checkers']}))
    table.insert(args, '--python-checkers')
    table.insert(args, checkerPath)
  end
  if review then table.insert(args, '--review') end
  if diagnostics then table.insert(args, '--diagnostics') end
  -- ctm-checkers' wheels first on PYTHONPATH: Python imports the engine from them.
  local environment = ctm.checkers.environment(nil, 'stack')
  local ok, output = pcall(function()
    return pandoc.system.with_environment(environment, function()
      return pandoc.pipe(python, args, '')
    end)
  end)
  if not ok then
    local detail = type(output) == 'table' and (output.output or '') or tostring(output)
    if detail == '' then detail = 'Python exited without a diagnostic (code ' ..
      tostring(type(output) == 'table' and output.error_code or '?') .. ')' end
    if diagnostics then
      setup()
      return pandoc.RawBlock('html', '<section class="stack-sympy stack-diagnostic" role="alert"><strong>Question could not be rendered</strong><pre>' .. escape(detail) .. '</pre></section>')
    end
    fail('stack-sympy: could not render ' .. opts.file .. ' / ' .. opts.question .. ': ' .. detail)
  end
  setup()
  if output:find('class="stack-sympy stack-diagnostic"', 1, true) then
    return pandoc.RawBlock('html', output)
  end
  if useFeedback then
    local selectionOpts = {['feedback-policy'] = opts['feedback-policy'],
      label = opts.label and opts.label ~= '' and opts.label or identifier}
    local explanationLanguage = opts['feedback-language']
    if explanationLanguage == nil or explanationLanguage == '' then explanationLanguage = documentLanguage end
    local data = {
      context = feedback.context(block, opts, false),
      policySelection = feedback.selection(block, selectionOpts),
      language = explanationLanguage,
      uiLanguage = documentLanguage
    }
    local attr = ' data-stack-feedback="' .. escape(quarto.json.encode(data)) .. '"'
    local changed
    output, changed = output:gsub('(<section class="stack%-sympy"[^>]*)(>)', function(prefix, closing)
      return prefix .. attr .. closing
    end, 1)
    if changed ~= 1 then fail('stack-sympy: could not add feedback to question card') end
  end
  local source = authoredSource(block)
  local xml = readFile(inputPath)
  -- The shared explicit-context resolver skips this generated group. It must
  -- never collect source-panel XML or grading internals from a tagged parent.
  return pandoc.RawBlock('html', '<div class="stack-question-group ai-feedback-ignore">' .. output ..
    '<div class="stack-source-panels">' ..
    sourcePanel('Show source', 'markdown', source) ..
    sourcePanel('Show STACK source', 'xml', xml) ..
    '</div></div>')
end

-- Whether the page gets AI feedback: a card asks for it (#| feedback: true)
-- and the build has it. A build without AI feedback (ai-feedback: enabled:
-- false, CTM_FEEDBACK=off; P22) gives the cards none and names them in its
-- build message (ctm.feedback.request).
local function detect(doc)
  feedbackRequested = false
  local wanted = false
  doc:walk({CodeBlock = function(b)
    if b.classes:includes('stack-question') then
      local opts = options(b.text)
      if booleanOption(opts, 'feedback') then wanted = true end
    end
  end})
  if wanted and quarto.doc.is_format('html') then
    ctm.settings.load(doc.meta)
    feedbackRequested = ctm.feedback.request('stack-sympy', true, '#| feedback: true')
  end
  if feedbackRequested then
    feedback = ctm.feedback
  end
  return doc
end

local function transform(doc)
  if feedbackRequested then
    feedback = ctm.feedback
    -- This is idempotent when ctm-libs' filter already ran.
    doc = feedback.prepare(doc)
  end
  documentLanguage = doc.meta.lang and pandoc.utils.stringify(doc.meta.lang) or 'en'
  doc.blocks = doc.blocks:walk({CodeBlock = render})
  return doc
end

return {
  {Pandoc = detect},
  {Callout = function(c)
    if feedbackRequested then return feedback.markCallout(c) end
    return c
  end},
  {Pandoc = transform}
}

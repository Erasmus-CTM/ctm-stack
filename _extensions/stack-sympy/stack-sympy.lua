-- Quarto HTML filter for trusted, authored STACK question XML.
local installed = false
local sequence = 0
local feedbackRequested = false
local feedback = nil
local documentLanguage = 'en'

local function fail(message)
  -- Quarto logs exceptions from block handlers yet can still return success.
  -- Stop Pandoc so an unsupported question cannot silently ship as an empty card.
  io.stderr:write(message .. '\n')
  io.stderr:flush()
  os.exit(1)
end

local function escape(s)
  return tostring(s):gsub('&', '&amp;'):gsub('<', '&lt;'):gsub('>', '&gt;'):gsub('"', '&quot;')
end

local function pathFromFilter()
  return pandoc.path.directory(quarto.utils.resolve_path('stack-sympy.lua'))
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

local function setup()
  if installed then return end
  installed = true
  quarto.doc.add_html_dependency({
    name = 'stack-sympy', version = '0.1.6',
    scripts = {{path = 'stack-sympy.js', afterBody = true}},
    stylesheets = {'stack-sympy.css'},
    resources = {
      {name = 'worker.js', path = 'worker.js'},
      {name = 'runtime-sources.js', path = 'runtime-sources.js'},
      {name = 'vendor/pyodide-runtime.js', path = 'vendor/pyodide-runtime.js'}
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
  local useFeedback = booleanOption(opts, 'feedback')
  sequence = sequence + 1
  local identifier = block.identifier ~= '' and block.identifier or ('stack-sympy-' .. sequence)
  local extensionPath = pathFromFilter()
  -- Author paths are relative to the QMD, unlike extension asset paths.
  local inputPath = pandoc.path.is_absolute(opts.file) and opts.file
    or pandoc.path.normalize(pandoc.path.join({pandoc.path.directory(quarto.doc.input_file), opts.file}))
  local python = os.getenv('STACK_SYMPY_PYTHON') or 'python3'
  local args = {'-m', 'stack_sympy.cli', 'render', '--errors-to-stdout', '--file', inputPath,
    '--question', opts.question, '--id', identifier,
    '--variants', tostring(variants), '--seed', tostring(seed)}
  if review then table.insert(args, '--review') end
  if diagnostics then table.insert(args, '--diagnostics') end
  local environment = pandoc.system.environment()
  local delimiter = pandoc.system.os == 'mingw32' and ';' or ':'
  environment.PYTHONPATH = extensionPath ..
    ((environment.PYTHONPATH and environment.PYTHONPATH ~= '') and (delimiter .. environment.PYTHONPATH) or '')
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

local function detect(doc)
  feedbackRequested = false
  doc:walk({CodeBlock = function(b)
    if b.classes:includes('stack-question') then
      local opts = options(b.text)
      if booleanOption(opts, 'feedback') then feedbackRequested = true end
    end
  end})
  if feedbackRequested then
    feedback = feedback or dofile(quarto.utils.resolve_path('feedback-loader.lua'))()
  end
  return doc
end

local function transform(doc)
  if feedbackRequested then
    feedback = feedback or dofile(quarto.utils.resolve_path('feedback-loader.lua'))()
    -- This is idempotent when the explicit ai-feedback filter already ran.
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

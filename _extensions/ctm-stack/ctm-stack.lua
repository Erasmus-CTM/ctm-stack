-- CTM STACK owns the card shell; backend preparation returns data only.
local ctm = dofile(quarto.utils.resolve_path('ctm-bootstrap.lua'))('ctm-stack', {api = 2})
local installed, sequence, feedbackRequested, documentLanguage = false, 0, false, 'en'
local feedback, seenBackends, warnedDefault = nil, {}, false
local feedbackDefault = 'auto'
local function fail(message) assert(false, 'ctm-stack: ' .. message) end
local function escape(s) return tostring(s or ''):gsub('&','&amp;'):gsub('<','&lt;'):gsub('>','&gt;'):gsub('"','&quot;') end
local function json(value) return pandoc.json.encode(value):gsub('<','\\u003c'):gsub('>','\\u003e'):gsub('&','\\u0026') end
local function text(key, ...) return ctm.locale.text('ctm-stack', key, documentLanguage, ...) end
local function version()
  local f = assert(io.open(quarto.utils.resolve_path('_extension.yml'), 'r'))
  local value = f:read('*a'):match('\nversion:%s*([^%s]+)'); f:close(); return value
end
local function readFile(path)
  local f, why = io.open(path, 'rb'); if not f then fail('could not read ' .. path .. ': ' .. tostring(why)) end
  local value = f:read('*a'); f:close(); return value
end
local function requireCheckers() ctm.checkers.require('ctm-stack', '1.1') end
local function options(source)
  local opts, active = {}, nil
  for line in (source .. '\n'):gmatch('([^\r\n]*)\n') do
    local body = line:match('^#| ?(.*)$')
    if body then
      local key, value = body:match('^([%w_-]+):%s*(.-)%s*$')
      if key then opts[key] = value; active = key
      elseif active and body:match('^%s') then
        if opts[active] == '|' then opts[active] = '' end
        opts[active] = opts[active] .. (opts[active] == '' and '' or '\n') .. body:gsub('^  ', '')
      elseif body:match('%S') then fail('only #| key: value options are allowed') end
    elseif line:match('%S') then fail('only #| key: value options are allowed') end
  end
  return opts
end
local function bool(opts, key, default)
  if opts[key] == nil then return default or false end
  if opts[key] == 'true' then return true end
  if opts[key] == 'false' then return false end
  fail(key .. ' must be true or false')
end
local function integer(opts, key, default, low, high)
  local n = tonumber(opts[key] or default)
  if not n or n ~= math.floor(n) or n < low or n > high then fail(key .. ' must be an integer from ' .. low .. ' to ' .. high) end
  return n
end
local function authoredPath(path)
  return pandoc.path.is_absolute(path) and path or pandoc.path.normalize(pandoc.path.join({pandoc.path.directory(quarto.doc.input_file), path}))
end
local function setup()
  if installed then return end
  installed = true; requireCheckers()
  ctm.runtime.worker(); ctm.checkers.use('stack'); ctm.locale.use('ctm-stack'); ctm.matrix.use()
  ctm.deps.html({name = 'ctm-ui', stylesheets = {'ui/ctm-ui.css'}})
  quarto.doc.add_html_dependency({name = 'ctm-stack', version = version(),
    scripts = {{path = 'ctm-stack.js', afterBody = true}}, stylesheets = {'ctm-stack.css'},
    resources = {{name = 'backends/sympy.js', path = 'backends/sympy.js'}}})
end
local function authoredSource(block)
  local longest=0; for ticks in block.text:gmatch('`+') do longest=math.max(longest,#ticks) end
  local fence=string.rep('`',math.max(3,longest+1)); local attrs={'.stack-question'}
  if block.identifier ~= '' then attrs[#attrs+1]='#' .. block.identifier end
  for _,class in ipairs(block.classes) do if class ~= 'stack-question' then attrs[#attrs+1]='.' .. class end end
  for key,value in pairs(block.attributes) do
    if not key:match('^data%-ai%-feedback%-') and not key:match('^__ctm') then
      attrs[#attrs+1]=key .. '="' .. escape(value) .. '"'
    end
  end
  return fence .. '{' .. table.concat(attrs,' ') .. '}\n' .. block.text .. '\n' .. fence
end
local function sourcePanel(label, language, source)
  return '<details class="stack-source"><summary>' .. escape(label) .. '</summary><pre><code class="language-'
    .. language .. '">' .. escape(source) .. '</code></pre></details>'
end
local function render(block)
  if not block.classes:includes('stack-question') then return nil end
  if not quarto.doc.is_format('html:js') then fail('interactive questions require HTML output') end
  local opts = options(block.text)
  if not opts.file or opts.file == '' then fail('#| file: is required') end
  if not opts.question or opts.question == '' then fail('#| question: is required') end
  local cas = opts.cas or ctm.settings.choice('stack','cas',{'sympy','maxima'},{default='sympy'})
  if cas ~= 'sympy' and cas ~= 'maxima' then fail('cas must be sympy or maxima') end
  -- This is the build registry. The card controller has no backend branch.
  if cas == 'maxima' then fail('the Maxima backend is not available yet') end
  if not opts.cas and not ctm.settings.string('stack','cas') and not warnedDefault then
    warnedDefault = true; quarto.log.info('ctm-stack: default CAS: sympy (provisional)')
  end
  if not seenBackends[cas] and next(seenBackends) then quarto.log.info('ctm-stack: this page mixes STACK backends') end
  local firstBackend = not seenBackends[cas]; seenBackends[cas] = true
  requireCheckers(); setup(); sequence = sequence + 1
  local identifier = opts.label or (block.identifier ~= '' and block.identifier) or ('ctm-stack-' .. sequence)
  local file = authoredPath(opts.file)
  local args = {'-m','ctm_checkers.stack.cli','prepare','--file',file,'--question',opts.question,'--id',identifier,
    '--variants',tostring(integer(opts,'variants',1,1,100)), '--seed',tostring(integer(opts,'seed',1,-2147483648,2147483647))}
  if opts['python-checkers'] then args[#args+1] = '--python-checkers'; args[#args+1] = authoredPath(opts['python-checkers']) end
  if bool(opts,'review') then args[#args+1] = '--review' end
  local ok, output = pcall(function()
    return pandoc.system.with_environment(ctm.checkers.environment(nil,'stack'), function()
      return pandoc.pipe(os.getenv('CTM_STACK_PYTHON') or os.getenv('STACK_SYMPY_PYTHON') or 'python3', args, '')
    end)
  end)
  if not ok then
    local detail = type(output) == 'table' and (output.output or tostring(output.error_code)) or tostring(output)
    if bool(opts,'diagnostics') then
      return pandoc.RawBlock('html','<section class="ctm-stack stack-diagnostic" role="alert"><strong>'
        .. escape(text('unsupportedQuestion')) .. '</strong><pre>' .. escape(detail) .. '</pre></section>')
    end
    fail('could not prepare ' .. opts.file .. ' / ' .. opts.question .. ': ' .. detail)
  end
  local payload = pandoc.json.decode(output)
  assert(payload.version == 2 and payload.variants and #payload.variants > 0, 'ctm-stack: backend prepare requires payload version 2 with variants')
  local attrs = ' class="ctm-stack" data-stack-id="' .. escape(identifier) .. '" data-backend="' .. cas
    .. '" data-lang="' .. documentLanguage .. '" data-stop-after="' .. tostring(ctm.runtime.stopAfter('stack')) .. '"'
  local validation = opts.validation or ctm.settings.choice('stack','validation',{'instant','button'},{default='instant'})
  if validation ~= 'instant' and validation ~= 'button' then fail('validation must be instant or button') end
  -- SymPy's bounded/cancellable automatic-validation admission is not shipped.
  attrs = attrs .. ' data-validation="button"'
  local useFeedback = feedbackRequested and (opts.feedback or feedbackDefault) ~= 'false'
  if opts.feedback and opts.feedback ~= 'true' and opts.feedback ~= 'false' and opts.feedback ~= 'auto' then fail('feedback must be auto, true or false') end
  if useFeedback then
    local selectionOpts = {['feedback-policy']=opts['feedback-policy'], label=opts.label or identifier}
    attrs = attrs .. ' data-stack-feedback="' .. escape(quarto.json.encode({
      context=feedback.context(block,opts,false), policySelection=feedback.selection(block,selectionOpts),
      language=opts['feedback-language'] or documentLanguage, uiLanguage=documentLanguage})) .. '"'
  end
  local save = opts.save or ctm.settings.choice('stack','save',{'answers','none'},{shared=true,default='answers'})
  if ctm.ui and ctm.ui.exercise then
    local record = ctm.ui.exercise{component='ctm-stack',id=opts.label or block.identifier,block=block,
      source=pandoc.utils.sha1(block.text):sub(1,16),save=save}
    for key,value in pairs(record.attributes or {}) do attrs = attrs .. ' ' .. key .. '="' .. escape(value) .. '"' end
  end
  local choices = {}
  for index,_ in ipairs(payload.variants) do choices[#choices+1] = '<option value="' .. (index-1) .. '">' .. escape(text('variantChoice',index)) .. '</option>' end
  local toolbar = '<div class="stack-toolbar"><label>' .. escape(text('variantLabel'))
    .. '<select class="stack-variant" aria-label="' .. escape(text('variantAriaLabel')) .. '">' .. table.concat(choices) .. '</select></label></div>'
  local buttons = '<button type="button" class="stack-validate">' .. escape(text('validateButton')) .. '</button>'
    .. '<button type="button" class="stack-check" disabled>' .. escape(text('checkButton')) .. '</button>'
    .. (payload.review and '<button type="button" class="stack-tests">' .. escape(text('testsButton')) .. '</button>' or '')
  local descriptor = firstBackend and '<script type="application/json" class="ctm-stack-backend" data-backend="' .. cas .. '">'
    .. json({id=cas,version=ctm.checkers.require('ctm-stack','1.1').version,adapter='backends/sympy.js',requires={isolation=false}}) .. '</script>' or ''
  local sourcePanels = bool(opts,'source-panels',ctm.settings.bool('stack','source-panels',{default=false}))
  local source = sourcePanels and '<div class="stack-source-panels">'
    .. sourcePanel(text('showSource'),'markdown',authoredSource(block))
    .. sourcePanel(text('showStackSource'),'xml',readFile(file)) .. '</div>' or ''
  local mathjax = ctm.assets and ctm.assets.url('mathjax3','es5/tex-chtml.js') or 'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js'
  return pandoc.RawBlock('html','<div class="stack-question-group ai-feedback-ignore">' .. descriptor
    .. '<section' .. attrs .. ' data-mathjax="' .. escape(mathjax) .. '">' .. toolbar
    .. '<div class="stack-prompt stack-question">' .. payload.variants[1].display.question_html .. '</div><div class="stack-actions">' .. buttons
    .. '</div><div class="stack-result" aria-live="polite"></div><div class="stack-generalfeedback" hidden></div>'
    .. '<script type="application/json" class="ctm-stack-data">' .. json(payload) .. '</script></section>' .. source .. '</div>')
end
local function detect(doc)
  ctm.settings.load(doc.meta); documentLanguage = ctm.locale.resolve('ctm-stack')
  local wanted, explicit = false, false
  local setting, origin = ctm.settings.choice('stack','feedback',{'auto','true','false'},{default='auto'})
  feedbackDefault = setting
  doc:walk({CodeBlock=function(b) if b.classes:includes('stack-question') then
    local opts=options(b.text); if opts.feedback == 'true' then explicit=true end; if opts.feedback ~= 'false' and setting ~= 'false' or opts.feedback == 'true' then wanted = true end
  end end})
  feedbackRequested = wanted and ctm.feedback.enabled()
  if explicit then feedbackRequested = ctm.feedback.request('ctm-stack',wanted,'#| feedback: true')
  elseif setting == 'true' then feedbackRequested = ctm.feedback.request('ctm-stack',wanted,'feedback: true' .. (origin and ' in ' .. origin or '')) end
  feedback = ctm.feedback
  return doc
end
return {{Pandoc=detect},{Callout=function(c) return feedbackRequested and feedback.markCallout(c) or c end},
  {Pandoc=function(doc)
    if feedbackRequested then doc=feedback.prepare(doc) end
    doc.blocks=doc.blocks:walk({CodeBlock=render})
    if ctm.ui and ctm.ui.finalize then doc=ctm.ui.finalize(doc) end
    return doc
  end}}

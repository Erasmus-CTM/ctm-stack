-- Locate one project installation of the shared extension. STACK does not
-- bundle, fork or load a second copy of the feedback runtime.
local function sharedFeedback()
  local base = quarto.project.directory or pandoc.path.directory(quarto.doc.input_file)
  while base and base ~= '' do
    local extensions = pandoc.path.join({base, '_extensions'})
    local candidates = {pandoc.path.join({extensions, 'ai-feedback', 'feedback-quarto.lua'})}
    local ok, entries = pcall(pandoc.system.list_directory, extensions)
    if ok then
      for _, owner in ipairs(entries) do
        table.insert(candidates, pandoc.path.join({extensions, owner, 'ai-feedback', 'feedback-quarto.lua'}))
      end
    end
    local found = {}
    for _, path in ipairs(candidates) do
      local file = io.open(path, 'r')
      if file then file:close(); table.insert(found, path) end
    end
    assert(#found <= 1, 'Multiple ai-feedback installations found; keep one project installation.')
    if #found == 1 then
      local manifest = io.open(pandoc.path.join({pandoc.path.directory(found[1]), '_extension.yml'}), 'r')
      local metadata = manifest and manifest:read('*a') or ''
      if manifest then manifest:close() end
      local major, minor = metadata:match('version:%s*["\']?(%d+)%.(%d+)')
      assert(major and (tonumber(major) > 0 or tonumber(minor) >= 8),
        'STACK feedback requires ai-feedback 0.8.0 or later and Quarto 1.8.27 or later. Run: quarto add Erasmus-CTM/ai-feedback')
      local shared = dofile(found[1])
      assert(shared.selection and shared.prepare and shared.context and shared.markCallout,
        'STACK feedback requires ai-feedback 0.8.0 or later. Run: quarto add Erasmus-CTM/ai-feedback')
      return shared
    end
    if quarto.project.directory then break end
    local parent = pandoc.path.directory(base)
    if parent == base then break end
    base = parent
  end
  error('STACK feedback requires the shared extension. Run: quarto add Erasmus-CTM/ai-feedback')
end
return sharedFeedback

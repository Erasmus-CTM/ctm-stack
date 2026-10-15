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
      local shared = dofile(found[1])
      assert(shared.selection and shared.prepare and shared.context and shared.markCallout,
        'STACK feedback requires ai-feedback 0.6.0 or later. Run: quarto add Erasmus-CTM/ai-feedback')
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

/* Grading runs in a disposable Worker: a timeout terminates runaway symbolic
 * calculations without freezing the student-facing page. */
'use strict';
importScripts('vendor/pyodide-runtime.js', 'runtime-sources.js');
var ready;
async function prepare() {
  if (ready) return ready;
  ready = (async function () {
    var py = await MathExerciseRuntime.ensurePyodide();
    await py.loadPackage('sympy');
    var files = globalThis.STACK_SYMPY_SOURCES;
    if (!files || !files['stack_sympy/__init__.py']) throw new Error('Bundled Python source is missing. Rebuild runtime-sources.js.');
    py.FS.mkdirTree('/home/pyodide/stack_sympy');
    Object.keys(files).forEach(function (path) {
      py.FS.writeFile('/home/pyodide/' + path, files[path]);
    });
    await py.runPythonAsync("import sys\nif '/home/pyodide' not in sys.path: sys.path.insert(0, '/home/pyodide')\nimport stack_sympy.engine");
    return py;
  })();
  ready.catch(function () { ready = null; });
  return ready;
}
self.onmessage = async function (event) {
  var msg = event.data;
  try {
    var py = await prepare();
    py.globals.set('_stack_request', JSON.stringify(msg));
    var result = await py.runPythonAsync([
      'import json',
      'from stack_sympy.engine import grade, validate, run_question_tests',
      '_request = json.loads(_stack_request)',
      'if _request["type"] == "grade":',
      '    _result = grade(_request["question"], _request["answers"], variant=_request["variant"])',
      'elif _request["type"] == "validate":',
      '    _result = validate(_request["question"], _request["answers"], variant=_request["variant"])',
      'elif _request["type"] == "tests":',
      '    _result = run_question_tests(_request["question"], seeds=[_request["variant"]["seed"]], variants=[_request["variant"]])',
      'else:',
      '    raise ValueError("Unknown worker request")',
      'json.dumps(_result, default=str)'
    ].join('\n'));
    self.postMessage({ id: msg.id, ok: true, result: JSON.parse(result) });
  } catch (error) {
    self.postMessage({ id: msg.id, ok: false, error: String(error && error.message || error) });
  }
};

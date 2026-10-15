/* Independent parity harness: execute the same Python adapter in the real
 * browser Pyodide runtime as the student-facing worker. */
'use strict';
importScripts('/_extensions/stack-sympy/vendor/pyodide-runtime.js',
              '/_extensions/stack-sympy/runtime-sources.js');

let py;
let loadedVersions;
async function initialize() {
  if (py) return loadedVersions;
  const instance = await MathExerciseRuntime.ensurePyodide();
  await instance.loadPackage('sympy');
  const sources = globalThis.STACK_SYMPY_SOURCES;
  if (!sources || !sources['stack_sympy/assessment.py']) {
    throw new Error('The committed browser Python bundle is missing');
  }
  instance.FS.mkdirTree('/home/pyodide/stack_sympy');
  for (const [name, source] of Object.entries(sources)) {
    instance.FS.writeFile('/home/pyodide/' + name, source);
  }
  instance.FS.mkdirTree('/home/pyodide/native_compliance');
  instance.FS.writeFile('/home/pyodide/native_compliance/__init__.py', '');
  for (const name of ['common.py', 'python_runner.py']) {
    const response = await fetch('/scripts/native_compliance/' + name);
    if (!response.ok) throw new Error('Cannot load parity module ' + name + ': HTTP ' + response.status);
    instance.FS.writeFile('/home/pyodide/native_compliance/' + name, await response.text());
  }
  const versions = JSON.parse(await instance.runPythonAsync([
    'import json, sys, sympy',
    "sys.path.insert(0, '/home/pyodide')",
    'from native_compliance.python_runner import evaluate_case',
    'json.dumps({"sympy_version": sympy.__version__})'
  ].join('\n')));
  const pinnedVersion = MathExerciseRuntime.indexURL.match(/\/v([^/]+)\/full\/$/)[1];
  if (typeof instance.version === 'string' && instance.version !== pinnedVersion) {
    throw new Error('Loaded Pyodide version does not match pinned bootstrap');
  }
  versions.pyodide_version = pinnedVersion;
  py = instance;
  loadedVersions = versions;
  return loadedVersions;
}

self.onmessage = async function (event) {
  const {id, type, item} = event.data;
  try {
    if (type === 'init') {
      const versions = await initialize();
      self.postMessage({id, ok: true, result: versions});
    } else if (type === 'evaluate') {
      if (!py) throw new Error('Pyodide worker was not initialized');
      py.globals.set('_parity_case_json', JSON.stringify(item));
      const result = await py.runPythonAsync([
        'import json',
        'from native_compliance.python_runner import evaluate_case',
        'json.dumps(evaluate_case(json.loads(_parity_case_json)), ensure_ascii=True)'
      ].join('\n'));
      self.postMessage({id, ok: true, result: JSON.parse(result)});
    } else {
      throw new Error('Unknown parity worker request: ' + type);
    }
  } catch (error) {
    self.postMessage({id, ok: false, error: String(error && error.stack || error)});
  }
};

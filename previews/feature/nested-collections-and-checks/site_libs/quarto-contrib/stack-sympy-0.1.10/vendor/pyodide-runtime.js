// Shared classic-script bootstrap for math-exercise and stack-sympy.
// Keep the vendored copy in stack-sympy byte-identical to this file.
(function (root) {
  'use strict';

  if (root.MathExerciseRuntime) return;

  var indexURL = 'https://cdn.jsdelivr.net/pyodide/v0.27.2/full/';

  function loadScript(src) {
    if (src === indexURL + 'pyodide.js' && typeof root.loadPyodide === 'function') {
      return Promise.resolve();
    }

    if (typeof document === 'undefined') {
      if (typeof root.importScripts !== 'function') {
        return Promise.reject(new Error('Cannot load Pyodide: no document or importScripts'));
      }
      try {
        root.importScripts(src);
        return Promise.resolve();
      } catch (error) {
        return Promise.reject(error);
      }
    }

    return new Promise(function (resolve, reject) {
      var script = document.querySelector('script[src="' + src + '"]');
      if (script && script.dataset.qLoaded === '1') { resolve(); return; }

      function loaded() {
        script.dataset.qLoaded = '1';
        resolve();
      }
      function failed() {
        // A failed tag must not trap a later attempt waiting for an event that
        // will never fire. This also permits a retry after a temporary outage.
        if (typeof script.remove === 'function') script.remove();
        reject(new Error('Failed to load: ' + src));
      }

      if (script) {
        script.addEventListener('load', loaded, { once: true });
        script.addEventListener('error', failed, { once: true });
        return;
      }
      script = document.createElement('script');
      script.src = src;
      script.onload = loaded;
      script.onerror = failed;
      document.head.appendChild(script);
    });
  }

  async function ensurePyodide() {
    // Some Quarto integrations declare these with top-level `let`, which is
    // visible to classic scripts but is not a property of globalThis.
    var coatless = typeof qpyodideInstance !== 'undefined'
      ? qpyodideInstance : root.qpyodideInstance;
    if (typeof coatless !== 'undefined') {
      root.mainPyodide = await coatless;
      return root.mainPyodide;
    }
    var existing = typeof mainPyodide !== 'undefined'
      ? mainPyodide : root.mainPyodide;
    if (typeof existing !== 'undefined') {
      root.mainPyodide = await existing;
      return root.mainPyodide;
    }

    // Share the in-flight initialization with all consumers on this page or
    // worker. Install the promise before either extension can start another.
    if (!root.__qExercisePyodide) {
      root.__qExercisePyodide = (async function () {
        await loadScript(indexURL + 'pyodide.js');
        return root.loadPyodide({ indexURL: indexURL });
      })();
    }
    var pending = root.__qExercisePyodide;
    try {
      root.mainPyodide = await pending;
      return root.mainPyodide;
    } catch (error) {
      if (root.__qExercisePyodide === pending) root.__qExercisePyodide = undefined;
      throw error;
    }
  }

  root.MathExerciseRuntime = {
    indexURL: indexURL,
    loadScript: loadScript,
    ensurePyodide: ensurePyodide
  };
})(globalThis);

/* Page-side SymPy adapter. It owns only its unpublished CTMWorker. */
(function (root) {
  'use strict';
  var registry = root.CTMStackAdapters = root.CTMStackAdapters || {};
  registry.sympy = function () {
    var runtime = null, ready = null, epoch = 0;
    function failure(error) {
      return {kind: 'runtime', code: error.code || 'stack-runtime', message: String(error.message || error), restarted: !!error.restarted};
    }
    // Bound preparation as well as interpreter initialization. A late completion
    // after a timeout must neither publish nor replace a later backend session.
    function install(started) {
      var token = ++epoch, proxy, timer;
      var R = root.MathExerciseRuntime;
      function current(py) {
        if (token === epoch) return;
        if (py && py.terminate) py.terminate('Superseded backend startup');
        throw new Error('Superseded backend startup');
      }
      var loading = Promise.resolve(started).then(async function (py) {
        proxy = py; current(py);
        await py.loadPackage('sympy'); current(py);
        await R.ensureCheckers(py, root.CTMCheckersStack); current(py);
        runtime = py; return py;
      });
      var limit = new Promise(function (_, reject) {
        timer = setTimeout(function () {
          var error = new Error('Python did not finish loading. Try again.'); error.code = 'pyodide-timeout'; reject(error);
        }, R.loadTimeout);
      });
      ready = Promise.race([loading, limit]).catch(function (error) {
        if (proxy && proxy.terminate) proxy.terminate(error);
        if (token === epoch) { epoch++; ready = null; runtime = null; }
        throw error;
      }).finally(function () { clearTimeout(timer); });
      return ready;
    }
    function start() {
      if (ready) return ready;
      var R = root.MathExerciseRuntime, worker = root.CTMWorker;
      if (!R || !worker || !root.CTMCheckersStack) return Promise.reject(new Error('The grader is missing on this page.'));
      return install(Promise.resolve().then(function () {
        return worker.start({indexURL: R.indexURL, publish: false, loadTimeout: R.loadTimeout,
          onRestart: function (started) { runtime = null; install(started); }});
      }));
    }
    return {
      isolationRequired: false,
      start: start,
      request: async function (request) {
        try {
          var py = await start();
          var text = await root.MathExerciseRuntime.callCheckers(py, 'stack.' + request.type,
            {question: request.question, variant: request.variant, answers: request.answers || {}}, root.CTMCheckersStack);
          var reply = typeof text === 'string' ? JSON.parse(text) : text;
          return reply.ok ? reply : {ok: false, error: reply.errorDetail || {kind: 'runtime', code: 'stack-protocol', message: String(reply.error)}};
        } catch (error) { return {ok: false, error: failure(error)}; }
      },
      stop: async function (reason) {
        var old = runtime;
        if (old) await root.MathExerciseRuntime.stop(reason, {runtime: old});
        return {restarted: runtime !== old};
      },
      restart: function (reason) {
        if (!runtime) return start();
        runtime.restart(reason); return ready;
      }
    };
  };
})(globalThis);

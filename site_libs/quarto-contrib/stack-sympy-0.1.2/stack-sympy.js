(function () {
  'use strict';
  var current = document.currentScript;
  var workerURL = new URL('worker.js', current.src);
  var worker = null;
  var pending = null;
  var sequence = 0;
  var pipeline = Promise.resolve();

  function resetWorker(error) {
    if (worker) worker.terminate();
    worker = null;
    if (pending) {
      clearTimeout(pending.timer);
      pending.reject(error);
      pending = null;
    }
  }

  function ensureWorker() {
    if (worker) return worker;
    worker = new Worker(workerURL);
    worker.onmessage = function (event) {
      var msg = event.data;
      if (!pending || pending.id !== msg.id) return;
      var task = pending;
      pending = null;
      clearTimeout(task.timer);
      if (msg.ok) task.resolve(msg.result);
      else task.reject(new Error(msg.error || 'The grader failed.'));
    };
    worker.onerror = function (event) {
      resetWorker(new Error(event.message || 'The grading worker could not start.'));
    };
    return worker;
  }

  // Run one Python request at a time: Pyodide's interpreter is not reentrant.
  function evaluate(payload) {
    var result = pipeline.catch(function () {}).then(function () {
      return new Promise(function (resolve, reject) {
        var id = ++sequence;
        var target;
        try { target = ensureWorker(); } catch (error) { reject(error); return; }
        var timer = setTimeout(function () {
          resetWorker(new Error('The calculation timed out. Try again.'));
        }, 120000);
        pending = { id: id, resolve: resolve, reject: reject, timer: timer };
        try { target.postMessage(Object.assign({ id: id }, payload)); }
        catch (error) { resetWorker(error); }
      });
    });
    pipeline = result;
    return result;
  }

  var MATHJAX_URL = 'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js';
  var mathQueue = Promise.resolve();

  function ensureMathJax() {
    if (window.MathJax && typeof window.MathJax.typesetPromise === 'function') {
      return Promise.resolve(window.MathJax.startup && window.MathJax.startup.promise)
        .then(function () { return window.MathJax; });
    }
    if (window.__stackSympyMathJax) return window.__stackSympyMathJax;
    var ownedScript = null;
    var pending = (async function () {
      // Keep an existing page's MathJax configuration. Version 3 recognizes
      // both \( ... \) and \[ ... \] by default; configure our own only when
      // Quarto has not installed one for ordinary document mathematics.
      if (!window.MathJax) {
        window.MathJax = {
          tex: { inlineMath: [['\\(', '\\)']], displayMath: [['\\[', '\\]']] }
        };
      }
      var script = document.querySelector('script[src*="mathjax"]');
      if (!script) {
        script = document.createElement('script');
        script.src = MATHJAX_URL;
        script.async = true;
        script.dataset.stackSympyMathjax = '1';
        ownedScript = script;
        var loaded = new Promise(function (resolve, reject) {
          script.onload = resolve;
          script.onerror = function () { reject(new Error('Could not load MathJax.')); };
        });
        document.head.appendChild(script);
        await loaded;
      } else if (!window.MathJax.startup || !window.MathJax.startup.promise) {
        await new Promise(function (resolve, reject) {
          var timer, poll;
          function finish(error) {
            clearTimeout(timer);
            clearInterval(poll);
            script.removeEventListener('load', loaded);
            script.removeEventListener('error', failed);
            if (error) reject(error); else resolve();
          }
          function loaded() { finish(); }
          function failed() { finish(new Error('Could not load MathJax.')); }
          timer = setTimeout(function () { finish(new Error('MathJax did not initialize.')); }, 30000);
          poll = setInterval(function () {
            if (window.MathJax && (typeof window.MathJax.typesetPromise === 'function' ||
                window.MathJax.startup && window.MathJax.startup.promise)) finish();
          }, 50);
          script.addEventListener('load', loaded);
          script.addEventListener('error', failed);
        });
      }
      if (window.MathJax.startup && window.MathJax.startup.promise) {
        await window.MathJax.startup.promise;
      }
      if (typeof window.MathJax.typesetPromise !== 'function') {
        throw new Error('MathJax did not expose a typesetting API.');
      }
      return window.MathJax;
    })();
    window.__stackSympyMathJax = pending;
    pending.catch(function () {
      if (ownedScript && ownedScript.isConnected) ownedScript.remove();
      if (window.__stackSympyMathJax === pending) delete window.__stackSympyMathJax;
    });
    return pending;
  }

  function math(element) {
    // MathJax's document state is shared across cards and is not reentrant.
    mathQueue = mathQueue.catch(function () {}).then(async function () {
      var mj = await ensureMathJax();
      if (element.isConnected) await mj.typesetPromise([element]);
    }).catch(function (error) { console.warn('STACK SymPy math display:', error); });
    return mathQueue;
  }

  function clearMath(element) {
    if (window.MathJax && typeof window.MathJax.typesetClear === 'function') {
      try { window.MathJax.typesetClear([element]); }
      catch (error) { console.warn('STACK SymPy math cleanup:', error); }
    }
  }

  function message(container, text, state) {
    clearMath(container);
    container.replaceChildren();
    container.dataset.state = state || '';
    var line = document.createElement('p');
    line.textContent = text;
    container.appendChild(line);
    math(container);
  }

  function node(tag, className, value) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    if (value != null) element.textContent = String(value);
    return element;
  }

  function showGrade(card, result) {
    var output = card.querySelector('.stack-result');
    clearMath(output);
    output.replaceChildren();
    output.dataset.state = result.status === 'invalid' ? 'invalid' : result.score >= 1 ? 'correct' : 'retry';
    if (result.status === 'invalid') {
      output.appendChild(node('p', 'stack-verdict', 'Check the input and try again.'));
    } else {
      output.appendChild(node('p', 'stack-verdict', result.score >= 1 ? 'Correct.' :
        result.score > 0 ? 'Partially correct (' + Math.round(result.score * 100) + '%).' : 'Not quite. Try again.'));
    }
    var inputResults = result.inputs || {};
    Object.keys(inputResults).forEach(function (name) {
      var detail = inputResults[name];
      var item = card.querySelector('.stack-answer[data-name="' + CSS.escape(name) + '"]');
      if (item) item.setAttribute('aria-invalid', detail.valid === false ? 'true' : 'false');
      var validation = card.querySelector('.stack-validation[data-name="' + CSS.escape(name) + '"]');
      if (detail.feedback && validation) {
        clearMath(validation);
        validation.textContent = detail.feedback;
      }
      else if (detail.feedback) output.appendChild(node('p', 'stack-input-feedback', name + ': ' + detail.feedback));
    });
    Object.keys(result.prts || {}).forEach(function (name) {
      var detail = result.prts[name];
      if (detail.feedback) {
        // The Python CASText renderer has already enforced an HTML allowlist.
        var feedback = node('div', 'stack-prt-feedback');
        feedback.innerHTML = detail.feedback;
        var inline = card.querySelector('.stack-feedback[data-name="' + CSS.escape(name) + '"]');
        if (inline) {
          clearMath(inline);
          inline.innerHTML = detail.feedback;
        }
        else output.appendChild(feedback);
      }
    });
    math(card);
  }

  function showValidation(card, result) {
    var output = card.querySelector('.stack-result');
    clearMath(output);
    output.replaceChildren();
    output.dataset.state = result.status === 'valid' ? 'valid' : 'invalid';
    output.appendChild(node('p', 'stack-verdict', result.status === 'valid' ?
      'Inputs parsed. Review them, then check your answer.' : 'Please correct the marked input and validate again.'));
    Object.keys(result.inputs || {}).forEach(function (name) {
      var detail = result.inputs[name];
      var input = card.querySelector('.stack-answer[data-name="' + CSS.escape(name) + '"]');
      var validation = card.querySelector('.stack-validation[data-name="' + CSS.escape(name) + '"]');
      if (input) input.setAttribute('aria-invalid', detail.valid ? 'false' : 'true');
      if (!validation) {
        validation = node('span', 'stack-validation');
        output.appendChild(node('p', '', name + ': '));
        output.appendChild(validation);
      }
      validation.dataset.state = detail.valid ? 'valid' : 'invalid';
      validation.dataset.latex = detail.latex || '';
      clearMath(validation);
      validation.textContent = detail.valid ? 'Interpreted as \\(' + detail.latex + '\\)' : detail.feedback;
      math(validation);
    });
  }

  function showTests(card, result) {
    var output = card.querySelector('.stack-result');
    clearMath(output);
    output.replaceChildren();
    output.dataset.state = result.passed ? 'correct' : 'retry';
    output.appendChild(node('p', 'stack-verdict', result.passed ? 'All authored tests passed.' : 'Some authored tests failed.'));
    var list = node('ul', 'stack-test-list');
    (result.results || []).forEach(function (test) {
      list.appendChild(node('li', '', (test.passed ? 'Pass' : 'Fail') +
        ' · ' + test.testcase + ' (seed ' + test.seed + ')'));
    });
    output.appendChild(list);
  }

  function initialize(card) {
    var data = card.querySelector('script.stack-sympy-data');
    if (!data) return;
    var payload;
    try { payload = JSON.parse(data.textContent); }
    catch (error) {
      message(card.querySelector('.stack-result'), 'Question data could not be read.', 'error');
      return;
    }
    var selector = card.querySelector('.stack-variant');
    var version = 0;
    var validatedSnapshot = null;
    var check = card.querySelector('.stack-check');
    var validate = card.querySelector('.stack-validate');
    if (check) check.disabled = true;
    function readAnswers() {
      var answers = {};
      card.querySelectorAll('.stack-answer[data-name]').forEach(function (input) { answers[input.dataset.name] = input.value; });
      return answers;
    }
    var variantAt = function () {
      var index = selector ? Number(selector.value) : 0;
      return payload.variants[index] || payload.variants[0];
    };
    function clear() {
      version++;
      validatedSnapshot = null;
      if (check) check.disabled = true;
      card.querySelectorAll('.stack-answer[data-name]').forEach(function (item) {
        item.value = '';
        item.removeAttribute('aria-invalid');
      });
      var output = card.querySelector('.stack-result');
      clearMath(output);
      output.replaceChildren();
      output.removeAttribute('data-state');
      card.querySelectorAll('.stack-validation, .stack-feedback').forEach(function (item) {
        clearMath(item);
        item.textContent = '';
        delete item.dataset.latex;
        delete item.dataset.state;
      });
    }
    if (selector) selector.addEventListener('change', function () {
      var variant = variantAt();
      var prompt = card.querySelector('.stack-prompt');
      if (prompt && variant) {
        clearMath(prompt);
        prompt.innerHTML = variant.question_html;
        math(prompt);
      }
      clear();
    });
    card.addEventListener('input', function (event) {
      if (event.target.matches('.stack-answer[data-name]')) {
        version++;
        validatedSnapshot = null;
        if (check) check.disabled = true;
        event.target.removeAttribute('aria-invalid');
        var output = card.querySelector('.stack-result');
        clearMath(output);
        output.replaceChildren();
        card.querySelectorAll('.stack-validation, .stack-feedback').forEach(function (item) {
          clearMath(item);
          item.textContent = '';
          delete item.dataset.latex;
          delete item.dataset.state;
        });
      }
    });
    async function act(type, button) {
      var resultBox = card.querySelector('.stack-result');
      var generation = version;
      var variant = variantAt();
      var answers = readAnswers();
      var snapshot = JSON.stringify(answers);
      if (type === 'grade' && validatedSnapshot !== snapshot) {
        if (check) check.disabled = true;
        message(resultBox, 'Validate the current inputs before checking.', 'invalid');
        return;
      }
      button.disabled = true;
      message(resultBox, type === 'grade' ? 'Checking with SymPy…' :
        type === 'validate' ? 'Parsing your inputs…' : 'Running authored tests…', 'loading');
      try {
        var result = await evaluate({ type: type, question: payload.question, variant: variant, answers: answers });
        if (generation !== version || JSON.stringify(readAnswers()) !== snapshot) return;
        if (type === 'grade') showGrade(card, result);
        else if (type === 'validate') {
          showValidation(card, result);
          validatedSnapshot = result.status === 'valid' ? snapshot : null;
          if (check) check.disabled = validatedSnapshot === null;
        } else showTests(card, result);
      } catch (error) {
        if (generation === version) message(resultBox, 'Could not check this answer: ' + error.message, 'error');
      } finally {
        if (type === 'grade') button.disabled = validatedSnapshot !== JSON.stringify(readAnswers());
        else button.disabled = false;
      }
    }
    if (check) check.addEventListener('click', function () { act('grade', check); });
    if (validate) validate.addEventListener('click', function () { act('validate', validate); });
    var tests = card.querySelector('.stack-tests');
    if (tests) tests.addEventListener('click', function () { act('tests', tests); });
    math(card);
  }

  document.querySelectorAll('.stack-sympy:not(.stack-diagnostic)').forEach(initialize);
})();

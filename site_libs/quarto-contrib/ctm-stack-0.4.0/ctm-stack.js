(function () {
  'use strict';
  var current = document.currentScript;
  var backends = new Map();
  function t(card, key, args) {
    return window.CTMLocales.format('ctm-stack', key, card.dataset.lang || 'en', args || {});
  }
  function backendFor(card) {
    var id = card.dataset.backend;
    if (backends.has(id)) return backends.get(id);
    var island = Array.from(document.querySelectorAll('script.ctm-stack-backend')).find(function (item) { return item.dataset.backend === id; });
    if (!island) throw new Error('Missing STACK backend descriptor: ' + id);
    var descriptor = JSON.parse(island.textContent);
    if (descriptor.id !== id || typeof descriptor.adapter !== 'string' || !descriptor.requires || typeof descriptor.requires.isolation !== 'boolean') {
      throw new Error('Invalid STACK backend descriptor');
    }
    var adapter = null, starting = null;
    var state = {queue: [], active: false, descriptor: descriptor};
    state.start = function () {
      if (!starting) starting = (async function () {
        if (descriptor.requires.isolation && !window.crossOriginIsolated) throw new Error('The backend requires cross-origin isolation.');
        await window.MathExerciseRuntime.loadScript(new URL(descriptor.adapter, current.src).href);
        var factory = (window.CTMStackAdapters || {})[id];
        if (typeof factory !== 'function') throw new Error('The backend adapter did not register: ' + id);
        adapter = factory(descriptor);
        for (var method of ['start', 'request', 'stop', 'restart']) if (typeof adapter[method] !== 'function') throw new Error('Invalid backend adapter: ' + method);
        if (typeof adapter.isolationRequired !== 'boolean' || adapter.isolationRequired !== descriptor.requires.isolation) throw new Error('Backend isolation requirement does not match its descriptor');
        await adapter.start();
        return adapter;
      })().catch(function (error) { starting = null; throw error; });
      return starting;
    };
    state.restart = async function (reason) {
      if (adapter && starting) await adapter.restart(reason); else { adapter = null; await state.start(); }
    };
    backends.set(id, state);
    return state;
  }
  // Requests superseded while queued never reach a backend. Loading and waiting
  // in this queue do not consume the calculation clock.
  function evaluate(card, payload, onSlow) {
    var state = backendFor(card), key = card.dataset.stackId + ':' + payload.type;
    return new Promise(function (resolve, reject) {
      state.queue = state.queue.filter(function (item) {
        if (item.key !== key) return true;
        item.resolve({superseded: true}); return false;
      });
      state.queue.push({key: key, resolve: resolve, reject: reject, payload: payload, card: card, onSlow: onSlow});
      pump(state);
    });
  }
  async function pump(state) {
    if (state.active) return;
    state.active = true;
    while (state.queue.length) {
      var job = state.queue.shift(), slowTimer, ceiling, cancelSlow, stopping, stopped = false, stopResult;
      try {
        var adapter = await state.start();
        var ms = Number(job.card.dataset.stopAfter) * 1000;
        slowTimer = setTimeout(function () {
          cancelSlow = job.onSlow(function () {
            stopped = true;
            stopping = Promise.resolve(adapter.stop('Stopped by the learner')).then(function (result) { stopResult = result; });
            return stopping;
          });
        }, ms);
        var limit = new Promise(function (_, reject) {
          ceiling = setTimeout(function () {
            state.restart('Calculation ceiling').catch(function () {});
            reject({kind: 'runtime', code: 'stack-timeout', message: t(job.card, 'calculationTimeout'), restarted: true});
          }, Math.max(120000, ms * 6));
        });
        var response = await Promise.race([adapter.request(job.payload), limit]);
        if (stopped) {
          await stopping;
          throw {kind: 'runtime', code: 'stack-stopped', restarted: !!(stopResult && stopResult.restarted)};
        }
        if (!response || typeof response.ok !== 'boolean') throw new Error('Invalid backend response');
        if (!response.ok) {
          if (!response.error || !['author','runtime'].includes(response.error.kind) || typeof response.error.message !== 'string') throw new Error('Invalid backend error');
          throw response.error;
        }
        job.resolve(response.result);
      } catch (error) {
        if (stopped) {
          try { await stopping; } catch (_) {}
          error = {kind: 'runtime', code: 'stack-stopped', restarted: !!(stopResult && stopResult.restarted)};
        }
        job.reject(error);
      } finally {
        clearTimeout(slowTimer); clearTimeout(ceiling); if (cancelSlow) cancelSlow();
      }
    }
    state.active = false;
  }
  var mathQueue = Promise.resolve();
  async function ensureMathJax() {
    if (window.MathJax && window.MathJax.startup && window.MathJax.startup.promise) await window.MathJax.startup.promise;
    if (!window.MathJax || !window.MathJax.typesetPromise) {
      var existing = document.querySelector('script[src*="mathjax"]');
      if (!window.MathJax) window.MathJax = {tex: {inlineMath: [['\\(', '\\)']], displayMath: [['\\[', '\\]']]}};
      var card = document.querySelector('.ctm-stack');
      await window.MathExerciseRuntime.loadScript(existing ? existing.src : card.dataset.mathjax);
    }
    if (window.MathJax.startup) await window.MathJax.startup.promise;
    if (typeof window.MathJax.typesetPromise !== 'function') throw new Error('MathJax did not expose a typesetting API.');
    return window.MathJax;
  }
  function structuredMessage(card, item) {
    if (!item) return '';
    var args = Object.assign({}, item.args || {});
    Object.keys(args).forEach(function (key) {
      if (Array.isArray(args[key])) args[key] = args[key].map(function (value) {
        return value && typeof value.latex === 'string' ? '\\(' + value.latex + '\\)' : String(value);
      }).join(', ');
    });
    return window.CTMLocales.format('ctm-stack', item.code, card.dataset.lang, args) || item.text || '';
  }
  function prtFeedback(card, target, detail) {
    target.replaceChildren();
    if (!Array.isArray(detail.feedbackParts)) { target.innerHTML = detail.feedback || ''; return; }
    detail.feedbackParts.forEach(function (part, index) {
      if (index) target.appendChild(document.createTextNode(' '));
      if (typeof part.html === 'string') {
        var span = document.createElement('span'); span.innerHTML = part.html; target.appendChild(span);
      } else if (part.message) target.appendChild(document.createTextNode(structuredMessage(card, part.message)));
    });
  }
  function math(element) {
    // MathJax's document state is shared across cards and is not reentrant.
    mathQueue = mathQueue.catch(function () {}).then(async function () {
      var mj = await ensureMathJax();
      if (element.isConnected) await mj.typesetPromise([element]);
    }).catch(function (error) { console.warn('CTM STACK math display:', error); });
    return mathQueue;
  }

  function clearMath(element) {
    if (window.MathJax && typeof window.MathJax.typesetClear === 'function') {
      try { window.MathJax.typesetClear([element]); }
      catch (error) { console.warn('CTM STACK math cleanup:', error); }
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
      output.appendChild(node('p', 'stack-verdict', t(card, 'checkInput')));
    } else {
      output.appendChild(node('p', 'stack-verdict', result.score >= 1 ? t(card, 'correct') :
        result.score > 0 ? t(card, 'partial', {pct: Math.round(result.score * 100)}) : t(card, 'retry')));
    }
    var inputResults = result.inputs || {};
    Object.keys(inputResults).forEach(function (name) {
      var detail = inputResults[name];
      var item = card.querySelector('.stack-answer[data-name="' + CSS.escape(name) + '"]');
      if (item) item.setAttribute('aria-invalid', detail.valid === false ? 'true' : 'false');
      var validation = card.querySelector('.stack-validation[data-name="' + CSS.escape(name) + '"]');
      if (detail.feedback && validation) {
        clearMath(validation);
        validation.textContent = structuredMessage(card, detail.message) || detail.feedback;
      }
      else if (detail.feedback) output.appendChild(node('p', 'stack-input-feedback', name + ': ' + detail.feedback));
    });
    Object.keys(result.prts || {}).forEach(function (name) {
      var detail = result.prts[name];
      if (detail.feedback) {
        // The Python CASText renderer has already enforced an HTML allowlist.
        var feedback = node('div', 'stack-prt-feedback');
        prtFeedback(card, feedback, detail);
        var inline = card.querySelector('.stack-feedback[data-name="' + CSS.escape(name) + '"]');
        if (inline) {
          clearMath(inline);
          prtFeedback(card, inline, detail);
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
      t(card, 'validationReady') : t(card, 'validationInvalid')));
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
      validation.textContent = detail.valid ? t(card, 'interpretedAs', {latex: detail.latex}) : structuredMessage(card, detail.message) || detail.feedback;
      math(validation);
    });
  }

  function showTests(card, result) {
    var output = card.querySelector('.stack-result');
    clearMath(output);
    output.replaceChildren();
    output.dataset.state = result.passed ? 'correct' : 'retry';
    output.appendChild(node('p', 'stack-verdict', result.passed ? t(card, 'testsPassed') : t(card, 'testsFailed')));
    var list = node('ul', 'stack-test-list');
    (result.results || []).forEach(function (test) {
      list.appendChild(node('li', '', (test.passed ? t(card, 'testPass') : t(card, 'testFail')) +
        ' · ' + t(card, 'testCase', {testcase: test.testcase, seed: test.seed})));
    });
    output.appendChild(list);
  }

  // The frozen question HTML is the learner's task. The card itself also
  // contains authored tests and the original XML in source panels.
  function feedbackTask(card, variant) {
    var template = document.createElement('template');
    template.innerHTML = variant.question_html;
    template.content.querySelectorAll('.stack-answer[data-name]').forEach(function (input) {
      input.replaceWith(document.createTextNode('[' + t(card, 'feedbackAnswer', {name: input.dataset.name}) + ']'));
    });
    template.content.querySelectorAll('.stack-validation, .stack-feedback').forEach(function (item) { item.remove(); });
    return window.AIFeedback.contextText(template.content);
  }

  function safeCheckEvidence(card, result) {
    var summary = { status: result.status === 'graded' ? 'graded' : 'invalid' };
    if (typeof result.score === 'number' && Number.isFinite(result.score)) summary.score = result.score;
    return [{ label: t(card, 'previousCheck'), text: JSON.stringify(summary) }];
  }

  function initialize(card) {
    var MatrixInput = window.MatrixInput;
    var storeHandle = null, restoring = false;
    var data = card.querySelector('script.ctm-stack-data');
    if (!data) return;
    var payload;
    try { payload = JSON.parse(data.textContent); }
    catch (error) {
      message(card.querySelector('.stack-result'), t(card, 'questionDataError'), 'error');
      return;
    }
    if (payload.version !== 2) { message(card.querySelector('.stack-result'), t(card, 'questionDataError'), 'error'); return; }
    var selector = card.querySelector('.stack-variant');
    var version = 0;
    var validatedSnapshot = null;
    var checkedEvidence = null;
    var feedbackHandle = null;
    var matrixEditors = new Map();
    var check = card.querySelector('.stack-check');
    var validate = card.querySelector('.stack-validate');
    if (check) check.disabled = true;
    function cellSource(raw) {
      var depth = 0;
      for (var i = 0; i < raw.length; i++) {
        var ch = raw[i];
        if (ch === '(') depth++;
        else if (ch === ')') { if (--depth < 0) return '()'; }
        else if (ch === '[' || ch === ']' || ch === '{' || ch === '}' || ch === ',' && depth === 0) return '()';
      }
      return depth === 0 ? '(' + raw + ')' : '()';
    }
    function readAnswers() {
      var answers = {};
      card.querySelectorAll('.stack-answer[data-name]').forEach(function (input) {
        var editor = matrixEditors.get(input);
        if (!editor) { answers[input.dataset.name] = input.value; return; }
        var value = editor.read();
        var rows = [];
        for (var r = 0; r < value.rows; r++) {
          // Parentheses keep raw commas/brackets inside their own scalar cell.
          // Incomplete cells become () and are rejected by the bounded parser.
          rows.push('[' + value.raw.slice(r * value.cols, (r + 1) * value.cols)
            .map(cellSource).join(',') + ']');
        }
        answers[input.dataset.name] = 'matrix(' + rows.join(',') + ')';
      });
      return answers;
    }
    function mountMatrices() {
      card.querySelectorAll('.stack-matrix[data-name]').forEach(function (host, index) {
        if (matrixEditors.has(host)) return;
        if (!MatrixInput) throw new Error(t(card, 'matrixMissing'));
        var renderer = MatrixInput.create({
          idPrefix: card.dataset.stackId + '-matrix-' + index,
          zeroDimensions: 'reject', maxEntries: 64,
          labels: Object.fromEntries(['matrixRows','matrixColumns','matrixAddRow','matrixRemoveRow','matrixAddColumn','matrixRemoveColumn','matrixSizeControls','emptyMatrix'].map(function (key) { return [key, t(card, key)]; })),
          onChange: function () { invalidate(); if (storeHandle && !restoring) storeHandle.changed(); }
        });
        host.innerHTML = renderer.renderHTML(JSON.parse(host.dataset.matrixSpec)).html;
        matrixEditors.set(host, renderer.mount(host));
      });
    }
    function destroyMatrices() {
      matrixEditors.forEach(function (editor) { editor.destroy(); });
      matrixEditors.clear();
    }
    function clearPresentation() {
      var output = card.querySelector('.stack-result');
      clearMath(output);
      output.replaceChildren();
      output.removeAttribute('data-state');
      matrixEditors.forEach(function (editor) { editor.setState({status: 'empty'}); });
      card.querySelectorAll('.stack-answer[data-name]').forEach(function (item) { item.removeAttribute('aria-invalid'); });
      card.querySelectorAll('.stack-validation, .stack-feedback').forEach(function (item) {
        clearMath(item);
        item.textContent = '';
        delete item.dataset.latex;
        delete item.dataset.state;
      });
    }
    function invalidate() {
      version++;
      validatedSnapshot = null;
      checkedEvidence = null;
      if (feedbackHandle) feedbackHandle.cancel({ clearOutput: true });
      if (check) check.disabled = true;
      clearPresentation();
    }
    var variantAt = function () {
      var index = selector ? Number(selector.value) : 0;
      return payload.variants[index] || payload.variants[0];
    };
    function responseIdentity() {
      return JSON.stringify([version, selector ? selector.value : '0', readAnswers()]);
    }
    // AI feedback is CTM Assessment's (ctm-libs, AIFeedback). A build without
    // AI (ai-feedback: enabled: false, CTM_FEEDBACK=off) loads none: the card
    // then has no Feedback button, and native checking works as always.
    var F = window.AIFeedback;
    if (card.hasAttribute('data-stack-feedback') && F) {
      var config;
      try { config = JSON.parse(card.dataset.stackFeedback); }
      catch (error) { config = {}; }
      var actions = card.querySelector('.stack-actions');
      var feedbackButton = node('button', 'stack-feedback-button ai-feedback-button',
        t(card, 'feedbackButton'));
      feedbackButton.type = 'button';
      var feedbackOutput = node('div', 'ai-feedback-output');
      feedbackOutput.setAttribute('aria-live', 'polite');
      if (actions) {
        actions.appendChild(feedbackButton);
        actions.after(feedbackOutput);
      } else card.append(feedbackButton, feedbackOutput);
      var gear = F.settingsButton(config.uiLanguage);
      if (actions) actions.appendChild(gear); else feedbackButton.after(gear);
      feedbackHandle = F.attach({
        id: 'stack-' + card.dataset.stackId,
        integration: 'stack',
        contextRefs: function () {
          return config.context && config.context.mode === 'explicit' ? config.context.refs : '';
        },
        policySelection: config.policySelection || {},
        uiLanguage: config.uiLanguage,
        button: feedbackButton,
        output: feedbackOutput,
        getRequest: function () {
          var answers = readAnswers();
          var names = Object.keys(answers);
          if (!Array.from(card.querySelectorAll('.stack-answer[data-name]')).some(function (input) {
            var editor = matrixEditors.get(input);
            return editor ? editor.read().raw.some(function (cell) { return cell.trim(); }) : input.value.trim();
          })) {
            throw new Error(t(card, 'needAnswerFirst'));
          }
          var identity = responseIdentity();
          return {
            _responseIdentity: identity,
            profile: 'mathematics',
            task: feedbackTask(card, variantAt().display),
            responses: names.map(function (name) {
              return { id: name, label: name, value: answers[name], format: 'text' };
            }),
            materials: F.contextMaterials(config.context || {}),
            evidence: checkedEvidence && checkedEvidence.identity === identity ? checkedEvidence.summary : [],
            feedback: { language: config.language || config.uiLanguage || document.documentElement.lang || 'en' }
          };
        }
      });
    }
    function clear() {
      version++;
      validatedSnapshot = null;
      checkedEvidence = null;
      if (feedbackHandle) feedbackHandle.reset();
      if (check) check.disabled = true;
      card.querySelectorAll('.stack-answer[data-name]').forEach(function (item) {
        var editor = matrixEditors.get(item);
        if (editor) editor.reset(); else item.value = '';
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
        destroyMatrices();
        clearMath(prompt);
        prompt.innerHTML = variant.display.question_html;
        accessibility(); mountMatrices();
        math(prompt);
      }
      clear();
    });
    card.addEventListener('input', function (event) {
      if (event.target.matches('.stack-answer[data-name]')) {
        invalidate();
        if (storeHandle && !restoring) storeHandle.changed();
      }
    });
    card.addEventListener('reset', function () { clear(); });
    async function act(type, button) {
      var resultBox = card.querySelector('.stack-result');
      if (type === 'grade') {
        checkedEvidence = null;
        if (feedbackHandle) feedbackHandle.reset('run');
      }
      var generation = version;
      var variant = variantAt();
      var answers = readAnswers();
      var snapshot = JSON.stringify(answers);
      if (type === 'grade' && validatedSnapshot !== snapshot) {
        if (check) check.disabled = true;
        message(resultBox, t(card, 'validateFirst'), 'invalid');
        return;
      }
      button.disabled = true;
      message(resultBox, type === 'grade' ? t(card, 'checking', {backend: card.dataset.backend}) :
        type === 'validate' ? t(card, 'parsing') : t(card, 'runningTests'), 'loading');
      try {
        var result = await evaluate(card, {type: type, question: payload.backend.question, variant: variant.plan, answers: answers}, function (stop) {
          var button = node('button', 'stack-stop', t(card, 'stop')); button.type = 'button';
          button.addEventListener('click', function () { button.disabled = true; stop(); });
          card.querySelector('.stack-actions').appendChild(button);
          return function () { button.remove(); };
        });
        if (result && result.superseded) return;
        if (generation !== version || JSON.stringify(readAnswers()) !== snapshot) return;
        if (type === 'grade') {
          showGrade(card, result);
          checkedEvidence = { identity: responseIdentity(), summary: safeCheckEvidence(card, result) };
          if (storeHandle) storeHandle.result({score: result.score, status: result.status === 'invalid' ? 'invalid' : result.score >= 1 ? 'correct' : result.score > 0 ? 'partial' : 'wrong', variant: identity()});
        }
        else if (type === 'validate') {
          showValidation(card, result);
          validatedSnapshot = result.status === 'valid' ? snapshot : null;
          if (check) check.disabled = validatedSnapshot === null;
        } else showTests(card, result);
        if (type === 'grade' || type === 'validate') {
          matrixEditors.forEach(function (editor, host) {
            var detail = (result.inputs || {})[host.dataset.name];
            // Only an explicit Python answer test supplies vector assessment.
            // These colors explain its result; PRT branches still award credit.
            editor.setState(type === 'grade' && result.status === 'graded' && detail &&
              detail.valid !== false && detail.assessment ? detail.assessment :
              {status: detail && detail.valid === false ? 'invalid' : 'empty'});
          });
        }
      } catch (error) {
        if (generation === version) {
          if (error.code === 'stack-stopped') message(resultBox, t(card, error.restarted ? 'stoppedRestarted' : 'stoppedInterrupted'), 'error');
          else {
            message(resultBox, error.kind === 'author' ? t(card, 'authorError', {reason: error.message || String(error)}) : t(card, 'errorCheck', {reason: error.message || String(error)}), 'error');
            if (error.kind !== 'author') {
              var retry = node('button', 'stack-retry', t(card, 'retryButton')); retry.type = 'button';
              retry.addEventListener('click', async function () {
                retry.disabled = true;
                try { await backendFor(card).restart('Retry'); await act(type, button); }
                catch (reason) { message(resultBox, t(card, 'errorCheck', {reason: reason.message || String(reason)}), 'error'); }
              }); resultBox.appendChild(retry);
            }
          }
        }
      } finally {
        if (type === 'grade') button.disabled = validatedSnapshot !== JSON.stringify(readAnswers());
        else button.disabled = false;
      }
    }
    if (check) check.addEventListener('click', function () { act('grade', check); });
    if (validate) validate.addEventListener('click', function () { act('validate', validate); });
    var tests = card.querySelector('.stack-tests');
    if (tests) tests.addEventListener('click', function () { act('tests', tests); });
    var actions = card.querySelector('.stack-actions');
    if (actions) {
      var reset = node('button', 'stack-reset', t(card, 'resetButton'));
      reset.type = 'button';
      reset.addEventListener('click', function () { clear(); if (storeHandle) storeHandle.flush(); });
      actions.appendChild(reset);
    }
    function identity() { var value = variantAt(); return {n: value.n, id: value.id, hash: value.hash}; }
    function accessibility() {
      card.querySelectorAll('.stack-validation, .stack-feedback').forEach(function (item, index) { item.id = card.dataset.stackId + '-detail-' + index; });
      card.querySelectorAll('.stack-answer[data-name]').forEach(function (item) {
        var spec = payload.common.inputs.find(function (input) { return input.name === item.dataset.name; });
        var label = spec && spec.label || item.dataset.name;
        item.setAttribute('aria-label', t(card, 'feedbackAnswer', {name: label}));
        var details = Array.from(card.querySelectorAll('.stack-validation, .stack-feedback')).filter(function (detail) { return detail.dataset.name === item.dataset.name || detail.classList.contains('stack-feedback'); });
        if (details.length) item.setAttribute('aria-describedby', details.map(function (detail) { return detail.id; }).join(' '));
        if (item.dataset.matrixSpec) { var matrix = JSON.parse(item.dataset.matrixSpec); matrix.label = label; item.dataset.matrixSpec = JSON.stringify(matrix); }
      });
    }
    function storedInputs() {
      var result = {answers: {}, matrices: {}};
      card.querySelectorAll('.stack-answer[data-name]').forEach(function (input) {
        var editor = matrixEditors.get(input);
        if (editor) result.matrices[input.dataset.name] = editor.read(); else result.answers[input.dataset.name] = input.value;
      });
      return result;
    }
    accessibility(); mountMatrices();
    if (window.CTMStore && card.dataset.ctmSource) {
      storeHandle = window.CTMStore.register({component: 'ctm-stack', id: card.dataset.ctmId, element: card,
        source: card.dataset.ctmSource, save: card.dataset.ctmSave !== 'false', variant: identity,
        variants: function () { return payload.variants.map(function (item) { return {n: item.n, id: item.id, hash: item.hash}; }); },
        read: storedInputs, write: function (value, meta) {
          restoring = true;
          try {
            if (meta.variant && selector) { selector.value = String(payload.variants.findIndex(function (item) { return item.id === meta.variant.id && item.hash === meta.variant.hash; })); selector.dispatchEvent(new Event('change')); }
            card.querySelectorAll('.stack-answer[data-name]').forEach(function (input) {
              var editor = matrixEditors.get(input);
              if (editor && value.matrices && value.matrices[input.dataset.name]) editor.write(value.matrices[input.dataset.name]);
              else if (!editor) input.value = (value.answers || {})[input.dataset.name] || '';
            }); invalidate();
          } finally { restoring = false; }
        }, clear: clear});
      storeHandle.restore();
    }
    card.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' || event.shiftKey || !event.target.closest('.stack-answer')) return;
      event.preventDefault(); if (check && !check.disabled) act('grade', check); else if (validate && !validate.disabled) act('validate', validate);
    });
    math(card);
  }

  document.querySelectorAll('.ctm-stack:not(.stack-diagnostic)').forEach(initialize);
})();

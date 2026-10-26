// SPDX-License-Identifier: AGPL-3.0-or-later
// Trusted Maxima programs only. Learner text must pass the STACK admission.
// The platform supplies verified bytes; neither this module nor ECL fetches code.
(function (root) {
  'use strict';
  class RuntimeFault extends Error {
    constructor(message) { super(message); this.kind = 'runtime'; this.code = 'maxima-runtime'; }
  }
  class CASError extends Error {
    constructor(message) { super(message); this.kind = 'cas'; this.code = 'maxima-cas'; }
  }
  function open({scope, execute, bytes, manifest, stackFiles, startup, onOutput = () => {}, locateFile = path => path, gcFreeSpaceDivisor}) {
    let output = '', cursor = 0, eof = 0, poisoned = false, started = false;
    if (gcFreeSpaceDivisor !== undefined) {
      if (!Number.isInteger(gcFreeSpaceDivisor) || gcFreeSpaceDivisor < 1 || gcFreeSpaceDivisor > 10000) throw new TypeError('Invalid GC diagnostic divisor');
      startup += '\n:lisp (defun maxima::$ctm_gc_stats () (cons (quote (maxima::mlist)) (multiple-value-list (si::gc-stats t))))\n';
    }
    const input = Array.from(startup, c => c.codePointAt(0));
    const consume = text => {
      output += text;
      onOutput(text);
      if (output.length > 2 * 1024 * 1024) throw new RuntimeFault('Maxima output exceeded its bound');
    };
    const session = {manifest, get poisoned() { return poisoned; }};
    return new Promise((resolve, reject) => {
      function fail(error) { poisoned = true; reject(error instanceof Error ? error : new RuntimeFault(String(error))); }
      try {
        execute('maxima_thread.js');
        const upstreamStart = scope.onmessage, Module = scope.Module, preInit = Module.preInit;
        Module.noExitRuntime = true;
        Module.locateFile = locateFile;
        // Passing the exact verified main module avoids platform-specific fetch.
        Module.wasmBinary = bytes.get('maxima.wasm');
        Module.print = consume; Module.printErr = consume;
        Module.onAbort = reason => { poisoned = true; fail(new RuntimeFault(String(reason))); };
        Module.preInit = function () {
          scope.FS.createLazyFile = function (parent, name, url, canRead, canWrite) {
            const path = String(url).replace(/^.*?:\/\/[^/]+\//, '').replace(/^\//, '');
            if (!bytes.has(path)) return; // Unserved share entries and omitted plotting.
            // Emscripten may mount these before typed heap views exist.
            scope.FS.createDataFile(parent, name, null, canRead, canWrite);
            const file = scope.FS.lookupPath(parent.replace(/\/$/, '') + '/' + name).node;
            file.contents = bytes.get(path); file.usedBytes = file.contents.length;
            return file;
          };
          preInit();
        };
        Module.preRun.push(function () {
          const {FS, MEMFS} = scope;
          if (gcFreeSpaceDivisor !== undefined) scope.ENV.GC_FREE_SPACE_DIVISOR = String(gcFreeSpaceDivisor);
          const missing = new FS.ErrnoError(44);
          MEMFS.ops_table.dir.node.lookup = () => { throw missing; };
          const ioctl = FS.ioctl;
          FS.ioctl = function (stream, operation, argument) {
            if (operation === 21531 && FS.isFile(stream.node.mode)) {
              scope.HEAP32[argument >> 2] = Math.max(0, stream.node.node_ops.getattr(stream.node).size - stream.position);
              return 0;
            }
            return ioctl.call(this, stream, operation, argument);
          };
          for (const path of ['/ctm/tmp', '/ctm/plots', '/ctm/obj', '/ctm/moodle-qtype_stack-master/tmp']) FS.mkdirTree(path);
          for (const file of stackFiles) {
            const path = '/ctm/moodle-qtype_stack-master/' + file.path;
            FS.mkdirTree(path.slice(0, path.lastIndexOf('/'))); FS.writeFile(path, file.bytes);
          }
        });
        Module.postRun.push(() => {
          const marker = /CTMSTACK-READY\|([^|]+)\|([^\r\n]+)/.exec(output);
          if (scope.ABORT || !marker || marker[1] !== String(manifest.stackLibraryVersion)) {
            fail(new RuntimeFault('Maxima did not reach the pinned STACK version: ' + output.slice(-4000))); return;
          }
          session.maximaVersion = marker[2]; output = ''; started = true; resolve(session);
        });
        scope.importScripts = (...urls) => {
          for (const url of urls) {
            const name = String(url).split('/').pop();
            if (name === 'maxima.js') {
              scope.readChar = () => cursor < input.length ? input[cursor++] : (++eof <= 4 ? -1 : (() => { throw new RuntimeFault('Repeated EOF'); })());
              scope.checkForInterrupt = () => scope.ctmInterrupt ? scope.ctmInterrupt() : 0;
              scope.writeChar = c => consume(String.fromCodePoint(c));
              scope.writeBaseString = (p, n) => {
                let value = ''; for (let i = 0; i < n; i++) value += String.fromCharCode(scope.HEAPU8[p + i]); consume(value);
              };
              scope.convertString = (p, n) => {
                let value = ''; for (let i = 0; i < n; i++) value += String.fromCodePoint(scope.HEAP32[(p >> 2) + i]); return value;
              };
              scope.writeString = (p, n) => consume(scope.convertString(p, n));
              scope.displayOutput = (...args) => consume(args.join(' '));
            }
            execute(name);
          }
        };
        scope.postMessage = () => {};
        upstreamStart({data: [new ArrayBuffer(8), new ArrayBuffer(4), new ArrayBuffer(4)]});
      } catch (error) { fail(error); }
      function lisp(text) {
        // ECL's base-string API is eight-bit. Reconstruct Unicode within Lisp.
        const literal = value => '"' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
        if (/[^\x00-\x7f]/u.test(text)) {
          const pieces = text.split(/([^\x00-\x7f])/u).filter(Boolean).map(part =>
            /[^\x00-\x7f]/u.test(part) ? '(string (code-char ' + part.codePointAt(0) + '))' : literal(part));
          text = "(eval (read-from-string (concatenate 'string " + pieces.join(' ') + ')))';
        }
        const saved = scope.stackSave();
        try {
          const pointer = scope.stringToUTF8OnStack(text);
          const string = scope.resolveGlobalSymbol('ecl_make_constant_base_string').sym(pointer, -1);
          const form = scope.resolveGlobalSymbol('si_string_to_object').sym(1, string, 0);
          const optional = scope.stackAlloc(4);
          scope.HEAPU32[optional >> 2] = 1; // ECL NIL; C varargs use a pointer.
          return scope.resolveGlobalSymbol('si_safe_eval').sym(3, form, 1, optional);
        } finally { scope.stackRestore(saved); }
      }
      session.evaluate = expression => {
        if (!started || poisoned) throw new RuntimeFault('Maxima session is unavailable');
        if (typeof expression !== 'string' || !expression.trim() || expression.length > 300000 || expression.includes('\0')) {
          throw new TypeError('Invalid trusted Maxima program');
        }
        output = '';
        const command = 'block([%ERR:["stack_map"],%NOTES:["stack_map"],%FEEDBACK:["stack_map"],%stmt:"ctm-native",_ctm_result],'
          + '_ctm_result:ctm_classified_errcatch(' + expression + '),'
          + 'if length(%ERR)>1 then _ctm_result:["learner"],'
          + 'ctm_emit(sconcat("CTMSTACK-RESULT|",stackjson_stringify(_ctm_result))))';
        try {
          lisp('(maxima::$eval_string "' + command.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '")');
          const records = output.split(/\r?\n/).filter(line => line.startsWith('CTMSTACK-RESULT|'));
          if (records.length !== 1) throw new RuntimeFault('Maxima returned an incomplete result');
          const value = JSON.parse(records[0].slice('CTMSTACK-RESULT|'.length));
          if (!Array.isArray(value) || !['ok', 'learner', 'internal'].includes(value[0])) throw new RuntimeFault('Invalid Maxima result');
          if (value[0] === 'learner') throw new CASError('Maxima could not evaluate the question program');
          if (value[0] !== 'ok' || value.length !== 2) throw new RuntimeFault('Internal Maxima condition');
          return value[1];
        } catch (error) {
          if (!(error instanceof CASError)) poisoned = true;
          throw error;
        }
      };
    });
  }
  root.CTMMaximaDirect = {open, RuntimeFault, CASError};
})(globalThis);

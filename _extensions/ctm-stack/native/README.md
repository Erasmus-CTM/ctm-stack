# Native Maxima transport and build foundation

This is the first M4a/M4b implementation change. It provides a shared direct
ECL call core, worker lifetime/deadline controls, and an internal Node build
runner against the unchanged **runtime-v3** release. Source-loaded STACK stays
the default. It does **not** yet make `cas: maxima` available in Quarto:
the native compiler, shared admission, backend adapter and reviewed-variants
producer still need integration. See the [implementation ledger](../../../plans/2026-10-native-m4a-m4b.md).

`direct-runtime.js` replaces the prototype's stdin/SAB transport with the
exported ECL call entry qualified by the runtime repository's step-0 research.
It uses the same Unicode reconstruction, optional-argument stack slot and
temporary-stack restoration, and the classified condition boundary accepted
for v3. Source references:

- [direct-call research worker](https://github.com/Erasmus-CTM/stack-wasm-maxima/blob/0ad2986/prototype/runtime-callentry/worker.js);
- [classified condition boundary](https://github.com/Erasmus-CTM/stack-wasm-maxima/blob/0ad2986/prototype/native/classified-errcatch.lisp).

These adapters are AGPL-3.0-or-later. STACK remains GPL-3.0-or-later; the
runtime's original notices and source offer are retained by the staging tool.
No upstream binary, generated JS, Wasm module or STACK library is modified.

## Reproduce without a browser

Use Python 3.12 and Node 22.16 or 24.19. Obtain the release files and an exact
STACK checkout, then stage locally:

```sh
gh release download runtime-v3 --repo Erasmus-CTM/stack-wasm-maxima --dir .cache/release --pattern maxima-runtime-v3.json --pattern maxima-runtime-v3.tar.gz
git clone https://github.com/maths/moodle-qtype_stack.git .cache/stack
git -C .cache/stack checkout --detach 33383047af39c204bf4442802a058f8b918b2b1b
python scripts/stage-native.py --release .cache/release --stack-source .cache/stack --output .cache/native-v3
mkdir -p test-results/native
gzip -dc tests/native/accepted-programs.json.gz > test-results/native/programs.json
node tests/native/session.test.mjs
node tests/native/integration.mjs .cache/native-v3 test-results/native/programs.json test-results/native/node.json
```

The stage tool checks the release record against the committed v3 pin, the
archive/manifest/assets against that record, and the full STACK library
against the committed source inventory. It reads committed Git blobs and
cannot silently consume edited worktree sources. Node repeats source and
runtime admission before a cache lookup.

The internal build protocol is schema 1:

```json
{"schema":1,"programs":[{"id":"answer","expression":"6*7"}]}
```

```sh
node scripts/native-build.mjs --runtime .cache/native-v3 --input build-programs.json --output build-results.json --cache .cache/native-plans
```

Only compiler-generated **trusted** Maxima programs belong here. Neither this
interface nor Node's execution context is a sandbox for hostile author code.
Learner input must eventually reach it only through the shared admission and
native engine. It exposes no Lisp message endpoint. No runner downloads a
browser, and neither staging nor building compiles Maxima.

The parent worker enforces a 180-second initialization limit and 30-second
per-program limit by default. Stop/timeout/internal failure rejects the active
request and terminates the worker. No failed program is retried. Ordinary
Maxima/domain errors retain the session. New sessions start after acknowledged
termination; stale messages cannot fulfill a later request. This initial
transport uses worker replacement, not a cooperative interrupt or raw reset.

Cache entries represent a **complete batch from a fresh interpreter**, never
individual commands skipped inside a live session. Their key binds the package,
all adapter sources, Node version and batch. Their result digest detects cache
corruption; it is not an authorization signature. A local author who can alter
both the cache and its digest is trusted. These entries do not approve or
publish variants and are not the final question-plan/receipt schema.

`browser-worker.js` is an internal qualification adapter using the same core.
Its caller supplies an expected package hash, every fetched byte is verified,
and all runtime reads use verified in-memory data. It requires neither
COOP/COEP nor SharedArrayBuffer. It is deliberately absent from the extension's
published card resources until the native backend is integrated.

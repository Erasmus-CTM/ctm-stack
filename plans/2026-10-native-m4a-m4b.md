# M4a and M4b: native STACK integration against runtime-v3

AC requested implementation on 26 October 2026. Runtime-v3 remains the fixed
runtime, with source-loaded STACK at `3338304`; no new compiler profile,
compiled STACK default, tag or release is part of this work.

The shared card shell, backend contract, reviewed-variants infrastructure and
H1 checker entry are already on main. The transport foundation and shared
JavaScript admission API have also merged. The compiler/card change below
replaces the unavailable-backend guards with a real native producer, runtime
staging diagnostics and the same publication/request contracts. The research
prototype is evidence and a regression oracle, not the production UI.

## Compiler/card implementation — 27 October 2026

AC requested a Python PRT compiler and a clean implementation rather than a
PHP dependency or line-by-line port. This supersedes the original compiler
language choice below. Typed Python IR emits a native Maxima program; there is
no second runtime tree interpreter. Upstream PHP is an oracle only. Its output
and our compiler independently match a Decimal/path reference on 120 DAGs and
2,572 verdict assignments. The adversarial audit records two upstream rendering
defects and a separately classified score-precision difference.

Implemented and locally exercised:

- Structural XML → pinned JS grammar IR → Python PRT compiler → runtime-v3
  preparation, XML tests, mandatory full-mark teacher vector and wrong probes.
  The native producer works with SymPy imports blocked.
- Common leased review history, backend-owned replay tapes, required approval,
  stable numbering, prose refresh and mathematical-edit invalidation.
- Quarto runtime resources and descriptor, sealed native card worker, native
  validation/grading/tests, fresh heaps on variant changes and mixed backends.
  The real rendered card earns full, partial and zero marks, rejects invalid
  input, recovers, and passes XML tests without starting Pyodide or requiring
  cross-origin isolation. Runtime loading precedes the calculation clock.
- Separate loading/calculation watchdogs, Stop, internal-fault retirement and
  rejection of late-generation replies. The failed request is never replayed.

This is a functional initial native subset, not completion of every M4a/M4b
acceptance item. Remaining work includes JSXGraph/general CASText coverage,
broader validation/message conformance, retiring the older SymPy admission
path, additional question-family coverage and the wider distribution/locales
phases. Native PythonCheckers are implemented in M4d below. The
following original checklist remains the full programme scope; CI evidence
for the compiler/card change is attached to its PR.

## First reviewable change: direct transport and supervised build core

The native directory provides one direct ECL call implementation for browser
and Node workers. It runs verified v3 bytes, source-loads the pinned complete
STACK library and returns from main before processing requests. It has no
stdin shared-memory transport, no public Lisp endpoint, no learner parser and
no card registration. It preserves the accepted Unicode handling, ECL varargs
calling convention, classified condition boundary and Wasm temporary-stack
restoration. It uses the v3 release unchanged.

The Node parent enforces separate initialization and calculation deadlines.
Internal faults, traps, malformed results and timeouts retire the worker;
ordinary CAS errors retain it. Failed requests are never replayed. A fresh
generation starts only after termination is acknowledged. Whole-batch build
results may be cached with runtime, STACK, adapter, request and Node identities;
cached results are not variant-approval receipts.

The 327-program replay is a gate for this first change. Actual new preparation,
validation, PRT/controller, Python continuation and UI parity will be gates for
their own integration changes. Browser transport coverage alone does not
certify the final production backend.

## M4a integration still to implement

1. Register the Maxima backend through the existing descriptor/factory contract,
   with loading, Stop, stale-result suppression and runtime/author/CAS outcomes.
   Bound calls before enabling instant validation. A page without Maxima cards
   must load no Maxima assets.
2. Implement one STACK-pin-bound JavaScript input admission shared by Maxima
   and SymPy, including the migrated S-13 goldens. Retire the Python admission
   only after both runtime and build-time verdict/message conformance passes.
3. Produce a version-2 native question/variant plan using the shared card shell,
   supported CASText and JSXGraph inputs. Preserve the build diagnostic for
   unsupported features and the plot policy. No runtime fallback to SymPy.
4. Implement and prove question-state isolation. A worker restart is proven
   isolation but costs initialization; raw whole-library stack_reset is not a
   valid isolation mechanism. Choose reuse only with explicit contamination
   tests for values, functions, properties, assumptions and library defaults.
5. Run actual installed-component mixed-backend acceptance, native comparisons,
   graphics, lifecycle/GC and language/error controls. The prototype's 316
   programs are a starting regression fixture, not coverage of new logic.

## M4b integration still to implement

1. Connect structural XML/CASText compilation to the Node runner. Evaluate
   preparation and question tests in native Maxima; do not generate Maxima
   plans by first evaluating a SymPy plan.
2. Extend the canonical shared variants producer for backend-owned Maxima
   seeds and native source/plan/test receipts, preserving required teacher
   approval, source identity, stale-plan rejection and review semantics.
3. Adopt STACK's compiled PRT/CASText controller where supported, with explicit
   capability diagnostics for the remaining subset. Do not preserve a second
   independently evolving response-tree implementation as the final design.
4. Connect the normal Quarto author flow to the runner and complete its plan
   cache and conformance suite, with no Chromium/Playwright dependency in
   author builds. Test the installed package, not only source checkouts.

H1's native continuation is implemented as M4d below using the text-only stack.check
contract; Moodle seed import is M4e. Neither is silently replaced by the old
prototype bridge. M4g compatibility/locales and M4h distribution/offline closure
remain separate, tracked phases. Report implementation evidence and deviations
at each phase boundary; AC retains merging and release ownership.

## M4d: native PythonChecker continuation — 27 October 2026

The compiled Maxima PRT suspends/resumes around Python nodes using opaque exact
written state. It retains all tree routing and scoring; there is no host-side
tree interpreter. Author builds invoke the existing H1 checker in isolated
Python processes. Browser cards own an unpublished private Pyodide worker,
loaded before the calculation clock. Stop, internal failure and variant
changes retire the native/Python pair. Ordinary native questions start no
Python interpreter. Source-loaded runtime-v3 and its archive format are unchanged.

Custom, supplied library and implicit block checkers are covered, including
numeric partial credit, invalid outcomes, escaped plain feedback, matrix axes,
fresh namespaces and final assigned identities. Declarative answers are resolved
in native Maxima; a small result-only checker endpoint reuses the common
expectation contract. It never prepares or grades mathematics. CI retains
normal native replay/lifecycle coverage; this change does not modify the ECL
call/lifetime boundary and does not trigger the full GC stress campaign.

Evidence: 32 independent mixed-tree verdict cases (including two consecutive
Python nodes and exact 39-digit state), five native integration families with
23 XML/declarative tests, and installed browser acceptance in Chromium,
Firefox and WebKit. CI artifacts contain the raw observations. Remaining
programme work includes JSXGraph/CASText breadth, validation/locales and
packaging/offline distribution; M4e seed import remains separate.

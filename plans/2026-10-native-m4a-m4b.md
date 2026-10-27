# M4a and M4b: native STACK integration against runtime-v3

AC requested implementation on 26 October 2026. Runtime-v3 remains the fixed
runtime, with source-loaded STACK at `3338304`; no new compiler profile,
compiled STACK default, tag or release is part of this work.

The shared card shell, backend contract, reviewed-variants infrastructure and
H1 checker entry are already on main. `cas: maxima` currently fails at build,
and the canonical variants resolver separately rejects a Maxima backend.
Those guards must stay until a real native producer and adapter satisfy the
same publication and request contracts. The research prototype is evidence
and a regression oracle, not the production UI implementation.

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

H1's native continuation is M4d and uses the merged text-only stack.check
contract; Moodle seed import is M4e. Neither is silently replaced by the old
prototype bridge. M4g compatibility/locales and M4h distribution/offline closure
remain separate, tracked phases. Report implementation evidence and deviations
at each phase boundary; AC retains merging and release ownership.

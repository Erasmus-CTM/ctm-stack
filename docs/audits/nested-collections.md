# Nested finite collections audit

Independent reviewer: GPT-6 Sol, xhigh, read-only review of the development
branch. Base: PR #9's green head `88ba6ee2a753ff79431d06dd9e3c95dba635bbb3`.
Final review: no remaining blockers in the declared bounded scope. The reviewer
independently passed 146 focused tests plus 17 subtests, bundle equality and
diff whitespace checks; full-suite/native/CI evidence is recorded separately.

## Scope

Nested lists/sets of existing scalar expressions; AlgEquiv, Sets, SameType and
collection EqualComAss; bounded, author-only finite helpers under normal
simplification. Limits: 32 members per container, six levels, 128 collection-tree
nodes. Learner set operators, logical leaves, infinite sets/intervals, matrices,
general collection arithmetic and EqualComAssRules remain unsupported.

Two executable XML examples cover nested values, typed input validation, held
forms, repeated set entries, helper values, CASText and authored qtests. Native
controls and project-owned portable fixtures cover behavior separately from the
unchanged 2,303-row upstream inventory.

## Findings and resolutions

- Held teacher and qtest aliases can lose x+x or repeated-member form when frozen.
  Verify dependencies transitively and reject unpreservable forms, including
  a transformation mixed with another held expression.
- Native floating set members differ from exact rational members, even for 0.5.
  Reject decimal literals anywhere beneath a set and transitive decimal author
  aliases reaching collection/helper expressions, qtests or CASText.
- Decimal list function calls and author transformations can lose binary64
  provenance and falsely pass after rational evaluation. Admit decimal list
  leaves only through the supported literal constant-arithmetic path; use exact
  fractions for functions, symbolic leaves and transforms.
- Feedback aliases and newly constructed learner collections can lose decimal
  arithmetic on serialization. Require a direct learner input name for dynamic
  collection checks, frozen author teacher values, and reject learner-dependent
  collection/helper construction. Static feedback aliases used as collection
  sans are conservatively excluded too.
- Learners can reference decimal-derived scalar author variables inside a list
  or set. Runtime validation now checks transitive definition provenance and
  rejects these answers with an exact-fractions diagnostic.
- Frozen exact rational teacher members have no child AST. Reconstruct that exact
  rational side during recursive list comparison so a literal decimal student
  expression retains its binary64 comparison.
- Preserve ordinary scalar author rand([decimal,...]) behavior: the collection
  decimal transformation boundary applies to a collection result, not to scalar
  random selection.
- Native SameType deliberately treats unequal list lengths as applicable and
  accepts any set/set pair. Document and test this rather than asserting a full
  nested-shape match. Ordinary answer-test notes remain abbreviated English.

## Explicit semantics

Nested radical-pair legacy row 202 has desired score -3, Python true and pinned
native false. It is recorded as a known native mathematical failure. Existing
row 212 remains a known port normalization difference, not a pass. Public
semantics documentation distinguishes both and gives discussion questions for
the STACK author. No expression-specific grader exception or upstream fixture
edit is used.

Author helpers require normal simplification; native held helper behavior can
retain duplicates or depend on written ordering. Direct helper calls in held
tests, helper feedback variables and helpers with question simplification off
fail clearly. Simplified frozen results remain usable. listify(set) supports
only rational scalar members in numeric order.

## Validation

The full non-rendering Python suite (571 tests plus 149 subtests), new XML qtests, generated runtime bundle,
corpus regeneration and pinned native compatibility are checked locally.
The native inventory executes 872 eligible cases without errors. Project
regressions separately cover mathematical results and unsupported boundaries;
local browser parity is intentionally unavailable. Quarto's Sass runtime cannot
run in this container, so local rendering/browser success is not claimed.
GitHub Actions must additionally pass site rendering, Worker/Pyodide browser
tests, portable parity, project regressions and compliance report assembly before
the PR is reported green.

"""Bounded finite collections: ordered lists and normalized structural sets.

Lists use scalar AlgEquiv at each position. Sets deliberately do not search
for a bijection using scalar AlgEquiv: STACK compares prepared set members.
SymPy's scalar canonicalization can differ from Maxima's; these differences
are recorded on the separate mathematical and native compatibility axes.
"""
from __future__ import annotations

import sympy as sp

from .expressions import HeldSet, is_collection, collection_items, validate_collection


def _unique(items):
    return list(dict.fromkeys(items))


def _prepare(items, *, mathematical_constants=False):
    # Retain structural scalar members. In particular, a scalar trigonometric
    # identity is not automatically a set-member match in pinned native STACK.
    result = []
    for item in items:
        # Bounded numeric complex exponentials have an exact rectangular
        # representation. Do not expand symbolic branches or arbitrary powers.
        factors = sp.Mul.make_args(item)
        exponentials = [x for x in factors if x.func == sp.exp]
        if (mathematical_constants and len(exponentials) == 1 and item.count_ops() <= 30
                and all(x.is_Rational for x in factors if x.func != sp.exp)):
            angle = exponentials[0].args[0] / (sp.I * sp.pi)
            if angle.is_Rational and abs(angle.p) <= 100 and angle.q <= 24:
                item = sp.expand_complex(item)
        result.append(item)
    return _unique(result)


def collection_test(name, student, teacher, scalar_equiv):
    """Return CAS applicability separately from syntactic input validity."""
    for value in (student, teacher):
        validate_collection(value)
    def result(correct, note="", feedback="", applicable=True):
        return {"valid": True, "correct": correct, "cas_valid": applicable,
                "note": note, "feedback": feedback}
    if name == "Sets":
        if not isinstance(teacher, HeldSet):
            return result(False, "ATSets_SB_not_set", "The teacher answer must be a set.", False)
        if not isinstance(student, HeldSet):
            return result(False, "ATSets_SA_not_set", "Enter a set using braces {...}.", False)
    elif type(student) is not type(teacher) or not is_collection(teacher):
        return result(False, feedback="The answer and teacher must have the same collection type.", applicable=False)
    if isinstance(teacher, list):
        if len(student) != len(teacher):
            return result(False, "ATList_wronglen", "The list has the wrong number of entries.")
        wrong = [str(i + 1) for i, (a, b) in enumerate(zip(student, teacher)) if not scalar_equiv(a, b, i)]
        return result(not wrong, "ATList_wrongentries" if wrong else "",
                      "Check list positions: " + ", ".join(wrong) + "." if wrong else "")
    original = collection_items(student)
    sa, ta = _unique(original), _unique(collection_items(teacher))
    # AlgEquiv simplifies/deduplicates before ATSet's cardinality check;
    # Sets reports duplicates after its normalization instead.
    if name == "AlgEquiv" and len(sa) != len(ta):
        return result(False, "ATSet_wrongsz", "The set has the wrong number of elements.")
    sa, ta = (_prepare(items, mathematical_constants=name == "AlgEquiv") for items in (sa, ta))
    extra = [x for x in sa if x not in ta]
    missing = [x for x in ta if x not in sa]
    correct = not extra and not missing
    if name == "AlgEquiv":
        return result(correct, "" if correct else "ATSet_wrongentries",
                      "Check the elements of the set." if not correct else "")
    duplicate = len(sa) < len(original)
    notes, feedback = [], []
    if duplicate:
        notes.append("ATSets_duplicates")
        feedback.append("Repeated elements were removed from the set.")
    if extra:
        notes.append("ATSets_wrongentries")
        # Keep feedback text-only: the engine appends it to sanitized HTML.
        feedback.append("Extra elements: " + ", ".join(str(x) for x in extra) + ".")
    if missing:
        notes.append("ATSets_missingentries")
        feedback.append("Missing elements: " + ", ".join(str(x) for x in missing) + ".")
    return result(correct, " | ".join(notes), " ".join(feedback))

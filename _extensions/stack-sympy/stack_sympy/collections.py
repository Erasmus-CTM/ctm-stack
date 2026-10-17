"""Bounded collection equality, applicability, and structural normalization.

Lists recurse using scalar AlgEquiv. Sets compare prepared structural members;
they do not search for a bijection using scalar algebraic proofs.
"""
from __future__ import annotations
import sympy as sp
from .expressions import (HeldSet, HeldList, MatrixValue, is_collection, collection_items,
                          collection_kind, validate_collection)


def normalized_value(value, *, mathematical_constants=False):
    """Automatic scalar canonicalization, recursively preserving collection type.

    No expansion or general scalar equality proof is used for set membership.
    """
    if is_collection(value):
        items = [normalized_value(x, mathematical_constants=mathematical_constants)
                 for x in collection_items(value)]
        if collection_kind(value) == 'set':
            return HeldSet(*unique(items))
        if collection_kind(value) == 'matrix':
            return MatrixValue(*items)
        return HeldList(*items) if isinstance(value, HeldList) else items
    if value.args:
        value = value.func(*(normalized_value(x) for x in value.args))
    factors = sp.Mul.make_args(value)
    exponentials = [x for x in factors if x.func == sp.exp]
    if (mathematical_constants and len(exponentials) == 1 and value.count_ops() <= 30
            and all(x.is_Rational for x in factors if x.func != sp.exp)):
        angle = exponentials[0].args[0] / (sp.I * sp.pi)
        if angle.is_Rational and abs(angle.p) <= 100 and angle.q <= 24:
            value = sp.expand_complex(value)
    return value


def structural_key(value):
    kind = collection_kind(value)
    if kind == 'scalar':
        return ('scalar', value)
    keys = [structural_key(x) for x in collection_items(value)]
    if kind == 'set':
        keys = sorted(set(keys), key=repr)
    return (kind, tuple(keys))


def unique(items):
    result, seen = [], set()
    for item in items:
        key = structural_key(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def same_type(student, teacher):
    """STACK SameType is AlgEquiv applicability, not recursive shape equality.

    ATList returns applicable before comparing members when lengths differ;
    ATSet returns applicable for every pair of supported sets.
    """
    sk, tk = collection_kind(student), collection_kind(teacher)
    if sk != tk:
        return False
    if tk == 'list':
        a, b = collection_items(student), collection_items(teacher)
        return len(a) != len(b) or all(same_type(x, y) for x, y in zip(a, b))
    return True


def collection_test(name, student, teacher, compare):
    for value in (student, teacher):
        validate_collection(value)
    def result(correct, note='', feedback='', applicable=True):
        return dict(valid=True, correct=correct, cas_valid=applicable, note=note, feedback=feedback)
    if name == 'Sets':
        if collection_kind(teacher) != 'set':
            return result(False, 'ATSets_SB_not_set', 'The teacher answer must be a set.', False)
        if collection_kind(student) != 'set':
            return result(False, 'ATSets_SA_not_set', 'Enter a set using braces {...}.', False)
    elif collection_kind(student) != collection_kind(teacher) or not is_collection(teacher):
        return result(False, feedback='The answer and teacher must have the same collection type.', applicable=False)
    if collection_kind(teacher) == 'matrix':
        if student.shape[0] != teacher.shape[0]:
            return result(False, 'ATMatrix_wrongsz_rows', 'The matrix has the wrong number of rows.')
        if student.shape[1] != teacher.shape[1]:
            return result(False, 'ATMatrix_wrongsz_columns', 'The matrix has the wrong number of columns.')
        entries = [compare(a, b, i) for i, (a, b) in enumerate(zip(student.args, teacher.args))]
        correct = all(entry['correct'] for entry in entries)
        return result(correct, '' if correct else 'ATMatrix_wrongentries',
                      '' if correct else 'Check the entries of the matrix.',
                      all(entry.get('cas_valid', entry['valid']) for entry in entries))
    if collection_kind(teacher) == 'list':
        sa, ta = collection_items(student), collection_items(teacher)
        if len(sa) != len(ta):
            return result(False, 'ATList_wronglen', 'The list has the wrong number of entries.')
        entries = [compare(a, b, i) for i, (a, b) in enumerate(zip(sa, ta))]
        wrong = [str(i + 1) for i, entry in enumerate(entries) if not entry['correct']]
        return result(not wrong, 'ATList_wrongentries' if wrong else '',
                      'Check list positions: ' + ', '.join(wrong) + '.' if wrong else '',
                      all(entry.get('cas_valid', entry['valid']) for entry in entries))
    original = collection_items(student)
    sa = unique(collection_items(normalized_value(student)))
    ta = unique(collection_items(normalized_value(teacher)))
    if name == 'AlgEquiv' and len(sa) != len(ta):
        return result(False, 'ATSet_wrongsz', 'The set has the wrong number of elements.')
    sa, ta = [unique([normalized_value(x, mathematical_constants=name == 'AlgEquiv') for x in items])
              for items in (sa, ta)]
    sa_keys, ta_keys = {structural_key(x) for x in sa}, {structural_key(x) for x in ta}
    extra = [x for x in sa if structural_key(x) not in ta_keys]
    missing = [x for x in ta if structural_key(x) not in sa_keys]
    correct = not extra and not missing
    if name == 'AlgEquiv':
        return result(correct, '' if correct else 'ATSet_wrongentries',
                      'Check the elements of the set.' if not correct else '')
    notes, feedback = [], []
    if len(sa) < len(original):
        notes.append('ATSets_duplicates')
        feedback.append('Repeated elements were removed from the set.')
    if extra:
        notes.append('ATSets_wrongentries')
        feedback.append('Extra elements: ' + ', '.join(str(x) for x in extra) + '.')
    if missing:
        notes.append('ATSets_missingentries')
        feedback.append('Missing elements: ' + ', '.join(str(x) for x in missing) + '.')
    return result(correct, ' | '.join(notes), ' '.join(feedback))

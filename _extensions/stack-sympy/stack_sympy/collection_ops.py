"""Author-only finite helpers in normal simplification mode."""
import sympy as sp
from .expressions import (HeldSet, Unsupported, InvalidAnswer, collection_kind,
                          collection_items, validate_collection)
from .collections import normalized_value, structural_key, unique


def collection_operation(name, arguments):
    # Bound the whole argument forest before transformation, including aliases.
    validate_collection(arguments)
    args = [normalized_value(x) for x in arguments]
    def arity(low, high=None):
        if not low <= len(args) <= (low if high is None else high):
            raise InvalidAnswer(f'{name} has an unsupported number of arguments')
    def sets():
        if any(collection_kind(x) != 'set' for x in args):
            raise InvalidAnswer(f'{name} requires sets')
    def finish(value):
        validate_collection(value)
        return value
    if name == 'set':
        arity(0,32)
        return finish(HeldSet(*unique(args)))
    if name in {'setify','listify'}:
        arity(1)
        kind = collection_kind(args[0])
        if name == 'setify':
            if kind != 'list':
                raise InvalidAnswer('setify requires a list')
            return finish(HeldSet(*unique(collection_items(args[0]))))
        if kind == 'list':
            return finish(list(collection_items(args[0])))
        if kind != 'set':
            raise InvalidAnswer('listify requires a set or list')
        items = collection_items(args[0])
        if any(not isinstance(x, sp.Rational) for x in items):
            raise Unsupported('listify ordering supports rational scalar set members only')
        return finish(sorted(items))
    if name == 'member':
        arity(2)
        if collection_kind(args[1]) not in {'list','set'}:
            raise InvalidAnswer('member requires a list or set as its second argument')
        return sp.true if structural_key(args[0]) in {structural_key(x) for x in collection_items(args[1])} else sp.false
    if name == 'cardinality':
        arity(1);sets()
        return sp.Integer(len(unique(collection_items(args[0]))))
    if name in {'subsetp','setdifference'}:
        arity(2);sets()
        keys = {structural_key(x) for x in collection_items(args[1])}
        if name == 'subsetp':
            return sp.true if all(structural_key(x) in keys for x in collection_items(args[0])) else sp.false
        return finish(HeldSet(*(x for x in collection_items(args[0]) if structural_key(x) not in keys)))
    if name in {'union','intersection'}:
        arity(0 if name == 'union' else 1,8);sets()
        if name == 'union':
            return finish(HeldSet(*unique([x for arg in args for x in collection_items(arg)])))
        other = [{structural_key(x) for x in collection_items(arg)} for arg in args[1:]]
        return finish(HeldSet(*(x for x in collection_items(args[0]) if all(structural_key(x) in s for s in other))))
    raise Unsupported('Unknown finite collection helper')

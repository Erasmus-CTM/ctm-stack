"""Public immutable value vocabulary for PythonChecker API version 1.

Checkers receive student and teacher values, then a JSON options dictionary,
not written student syntax. Held sets and logic deliberately
retain repetitions; they are not simplifying SymPy sets/Boolean constructors.
"""
from sympy import ImmutableMatrix as Matrix
from .expressions import (HeldList as ListValue, HeldSet as SetValue,
                          Equation, Logical, collection_items)

API_VERSION = 1
__all__ = ["API_VERSION", "Matrix", "ListValue", "SetValue", "Equation",
           "Logical", "collection_items"]

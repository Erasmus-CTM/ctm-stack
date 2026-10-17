"""Shared, JSON-safe conformance vocabulary; no host or browser dependencies."""

from __future__ import annotations

import re

SUPPORTED_TESTS = frozenset({
    "AlgEquiv", "Sets", "SameType", "EqualComAss", "FacForm", "SingleFrac", "LowestTerms",
    "NumAbsolute", "NumRelative", "NumDecPlaces",
})
CONTROLLED_ERRORS = frozenset({"invalid_student", "invalid_teacher", "invalid_option"})
OBSERVATION_FIELDS = (
    "kind", "valid", "correct", "cas_valid", "note", "feedback", "exception_type", "message",
)


def expected_error_kind(answer_note: str) -> str | None:
    """Read the asserted error's source field from an upstream fixture note.

    An unknown or contradictory note is intentionally not a wildcard. The
    evaluator does not read this note; only the desired-outcome comparison does.
    """
    if not isinstance(answer_note, str):
        return None
    patterns = {
        "invalid_student": (r"_STACKERROR_SAns\.", r"TEST_FAILED-Empty SA\."),
        "invalid_teacher": (r"_STACKERROR_TAns\.", r"TEST_FAILED-Empty TA\."),
        "invalid_option": (r"_STACKERROR_Opt\.", r"_STACKERROR_tol\.",
                           r"_OptNotInt\.", r"STACKERROR_OPTION\."),
    }
    found = [kind for kind, expressions in patterns.items()
             if any(re.search(expression, answer_note) for expression in expressions)]
    return found[0] if len(found) == 1 else None


def desired_outcome(score: int, answer_note: str = "") -> dict:
    """Interpret upstream fixture codes on the mathematical desired axis.

    -2/-3 describe known native deviations, not a waiver for the adapter.
    """
    if type(score) is not int or score not in (-3, -2, -1, 0, 1):
        raise ValueError(f"Unknown fixture expected_score: {score!r}")
    if score == -1:
        return {"kind": "controlled_error", "correct": None,
                "error_kind": expected_error_kind(answer_note)}
    return {"kind": "result", "correct": score in (1, -3)}


def comparable(observation: dict) -> dict:
    """Only stable semantic fields participate in parity and policy checks."""
    return {key: observation[key] for key in OBSERVATION_FIELDS if key in observation}


def matches_desired(observation: dict, score: int, answer_note: str = "") -> bool:
    desired = desired_outcome(score, answer_note)
    if desired["kind"] == "controlled_error":
        return (desired["error_kind"] in CONTROLLED_ERRORS
                and observation.get("kind") == desired["error_kind"])
    return (observation.get("kind") == "result"
            and observation.get("valid") is True
            and observation.get("correct") is desired["correct"])

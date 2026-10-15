"""Shared, JSON-safe conformance vocabulary; no host or browser dependencies."""

from __future__ import annotations

SUPPORTED_TESTS = frozenset({
    "AlgEquiv", "EqualComAss", "FacForm", "SingleFrac", "LowestTerms",
    "NumAbsolute", "NumRelative", "NumDecPlaces",
})
CONTROLLED_ERRORS = frozenset({"invalid_student", "invalid_teacher", "invalid_option"})
OBSERVATION_FIELDS = (
    "kind", "valid", "correct", "cas_valid", "note", "feedback", "exception_type", "message",
)


def desired_outcome(score: int) -> dict:
    """Interpret upstream fixture codes on the mathematical desired axis.

    -2/-3 describe known native deviations, not a waiver for the adapter.
    """
    if type(score) is not int or score not in (-3, -2, -1, 0, 1):
        raise ValueError(f"Unknown fixture expected_score: {score!r}")
    if score == -1:
        return {"kind": "controlled_error", "correct": None}
    return {"kind": "result", "correct": score in (1, -3)}


def comparable(observation: dict) -> dict:
    """Only stable semantic fields participate in parity and policy checks."""
    return {key: observation[key] for key in OBSERVATION_FIELDS if key in observation}


def matches_desired(observation: dict, score: int) -> bool:
    desired = desired_outcome(score)
    if desired["kind"] == "controlled_error":
        return observation.get("kind") in CONTROLLED_ERRORS
    return (observation.get("kind") == "result"
            and observation.get("valid") is True
            and observation.get("correct") is desired["correct"])

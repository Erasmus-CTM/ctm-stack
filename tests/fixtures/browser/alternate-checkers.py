"""Same ID on a second card must not replace another card's source."""
calls = 0


def check(student, teacher):
    global calls
    calls += 1
    return {"valid": True, "correct": bool(calls == 1 and student == teacher + 1),
            "feedback": "<b>Literal custom diagnostic</b>"}


CHECKERS = {"positive_multiple": check}

def paint(student, teacher, options):
    return {"valid": True, "correct": True,
            "assessment": {"columns": ["correct"] * student.cols}}


def domain(student, teacher, options):
    valid = student[0, 0] > 0
    return {"valid": bool(valid), "correct": bool(valid),
            "feedback": "" if valid else "Enter a positive entry."}


CHECKERS = {"paint": paint, "domain": domain}

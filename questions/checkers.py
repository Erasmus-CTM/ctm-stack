"""Trusted checker: source for the positive-integer-multiple example."""

def check(response, symbols):
    student = response["answers"]["ans"]
    divisor = response["variables"]["d"]
    if student.is_Integer is not True:
        return {"valid": False, "feedback": "Enter an integer value."}
    correct = student > 0 and student % divisor == 0
    return {"correct": bool(correct),
            "feedback": "" if correct else "Use a positive integer multiple of the given number."}

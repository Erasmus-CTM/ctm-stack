"""Independently challenge the live teaching copies, preserving source imports."""
from pathlib import Path
from xml.etree import ElementTree as ET


from stack_sympy.engine import grade, instantiate, run_question_tests
from stack_sympy.importer import import_xml

ROOT = Path(__file__).resolve().parents[1]


def test_corrected_copies_replay_their_author_tests_on_every_deployed_seed():
    for path in sorted((ROOT / "questions/corrected").glob("*.xml")):
        question = import_xml(path)[0]
        seeds = [int(s.text) for s in ET.parse(path).findall("question/deployedseed")]
        result = run_question_tests(question, seeds=seeds)
        assert result["passed"], (path.name, result)


def test_reduced_wrong_values_never_pass_the_live_fraction_question():
    original = import_xml(ROOT / "questions/corpus/AlgMap-2-5.xml")[0]
    corrected = import_xml(ROOT / "questions/corrected/AlgMap-2-5.xml")[0]
    for seed in (554625703, 2004313867, 1257826844, 533970977, 1878644045):
        variant = instantiate(corrected, seed)
        assert grade(corrected, {"ans": str(variant["env"]["ta"])}, variant=variant)["score"] == 1
        assert grade(corrected, {"ans": "123/127"}, variant=variant)["score"] == 0
        assert grade(original, {"ans": "123/127"}, seed=seed)["score"] == 1


def test_exponent_feedback_uses_the_product_rule():
    for filename in ("AlgMap-1-5.xml", "AlgMap-6-4.xml"):
        corrected = ET.parse(ROOT / "questions/corrected" / filename)
        feedback = corrected.findtext("question/generalfeedback/text")
        assert r"c^a\cdot c^b=c^{a+b}" in feedback
        assert "c^a+c^b=c^{a+b}" not in feedback
        # A numeric counterexample separates the wrong rule from the right one.
        assert 2**2 + 2**3 != 2**5
        assert 2**2 * 2**3 == 2**5

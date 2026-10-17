"""Input schema boundaries and independent matrix editor packaging."""
import json
from pathlib import Path

import pytest

from stack_sympy.importer import import_xml, UnsupportedQuestion
from stack_sympy.engine import instantiate, run_question_tests

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'questions/bounded-matrices.xml'


def test_bounded_matrix_example_and_frozen_input():
    question = import_xml(SOURCE)[0]
    assert question['inputs'][0]['matrix']['rows'] == {'auto': True, 'initial': 2, 'min': 1, 'max': 4}
    variant = instantiate(question, 17)
    assert 'data-matrix-spec=' in variant['question_html']
    assert 'stack-matrix' in variant['question_html']
    assert run_question_tests(question)['passed']


@pytest.mark.parametrize('before,after', [
    ('min="1"', 'min="0"'), ('max="4"', 'max="17"'),
    ('max="4"', 'max="16"'), ('resizable="1"', 'resizable="0"'),
    ('initial="2"', 'initial="99"'), ('<type>matrix</type>', '<type>algebraic</type>'),
])
def test_matrix_input_schema_rejects_unsupported_bounds(before, after):
    with pytest.raises(UnsupportedQuestion):
        import_xml(SOURCE.read_text().replace(before, after))


def test_native_fixed_input_derives_dimensions_from_teacher():
    import re
    source = re.sub(r'<matrix>.*?</matrix>', '', SOURCE.read_text())
    question = import_xml(source)[0]
    assert question['inputs'][0]['matrix'] is None
    # The resizable example deliberately contains wrong-shape qtests, which
    # are outside the fixed input's authoring contract after removing config.
    question['qtests'] = []
    assert '&quot;auto&quot;: false' in instantiate(question, 17)['question_html']

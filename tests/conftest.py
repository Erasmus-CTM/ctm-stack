"""Controlled Quarto pages for behavioral tests, independent of site copy.

The tests import ctm_checkers (with its STACK engine) from the wheels of the
installed ctm-checkers, as the build's Python does (tests/ctm_parts.py)."""
import shutil
import xml.etree.ElementTree as ET

import pytest

import ctm_parts

ctm_parts.python_path()
from test_render import ROOT, render_site


@pytest.fixture(scope="session")
def browser_site(tmp_path_factory):
    project = tmp_path_factory.mktemp("browser-project")
    shutil.copytree(ROOT / "tests/fixtures/browser", project, dirs_exist_ok=True)
    shutil.copytree(ROOT / "_extensions/ctm-stack", project / "_extensions/ctm-stack")
    ctm_parts.install(project)
    shutil.copytree(ROOT / "questions", project / "questions")
    # Test-owned notes distinguish mathematical variants so the shared chooser
    # can be exercised independently of legacy examples with a constant note.
    for name,note in {'polynomial-expansion.xml':'a={@a@}, b={@b@}',
                      'bounded-matrices.xml':'a={@a@}',
                      'python-checker.xml':'d={@d@}'}.items():
        path=project/'questions'/name
        tree=ET.parse(path);question=tree.getroot().find('question')
        node=question.find('questionnote')
        if node is None:node=ET.SubElement(question,'questionnote')
        text=node.find('text')
        if text is None:text=ET.SubElement(node,'text')
        text.text=note;tree.write(path,encoding='unicode')
    # The alternate checker intentionally has a different mathematical rule.
    # Give that test-owned card its own truthful XML tests; V5 runs them at build.
    alternate=ET.parse(project/'questions/python-checker.xml')
    for case,value,score in zip(alternate.findall('.//qtest'),('d+1','d','-d','d+2'),(1,0,0,0)):
        case.find('testinput/value').text=value
        expected=case.find('expected')
        expected.find('expectedscore').text=str(score)
        expected.find('expectedpenalty').text='0' if score else '0.1'
        expected.find('expectedanswernote').text='multiple-T' if score else 'multiple-F'
    alternate.write(project/'questions/alternate-python-checker.xml',encoding='unicode')
    return render_site(project)

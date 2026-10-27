"""Structural input and author-service diagnostics, without a Wasm startup."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
NATIVE=ROOT/'_extensions/ctm-stack/native'
spec=importlib.util.spec_from_file_location('native_frontend_controls',NATIVE/'compiler.py')
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)


def test_nested_list_text_is_not_mistaken_for_a_castext_block(tmp_path):
    source=Path(os.environ.get('CTM_CHECKERS_SOURCE',ROOT/'_ctm-checkers-source'))/'examples/stack/polynomial-expansion.xml'
    tree=ET.parse(source)
    question=tree.getroot().find('question')
    question.find('questiontext/text').text=r'Compare \([[a,b],[c,d]]\). [[input:ans]] [[validation:ans]]'
    target=tmp_path/'question.xml';tree.write(target,encoding='unicode')
    model,_=compiler.model(target,question.findtext('name/text'))
    assert '[[a,b]' in model['questiontext']


def test_failed_server_request_exits_even_when_the_input_pipe_stays_open():
    child=subprocess.Popen([os.environ.get('CTM_STACK_NODE','node'),str(NATIVE/'compile-question.mjs'),'--server'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        child.stdin.write((json.dumps({'id':1,'request':{'schema':999}})+'\n').encode())
        child.stdin.flush()
        assert child.wait(timeout=5)==1
        assert b'Expected an installed STACK wheel hash' in child.stderr.read()
        assert child.stdout.read()==b''
    finally:
        if child.poll() is None:child.kill();child.wait()
        child.stdin.close();child.stdout.close();child.stderr.close()

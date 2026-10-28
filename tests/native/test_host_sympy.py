"""The build-time host SymPy guard against ctm-libs' record of its Pyodide's SymPy."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('native_host_sympy',ROOT/'_extensions/ctm-stack/native/compiler.py')
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)


def libs(tmp_path,record):
    folder=tmp_path/'ctm-libs';(folder/'runtime').mkdir(parents=True)
    (folder/'runtime/pyodide-sympy.json').write_text(json.dumps(record))
    return folder


def test_matching_host_sympy_builds(tmp_path):
    folder=libs(tmp_path,{'pyodide':'0.28.3','sympy':'1.13.3'})
    assert compiler.pyodide_sympy(folder)=={'pyodide':'0.28.3','sympy':'1.13.3','path':str(folder/'runtime/pyodide-sympy.json')}
    compiler.check_host_sympy({'version':[3,12,0],'sympyVersion':'1.13.3'},'python',folder)


def test_other_host_sympy_stops_with_both_versions_and_the_install_command(tmp_path):
    folder=libs(tmp_path,{'pyodide':'0.28.3','sympy':'1.13.3'})
    with pytest.raises(ValueError) as error:
        compiler.check_host_sympy({'version':[3,12,0],'sympyVersion':'1.14.0'},'/env/bin/python',folder)
    message=str(error.value)
    assert 'Host SymPy 1.14.0' in message and 'SymPy 1.13.3' in message and 'Pyodide 0.28.3' in message
    assert 'python-checker-identity' in message
    assert "\"/env/bin/python\" -m pip install 'sympy==1.13.3'" in message


def test_questions_without_python_and_ctm_libs_without_the_record_are_unchanged(tmp_path):
    folder=libs(tmp_path,{'pyodide':'0.28.3','sympy':'1.13.3'})
    compiler.check_host_sympy(None,'python',folder)
    (tmp_path/'old').mkdir()
    assert compiler.pyodide_sympy(tmp_path/'old') is None
    compiler.check_host_sympy({'sympyVersion':'1.14.0'},'python',tmp_path/'old')


def test_a_malformed_record_is_an_error(tmp_path):
    with pytest.raises(ValueError,match='records no Pyodide and SymPy'):
        compiler.pyodide_sympy(libs(tmp_path,{'pyodide':'0.28.3'}))

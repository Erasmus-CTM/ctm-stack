"""Image integrity, independent process launches and cold/image failure gates."""
import json
import re
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from native_compliance import native_image as image
from native_compliance import maxima_runner as native
from benchmark_native_image import compare


def test_image_manifest_rejects_runtime_mismatch_and_corruption():
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        binary = directory / 'stack-gcl'
        binary.write_bytes(b'pristine image')
        identity = {'stack_sha': native.STACK_SHA, 'runtime': 'gcl'}
        manifest = {'identity': identity, 'key': image.fingerprint(identity), 'image_sha256': image.digest(binary)}
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        with patch.object(image, 'identity', return_value=identity):
            assert image.validate(directory, ROOT, 'maxima') == manifest
            binary.write_bytes(b'corrupt')
            with pytest.raises(native.NativeProcessError, match='digest'):
                image.validate(directory, ROOT, 'maxima')
        with patch.object(image, 'identity', return_value={'runtime': 'different'}):
            with pytest.raises(native.NativeProcessError, match='provenance'):
                image.validate(directory, ROOT, 'maxima')


def test_direct_image_preserves_wrapper_options_and_private_environment():
    command = image.command(Path('snapshot'), Path('case.mac'))
    assert command[1:] == ['-eval', '(cl-user::run)', '-f', '--', '--very-quiet', '--batch=case.mac']
    with patch.dict(image.os.environ, {'GCL_MEM_MULTIPLE': '0.7'}):
        env = image.environment(Path('private'))
    assert env['MAXIMA_USERDIR'] == str(Path('private'))
    assert env['MAXIMA_TEMPDIR'] == str(Path('private/tmp'))
    assert env['MAXIMA_OBJDIR'] == str(Path('private/obj'))
    assert env['GCL_MEM_MULTIPLE'] == '0.7'
    assert env['GCL_GC_PAGE_THRESH'] == '0.2'


def test_actual_runtime_detection_requires_printed_build_record_not_available_backend():
    info = 'build_info(lisp_name = "GNU Common Lisp (GCL)", lisp_version = "GCL 2.6.14")'
    with patch.object(native, '_command', return_value='echoed input\nNATIVE-IMAGE-BUILD|'+info+'\n') as call:
        assert image.runtime_identity('maxima') == info
        assert 'print(sconcat(' in call.call_args[0][0][-1]
    for output in ('available: gcl sbcl', 'NATIVE-IMAGE-BUILD|build_info(lisp_name="SBCL")',
                   'NATIVE-IMAGE-BUILD|'+info+'\nNATIVE-IMAGE-BUILD|'+info):
        with patch.object(native, '_command', return_value=output), pytest.raises(native.NativeProcessError):
            image.runtime_identity('maxima')


@pytest.mark.parametrize('key', ['MAXIMA_PREFIX', 'MAXIMA_LISP', 'LISP_OPTIONS', 'VERPKGLIBDIR', 'GCL_UNRANDOMIZE'])
def test_unsupported_runtime_overrides_fail_closed(key):
    with patch.dict(image.os.environ, {key: 'override'}), pytest.raises(native.NativeProcessError, match='override'):
        image.identity(ROOT, 'maxima')


def test_preloaded_batch_rebases_paths_without_loading_stack_again():
    with tempfile.TemporaryDirectory() as temp:
        # This unit checks emitted Maxima, not OS symlink privileges.
        with patch.object(Path, 'symlink_to'):
            batch = native.make_batch(ROOT, [], Path(temp), 0, preloaded=True)
    assert 'load(' not in batch
    assert 'STACK_SETUP(true)' in batch
    assert 'stacklocation:' in batch and 'stacktmplocation:' in batch
    assert 'file_search_maxima:append' in batch and 'file_search_lisp:append' in batch
    assert 'STACKNATIVE-BEGIN|0|0' in batch


def test_runner_launches_separate_image_processes_with_private_homes():
    rows = [{'id': 'a'*64+'-'+str(n), 'test': 'AlgEquiv', 'student': 'x', 'teacher': 'x', 'options': ''}
            for n in (1, 2)]
    launches = []
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp)
        library = source / 'stack/maxima'
        library.mkdir(parents=True)
        (library / 'stacklocallinux.mac').write_text('')
        (library / 'stackmaxima.mac').write_text('stackmaximaversion:123$')
        def command(argv, timeout, **kwargs):
            if argv[0] == 'git':
                return native.STACK_SHA
            if '--version' in argv:
                return 'Maxima GCL'
            batch = Path(argv[-1].removeprefix('--batch='))
            text = batch.read_text()
            assert 'load(' not in text
            assert argv[1:5] == ['-eval', '(cl-user::run)', '-f', '--']
            assert kwargs['env']['MAXIMA_USERDIR'] == str(batch.parent)
            launches.append(str(batch.parent))
            if 'STACKNATIVE-DIAG|' in text:
                return 'STACKNATIVE-BEGIN|0|0\nSTACKNATIVE-DIAG|'+json.dumps([None]*len(native.PROBE_KEYS))+'\nSTACKNATIVE-END|0|0\n'
            number = re.search(r'STACKNATIVE-BEGIN\|(\d+)\|1', text)[1]
            case_id = re.search(r'STACKNATIVE\|([a-f0-9]{64}-\d+)\|', text)[1]
            return f'STACKNATIVE-BEGIN|{number}|1\nSTACKNATIVE|{case_id}|[true,true,""]\nSTACKNATIVE-END|{number}|1\n'
        with patch.object(Path, 'symlink_to'), patch.object(native, '_command', side_effect=command), patch.object(
                native.shutil, 'which', return_value='maxima'), patch.object(image, 'validate', return_value={'key': 'verified'}):
            report = native.run_native(rows, source, image=source, jobs=1)
    assert len(launches) == len(set(launches)) == 3  # warm-up and two independent case processes
    assert report['summary']['ok'] == 2
    assert report['metadata']['preloaded_image'] == {'key': 'verified'}


def test_benchmark_fails_on_answer_note_and_probe_difference():
    case = {'id': 'a'*64+'-1', 'test': 'AlgEquiv', 'student': 'x', 'teacher': 'x', 'options': ''}
    def report(note):
        return {'metadata': {'loader_probe': {'i': '%i'}, 'native_scope_sha256': 'same'},
                'summary': {'total': 1}, 'observations': [{'answer_note': note, 'correct': True}]}
    clean = {'observations': [{'correct': True}, {'correct': False}]}
    with patch('benchmark_native_image.run_native', side_effect=[report('a'), report('b'), clean, clean]), patch(
            'benchmark_native_image.run_standalone_probe', return_value={'probe': {}}):
        assert compare([case], ROOT, ROOT)['passed'] is False
    with patch('benchmark_native_image.run_native', side_effect=[report('a'), report('a'), clean, clean]), patch(
            'benchmark_native_image.run_standalone_probe', side_effect=[{'probe': {'x': 1}}, {'probe': {'x': 2}}]):
        assert compare([case], ROOT, ROOT)['passed'] is False

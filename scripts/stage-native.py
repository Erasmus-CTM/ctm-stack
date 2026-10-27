#!/usr/bin/env python3
"""Stage a verified local runtime-v3 release and exact source-loaded STACK.

No network fetch, build or browser is required. The release files are obtained
from stack-wasm-maxima's GitHub Release; hashes are checked before extraction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / '_extensions/ctm-stack/native'
STACK = json.loads((Path(__file__).resolve().parents[1]/'_extensions/ctm-stack/native/stack-pin.json').read_text())['revision']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stage(release, stack, output):
    pin = json.loads((NATIVE / 'release.json').read_bytes())
    encoded = (release / pin['record']).read_bytes()
    if digest(encoded) != pin['recordSha256']:
        raise ValueError('Runtime release record differs from the v3 pin')
    record = json.loads(encoded)
    if record['tag'] != 'runtime-v3' or record['compilerProfile'] != 'ecl-oz-maxima-oz':
        raise ValueError('Wrong runtime release or compiler profile')
    archive = release / 'maxima-runtime-v3.tar.gz'
    if record['files'][archive.name] != {'sha256': digest(archive.read_bytes()), 'bytes': archive.stat().st_size}:
        raise ValueError('Runtime archive differs from its release record')
    actual = subprocess.check_output(['git', '-C', str(stack), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != STACK:
        raise ValueError('STACK checkout must identify the exact pinned revision')
    if output.exists():
        raise ValueError('Choose a fresh output directory; an existing runtime package is never overwritten')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        work = Path(temporary)
        unpacked = work / 'release'
        unpacked.mkdir()
        with tarfile.open(archive) as bundle:
            members = bundle.getmembers()
            for member in members:
                p = Path(member.name)
                if p.is_absolute() or '..' in p.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('Unsafe runtime archive member')
            bundle.extractall(unpacked, filter='data')
        manifest_bytes = (unpacked / 'manifest.json').read_bytes()
        if digest(manifest_bytes) != record['runtimeManifestSha256']:
            raise ValueError('Runtime manifest differs from the release record')
        manifest = json.loads(manifest_bytes)
        package = work / 'package'
        package.mkdir()
        shutil.copytree(unpacked / 'runtime', package / 'runtime')
        for item in manifest['runtimeAssets']:
            p = Path(item['path'])
            if p.is_absolute() or '..' in p.parts or '\\' in str(p):
                raise ValueError('Unsafe runtime asset path')
            body = (package / 'runtime' / p).read_bytes()
            if len(body) != item['bytes'] or digest(body) != item['sha256']:
                raise ValueError('Runtime asset differs from its manifest: ' + str(p))
        stack_files = []
        # Read exact Git blobs, rather than trusting a possibly edited worktree.
        names = subprocess.check_output(['git', '-C', str(stack), 'ls-tree', '-r', '--name-only', STACK, 'stack/maxima'], text=True).splitlines()
        for name in names:
            if Path(name).suffix not in ('.mac', '.lisp'):
                continue
            body = subprocess.check_output(['git', '-C', str(stack), 'show', STACK + ':' + name])
            target = package / 'stack' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            stack_files.append({'path': name, 'bytes': len(body), 'sha256': digest(body)})
        expected_stack = json.loads((NATIVE / 'stack-files.json').read_bytes())
        if stack_files != expected_stack['files'] or STACK != expected_stack['revision']:
            raise ValueError('STACK library differs from the committed source inventory')
        library = (package / 'stack/stack/maxima/stackmaxima.mac').read_text()
        import re
        version = re.search(r'stackmaximaversion:(\d+)', library)[1]
        classified = (NATIVE / 'classified-errcatch.lisp').read_text().strip()
        startup = manifest['startupAdapter']['content'] + '\n'.join([
            'ctm_emit(s):=printf(true,"~%~a~%",s)$', 'display2d:false$',
            'maxima_userdir:"/ctm"$',
            'load("/ctm/moodle-qtype_stack-master/stack/maxima/stacklocallinux.mac")$',
            'display2d:false$', 'linel:1000000$', ':lisp ' + classified,
            'ctm_emit(sconcat("CTMSTACK-READY|",stackmaximaversion,"|",MAXIMA_VERSION_STR))$', '',
        ])
        spec = {'schema': 1, 'runtimeTag': record['tag'], 'releaseRecordSha256': pin['recordSha256'],
                'runtimeManifestSha256': record['runtimeManifestSha256'], 'runtimeAssets': manifest['runtimeAssets'],
                'stackFiles': stack_files, 'startup': startup,
                'manifest': {'stackRevision': STACK, 'stackLibraryVersion': version,
                             'runtimeAssets': manifest['runtimeAssets']}}
        (package / 'package.json').write_text(json.dumps(spec, indent=2) + '\n')
        # Retain the original GPL/LGPL source offer and licence information.
        for name in ('LICENSES', 'BUILD-NOTICES.md', 'SITE-NOTICES-context.md'):
            source = unpacked / name
            if source.is_dir(): shutil.copytree(source, package / name)
            elif source.is_file(): shutil.copy2(source, package / name)
        (package / pin['record']).write_bytes(encoded)
        (package / 'release-manifest.json').write_bytes(manifest_bytes)
        (package / 'SOURCE-OFFER.txt').write_text(
            'Runtime-v3 source archives, exact build recipe and licence notices:\n'
            'https://github.com/Erasmus-CTM/stack-wasm-maxima/releases/tag/runtime-v3\n'
            'Source archive: maxima-runtime-v3-sources.tar.gz\n'
            'SHA-256: ' + record['files']['maxima-runtime-v3-sources.tar.gz']['sha256'] + '\n'
            'STACK source revision (GPL-3.0-or-later): ' + STACK + '\n'
            'https://github.com/maths/moodle-qtype_stack/tree/' + STACK + '\n')
        shutil.move(str(package), output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--stack-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stage(args.release.resolve(), args.stack_source.resolve(), args.output.resolve())

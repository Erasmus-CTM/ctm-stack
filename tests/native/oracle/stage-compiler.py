#!/usr/bin/env python3
"""Stage the pinned upstream PHP compiler independently of runtime-v3 bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

INDEX = Path(__file__).resolve().with_name('compiler-files.json')
PIN = json.loads((Path(__file__).resolve().parents[3]/'_extensions/ctm-stack/native/stack-pin.json').read_text())['revision']


def inventory(source):
    revision = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision != PIN:
        raise ValueError('Wrong STACK compiler revision')
    records = []
    tree = subprocess.check_output(['git','-C',str(source),'ls-tree','-rz','HEAD'])
    for row in tree.split(b'\0'):
        if not row:
            continue
        metadata, path = row.split(b'\t',1); name = path.decode()
        selected = ((name.startswith('stack/') and name.endswith(('.php','.json')))
                    or name.startswith('api/emulation/') and name.endswith('.php')
                    or name in {'lang/en/qtype_stack.php','lang/multilang.php','locallib.php',
                                'vle_specific.php','version.php','api/config_sample.txt','COPYING.txt'})
        if not selected:
            continue
        mode,kind,oid = metadata.decode().split()
        if mode != '100644' or kind != 'blob':
            raise ValueError('Compiler source is not a regular file: ' + name)
        file = source / name
        body = file.read_bytes() if file.is_file() and not file.is_symlink() else subprocess.check_output(
            ['git','-C',str(source),'show',PIN+':'+name])
        if hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest() != oid:
            raise ValueError('Compiler working tree differs from the pinned Git blob: '+name)
        records.append({'path':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
    return {'schema':1,'stackRevision':PIN,'files':records}


def stage(source, output):
    index = json.loads(INDEX.read_text())
    if inventory(source) != index:
        raise ValueError('Compiler source inventory differs from its committed pin')
    if output.exists():
        raise ValueError('Choose a fresh compiler staging directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        work = Path(temp)/'compiler'; work.mkdir()
        for record in index['files']:
            name = record['path']; target = work/name; target.parent.mkdir(parents=True,exist_ok=True)
            file = source/name
            body = file.read_bytes() if file.is_file() else subprocess.check_output(['git','-C',str(source),'show',PIN+':'+name])
            if len(body)!=record['bytes'] or hashlib.sha256(body).hexdigest()!=record['sha256']:
                raise ValueError('Compiler source changed during staging: '+name)
            target.write_bytes(body)
        (work/'compiler.json').write_bytes(INDEX.read_bytes())
        shutil.move(str(work),output)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack-source',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--record-index',action='store_true')
    args=parser.parse_args()
    if args.record_index:
        INDEX.write_text(json.dumps(inventory(args.stack_source),indent=2)+'\n')
    elif args.output:
        stage(args.stack_source,args.output)
    else:
        parser.error('--output is required')

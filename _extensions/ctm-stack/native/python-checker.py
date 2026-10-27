#!/usr/bin/env python3
"""Question-owned host CPython checker service (trusted, unsandboxed H1 code).

Only written values cross this boundary. Each H1 invocation creates its own
checker namespace; imports/caches are shared within this question's process.
"""
import json
from pathlib import Path
import sys

BOUND=2*1024*1024

def read():
    raw=sys.stdin.buffer.readline(BOUND+1)
    if len(raw)>BOUND:raise ValueError('Python checker request exceeds 2 MiB')
    return json.loads(raw) if raw else None

def send(value):
    encoded=json.dumps(value,allow_nan=False)
    if len(encoded.encode())>BOUND:raise ValueError('Python checker response exceeds 2 MiB')
    print(encoded,flush=True)

if __name__=='__main__':
    config=read();paths=config['paths']
    if not isinstance(paths,list) or not all(isinstance(p,str) and Path(p).is_absolute() for p in paths):
        raise ValueError('Expected installed absolute checker wheel paths')
    sys.path[:0]=paths
    import sympy
    from ctm_checkers.stack.page import check,test_results
    send({'type':'ready','version':list(sys.version_info[:3]),'sympyVersion':sympy.__version__})
    sequence=0
    while (message:=read()) is not None:
        sequence+=1
        if message.get('id')!=sequence:raise ValueError('Python checker request sequence differs')
        request=message['request']
        handler=test_results if request.get('operation')=='test-results' else check
        send({'id':sequence,**handler(request)})

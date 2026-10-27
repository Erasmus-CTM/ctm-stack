#!/usr/bin/env python3
"""Isolated author-build invocation of the existing text-only H1 checker API.

Native Maxima already evaluated the question and admitted the learner answer.
Python receives only written values; it never instantiates a question here.
"""
import json
from pathlib import Path
import sys

if __name__=='__main__':
    raw=sys.stdin.buffer.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError('Python checker request exceeds 2 MiB')
    payload=json.loads(raw)
    paths=payload['paths']
    if not isinstance(paths,list) or not all(isinstance(p,str) and Path(p).is_absolute() for p in paths):
        raise ValueError('Expected installed absolute checker wheel paths')
    sys.path[:0]=paths
    from ctm_checkers.stack.page import check,test_results
    request=payload['request']
    handler=test_results if request.get('operation')=='test-results' else check
    print(json.dumps(handler(request),allow_nan=False))

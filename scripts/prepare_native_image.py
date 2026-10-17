"""Fingerprint, build or validate the pristine native STACK/GCL image."""
import argparse
import json
from pathlib import Path
import shutil
from native_compliance.native_image import build, identity, fingerprint, validate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stack-source', type=Path, required=True)
parser.add_argument('--image', type=Path, default=Path('.native-stack-image'))
parser.add_argument('--maxima', default='maxima')
parser.add_argument('--key-only', action='store_true')
args = parser.parse_args()
executable = shutil.which(args.maxima)
if not executable:
    parser.error('Maxima executable not found')
if args.key_only:
    print(fingerprint(identity(args.stack_source, executable)))
elif (args.image / 'manifest.json').exists():
    manifest = validate(args.image, args.stack_source, executable)
    (args.image / 'cache-status.json').write_text(json.dumps({'status': 'hit'})+'\n')
    print(json.dumps({'cache': 'hit', **manifest}))
else:
    manifest = build(args.image, args.stack_source, executable)
    (args.image / 'cache-status.json').write_text(json.dumps({'status': 'built'})+'\n')
    print(json.dumps({'cache': 'built', **manifest}))

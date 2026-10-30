#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the actual guest inputs before starting QEMU."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path, compressed=False):
    result = hashlib.sha256()
    with (gzip.open(path, 'rb') if compressed else path.open('rb')) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile', choices=('core', 'framework'), required=True)
parser.add_argument('--kernel', type=Path, required=True)
parser.add_argument('--initrd', type=Path, required=True)
args = parser.parse_args()
inputs = json.loads((ROOT / f'out/vm/runtime-inputs-{args.profile}.json').read_text())
kernel_sha = digest(args.kernel)
if kernel_sha != inputs['kernel_sha256']:
    raise SystemExit('Kernel differs from staged input record; rebuild with HMOS_VM_KERNEL set')
archive = ROOT / f'out/vm/{args.profile}-compact.cpio.gz'
archive_sha = digest(archive)
initrd_sha = digest(args.initrd)
if initrd_sha != archive_sha:
    with args.initrd.open('rb') as stream:
        compressed = stream.read(2) == b'\x1f\x8b'
    if digest(args.initrd, compressed) != digest(archive, True):
        raise SystemExit('Initrd differs from staged archive')
record = {'kernel': str(args.kernel.resolve()), 'kernel_sha256': kernel_sha,
          'initrd': str(args.initrd.resolve()), 'initrd_sha256': initrd_sha,
          'archive_sha256': archive_sha}
(ROOT / f'out/vm/launch-{args.profile}.json').write_text(json.dumps(record, indent=2) + '\n')

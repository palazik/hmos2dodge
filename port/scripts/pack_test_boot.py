#!/usr/bin/env python3
"""Replace only the kernel in a supplied, Android-tested OP13 boot image."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stock-boot', type=Path, required=True)
parser.add_argument('--kernel', type=Path, default=ROOT / 'out/kernel/Image')
parser.add_argument('--output', type=Path, default=ROOT / 'out/boot/op13-hmos-test.img')
args = parser.parse_args()
source, kernel, output = (p.resolve() for p in (args.stock_boot, args.kernel, args.output))
if output.exists():
    parser.error(f'output already exists: {output}')
if source == output or kernel == output:
    parser.error('output must be a new file')
with source.open('rb') as f:
    header = f.read(4096)
if header[:8] != b'ANDROID!' or struct.unpack_from('<I', header, 40)[0] not in (3, 4):
    parser.error('expected an OP13 Android boot image with header v3/v4; refusing donor/sweet v2')
with kernel.open('rb') as f:
    kernel_header = f.read(64)
if kernel_header[56:60] != b'ARM\x64':
    parser.error('expected an uncompressed ARM64 Linux Image')
tool = ROOT / 'bin/Linux/x86_64/magiskboot'


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def is_dtb_chain(data):
    """Reject magiskboot's false split at the Image's builtin empty DTB."""
    pos = 0
    count = 0
    while pos < len(data):
        if not any(data[pos:]):
            return count > 0
        while pos < len(data) and data[pos] == 0:
            pos += 1
        if data[pos:pos + 4] != b'\xd0\x0d\xfe\xed' or pos + 40 > len(data):
            return False
        length = struct.unpack_from('>I', data, pos + 4)[0]
        if length < 40 or pos + length > len(data):
            return False
        pos += length
        count += 1
    return count > 0


output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='op13-boot-', dir=ROOT / 'work') as tmp:
    tmp = Path(tmp)
    subprocess.run([str(tool), 'unpack', '-h', str(source)], cwd=tmp, check=True)
    genuine_appended_dtb = b''
    if (tmp / 'kernel_dtb').exists():
        split = (tmp / 'kernel_dtb').read_bytes()
        if is_dtb_chain(split):
            genuine_appended_dtb = split
        else:
            print('Discarding false kernel_dtb split inside the old kernel; using the complete new Image')
            (tmp / 'kernel_dtb').unlink()
    before = {p.name: digest(p) for p in tmp.iterdir() if p.is_file() and p.name not in ('kernel', 'kernel_dtb')}
    shutil.copy2(kernel, tmp / 'kernel')
    candidate = tmp / 'candidate.img'
    subprocess.run([str(tool), 'repack', str(source), str(candidate)], cwd=tmp, check=True)
    # The original OEM-signed boot hash cannot authenticate a replacement
    # kernel. Do not retain a misleading stale AVB footer in a temporary image.
    with candidate.open('rb') as f:
        f.seek(-64, 2)
        stale_avb_footer = f.read(4) == b'AVBf'
    if stale_avb_footer:
        avb = ROOT / 'kernel_workspace/build-tools/linux-x86/bin/avbtool'
        subprocess.run([str(avb), 'erase_footer', '--image', str(candidate)], check=True)
    check = tmp / 'verify'
    check.mkdir()
    subprocess.run([str(tool), 'unpack', '-h', str(candidate)], cwd=check, check=True)
    for name, sha in before.items():
        if not (check / name).is_file() or digest(check / name) != sha:
            raise RuntimeError(f'repacked boot changed non-kernel component: {name}')
    # Compare the actual kernel field, not magiskboot's heuristic DTB split.
    with candidate.open('rb') as f:
        candidate_header = f.read(4096)
        candidate_size = struct.unpack_from('<I', candidate_header, 8)[0]
        actual_kernel_field = f.read(candidate_size)
    expected_kernel_field = kernel.read_bytes() + genuine_appended_dtb
    if actual_kernel_field != expected_kernel_field:
        raise RuntimeError('repacked kernel field does not exactly match requested Image plus genuine DTBs')
    shutil.copy2(candidate, output)
manifest = {'stock_boot': str(source), 'stock_sha256': digest(source),
            'kernel_sha256': digest(kernel), 'output_sha256': digest(output),
            'preserved_components': before,
            'genuine_appended_dtb_size': len(genuine_appended_dtb),
            'genuine_appended_dtb_sha256': hashlib.sha256(genuine_appended_dtb).hexdigest(),
            'stale_oem_avb_footer_removed': stale_avb_footer,
            'status': 'build verified; Android boot and vendor-module ABI not device tested'}
output.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Temporary test image: {output}\nTest manually: fastboot boot {output}')

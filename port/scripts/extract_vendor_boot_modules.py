#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Extract regular module files from a vendor boot image into workspace work/."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path)
args = parser.parse_args()
image = args.image.resolve()
if not stat.S_ISREG(image.stat().st_mode):
    raise SystemExit('Input must be a regular image file')
data = image.read_bytes()
if data[:8] != b'VNDRBOOT' or len(data) < 2128:
    raise SystemExit('Expected a vendor boot header')
version, page = struct.unpack_from('<II', data, 8)
size = struct.unpack_from('<I', data, 24)[0]
header_size, dtb_size = struct.unpack_from('<II', data, 2096)
if version not in (3, 4) or page not in (2048, 4096, 8192, 16384) or header_size < 2112:
    raise SystemExit('Unsupported vendor boot header')
align = lambda value: (value + page - 1) // page * page
start = align(header_size)
if start + size > len(data):
    raise SystemExit('Truncated vendor ramdisk')
fragments = [(0, size, 1)]
if version == 4:
    table_size, count, entry_size = struct.unpack_from('<III', data, 2112)
    table = start + align(size) + align(dtb_size)
    if entry_size < 108 or count * entry_size > table_size or table + table_size > len(data):
        raise SystemExit('Invalid vendor ramdisk table')
    fragments = []
    for index in range(count):
        length, offset, kind = struct.unpack_from('<III', data, table + index * entry_size)
        if offset + length > size:
            raise SystemExit('Invalid vendor fragment bounds')
        if kind != 2:  # recovery-only fragments are outside normal boot
            fragments.append((offset, length, kind))
digest = hashlib.sha256(data).hexdigest()
output = ROOT / 'work/module-sources' / digest[:16]
output.mkdir(parents=True, exist_ok=True)
modules = {}
with tempfile.TemporaryDirectory(prefix='vendor-modules-', dir=ROOT / 'work') as folder:
    for index, (offset, length, kind) in enumerate(fragments):
        raw = data[start + offset:start + offset + length]
        if raw[:6] not in (b'070701', b'070702'):
            packed, unpacked = Path(folder) / 'packed', Path(folder) / 'unpacked'
            packed.write_bytes(raw)
            result = subprocess.run([str(ROOT / 'bin/Linux/x86_64/magiskboot'), 'decompress',
                                     str(packed), str(unpacked)], capture_output=True)
            if result.returncode:
                raise SystemExit('Ramdisk decompression failed: ' + result.stderr.decode(errors='replace'))
            raw = unpacked.read_bytes()
        pos = 0
        saw_trailer = False
        while pos < len(raw):
            if pos + 110 > len(raw) or raw[pos:pos + 6] not in (b'070701', b'070702'):
                raise SystemExit('Invalid cpio header')
            fields = [int(raw[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
            name_size, file_size = fields[11], fields[6]
            name_start = pos + 110
            payload = (name_start + name_size + 3) & ~3
            end = payload + file_size
            if name_size < 1 or name_size > 4096 or end > len(raw) or raw[name_start + name_size - 1] != 0:
                raise SystemExit('Invalid cpio entry bounds/name')
            name = raw[name_start:name_start + name_size - 1].decode()
            saw_trailer = name == 'TRAILER!!!'
            entry = PurePosixPath(name)
            if entry.is_absolute() or '..' in entry.parts:
                raise SystemExit('Unsafe cpio path')
            if raw[pos:pos + 6] == b'070702' and sum(raw[payload:end]) & 0xffffffff != fields[12]:
                raise SystemExit('Invalid cpio CRC')
            if name.startswith('lib/modules/') and name.endswith('.ko') and stat.S_ISREG(fields[1]):
                target = output / entry.name
                blob = raw[payload:end]
                if target.exists() and target.read_bytes() != blob:
                    raise SystemExit('Conflicting module basename: ' + entry.name)
                target.write_bytes(blob)
                modules[entry.name] = hashlib.sha256(blob).hexdigest()
            pos = (end + 3) & ~3
            if name == 'TRAILER!!!':
                while pos < len(raw) and raw[pos] == 0:
                    pos += 1
        if not saw_trailer:
            raise SystemExit('Incomplete cpio archive')
if not modules:
    raise SystemExit('No regular module files found')
(output / 'extraction.json').write_text(json.dumps({
    'image': str(image), 'image_sha256': digest, 'fragments': fragments,
    'module_sha256': modules, 'scope': 'Extraction only; no signature or compatibility claim',
}, indent=2) + '\n')
print(output)

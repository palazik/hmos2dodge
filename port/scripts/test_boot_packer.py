#!/usr/bin/env python3
"""Regression checks for embedded-empty-DTB false positives and real DTBs."""
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DTB = bytes.fromhex('d00dfeed00000048000000380000004800000028000000110000001000000000'
                    '0000000000000010000000000000000000000000000000000000000100000000'
                    '0000000200000009')
assert len(DTB) == 72


def kernel(fill):
    data = bytearray(4096)
    data[16:24] = struct.pack('<Q', 8192)
    data[56:60] = b'ARM\x64'
    data[80:88] = fill
    return data


with tempfile.TemporaryDirectory(prefix='boot-regression-', dir=ROOT / 'work') as tmp:
    tmp = Path(tmp)
    new = kernel(b'newimage')
    # New Image also contains an embedded DTB followed by real kernel data.
    new[128:200] = DTB
    new[256:264] = b'new-tail'
    (tmp / 'Image').write_bytes(new)
    for case in ('plain', 'embedded-empty-dtb', 'real-appended-dtb'):
        old = kernel(b'oldimage')
        appended = b''
        if case == 'embedded-empty-dtb':
            old[128:200] = DTB
            old[256:264] = b'old-tail'
        elif case == 'real-appended-dtb':
            appended = DTB
        field = old + appended
        header = struct.pack('<8sIIII4II', b'ANDROID!', len(field), 0, 0, 1584, 0, 0, 0, 0, 4)
        header += bytes(1536) + struct.pack('<I', 0)
        source = tmp / (case + '-source.img')
        output = tmp / (case + '-packed.img')
        source.write_bytes(header.ljust(4096, b'\0') + field + bytes((-len(field)) % 4096))
        result = subprocess.run(['python3', str(ROOT / 'port/scripts/pack_test_boot.py'),
                                 '--stock-boot', str(source), '--kernel', str(tmp / 'Image'),
                                 '--output', str(output)], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        raw = output.read_bytes()
        size = struct.unpack_from('<I', raw, 8)[0]
        assert raw[4096:4096 + size] == new + appended, case
        assert source.read_bytes()[4096:4096 + len(field)] == field, 'source modified'
        print('PASS boot packer: ' + case)

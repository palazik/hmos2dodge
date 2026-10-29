#!/usr/bin/env python3
"""Register ARM64 only in a new, empty user-namespace binfmt_misc registry."""
from pathlib import Path
import sys

registry, emulator = map(Path, sys.argv[1:])
if set(p.name for p in registry.iterdir()) != {'register', 'status'}:
    raise SystemExit('Refusing a nonempty binfmt registry; a fresh private mount is required')
magic = b'\x7fELF\x02\x01\x01\x00' + bytes(8) + b'\x02\x00\xb7\x00'
mask = b'\xff' * 7 + bytes(9) + b'\xfe\xff\xff\xff'
assert len(magic) == len(mask) == 20
def escaped(data):
    return ''.join(f'\\x{byte:02x}' for byte in data).encode()

record = b':ohos-aarch64:M::' + escaped(magic) + b':' + escaped(mask) + b':' + str(emulator).encode() + b':F'
(registry / 'register').write_bytes(record)

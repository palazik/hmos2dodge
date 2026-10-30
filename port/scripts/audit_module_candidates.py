#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare early-module candidates against captured drivers without loading any."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from audit_op13_modules import module, sections


def export_crcs(path):
    data = path.read_bytes()
    sections(data)  # validates the ELF header and section payload bounds
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count = struct.unpack_from('<HH', data, 58)
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size) for i in range(count)]
    result = {}
    for header in headers:
        if header[1] != 2:
            continue
        strings = headers[header[6]]
        table = data[strings[4]:strings[4] + strings[5]]
        if header[9] != 24 or header[5] % 24:
            raise ValueError('Invalid ELF symbol table')
        for pos in range(header[4], header[4] + header[5], 24):
            name, _, _, index, value, _ = struct.unpack_from('<IBBHQQ', data, pos)
            name = table[name:].split(b'\0', 1)[0].decode()
            if not name.startswith('__crc_'):
                continue
            if index == 0xfff1:  # SHN_ABS
                crc = value
            elif index < len(headers) and headers[index][1] != 8 and value + 4 <= headers[index][5]:
                crc = struct.unpack_from('<I', data, headers[index][4] + value)[0]
            else:
                raise ValueError('Invalid exported CRC location: ' + name)
            result[name[6:]] = crc
    return result


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--captured', type=Path, required=True)
parser.add_argument('--candidates', type=Path, required=True)
parser.add_argument('--candidate-image', type=Path, required=True)
parser.add_argument('--symvers', type=Path, default=Path('out/kernel/vmlinux.symvers'))
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
image_sha256 = hashlib.sha256(args.candidate_image.read_bytes()).hexdigest()
provenance = json.loads((args.candidates / 'extraction.json').read_text())
if provenance['image_sha256'] != image_sha256:
    raise SystemExit('Candidate image differs from extraction record')
kernel = {f[1]: (int(f[0], 16), 'built kernel') for line in args.symvers.read_text().splitlines()
          if len(f := line.split()) >= 2}
captured = {m['name']: (p, m) for p in sorted(args.captured.glob('*.ko')) if (m := module(p, {}))}
candidates = {m['name']: (p, m) for p in sorted(args.candidates.glob('*.ko')) if (m := module(p, {}))}
if not captured or not candidates:
    raise SystemExit('Both module inventories must be nonempty')
if {p.name: info['sha256'] for p, info in candidates.values()} != provenance['module_sha256']:
    raise SystemExit('Candidate modules differ from extraction record')
selected, missing = {}, set()


def visit(name):
    if name in selected or name in missing:
        return
    item = captured.get(name, candidates.get(name))
    if item is None:
        missing.add(name)
        return
    selected[name] = item
    for dependency in item[1]['depends']:
        visit(dependency)


for target in ('msm_drm', 'msm_kgsl'):
    visit(target)
exports, conflicts = dict(kernel), []
for name, (path, _) in selected.items():
    for symbol, crc in export_crcs(path).items():
        if symbol in exports and exports[symbol][0] != crc:
            conflicts.append({'symbol': symbol, 'providers': [exports[symbol][1], name]})
        exports[symbol] = (crc, name)
matches, mismatches, absent = 0, [], []
for name, (path, _) in selected.items():
    versions = sections(path.read_bytes()).get('__versions', b'')
    for pos in range(0, len(versions), 64):
        crc = struct.unpack_from('<Q', versions, pos)[0]
        symbol = versions[pos + 8:pos + 64].split(b'\0', 1)[0].decode()
        if symbol not in exports:
            absent.append({'module': name, 'symbol': symbol})
            continue
        actual, provider = exports[symbol]
        if actual == crc:
            matches += 1
        else:
            mismatches.append({'module': name, 'symbol': symbol, 'provider': provider,
                               'import_crc': hex(crc), 'export_crc': hex(actual)})
report = {
    'scope': 'Offline display/GPU dependency closure and import/export CRC comparison; no loading or device proof',
    'candidate_image': str(args.candidate_image),
    'candidate_image_sha256': image_sha256,
    'extraction_provenance_verified': True,
    'symvers_sha256': hashlib.sha256(args.symvers.read_bytes()).hexdigest(),
    'selected_modules': [{'name': name, 'source': 'capture' if name in captured else 'candidate',
                          'sha256': info['sha256'], 'vermagic': info['vermagic']}
                         for name, (_, info) in sorted(selected.items())],
    'missing_dependency_modules': sorted(missing), 'matching_imports': matches,
    'mismatches': mismatches, 'absent_imports': absent, 'conflicting_exports': conflicts,
    'modules_loaded': False, 'phone_images_modified': False,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'closure_modules': len(selected), 'missing_modules': len(missing),
                  'matching_imports': matches, 'mismatching_imports': len(mismatches),
                  'absent_imports': len(absent), 'conflicting_exports': len(conflicts)}, indent=2))
raise SystemExit(1 if mismatches or absent or conflicts or missing else 0)

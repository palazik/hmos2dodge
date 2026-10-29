#!/usr/bin/env python3
"""Read captured ARM64 modules; compare imported CRCs without loading them."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def sections(data):
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('expected little-endian ARM64 ELF64')
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 58)
    if size != 64 or not count or names_index >= count or offset + size * count > len(data):
        raise ValueError('invalid section table')
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size) for i in range(count)]
    names_header = headers[names_index]
    names = data[names_header[4]:names_header[4] + names_header[5]]
    result = {}
    for header in headers:
        name = names[header[0]:].split(b'\0', 1)[0].decode()
        if header[1] == 8:  # SHT_NOBITS has no payload in the file
            continue
        start, length = header[4:6]
        if start + length > len(data):
            raise ValueError('truncated section')
        result[name] = data[start:start + length]
    return result


def module(path, exports):
    data = path.read_bytes()
    elf = sections(data)
    info = {}
    for entry in elf.get('.modinfo', b'').split(b'\0'):
        if b'=' in entry:
            key, value = entry.decode().split('=', 1)
            info.setdefault(key, []).append(value)
    versions = elf.get('__versions', b'')
    if len(versions) % 64:
        raise ValueError(f'{path}: invalid modversion_info records')
    imported = {}
    for offset in range(0, len(versions), 64):
        crc = struct.unpack_from('<Q', versions, offset)[0]
        name = versions[offset + 8:offset + 64].split(b'\0', 1)[0].decode()
        imported[name] = crc
    mismatches = []
    matched = 0
    unavailable = []
    for name, crc in imported.items():
        if name not in exports:
            unavailable.append(name)
        elif crc != exports[name]:
            mismatches.append({'symbol': name, 'module_crc': hex(crc), 'built_crc': hex(exports[name])})
        else:
            matched += 1
    return {
        'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
        'name': info.get('name', [path.stem.replace('-', '_')])[0],
        'vermagic': info.get('vermagic', []), 'firmware': info.get('firmware', []),
        'depends': [name.replace('-', '_') for name in info.get('depends', [''])[0].split(',') if name],
        'version_records': len(imported), 'matching_built_crcs': matched,
        'crc_mismatches': mismatches, 'imports_absent_from_built_symvers': unavailable,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--symvers', type=Path, default=Path('out/kernel/vmlinux.symvers'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    exports = {fields[1]: int(fields[0], 16) for line in args.symvers.read_text().splitlines()
               if len(fields := line.split()) >= 2}
    modules_dir = args.capture / 'vendor_lib_modules'
    modules = [module(path, exports) for path in sorted(modules_dir.glob('*.ko'))]
    if not modules:
        raise SystemExit('No modules found')
    by_name = {item['name']: item for item in modules}
    loaded = {line.split()[0] for line in (args.capture / 'modules.txt').read_text().splitlines() if line.strip()}
    for item in modules:
        item['loaded_in_capture'] = item['name'] in loaded
    visiting, visited, order, missing = set(), set(), [], set()

    def visit(name):
        if name in visited:
            return
        if name not in by_name:
            missing.add(name)
            return
        if name in visiting:
            raise ValueError(f'dependency cycle: {name}')
        visiting.add(name)
        for dep in by_name[name]['depends']:
            visit(dep)
        visiting.remove(name)
        visited.add(name)
        order.append(name)

    for target in ['msm_drm', 'msm_kgsl']:
        visit(target)
    duplicate_dir = args.capture / 'vendor_dlkm_lib_modules'
    duplicates = all((duplicate_dir / item['file']).is_file() and
                     hashlib.sha256((duplicate_dir / item['file']).read_bytes()).hexdigest() == item['sha256']
                     for item in modules)
    report = {
        'capture': str(args.capture), 'symvers': str(args.symvers),
        'symvers_sha256': hashlib.sha256(args.symvers.read_bytes()).hexdigest(),
        'scope': 'Offline metadata/CRC audit only. Does not certify module loading, signatures, full ABI, hardware or ARB.',
        'vendor_and_vendor_dlkm_module_bytes_equal': duplicates,
        'module_count': len(modules),
        'modules_with_crc_mismatches': sum(bool(item['crc_mismatches']) for item in modules),
        'display_gpu_dependency_order_captured_only': order,
        'display_gpu_dependencies_not_captured': sorted(missing),
        'dependency_order_executable': False,
        'modules': modules,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'modules'}, indent=2))


if __name__ == '__main__':
    main()

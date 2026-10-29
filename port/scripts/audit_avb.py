#!/usr/bin/env python3
"""Read image AVB metadata; do not infer OP13 stored rollback state from it."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[2]


def inspect(path):
    result = {'path': str(path), 'size': path.stat().st_size}
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
        result['sha256'] = h.hexdigest()
        f.seek(0)
        boot = f.read(44)
        if boot[:8] == b'ANDROID!':
            result['boot_header_version'] = struct.unpack_from('<I', boot, 40)[0]
            result['boot_os_version_field'] = struct.unpack_from('<I', boot, 16)[0]
        f.seek(-64, 2)
        footer = f.read(64)
        if footer[:4] != b'AVBf':
            result['avb_footer'] = 'absent'
            result['rollback_index'] = None
            result['rollback_index_location'] = None
            return result
        _, major, minor, original_size, offset, size, _ = struct.unpack('>4sIIQQQ28s', footer)
        if offset + size > path.stat().st_size or size < 256:
            raise ValueError('invalid AVB footer bounds')
        f.seek(offset)
        header = f.read(256)
        if header[:4] != b'AVB0':
            raise ValueError('missing vbmeta header')
        result.update(avb_footer='present', footer_version=f'{major}.{minor}',
                      original_image_size=original_size, vbmeta_offset=offset,
                      vbmeta_size=size, algorithm_type=struct.unpack_from('>I', header, 28)[0],
                      rollback_index=struct.unpack_from('>Q', header, 112)[0],
                      flags=struct.unpack_from('>I', header, 120)[0],
                      rollback_index_location=struct.unpack_from('>I', header, 124)[0])
    return result


if __name__ == '__main__':
    manifest = json.loads((ROOT / 'out/boot/op13-hmos-test.json').read_text())
    source = inspect(Path(manifest['stock_boot']))
    candidate = inspect(ROOT / 'out/boot/op13-hmos-test.img')
    report = {
        'source': source, 'candidate': candidate,
        'source_matches_pack_manifest': source['sha256'] == manifest['stock_sha256'],
        'candidate_matches_pack_manifest': candidate['sha256'] == manifest['output_sha256'],
        'device_stored_avb_rollback_indexes': 'unknown',
        'oplus_firmware_arb_state': 'unknown',
        'arb_compatibility_established': False,
        'scope': 'offline read-only image metadata; footer absence is not ARB bypass or compatibility proof',
        'device_writes': 'none',
    }
    output = ROOT / 'port/docs/avb-arb-audit.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

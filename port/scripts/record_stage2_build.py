#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record actual raw-image build inputs without carrying stale manual hashes."""
import argparse
import hashlib
import json
from pathlib import Path
from stage2_sources import expected_hashes

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('minimal', 'logging', 'core', 'framework'), required=True)
    args = parser.parse_args()
    native = args.profile == 'framework'
    stage = ROOT / ('work/stage2-framework-root' if native else 'work/stage2-root')
    image = ROOT / ('out/experiments/stage2-framework/system.img' if native else 'out/experiments/stage2/system.img')
    inputs = [stage / 'system/bin/init', stage / 'hmos/bootstrap/etc/init.cfg',
              ROOT / 'port/src/dsu_stage2.c', ROOT / 'port/src/dsu_probe.c']
    inputs += sorted((stage / 'hmos/overrides').rglob('*'))
    if native:
        inputs += sorted((stage / 'hmos/bootstrap').rglob('*'))
        inputs += [ROOT / 'port/src' / name for name in ('native_framework.h', 'native_storage.h', 'ram_data.h', 'vendor_layout.h')]
        inputs += [ROOT / 'port/scripts' / name for name in ('framework_profile.py', 'prepare_native_framework.py')]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in inputs if p.is_file()}
    report = {'image': str(image.relative_to(ROOT)), 'sha256': sha(image),
              'bytes': image.stat().st_size, 'profile': args.profile,
              'input_sha256': hashes, 'framework_candidate_integrated': native,
              'framework_scope': 'eight services; no SceneBoard or hardware startup' if native else None,
              'private_devices': native, 'ram_ext4_data': native,
              'payload_image_sha256': expected_hashes(args.profile),
              'vendor_base': 'OP13 stock' if native else 'donor lab fixture',
              'odm_base': 'OP13 stock' if native else None,
              'vendor_native_runtime': 'OHOS bin/lib64 layered over stock base' if native else 'donor',
              'guest_observer_policy_included': False,
              'native_dsu_tested': False, 'sceneboard_started': False,
              'arb_compatibility_established': False,
              'signing': 'offline development key; OEM trust unverified',
              'ui_mount_order': 'curated sys_prod etc bound read-only after donor masks'}
    (image.parent / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    if native:
        component = ROOT / 'out/framework/native/manifest.json'
        content = json.loads(component.read_text())
        content.update(scope='Native framework bootstrap component packed into an experimental raw image',
                       raw_image=str(image.relative_to(ROOT)), raw_image_sha256=report['sha256'])
        component.write_text(json.dumps(content, indent=2) + '\n')
    # Keep the older descriptive manifest's generated hashes consistent too.
    old = image.parent / 'manifest.json'
    if old.exists():
        content = json.loads(old.read_text())
        content.update(config_sha256=sha(stage / 'hmos/bootstrap/etc/init.cfg'),
                       wrapper_sha256=sha(stage / 'system/bin/init'))
        old.write_text(json.dumps(content, indent=2) + '\n')
    print('Recorded raw image:', report['sha256'])


if __name__ == '__main__':
    main()

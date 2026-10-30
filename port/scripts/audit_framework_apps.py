#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inspect extracted donor UI packages without modifying or signing them."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'work/framework-assets/system/system/app'


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


packages = []
for folder in ('SceneBoard', 'SystemResources'):
    paths = sorted((ASSETS / folder).iterdir())
    if not paths:
        raise SystemExit('Missing extracted package folder: ' + folder)
    for path in paths:
        if path.suffix not in ('.hap', '.hsp'):
            continue
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise SystemExit(f'Invalid zip CRC: {path.name}:{bad}')
            manifest = json.loads(archive.read('module.json'))
            app, module = manifest['app'], manifest['module']
            packages.append({
                'path': '/system/app/' + str(path.relative_to(ASSETS)),
                'bytes': path.stat().st_size, 'sha256': sha256(path),
                'bundle': app['bundleName'], 'version': app.get('versionName'),
                'min_api': app.get('minAPIVersion'), 'target_api': app.get('targetAPIVersion'),
                'compile_sdk': app.get('compileSdkVersion'),
                'module': module.get('name'), 'type': module.get('type'),
                'main_element': module.get('mainElement'),
                'virtual_machine': module.get('virtualMachine'),
                'device_types': module.get('deviceTypes', []),
                'dependencies': module.get('dependencies', []),
                'defined_permission_count': len(module.get('definePermissions', [])),
                'requested_permission_count': len(module.get('requestPermissions', [])),
                'abc_entries': [n for n in archive.namelist() if n.endswith('.abc')],
                'native_library_entries': [n for n in archive.namelist() if n.endswith('.so')],
                'zip_crc_check': 'passed',
            })
report = {'scope': 'Original donor package metadata and zip CRCs; no execution, install or signature-trust verification',
          'donor_system_sha256': sha256(ROOT / 'hmos5/system.img'),
          'packages': packages, 'packages_modified': False,
          'installed_into_android': False, 'sceneboard_boot_established': False}
output = ROOT / 'port/docs/framework-apps.json'
output.write_text(json.dumps(report, indent=2) + '\n')
print(f'Checked {len(packages)} original HAP/HSP archives; report: {output}')

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage an audited display/GPU module set; never load or force a module."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from audit_op13_modules import module

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--audit', type=Path, default=ROOT / 'out/kernel/current-early-module-candidates.json')
parser.add_argument('--early-modules', type=Path, required=True)
parser.add_argument('--capture', type=Path, default=ROOT / 'work/device-hardware/20261029-163450')
args = parser.parse_args()
audit = json.loads(args.audit.read_text())
for key in ('mismatches', 'absent_imports', 'conflicting_exports', 'missing_dependency_modules'):
    if audit[key]:
        raise SystemExit('Refusing unresolved/incompatible module set: ' + key)
symvers = ROOT / 'out/kernel/vmlinux.symvers'
if hashlib.sha256(symvers.read_bytes()).hexdigest() != audit['symvers_sha256']:
    raise SystemExit('Kernel symbols changed since module audit')
extraction = json.loads((args.early_modules / 'extraction.json').read_text())
if extraction['image_sha256'] != audit['candidate_image_sha256']:
    raise SystemExit('Early-module image provenance differs from audit')
inventories = {}
for source, directory in (('capture', args.capture / 'vendor_lib_modules'), ('candidate', args.early_modules)):
    inventories[source] = {info['name']: (path, info) for path in sorted(directory.glob('*.ko'))
                           if (info := module(path, {}))}
selected = {}
for item in audit['selected_modules']:
    path, info = inventories[item['source']][item['name']]
    if info['sha256'] != item['sha256']:
        raise SystemExit('Module changed since audit: ' + item['name'])
    selected[item['name']] = (path, info, item['source'])
order, active, visited = [], set(), set()
def visit(name):
    if name in visited:
        return
    if name in active or name not in selected:
        raise SystemExit('Unresolved/cyclic module dependency: ' + name)
    active.add(name)
    for dependency in selected[name][1]['depends']:
        visit(dependency)
    active.remove(name)
    visited.add(name)
    order.append(name)
for target in ('msm_drm', 'msm_kgsl'):
    visit(target)
output = ROOT / 'out/modules/op13-current'
output.mkdir(parents=True, exist_ok=True)
expected_files = {path.name for path, _, _ in selected.values()}
if {path.name for path in output.glob('*.ko')} - expected_files:
    raise SystemExit('Staging directory contains stale module files; use a clean generated output')
loaded = {line.split()[0] for line in (args.capture / 'modules.txt').read_text().splitlines() if line.strip()}
entries = []
for name in order:
    path, info, source = selected[name]
    destination = output / path.name
    if destination.exists():
        destination.unlink()
    shutil.copy2(path, destination)
    entries.append({'name': name, 'file': path.name, 'sha256': info['sha256'],
                    'source': source, 'depends': info['depends'], 'vermagic': info['vermagic'],
                    'firmware': info['firmware'], 'loaded_in_android_capture': name in loaded})
report = {'scope': 'Audited offline module payload and dependency order; no native loading/hardware proof',
          'auto_load': False, 'force_flags': False, 'candidate_image_sha256': audit['candidate_image_sha256'],
          'kernel_sha256': hashlib.sha256((ROOT / 'out/kernel/Image').read_bytes()).hexdigest(),
          'symvers_sha256': audit['symvers_sha256'],
          'audit_sha256': hashlib.sha256(args.audit.read_bytes()).hexdigest(),
          'modules': entries, 'required_firmware_names': sorted({f for m in entries for f in m['firmware']}),
          'firmware_bytes_supplied': False, 'modules_loaded_by_this_tool': False}
gpu_names = ('gen80000_aqe.fw', 'gen80000_gmu.bin', 'gen80000_sqe.fw', 'gen80000_zap.mbn')
capture_firmware = (args.capture / 'firmware-files.txt').read_text()
gpu_binary = selected['msm_kgsl'][0].read_bytes()
if not all('/vendor/firmware/' + name in capture_firmware and name.encode() + b'\0' in gpu_binary for name in gpu_names):
    raise SystemExit('Expected OP13 GPU firmware names are not supported by capture/driver evidence')
report['gpu_firmware_names_from_capture_and_driver'] = list(gpu_names)
report['gpu_firmware_bytes_available'] = False
(output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
(output / 'load-order.txt').write_text('\n'.join(m['file'] for m in entries) + '\n')
print(json.dumps({'output': str(output), 'modules': len(entries),
                  'early_modules': sum(m['source'] == 'candidate' for m in entries),
                  'loaded_in_android_capture': sum(m['loaded_in_android_capture'] for m in entries)}, indent=2))

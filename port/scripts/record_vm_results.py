#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record completed native-kernel guest observations without claiming phone boot."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
log_path = ROOT / 'work/logs/vm-core.log'
log = log_path.read_text(errors='replace')
inputs = json.loads((ROOT / 'out/vm/runtime-inputs.json').read_text())
for name, digest in inputs['source_sha256'].items():
    if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Guest source changed since archive build: ' + name)
if 'VM runtime observation ended' not in log:
    raise SystemExit('Incomplete guest observation')
checks = {
    'kernel_probe_passed': 'VM KERNEL CHECK PASS failures=0' in log,
    'samgr_donor_domain_observed': bool(re.search(r'VM-PROCESS samgr pid=\d+ attr/current: u:r:samgr:s0', log)),
    'samgr_ready_parameter_set': bool(re.search(r'SystemSetParameter name bootevent.samgr.ready .*ret: 0', log)),
    'access_token_service_published_sa3503': 'Publish SA:3503 result:0' in log,
    'observer_obtained_sa3503': 'VM-SA id=3503 registered=true' in log,
    'final_selinux_enforcing': 'VM final SELinux enforce=1' in log,
    'ext4_io_errors_absent': 'EXT4-fs error' not in log and 'Buffer I/O error' not in log,
}
report = {
    'scope': 'Diskless QEMU ARM64 virt with the Android-tested kernel; no DSU or OP13 hardware emulation',
    'inputs': inputs,
    'log': str(log_path.relative_to(ROOT)),
    'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
    'archive_sha256': hashlib.sha256((ROOT / 'out/vm/core-compact.cpio.gz').read_bytes()).hexdigest(),
    'checks': checks,
    'early_label_preparation_permissive': True,
    'observer_policy_is_guest_only': True,
    'known_limitations': [
        'Original init policy reload logs a failure after the lab preloads policy',
        'Core services only; no application launch or full framework readiness',
        'Missing system services/configuration still produce runtime errors',
        'SceneBoard, display, GPU, input and actual OP13 DSU boot untested',
    ],
    'phone_partitions_written': False,
    'arb_compatibility_established': False,
}
output = ROOT / 'port/docs/native-kernel-result.json'
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(checks, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)

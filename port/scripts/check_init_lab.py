#!/usr/bin/env python3
"""Require init job evidence from PID 1, not a failed policy compiler child."""
import json
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
logs = ROOT / 'work/logs'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prefix', default='ohos-init')
args = parser.parse_args()
prefix = args.prefix
raw = (logs / f'{prefix}-kmsg.txt').read_text(errors='replace')
readable = re.sub(r'(?=<[0-9]>\[pid=)', '\n', raw)
(logs / f'{prefix}-kmsg-readable.txt').write_text(readable)
jobs = re.findall(r'\[pid=(\d+)\]\[Init\].*?boot job (pre-init|init|post-init) finish[^\n]*', readable)
passed = all(('1', name) in jobs for name in ('pre-init', 'init', 'post-init'))
marker = (logs / f'{prefix}-marker.txt').read_text()
passed = passed and marker == 'reached-post-init'
report = {'kind': 'ARM64 userspace emulation in isolated user/PID/mount/network namespaces',
          'init': 'original donor binary; no executable patch',
          'profile': prefix,
          'external_init_modules': False, 'ohos_selinux_policy_loaded': False,
          'pid1_startup_jobs_passed': passed, 'observed_jobs': jobs, 'marker': marker,
          'dsu_emulated': False, 'op13_hardware_emulated': False,
          'complete_harmonyos_boot': False}
if prefix != 'ohos-init':
    status = logs / f'{prefix}-hilog-status.txt'
    dump = logs / f'{prefix}-hilog-dump.txt'
    logger_ok = status.exists() and status.read_text().strip() == '0' and dump.exists() and bool(dump.stat().st_size)
    report['hilog_client_read_passed'] = logger_ok
    passed = passed and logger_ok
    report['samgr_ready'] = False  # Requires native Binder/token/policy evidence.
(logs / f'{prefix}-lab-result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
if not passed:
    raise SystemExit('FAIL: minimal startup jobs did not all complete as PID 1')

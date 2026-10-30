#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Query BinderFS genfs labels in libsepol memory; never load host policy."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
policy = ROOT / 'out/selinux/donor-runtime-op13/policy.31'
prefix = ROOT / 'work/policy-tools/usr'
executable = ROOT / 'work/check-binderfs-policy'
# The genfs API is private and unavailable from the shared library. Link the
# matching static archive explicitly rather than resolve host libsepol.
subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-O2',
                '-I' + str(prefix / 'include'),
                str(ROOT / 'port/src/check_binderfs_policy.c'),
                str(prefix / 'lib/x86_64-linux-gnu/libsepol.a'),
                '-o', str(executable)], check=True)
result = subprocess.run([str(executable), str(policy)], text=True,
                        capture_output=True, check=True)
labels = json.loads(result.stdout)
output = ROOT / 'out/selinux/binderfs-labels.json'
output.write_text(json.dumps({'policy_sha256': hashlib.sha256(policy.read_bytes()).hexdigest(),
                             'labels': labels, 'host_policy_loaded': False}, indent=2) + '\n')
print('PASS BinderFS root and three device genfs labels match donor types')

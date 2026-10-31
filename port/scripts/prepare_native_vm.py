#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage the actual native bootstrap helpers in a diskless guest fixture."""
import hashlib
import json
import os
from pathlib import Path
from prepare_framework import ROOT
from prepare_vm_runtime import link_tree, replace_file

source = ROOT / 'work/system-vm/runtime-root-foundation'
stage = ROOT / 'work/system-vm/runtime-root-native'
fixture = stage / 'native-root'
native = ROOT / 'out/framework/native'
stage.mkdir(parents=True, exist_ok=True)
def ignore(path, names):
    return [n for n in names if Path(path) == source / 'vm' and n in ('data.ext4', 'data-directories')]
link_tree(source, fixture, ignore)
link_tree(native / 'etc', fixture / 'system/etc')
link_tree(native / 'vendor_etc', fixture / 'vendor/etc')
link_tree(native / 'init_modules', fixture / 'system/lib64/init')
# Only the test fixture gets observer permissions. The native component's
# regular policy inode is unlinked before replacement and stays unchanged.
policy = ROOT / 'out/selinux/donor-runtime-op13-vm/policy.31'
regular = native / 'vendor_etc/selinux/prebuild_sepolicy/policy.31'
regular_sha = hashlib.sha256(regular.read_bytes()).hexdigest()
replace_file(policy, fixture / 'vendor/etc/selinux/prebuild_sepolicy/policy.31')
assert hashlib.sha256(regular.read_bytes()).hexdigest() == regular_sha
replace_file(ROOT / 'work/system-vm/probe-root/init', stage / 'init')
for name in ('dev', 'sys', 'proc', 'vm', 'hmos/bootstrap'):
    (stage / name).mkdir(parents=True, exist_ok=True)
replace_file(native / 'data-directories', stage / 'hmos/bootstrap/data-directories')
(stage / 'vm/profile').write_text('native\n')
# Select the expanded observer inside the fixture, without altering services.
replace_file(source / 'vm/profile', fixture / 'vm/profile')
inputs = json.loads((ROOT / 'out/vm/runtime-inputs-foundation.json').read_text())
inputs.update(profile='native', services=json.loads((native / 'manifest.json').read_text())['services'],
              init_config_sha256=hashlib.sha256((fixture / 'system/etc/init.cfg').read_bytes()).hexdigest(),
              native_bootstrap_policy_sha256=regular_sha,
              native_helper_code_executed=['native_devices', 'native_ram_data', 'native_policy_and_storage'],
              dsu_handoff_exercised=False, op13_hardware_emulated=False)
for name in ('port/scripts/prepare_native_vm.py', 'port/scripts/prepare_native_framework.py'):
    inputs['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
(ROOT / 'out/vm/runtime-inputs-native.json').write_text(json.dumps(inputs, indent=2) + '\n')
print(stage)

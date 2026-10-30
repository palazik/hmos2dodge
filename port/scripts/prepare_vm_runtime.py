#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage an isolated native-kernel core lab; no phone partitions or donor jobs."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
from prepare_framework import ROOT, prepare


def replace_file(source, target):
    if target.exists() or target.is_symlink():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def link_tree(source, target, ignore=None):
    """Repeatable staging; never change source file contents or permissions."""
    target.mkdir(parents=True, exist_ok=True)
    omitted = set(ignore(str(source), [p.name for p in source.iterdir()])) if ignore else set()
    for path in source.iterdir():
        if path.name in omitted:
            continue
        dest = target / path.name
        if path.is_symlink():
            if dest.is_symlink() and os.readlink(dest) == os.readlink(path):
                continue
            if dest.exists() or dest.is_symlink(): dest.unlink()
            dest.symlink_to(os.readlink(path))
        elif path.is_dir():
            link_tree(path, dest, ignore)
        elif not dest.exists() or not os.path.samefile(path, dest):
            if dest.exists(): dest.unlink()
            os.link(path, dest)


def main():
    stage = ROOT / 'work/system-vm/runtime-root'
    stage.mkdir(parents=True, exist_ok=True)
    system = ROOT / 'work/ohos-runtime/system/system'
    # Hardlinks avoid duplicating firmware on the host. Only cpio copies enter
    # the guest. Never edit a linked file in place; replace_file unlinks first.
    def ignore(path, names):
        if Path(path) == system / 'etc':
            return [name for name in names if name == 'init' or name.startswith('init.')]
        if Path(path) == system / 'lib64':
            return ['init']
        return []
    link_tree(system, stage / 'system', ignore)
    link_tree(ROOT / 'work/donor-configs/system/system/profile', stage / 'system/profile')
    for name in ('dev', 'sys', 'proc', 'data', 'mnt', 'storage', 'metadata',
                 'vendor/etc', 'chip_prod/etc', 'sys_prod/etc', 'cust', 'patch_hw', 'vm'):
        (stage / name).mkdir(parents=True, exist_ok=True)
    for name in ('bin', 'etc', 'lib', 'lib64'):
        path = stage / name
        if not path.exists():
            path.symlink_to('system/' + name)
    (stage / 'system/etc/init').mkdir(exist_ok=True)
    # Register the original policy/context commands, but expose no autorun,
    # hardware, firmware, migration, watchdog or reboot plugin collections.
    plugins = stage / 'system/lib64/init'
    plugins.mkdir(exist_ok=True)
    replace_file(system / 'lib64/init/libselinuxadp.z.so', plugins / 'libselinuxadp.z.so')
    (plugins / 'autorun').mkdir(exist_ok=True)
    (plugins / 'reboot').mkdir(exist_ok=True)
    vendor_selinux = ROOT / 'work/donor-configs/vendor/etc/selinux'
    link_tree(vendor_selinux, stage / 'vendor/etc/selinux')
    policy = ROOT / 'out/selinux/donor-runtime-op13-vm/policy.31'
    replace_file(policy, stage / 'vendor/etc/selinux/prebuild_sepolicy/policy.31')
    replace_file(system / 'etc/selinux/system.cil.sha256',
                 stage / 'vendor/etc/selinux/prebuild_sepolicy.system.cil.sha256')
    # Canonical identities/domains and token permissions are retained.
    framework, _ = prepare()
    resource_limits = next(j['cmds'] for j in framework['jobs']
                           if j['name'] == 'hmos-framework-resources')
    names = {'hilogd', 'samgr', 'accesstoken_service'}
    services = [copy.deepcopy(s) for s in framework['services'] if s['name'] in names]
    directories = framework['jobs'][0]['cmds'] + [
        'mkdir /data/log 0755 root root', 'mkdir /data/log/hilog 0750 logd log',
        'mkdir /data/log/dict 0755 logd log']
    config = {'import': [], 'services': services, 'jobs': [
        {'name': 'pre-init', 'cmds': resource_limits + directories + [
            'restorecon /system', 'restorecon /vendor', 'restorecon /data',
            'chown access_token access_token /dev/access_token_id',
            'chmod 0666 /dev/access_token_id',
            'chmod 0666 /dev/binder', 'chmod 0666 /dev/hwbinder', 'chmod 0666 /dev/vndbinder',
            'load_access_token_id ',
            'write /dev/hmos-init-stage2 reached-pre-init']},
        {'name': 'init', 'cmds': ['setparam ohos.boot.hardware op13_vm',
                                 'start hilogd', 'start samgr',
                                 'start accesstoken_service',
                                 'write /dev/hmos-init-stage2 reached-init']},
        {'name': 'post-init', 'cmds': ['write /dev/hmos-init-stage2 reached-post-init']},
        {'name': 'param:bootevent.samgr.ready=true', 'condition': 'bootevent.samgr.ready=true',
         'cmds': ['start accesstoken_service']},
    ]}
    # Provision a fresh private filesystem before enforcement, as a donor
    # installation normally has these directories before runtime init jobs.
    users = {w[0]: int(w[2]) for line in (system / 'etc/passwd').read_text().splitlines()
             if (w := line.split(':')) and len(w) > 2}
    groups = {w[0]: int(w[2]) for line in (system / 'etc/group').read_text().splitlines()
              if (w := line.split(':')) and len(w) > 2}
    provision = []
    for command in directories:
        _, path, mode, owner, group = command.split()
        provision.append(f'{path} {mode} {users[owner]} {groups[group]}')
    (stage / 'vm/data-directories').write_text('\n'.join(provision) + '\n')
    cfg = stage / 'system/etc/init.cfg'
    if cfg.exists(): cfg.unlink()
    cfg.write_text(json.dumps(config, indent=2) + '\n')
    replace_file(ROOT / 'work/system-vm/probe-root/init', stage / 'init')
    replace_file(ROOT / 'out/vm/sa-query', stage / 'system/bin/sa-query')
    (stage / 'vm/profile').write_text('core\n')
    report = {'profile': 'native-kernel core lab', 'services': sorted(names),
              'donor_identities_preserved': True,
              'kernel': 'out/baseline-android/Image',
              'kernel_sha256': hashlib.sha256((ROOT / 'out/baseline-android/Image').read_bytes()).hexdigest(),
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in ('port/src/vm_init.c', 'port/src/dsu_stage2.c',
                                             'port/src/dsu_probe.c', 'port/scripts/prepare_vm_runtime.py',
                                             'port/scripts/vm_file_list.py')}, 'disks': [], 'network': False,
              'private_data': '128 MiB ext4 file inside cpio, loop-mounted from guest RAM only',
              'observer_policy': 'port/selinux/vm-diagnostics.cil; guest only, never a phone policy',
              'policy_sha256': hashlib.sha256(policy.read_bytes()).hexdigest(),
              'init_config_sha256': hashlib.sha256(cfg.read_bytes()).hexdigest(),
              'init_plugins': ['libselinuxadp.z.so'],
              'hardware_emulated': 'QEMU virt only; OP13 hardware is not emulated',
              'native_phone_tested': False}
    output = ROOT / 'out/vm'
    output.mkdir(exist_ok=True)
    (output / 'runtime-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
    print(stage)


if __name__ == '__main__':
    main()

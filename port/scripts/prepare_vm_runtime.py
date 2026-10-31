#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage an isolated native-kernel core lab; no phone partitions or donor jobs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from prepare_framework import ROOT
from framework_profile import build_profile


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('core', 'framework', 'foundation'), default='core')
    args = parser.parse_args()
    stage = ROOT / ('work/system-vm/runtime-root-' + args.profile)
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
    if args.profile == 'foundation':
        link_tree(ROOT / 'work/framework-assets/system/system/app/SystemResources',
                  stage / 'system/app/SystemResources')
        link_tree(ROOT / 'work/huks-inspect/vendor/lib64/chipsetsdk',
                  stage / 'vendor/lib64/chipsetsdk')
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
    config, provision, names, adapted_directories = build_profile(args.profile)
    (stage / 'vm/data-directories').write_text('\n'.join(provision) + '\n')
    cfg = stage / 'system/etc/init.cfg'
    if cfg.exists(): cfg.unlink()
    cfg.write_text(json.dumps(config, indent=2) + '\n')
    replace_file(ROOT / 'work/system-vm/probe-root/init', stage / 'init')
    replace_file(ROOT / 'out/vm/sa-query', stage / 'system/bin/sa-query')
    (stage / 'vm/profile').write_text(args.profile + '\n')
    kernel_input = Path(os.environ.get('HMOS_VM_KERNEL', str(ROOT / 'out/baseline-android/Image'))).resolve()
    kernel_name = str(kernel_input.relative_to(ROOT)) if kernel_input.is_relative_to(ROOT) else str(kernel_input)
    report = {'profile': args.profile, 'services': sorted(names),
              'donor_identities_preserved': True,
              'kernel': kernel_name,
              'kernel_sha256': hashlib.sha256(kernel_input.read_bytes()).hexdigest(),
              'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in ('port/src/vm_init.c', 'port/src/dsu_stage2.c',
                                             'port/src/ram_data.h', 'port/src/native_storage.h',
                                             'port/src/native_framework.h', 'port/selinux/op13-ramdata.cil',
                                             'port/src/dsu_probe.c', 'port/src/vm_sa_query.cpp',
                                             'port/scripts/prepare_framework.py', 'port/scripts/framework_profile.py',
                                             'port/selinux/vm-diagnostics.cil',
                                             'port/scripts/prepare_vm_runtime.py',
                                             'port/scripts/vm_file_list.py')}, 'disks': [], 'network': False,
              'private_data': '128 MiB ext4 file inside cpio, loop-mounted from guest RAM only',
              'observer_policy': 'port/selinux/vm-diagnostics.cil; guest only, never a phone policy',
              'policy_sha256': hashlib.sha256(policy.read_bytes()).hexdigest(),
              'init_config_sha256': hashlib.sha256(cfg.read_bytes()).hexdigest(),
              'init_plugins': ['libselinuxadp.z.so'],
              'adapted_data_directories': adapted_directories,
              'system_resource_sha256': {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in (stage / 'system/app/SystemResources').glob('*.hap')},
              'donor_huks_library_sha256': {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in (stage / 'vendor/lib64/chipsetsdk').glob('*huks*.so')},
              'hardware_emulated': 'QEMU virt only; OP13 hardware is not emulated',
              'native_phone_tested': False}
    output = ROOT / 'out/vm'
    output.mkdir(exist_ok=True)
    (output / ('runtime-inputs-' + args.profile + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    if args.profile == 'core':
        (output / 'runtime-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
    print(stage)


if __name__ == '__main__':
    main()

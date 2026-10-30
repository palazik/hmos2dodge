#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage an isolated native-kernel core lab; no phone partitions or donor jobs."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
from prepare_framework import ROOT, data_mkdir, prepare


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
    # Canonical identities/domains and token permissions are retained.
    framework, _ = prepare()
    resource_limits = next(j['cmds'] for j in framework['jobs']
                           if j['name'] == 'hmos-framework-resources')
    names = {'hilogd', 'samgr', 'accesstoken_service'}
    if args.profile != 'core':
        names.update(('accountmgr', 'appspawn'))
    if args.profile == 'foundation':
        names.add('foundation')
    services = [copy.deepcopy(s) for s in framework['services'] if s['name'] in names]
    if args.profile != 'core':
        fault_cfg = json.loads((system / 'etc/init/faultloggerd.cfg').read_text())
        fault = copy.deepcopy(next(s for s in fault_cfg['services'] if s['name'] == 'faultloggerd'))
        fault.pop('jobs', None)
        fault.pop('writepid', None)
        fault.update(disabled=1, **{'start-mode': 'condition'})
        services.insert(0, fault)
        names.add('faultloggerd')
    huks_cfg = None
    if args.profile == 'foundation':
        huks_cfg = json.loads((system / 'etc/init/huks_service.cfg').read_text())
        huks = copy.deepcopy(next(s for s in huks_cfg['services'] if s['name'] == 'huks_service'))
        huks.pop('jobs', None)
        huks.pop('writepid', None)
        huks.update(disabled=1, **{'start-mode': 'condition'})
        services.append(huks)
        names.add('huks_service')
        installs_cfg = json.loads((system / 'etc/init/installs.cfg').read_text())
        installs = copy.deepcopy(next(s for s in installs_cfg['services'] if s['name'] == 'installs'))
        installs.update(disabled=1, **{'start-mode': 'condition'})
        services.append(installs)
        names.add('installs')
    directories = framework['jobs'][0]['cmds'] + [
        'mkdir /data/log 0755 root root', 'mkdir /data/log/hilog 0750 logd log',
        'mkdir /data/log/dict 0755 logd log']
    if args.profile != 'core':
        directories += ['mkdir /data/log/faultlog 0750 hiview log',
                        'mkdir /data/log/faultlog/temp 0770 system system',
                        'mkdir /data/log/faultlog/hilog 0750 logd log',
                        'mkdir /data/log/faultlog/debug 0770 system system']
    adapted_directories = []
    if args.profile == 'foundation':
        # This donor library uses a newer BMS tree than foundation.cfg creates.
        # A fresh lab filesystem has no installed-phone directory migration.
        adapted_directories = [
            'mkdir /data/service/el1/public/bms 0700 foundation foundation',
            'mkdir /data/service/el1/public/bms/bundle_manager_service 0700 foundation foundation',
            'mkdir /data/service/el1/public/bms/bundle_manager_service/lock 0700 foundation foundation']
        directories += adapted_directories
        directories += ['mkdir /data/data 0771 system system']
        directories += [command for job in huks_cfg['jobs'] for command in job['cmds'] if data_mkdir(command)]
        directories += ['mkdir /data/local 0751 root root']
        directories += [command for job in installs_cfg['jobs'] for command in job['cmds'] if data_mkdir(command)]
        original_init = json.loads((system / 'etc/init.cfg').read_text())
        public_bundle_paths = {'/data/app', '/data/app/el1', '/data/app/el1/bundle',
                               '/data/app/el1/bundle/public'}
        directories += [command for job in original_init['jobs'] for command in job['cmds']
                        if command.startswith('mkdir ') and command.split()[1] in public_bundle_paths]
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
    if args.profile != 'core':
        # Only literal commands from the donor appspawn cfg; all targets are
        # private guest /mnt or /dev. Never import the wider donor boot jobs.
        source_cfg = json.loads((system / 'etc/init/appspawn.cfg').read_text())
        allowed = {cmd for job in source_cfg['jobs'] for cmd in job['cmds']}
        sandbox = ['mkdir /mnt/sandbox',
                   'mkdir /mnt/sandbox/com.ohos.render/ 0711 nwebspawn nwebspawn',
                   'mkdir /mnt/startup', 'mkdir /mnt/startup/appspawn 0700 root root',
                   'mkdir /mnt/startup/nwebspawn/ 0700 nwebspawn nwebspawn',
                   'mkdir /dev/pids', 'mount cgroup none /dev/pids pids',
                   'chown root appspawn /dev/pids',
                   'chown root appspawn /dev/pids/tasks',
                   'chown root appspawn /dev/pids/cgroup.procs',
                   'chmod 0755 /dev/pids', 'chmod 0755 /dev/pids/tasks',
                   'chmod 0755 /dev/pids/cgroup.procs']
        if not set(sandbox) <= allowed:
            raise ValueError('Donor appspawn prerequisite commands changed')
        # The already labeled /mnt parent restricts runtime init creation.
        # Provision private guest mountpoints before restoring labels, as for
        # the fresh-data tree; keep the original jobs for native ordering.
        for command in sandbox:
            fields = command.split()
            if fields[0] != 'mkdir' or not fields[1].startswith('/mnt/'):
                continue
            _, path, *attributes = fields
            mode, owner, group = attributes or ('0755', 'root', 'root')
            provision.append(f'{path} {mode} {users[owner]} {groups[group]}')
        (stage / 'vm/data-directories').write_text('\n'.join(provision) + '\n')
        config['jobs'][0]['cmds'] += sandbox
        config['jobs'][1]['cmds'].insert(0, 'start faultloggerd')
        config['jobs'][1]['cmds'] += ['start accountmgr', 'start appspawn']
        if args.profile == 'foundation':
            start_account = config['jobs'][1]['cmds'].index('start accountmgr')
            config['jobs'][1]['cmds'].insert(start_account, 'start huks_service')
            config['jobs'][1]['cmds'] += ['start foundation']
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
                                             'port/src/dsu_probe.c', 'port/src/vm_sa_query.cpp',
                                             'port/scripts/prepare_framework.py',
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

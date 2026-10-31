#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared canonical service/configuration model for isolated startup profiles."""
import copy
import json
from prepare_framework import ROOT, data_mkdir, prepare


def build_profile(profile):
    if profile not in ('core', 'framework', 'foundation'):
        raise ValueError('Unknown service profile: ' + profile)
    system = ROOT / 'work/ohos-runtime/system/system'
    # Canonical identities/domains and token permissions are retained.
    framework, _ = prepare()
    resource_limits = next(j['cmds'] for j in framework['jobs']
                           if j['name'] == 'hmos-framework-resources')
    names = {'hilogd', 'samgr', 'accesstoken_service'}
    if profile != 'core':
        names.update(('accountmgr', 'appspawn'))
    if profile == 'foundation':
        names.add('foundation')
    services = [copy.deepcopy(s) for s in framework['services'] if s['name'] in names]
    if profile != 'core':
        fault_cfg = json.loads((system / 'etc/init/faultloggerd.cfg').read_text())
        fault = copy.deepcopy(next(s for s in fault_cfg['services'] if s['name'] == 'faultloggerd'))
        fault.pop('jobs', None)
        fault.pop('writepid', None)
        fault.update(disabled=1, **{'start-mode': 'condition'})
        services.insert(0, fault)
        names.add('faultloggerd')
    huks_cfg = None
    if profile == 'foundation':
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
    if profile != 'core':
        directories += ['mkdir /data/log/faultlog 0750 hiview log',
                        'mkdir /data/log/faultlog/temp 0770 system system',
                        'mkdir /data/log/faultlog/hilog 0750 logd log',
                        'mkdir /data/log/faultlog/debug 0770 system system']
    adapted_directories = []
    if profile == 'foundation':
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
    if profile != 'core':
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
        config['jobs'][0]['cmds'] += sandbox
        config['jobs'][1]['cmds'].insert(0, 'start faultloggerd')
        config['jobs'][1]['cmds'] += ['start accountmgr', 'start appspawn']
        if profile == 'foundation':
            start_account = config['jobs'][1]['cmds'].index('start accountmgr')
            config['jobs'][1]['cmds'].insert(start_account, 'start huks_service')
            config['jobs'][1]['cmds'] += ['start foundation']
    return config, provision, names, adapted_directories

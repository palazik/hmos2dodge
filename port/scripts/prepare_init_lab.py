#!/usr/bin/env python3
"""Create a minimal HarmonyOS init config for an isolated offline PID-1 test."""
from pathlib import Path
import argparse
import copy
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile', choices=('minimal', 'logging', 'core'), default='minimal')
args = parser.parse_args()
source = ROOT / 'work/ohos-runtime/system/system/etc'
target = ROOT / ('work/init-lab-config' if args.profile == 'minimal' else f'work/init-lab-{args.profile}-config')
target.mkdir(exist_ok=True)
# Preserve the donor's linker and account databases; no donor service graph.
for name in ('passwd', 'group', 'ld-musl-aarch64.path', 'ld-musl-namespace-aarch64.ini'):
    shutil.copy2(source / name, target / name)
for name in ('param', 'selinux'):
    if not (target / name).exists():
        shutil.copytree(source / name, target / name, symlinks=True)
for p in target.rglob('*'):
    if p.is_dir(): p.chmod(p.stat().st_mode | 0o700)
policy_config = target / 'selinux/config'
if policy_config.exists(): policy_config.chmod(policy_config.stat().st_mode | 0o200)
shutil.copy2(source / 'selinux/config', policy_config)
(target / 'init').mkdir(exist_ok=True)
config = {
    'import': [],
    'jobs': [
        {'name': 'pre-init', 'cmds': [
            'mkdir /data/service 0711 root root',
            'mkdir /data/service/el0 0711 root root',
            'mkdir /data/service/el0/startup 0755 root root',
            'mkdir /data/service/el0/startup/init 0755 root root',
            'write /dev/hmos-init-stage2 reached-pre-init',
        ]},
        {'name': 'init', 'cmds': [
            'setparam ohos.boot.hardware op13_dsu',
            'setparam hmos.dsu.init.ready true',
            'write /dev/hmos-init-stage2 reached-init',
        ]},
        {'name': 'post-init', 'cmds': ['write /dev/hmos-init-stage2 reached-post-init']},
    ],
    'services': [],
}
if args.profile in ('logging', 'core'):
    logger = json.loads((source / 'init/hilogd.cfg').read_text())
    service = copy.deepcopy(next(s for s in logger['services'] if s['name'] == 'hilogd'))
    # Initial bring-up profiles run these core daemons as root. Their final
    # production identities/security domains still require integration.
    service.update(uid='root', gid=['root'], critical=[0, 4, 60], sandbox=0)
    service.pop('secon', None)
    service['file'] = ['/dev/kmsg rd 0600 root root']
    for socket in service.get('socket', []):
        socket.update(uid='root', gid='root')
    config['services'].append(service)
    config['jobs'][0]['cmds'] += [
        'mkdir /data/log 0755 root root', 'mkdir /data/log/hilog 0755 root root',
        'mkdir /data/log/dict 0755 root root', 'start hilogd',
    ]
if args.profile == 'core':
    samgr_cfg = json.loads((source / 'init/samgr_standard.cfg').read_text())
    service = copy.deepcopy(next(s for s in samgr_cfg['services'] if s['name'] == 'samgr'))
    service.update(uid='root', gid=['root'], critical=[0, 4, 60], sandbox=0)
    service.pop('secon', None)
    service['file'] = ['/dev/kmsg rd 0600 root root']
    config['services'].append(service)
    config['jobs'][0]['cmds'] += ['mkdir /data/samgr 0755 root root']
(target / 'init.cfg').write_text(json.dumps(config, indent=2) + '\n')
# This is not the full HarmonyOS service configuration; successful markers
# establish only that the proprietary init loaded and executed these jobs.
print(target)

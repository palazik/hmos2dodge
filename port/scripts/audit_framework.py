#!/usr/bin/env python3
"""Map donor services and system abilities; never execute startup commands."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SYSTEM = ROOT / 'work/ohos-runtime/system/system'
VENDOR = ROOT / 'work/donor-configs/vendor'
PROFILES = ROOT / 'work/donor-configs/system/system/profile'
FOCUS = {'hilogd', 'samgr', 'accesstoken_service', 'appspawn', 'foundation',
         'render_service', 'composer_host', 'allocator_host', 'storage_daemon',
         'storage_manager', 'accountmgr', 'multimodalinput', 'hdf_devmgr'}


def main():
    paths = sorted(set(SYSTEM.glob('etc/init/*.cfg')) |
                   set(SYSTEM.glob('etc/init*.cfg')) |
                   set(VENDOR.glob('etc/init/*.cfg')) |
                   set(VENDOR.glob('etc/init*.cfg')) |
                   set((ROOT / 'work/donor-configs/chip_prod').glob('etc/init/*.cfg')))
    services, hazards, errors, imports = {}, [], [], []
    for path in paths:
        try:
            cfg = json.loads(path.read_bytes())
        except (ValueError, UnicodeError) as error:
            errors.append({'file': str(path.relative_to(ROOT)), 'error': str(error)})
            continue
        origin = str(path.relative_to(ROOT))
        for entry in cfg.get('import', []):
            imports.append({'file': origin, 'import': entry})
        for service in cfg.get('services', []):
            services.setdefault(service['name'], []).append({'file': origin, 'definition': service})
        for job in cfg.get('jobs', []):
            for command in job.get('cmds', []):
                if not isinstance(command, str):
                    continue
                verb = command.split()[0] if command.split() else ''
                if ('/dev/block' in command or verb in ('mount_fstab', 'umount_fstab',
                    'format', 'reboot', 'swapon_all', 'restorecon') or
                    re.search(r'/(persist|metadata|misc|firmware_mnt)(?:/|\s|$)', command)):
                    hazards.append({'file': origin, 'job': job['name'], 'command': command,
                                    'disposition': 'requires explicit adaptation before full DSU startup'})
    abilities = {}
    for path in sorted(PROFILES.glob('*.json')):
        try:
            cfg = json.loads(path.read_bytes())
        except ValueError as error:
            errors.append({'file': str(path.relative_to(ROOT)), 'error': str(error)})
            continue
        for ability in cfg.get('systemability', []):
            abilities.setdefault(str(ability['name']), []).append({
                'process': cfg.get('process'), 'profile': path.name, 'definition': ability})
    foundation = [entry for entries in abilities.values() for entry in entries
                  if entry['process'] == 'foundation']
    dependencies = sorted({str(dep) for entry in foundation for dep in entry['definition'].get('depend', [])})
    focus = {}
    for name in sorted(FOCUS):
        definitions = services.get(name, [])
        focus[name] = {'definitions': definitions,
                       'effective_definition': 'not inferred; directory/import load order must be established'}
    output = ROOT / 'port/docs/framework-integration.json'
    report = {
        'scope': 'Static service/SA mapping. Does not start services, establish readiness, or certify full boot.',
        'config_files_scanned': len(paths), 'parse_errors': errors,
        'unique_services': len(services), 'service_definitions': sum(map(len, services.values())),
        'services_with_multiple_definitions': {k: [d['file'] for d in v] for k, v in services.items() if len(v) > 1},
        'system_ability_ids': len(abilities), 'imports': imports,
        'focus_services': focus,
        'foundation_declared_dependencies': {dep: abilities.get(dep, []) for dep in dependencies},
        'foundation_abilities': foundation, 'startup_commands_needing_adaptation': hazards,
        'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'sceneboard': 'Application launched by framework, not a standalone init service; full application startup remains unwired',
    }
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('config_files_scanned', 'unique_services',
                     'service_definitions', 'system_ability_ids', 'parse_errors')}, indent=2))
    print('Foundation dependencies:', ', '.join(dependencies))
    print('Commands requiring adaptation:', len(hazards))


if __name__ == '__main__':
    main()

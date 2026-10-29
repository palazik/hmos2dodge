#!/usr/bin/env python3
"""Compile donor policy offline; keep strict and donor-runtime results distinct."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('strict', 'donor-runtime'), default='strict')
    parser.add_argument('--compiler', type=Path,
                        default=ROOT / 'work/policy-tools/usr/bin/secilc')
    parser.add_argument('--with-op13', action='store_true', help='include the supplemental OP13 DRM map policy')
    args = parser.parse_args()
    system = ROOT / 'work/ohos-runtime/system/system/etc/selinux'
    vendor = ROOT / 'work/donor-configs/vendor/etc/selinux'
    inputs = [system / 'system_common.cil', vendor / 'vendor_common.cil',
              vendor / 'public_common.cil', system / 'system.cil',
              vendor / 'vendor.cil', vendor / 'public.cil',
              system / 'compatible/40.cil']
    if args.with_op13:
        inputs.append(ROOT / 'port/selinux/op13-drm.cil')
    for path in inputs:
        if not path.is_file():
            raise SystemExit('Missing original policy input: ' + str(path))
    input_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    output = ROOT / 'out/selinux' / (args.mode + ('-op13' if args.with_op13 else ''))
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'policy.31.partial'
    command = [str(args.compiler), '-m', '-M', 'true', '-G', '-c', '31', '-O',
               '-f', str(output / 'compiled-file-contexts'), '-o', str(temporary)]
    if args.mode == 'donor-runtime':
        # This matches OpenHarmony 5.1 load_policy.cpp's runtime compiler.
        # It is NOT a strict neverallow pass or a change to kernel enforcement.
        command.append('-N')
    command.extend(str(path) for path in inputs)
    env = os.environ.copy()
    library_path = ROOT / 'work/policy-tools/usr/lib/x86_64-linux-gnu'
    env['LD_LIBRARY_PATH'] = str(library_path) + (':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    if any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != value
           for name, value in input_hashes.items()):
        if temporary.exists():
            temporary.unlink()
        raise SystemExit('Policy inputs changed during compilation; result discarded')
    log = output / 'compiler.log'
    log.write_text(result.stdout + result.stderr)
    report = {
        'mode': args.mode, 'exit_code': result.returncode,
        'op13_supplement': args.with_op13,
        'compile_passed': result.returncode == 0,
        'neverallow_checks_enabled': args.mode == 'strict',
        'neverallow_failures_reported': result.stderr.count('neverallow check failed'),
        'policy_version': 31,
        'source_inputs_modified': False,
        'policy_loaded_into_host_or_device': False,
        'native_service_readiness': 'not established',
        'compiler_sha256': hashlib.sha256(args.compiler.read_bytes()).hexdigest(),
        'input_sha256': input_hashes,
        'log': str(log.relative_to(ROOT)),
        'upstream_runtime_reference': 'https://github.com/openharmony/security_selinux_adapter/blob/OpenHarmony-5.1.0-Release/framework/policycoreutils/src/load_policy.cpp',
    }
    if result.returncode == 0:
        policy = output / 'policy.31'
        temporary.replace(policy)
        report['policy_sha256'] = hashlib.sha256(policy.read_bytes()).hexdigest()
        report['policy_bytes'] = policy.stat().st_size
    elif temporary.exists():
        temporary.unlink()
    (output / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()

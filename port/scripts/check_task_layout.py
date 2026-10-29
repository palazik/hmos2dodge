#!/usr/bin/env python3
"""Compare task_struct size and selected vendor-sensitive offsets to backup."""
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
K = ROOT / 'kernel_workspace/common'
OUT = K / 'kout'
CHECK = ROOT / 'work/task-layout'
CHECK.mkdir(parents=True, exist_ok=True)
fields = ['pid', 'tgid', 'real_parent', 'cred', 'comm', 'android_vendor_data1',
          'android_oem_data1', 'thread']
compiler = ROOT / 'kernel_workspace/zyc-clang/bin/clang'
args = [str(compiler), '--target=aarch64-linux-gnu', '-D__KERNEL__', '-nostdinc',
        '-mgeneral-regs-only', '-fno-pic', '-fno-PIE', '-std=gnu11', '-Wno-unknown-warning-option']
for directory in ['arch/arm64/include', 'kout/arch/arm64/include/generated', 'include',
                  'kout/include', 'arch/arm64/include/uapi',
                  'kout/arch/arm64/include/generated/uapi', 'include/uapi', 'kout/include/generated/uapi']:
    args += ['-I', str(K / directory)]
for header in ['include/linux/compiler-version.h', 'include/linux/kconfig.h', 'include/linux/compiler_types.h']:
    args += ['-include', str(K / header)]
layouts = {}
for name, header in [('baseline', ROOT / 'work/kernel-baseline/include/linux/sched.h'),
                     ('patched', K / 'include/linux/sched.h')]:
    source = CHECK / f'{name}.c'
    source.write_text(f'#include "{header}"\nconst unsigned long task_layout[] = {{\n'
                      'sizeof(struct task_struct),\n' +
                      ',\n'.join('__builtin_offsetof(struct task_struct, ' + f + ')' for f in fields) + '\n};\n')
    obj = CHECK / f'{name}.o'
    raw = CHECK / f'{name}.bin'
    subprocess.run(args + ['-c', str(source), '-o', str(obj)], cwd=OUT, check=True)
    subprocess.run(['llvm-objcopy', '--dump-section', f'.rodata={raw}', str(obj)], check=True)
    values = struct.unpack('<' + 'Q' * (1 + len(fields)), raw.read_bytes())
    layouts[name] = dict(zip(['sizeof'] + fields, values))
report = {'task_struct': layouts, 'equal': layouts['baseline'] == layouts['patched'],
          'scope': 'task_struct size and listed offsets only; full module ABI still requires validation'}
(CHECK / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
if not report['equal']:
    raise SystemExit('FAIL task_struct layout changed')

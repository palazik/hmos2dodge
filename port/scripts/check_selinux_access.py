#!/usr/bin/env python3
"""Evaluate selected policy decisions in libsepol memory, without a kernel load."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class Decision(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ('allowed', 'decided', 'auditallow', 'auditdeny', 'seqno')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=ROOT / 'out/selinux/donor-runtime/policy.31')
    parser.add_argument('--library', type=Path,
                        default=ROOT / 'work/policy-tools/usr/lib/x86_64-linux-gnu/libsepol.so.2')
    parser.add_argument('--output', type=Path, default=ROOT / 'out/selinux/access-decisions.json')
    parser.add_argument('--include-vm-observer', action='store_true', help='also query guest observer SA permissions')
    args = parser.parse_args()
    lib = C.CDLL(str(args.library.resolve()))
    libc = C.CDLL(None)
    libc.fopen.argtypes, libc.fopen.restype = [C.c_char_p, C.c_char_p], C.c_void_p
    libc.fclose.argtypes, libc.fclose.restype = [C.c_void_p], C.c_int
    lib.sepol_set_policydb_from_file.argtypes = [C.c_void_p]
    lib.sepol_set_policydb_from_file.restype = C.c_int
    lib.sepol_context_to_sid.argtypes = [C.c_char_p, C.c_size_t, C.POINTER(C.c_uint32)]
    lib.sepol_context_to_sid.restype = C.c_int
    lib.sepol_string_to_security_class.argtypes = [C.c_char_p, C.POINTER(C.c_uint16)]
    lib.sepol_string_to_security_class.restype = C.c_int
    lib.sepol_string_to_av_perm.argtypes = [C.c_uint16, C.c_char_p, C.POINTER(C.c_uint32)]
    lib.sepol_string_to_av_perm.restype = C.c_int
    lib.sepol_compute_av.argtypes = [C.c_uint32, C.c_uint32, C.c_uint16, C.c_uint32, C.POINTER(Decision)]
    lib.sepol_compute_av.restype = C.c_int
    stream = libc.fopen(str(args.policy.resolve()).encode(), b'rb')
    if not stream:
        raise SystemExit('Cannot open policy')
    try:
        if lib.sepol_set_policydb_from_file(stream):
            raise SystemExit('Cannot parse binary policy')
    finally:
        libc.fclose(stream)

    def sid(context):
        encoded = context.encode()
        result = C.c_uint32()
        if lib.sepol_context_to_sid(encoded, len(encoded) + 1, C.byref(result)):
            raise ValueError('Invalid policy context: ' + context)
        return result.value

    queries = [('samgr', 'bootevent_param', 'parameter_service', ['set']),
               ('samgr', 'dev_dri_file', 'chr_file', ['map']),
               ('render_service', 'dev_dri_file', 'chr_file', ['open', 'read', 'write', 'map', 'ioctl']),
               ('composer_host', 'dev_dri_file', 'chr_file', ['open', 'read', 'write', 'map', 'ioctl']),
               ('allocator_host', 'dev_dri_file', 'chr_file', ['open', 'read', 'write', 'map', 'ioctl'])]
    if args.include_vm_observer:
        queries += [('init', 'sa_accesstoken_manager_service', 'samgr_class', ['get']),
                    ('accesstoken_service', 'sa_accesstoken_manager_service', 'samgr_class', ['get', 'add'])]
    decisions = []
    for source, target, class_name, permissions in queries:
        source_context, target_context = f'u:r:{source}:s0', f'u:object_r:{target}:s0'
        source_sid, target_sid = sid(source_context), sid(target_context)
        cls = C.c_uint16()
        if lib.sepol_string_to_security_class(class_name.encode(), C.byref(cls)):
            raise SystemExit('Unknown policy class: ' + class_name)
        results = {}
        for permission in permissions:
            mask, decision = C.c_uint32(), Decision()
            if lib.sepol_string_to_av_perm(cls, permission.encode(), C.byref(mask)):
                raise SystemExit('Unknown policy permission: ' + permission)
            if lib.sepol_compute_av(source_sid, target_sid, cls, mask, C.byref(decision)):
                raise SystemExit('Policy access calculation failed')
            results[permission] = decision.allowed & mask.value == mask.value
        decisions.append({'source': source_context, 'target': target_context,
                          'class': class_name, 'allowed': results})
    report = {'scope': 'Offline policy decisions only; no kernel policy load, device access or service readiness test',
              'policy_sha256': hashlib.sha256(args.policy.read_bytes()).hexdigest(),
              'ioctl_limitation': 'Base ioctl permission only; driver-specific extended ioctl permissions are not evaluated',
              'decisions': decisions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

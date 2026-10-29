#!/usr/bin/env python3
"""Stream-verify flat EROFS payload files, including files larger than 2 GiB.

The bundled old fsck.erofs makes oversized single reads on the 2.9 GiB donor
system.img. This verifier checks every embedded donor byte with bounded reads.
Supports only flat EROFS layouts produced by build_probe.sh (no compression).
"""
import hashlib
import argparse
import json
from pathlib import Path
import stat
import struct

ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / 'out/dsu/op13-hmos-mount-probe.img'


class FlatErofs:
    def __init__(self, image):
        self.f = image.open('rb')
        self.f.seek(1024)
        sb = self.f.read(128)
        if struct.unpack_from('<I', sb)[0] != 0xE0F5E1E2:
            raise ValueError('not EROFS')
        self.block = 1 << sb[12]
        self.root = struct.unpack_from('<H', sb, 14)[0]
        self.limit = struct.unpack_from('<I', sb, 36)[0] * self.block
        self.meta = struct.unpack_from('<I', sb, 40)[0] * self.block

    def read(self, offset, size):
        if offset < 0 or offset + size > self.limit:
            raise ValueError('extent outside EROFS filesystem')
        self.f.seek(offset)
        data = self.f.read(size)
        if len(data) != size:
            raise ValueError('short image read')
        return data

    def inode(self, nid):
        pos = self.meta + nid * 32
        data = self.read(pos, 64)
        fmt, xattrs, mode = struct.unpack_from('<HHH', data)
        extended = fmt & 1
        layout = (fmt >> 1) & 7
        if layout not in (0, 2):
            raise ValueError(f'unsupported compressed/chunked inode {nid}: {layout}')
        size = struct.unpack_from('<Q' if extended else '<I', data, 8)[0]
        raw = struct.unpack_from('<I', data, 16)[0] * self.block
        inline = pos + (64 if extended else 32) + (12 + (xattrs - 1) * 4 if xattrs else 0)
        segments = []
        if layout == 0:
            segments.append((raw, size))
        else:
            whole = size // self.block * self.block
            if whole:
                segments.append((raw, whole))
            if size - whole:
                segments.append((inline, size - whole))
        return mode, size, segments

    def chunks(self, nid):
        for offset, size in self.inode(nid)[2]:
            while size:
                n = min(size, 1024 * 1024)
                yield self.read(offset, n)
                offset += n
                size -= n

    def lookup(self, path):
        nid = self.root
        for component in path.strip('/').split('/'):
            mode, _, _ = self.inode(nid)
            if not stat.S_ISDIR(mode):
                raise ValueError('not a directory')
            data = b''.join(self.chunks(nid))
            found = None
            for start in range(0, len(data), self.block):
                block = data[start:start + self.block]
                first_name = struct.unpack_from('<H', block, 8)[0]
                count = first_name // 12
                for i in range(count):
                    child, name_offset = struct.unpack_from('<QH', block, i * 12)
                    end = struct.unpack_from('<H', block, (i + 1) * 12 + 8)[0] if i + 1 < count else len(block)
                    name = block[name_offset:end].rstrip(b'\0').decode()
                    if name == component:
                        found = child
                        break
                if found is not None:
                    break
            if found is None:
                raise FileNotFoundError(path)
            nid = found
        return nid


def verify(image, report_path, check_bootstrap=False, profile='minimal', check_display=False):
    expected = {}
    for line in (ROOT / 'port/docs/input-images.sha256').read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        expected[Path(name).name] = sha
    fs = FlatErofs(image)
    report = {}
    for part in ('system', 'vendor', 'chip_prod', 'sys_prod', 'cust', 'patch'):
        name = part + '.img'
        nid = fs.lookup('hmos/images/' + name)
        h = hashlib.sha256()
        for block in fs.chunks(nid):
            h.update(block)
        sha = h.hexdigest()
        report[name] = {'sha256': sha, 'size': fs.inode(nid)[1], 'matches_input': sha == expected[name]}
        if not report[name]['matches_input']:
            raise SystemExit(f'FAIL embedded donor mismatch: {name}')
        print(f'PASS {name}: every embedded byte matches source', flush=True)
    if check_bootstrap:
        cfg = json.loads(b''.join(fs.chunks(fs.lookup('hmos/bootstrap/etc/init.cfg'))))
        expected_services = {'minimal': set(), 'logging': {'hilogd'}, 'core': {'hilogd', 'samgr'}}[profile]
        services = cfg.get('services', [])
        if {s['name'] for s in services} != expected_services or cfg.get('import') != []:
            raise SystemExit('FAIL bootstrap services/imports do not match the declared profile')
        for service in services:
            if service['path'] != ['/system/bin/' + service['name']] or service.get('critical', [0])[0] != 0:
                raise SystemExit('FAIL unexpected bootstrap service executable or critical flag')
        allowed = {'mkdir', 'setparam', 'write', 'start'}
        for job in cfg['jobs']:
            for command in job['cmds']:
                if command.split()[0] not in allowed or '/dev/block' in command:
                    raise SystemExit('FAIL unexpected bootstrap command: ' + command)
                if command.startswith('start ') and command.split()[1] not in expected_services:
                    raise SystemExit('FAIL unexpected bootstrap start target')
        report['bootstrap'] = {'profile': profile, 'services': sorted(expected_services), 'imports': 0,
                               'init_jobs': [j['name'] for j in cfg['jobs']]}
        print(f'PASS {profile} bootstrap config: declared services only; no imports/block-device commands', flush=True)
    if check_display:
        report['display_overrides'] = {}
        for name in ('libdisplay_buffer_vdi_impl.z.so', 'libdisplay_composer_vdi_impl.z.so'):
            embedded = b''.join(fs.chunks(fs.lookup('hmos/overrides/vendor/lib64/' + name)))
            built = (ROOT / 'out/display' / name).read_bytes()
            if embedded != built: raise SystemExit('FAIL display library differs from build: ' + name)
            report['display_overrides'][name] = hashlib.sha256(embedded).hexdigest()
        print('PASS both display overrides exactly match rebuilt libraries', flush=True)
        report['ui_overrides'] = {}
        for relative in ('sys_prod/etc/window/resources/display_manager_config.xml',
                         'sys_prod/etc/graphic/hgm_policy_config.xml'):
            embedded = b''.join(fs.chunks(fs.lookup('hmos/overrides/' + relative)))
            built = (ROOT / 'out/ui-config/overrides' / relative).read_bytes()
            if embedded != built: raise SystemExit('FAIL UI configuration differs from build: ' + relative)
            report['ui_overrides'][relative] = hashlib.sha256(embedded).hexdigest()
        print('PASS OP13 geometry and refresh policy overrides exactly match generated files', flush=True)
    fs.f.close()
    report_path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=IMAGE)
    parser.add_argument('--report', type=Path, default=ROOT / 'out/dsu/payload-verification.json')
    parser.add_argument('--check-bootstrap', action='store_true')
    parser.add_argument('--profile', choices=('minimal', 'logging', 'core'), default='minimal')
    parser.add_argument('--check-display', action='store_true')
    args = parser.parse_args()
    verify(args.image, args.report, args.check_bootstrap, args.profile, args.check_display)

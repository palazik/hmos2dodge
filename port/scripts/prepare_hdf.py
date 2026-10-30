#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Remove the Kirin display-engine device; preserve the HDF host layout."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TOKEN = r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|[{}]|[^\s]'


def node_span(text, wanted):
    tokens = list(re.finditer(TOKEN, text))
    stack, spans = [], []
    for index, token in enumerate(tokens):
        if token[0] == '{':
            previous = tokens[index - 1]
            if not re.fullmatch(r'[A-Za-z_]\w*', previous[0]):
                raise ValueError('Unexpected HCS node syntax')
            stack.append((previous[0], previous.start()))
        elif token[0] == '}':
            if not stack:
                raise ValueError('Unbalanced HCS')
            if tuple(name for name, _ in stack) == wanted:
                spans.append((stack[-1][1], token.end()))
            stack.pop()
    if stack or len(spans) != 1:
        raise ValueError(f'Expected exactly one node: {wanted}')
    return spans[0]


def remove_kirin_displayengine(text):
    start, end = node_span(text, ('root', 'device_info', 'display_composer', 'displayengine_device'))
    removed = text[start:end]
    if 'libdisplayengine_driver.z.so' not in removed:
        raise ValueError('Unexpected displayengine device')
    return text[:start] + text[end:], removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT /
        'work/donor-configs/chip_prod/chip_prod/etc/hdfconfig/hdf_default.hcb')
    parser.add_argument('--compiler', type=Path, default=ROOT / 'work/hc-gen-build/hc-gen')
    args = parser.parse_args()
    tool = args.compiler.resolve()
    output = ROOT / 'out/hdf'
    output.mkdir(parents=True, exist_ok=True)

    def run(*values):
        subprocess.run([str(tool), *map(str, values)], check=True)

    original = args.input.read_bytes()
    run('-d', '-o', output / 'donor.hcs', args.input)
    donor = (output / 'donor.d.hcs').read_text()
    # Reject compiler or format discrepancies BEFORE producing a port candidate.
    run('-b', '-o', output / 'roundtrip.hcb', output / 'donor.d.hcs')
    if (output / 'roundtrip.hcb').read_bytes() != original:
        raise ValueError('Donor HCB did not round-trip byte-for-byte; refusing adaptation')
    candidate, removed = remove_kirin_displayengine(donor)
    (output / 'op13.hcs').write_text(candidate)
    run('-b', '-o', output / 'op13.hcb', output / 'op13.hcs')
    run('-d', '-o', output / 'op13-check.hcs', output / 'op13.hcb')
    checked = (output / 'op13-check.d.hcs').read_text()
    # Ignore formatting between tokens; preserve whitespace INSIDE strings.
    normalized = lambda value: re.findall(TOKEN, value)
    if normalized(checked) != normalized(candidate):
        raise ValueError('Candidate configuration changed during compilation')
    hosts = lambda value: re.findall(r'hostName\s*=\s*"([^"\n]+)"', value)
    if hosts(donor) != hosts(checked):
        raise ValueError('Host order changed')
    if args.input.read_bytes() != original:
        raise ValueError('Donor source changed during build')
    report = {
        'donor_sha256': hashlib.sha256(original).hexdigest(),
        'candidate_sha256': hashlib.sha256((output / 'op13.hcb').read_bytes()).hexdigest(),
        'compiler_sha256': hashlib.sha256(tool.read_bytes()).hexdigest(),
        'donor_roundtrip_byte_identical': True,
        'candidate_roundtrip_text_equivalent': True,
        'host_names_and_order_preserved': True, 'hosts': hosts(donor),
        'removed_device': 'root.device_info.display_composer.displayengine_device',
        'removed_module': 'libdisplayengine_driver.z.so',
        'core_image_integration': False, 'native_hdf_tested': False,
        'scope': 'One device removed; other hosts retained but not enabled by this tool',
    }
    (output / 'adaptation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS donor byte round-trip, candidate semantic round-trip, unchanged host order')


if __name__ == '__main__':
    main()

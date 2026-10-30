#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise narrow HCS removal and reject ambiguous donor layouts."""
from prepare_hdf import ROOT, TOKEN, remove_kirin_displayengine
import json
import re

donor = (ROOT / 'out/hdf/donor.d.hcs').read_text()
candidate, removed = remove_kirin_displayengine(donor)
assert 'libdisplayengine_driver.z.so' in removed
assert 'libdisplayengine_driver.z.so' not in candidate
assert 'libdisplay_composer_driver_1.0.z.so' in candidate
assert 'liballocator_driver_1.0.z.so' in candidate
report = json.loads((ROOT / 'out/hdf/adaptation.json').read_text())
assert report['donor_roundtrip_byte_identical']
assert report['candidate_roundtrip_text_equivalent']
assert report['host_names_and_order_preserved']
assert report['hosts'][7:9] == ['composer_host', 'allocator_host']
checked = (ROOT / 'out/hdf/op13-check.d.hcs').read_text()
assert re.findall(TOKEN, candidate) == re.findall(TOKEN, checked)
# Braces inside quoted strings must not terminate the removed subtree.
fixture = '''root { device_info { display_composer {
displayengine_device { moduleName = "libdisplayengine_driver.z.so";
value = "} { \\"quoted\\""; nested { test = "}"; } }
composer_device { moduleName = "keep-me"; } } } }'''
adapted, _ = remove_kirin_displayengine(fixture)
assert 'keep-me' in adapted and 'libdisplayengine_driver.z.so' not in adapted
for value in ('root {}', fixture + fixture, fixture + '}'):
    try:
        remove_kirin_displayengine(value)
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted missing/duplicate/unbalanced node')
print('PASS narrow HDF removal: host IDs 7/8 retained; composer and allocator retained; ambiguous layouts rejected')

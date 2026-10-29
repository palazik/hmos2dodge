#!/usr/bin/env python3
"""Attach verifiable development AVB metadata; OEM key trust is device-specific."""
from pathlib import Path
import argparse
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image', type=Path, action='append', help='specific image(s); default: out/dsu/*.img')
args = parser.parse_args()
key = ROOT / 'work/keys/dsu-development.pem'
key.parent.mkdir(parents=True, exist_ok=True)
if not key.exists():
    subprocess.run(['openssl', 'genrsa', '-out', str(key), '4096'], check=True)
    key.chmod(0o600)
avb = ROOT / 'kernel_workspace/build-tools/linux-x86/bin/avbtool'
images = [p.resolve() for p in args.image] if args.image else sorted((ROOT / 'out/dsu').glob('*.img'))
for image in images:
    with image.open('rb') as f:
        f.seek(-64, 2)
        signed = f.read(4) == b'AVBf'
    if not signed:
        size = image.stat().st_size
        partition_size = ((size * 103 // 100 + 4 * 1024 * 1024 + 4095) // 4096) * 4096
        subprocess.run([str(avb), 'add_hashtree_footer', '--image', str(image),
                        '--partition_name', 'system', '--partition_size', str(partition_size),
                        '--hash_algorithm', 'sha256', '--do_not_generate_fec',
                        '--algorithm', 'SHA256_RSA4096', '--key', str(key),
                        '--prop', 'com.android.build.system.security_patch:2026-07-01',
                        '--prop', 'com.android.build.system.os_version:16'], check=True)
    # avbtool resolves the hashtree descriptor against its partition name.
    with tempfile.TemporaryDirectory(prefix='avb-verify-', dir=ROOT / 'work') as tmp:
        verify_image = Path(tmp) / 'system.img'
        verify_image.symlink_to(image)
        subprocess.run([str(avb), 'verify_image', '--image', str(verify_image), '--key', str(key)], check=True)
    result = subprocess.run([str(avb), 'info_image', '--image', str(image)], text=True, capture_output=True, check=True)
    image.with_suffix('.avb.txt').write_text(result.stdout)
subprocess.run([str(avb), 'extract_public_key', '--key', str(key),
                '--output', str(ROOT / 'out/dsu/development.avbpubkey')], check=True)

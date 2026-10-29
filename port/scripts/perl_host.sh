#!/usr/bin/env bash
# Work around this host's broken Perl POSIX.so without changing kernel sources.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
if [[ ${1:-} == *generate_initcall_order.pl ]]; then
    task_script=$1
    shift
    python3 - "$task_script" "$task_root/work/generate_initcall_order.pl" <<'PY'
import pathlib, sys
source = pathlib.Path(sys.argv[1]).read_text()
old = 'use POSIX ":sys_wait_h";'
assert source.count(old) == 1
# This script only uses WNOHANG; its Linux UAPI value is 1.
pathlib.Path(sys.argv[2]).write_text(source.replace(old, 'use constant WNOHANG => 1;'))
PY
    exec /usr/bin/perl "$task_root/work/generate_initcall_order.pl" "$@"
fi
exec /usr/bin/perl "$@"

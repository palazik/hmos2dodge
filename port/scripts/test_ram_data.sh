#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
task_output="$task_root/work/ramdata-check"
mkdir -p "$task_output"
gcc -Wall -Wextra -Werror -O2 "$task_root/port/src/ram_data_check.c" -o "$task_output/check"
truncate -s 16M "$task_output/generated-physical-fixture"
"$task_output/check" "$task_output/generated-physical-fixture"

#!/usr/bin/env python3
"""Adapt the token/Binder portion of hmos2sweet to this Android 6.6 tree.

Back up every original before editing; never apply the sweet hardware patches.
"""
import difflib
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
K = ROOT / 'kernel_workspace/common'
BACKUP = ROOT / 'work/kernel-baseline'
PATCH = next((ROOT / 'work/reference-source/src/kernel/patches').glob('0001-*'))
changed = []


def write(name, data):
    p = K / name
    original = BACKUP / name
    if p.exists() and not original.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, original)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data)
    changed.append(name)


def edit(name, old, new):
    p = K / name
    text = p.read_text()
    if new in text:
        changed.append(name)
        return
    if text.count(old) != 1:
        raise RuntimeError(f'{name}: expected one anchor: {old!r}')
    write(name, text.replace(old, new, 1))


def added_file(name):
    section = PATCH.read_text().split(f'diff --git a/{name} b/{name}\n', 1)[1].split('\ndiff --git ', 1)[0]
    return ''.join(line[1:] + '\n' for line in section.splitlines()
                   if line.startswith('+') and not line.startswith('+++'))


# Reuse the Huawei token ioctl ABI from the reference, preserving its license.
for name in ('drivers/accesstokenid/Kconfig', 'drivers/accesstokenid/Makefile',
             'drivers/accesstokenid/access_tokenid.h'):
    write(name, added_file(name))
driver = added_file('drivers/accesstokenid/access_tokenid.c')
driver = driver.replace('#include <linux/cred.h>', '#include <linux/cred.h>\n#include <linux/hmos_compat.h>')
driver = driver.replace('DEFINE_RWLOCK(token_rwlock);', '''/* Opt in only from the experimental DSU PID 1. Default Android semantics. */
bool hmos_compat_enabled;
module_param_named(compat, hmos_compat_enabled, bool, 0600);
MODULE_PARM_DESC(compat, "Enable HarmonyOS Binder/token extensions (default off)");

DEFINE_RWLOCK(token_rwlock);''')
driver = driver.replace('unsigned int func_cmd = _IOC_NR(cmd);', '''unsigned int func_cmd = _IOC_NR(cmd);

\tif (!READ_ONCE(hmos_compat_enabled))
\t\treturn -EOPNOTSUPP;''')
driver = driver.replace('err = misc_register(&access_tokenid_device);', '''g_cache = kmem_cache_create("access_token_node", sizeof(struct token_perm_node), 0, SLAB_HWCACHE_ALIGN, NULL);
\tif (!g_cache)
\t\treturn -ENOMEM;
\terr = misc_register(&access_tokenid_device);''')
driver = driver.replace('pr_err("access_tokenid register failed\\n");', 'pr_err("access_tokenid register failed\\n");\n\t\tkmem_cache_destroy(g_cache);')
driver = driver.replace('''\n\tg_cache = kmem_cache_create("access_token_node", sizeof(struct token_perm_node), 0, SLAB_HWCACHE_ALIGN, NULL);
\tif (g_cache == NULL) {
\t\tpr_err("access_tokenid kmem_cache create failed\\n");
\t\treturn -ENOMEM;
\t}
''', '\n')
write('drivers/accesstokenid/access_tokenid.c', driver)
write('include/linux/hmos_compat.h', '''/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_HMOS_COMPAT_H
#define _LINUX_HMOS_COMPAT_H
#include <linux/types.h>
#ifdef CONFIG_ACCESS_TOKENID
extern bool hmos_compat_enabled;
#endif
#endif
''')
edit('drivers/Kconfig', 'source "drivers/android/Kconfig"',
     'source "drivers/android/Kconfig"\n\nsource "drivers/accesstokenid/Kconfig"')
edit('drivers/Makefile', 'obj-y\t\t\t\t+= android/',
     'obj-y\t\t\t\t+= android/\nobj-$(CONFIG_ACCESS_TOKENID)\t+= accesstokenid/')

# Consume unused KABI padding rather than shifting task_struct/vendor offsets.
edit('include/linux/sched.h', '\tANDROID_KABI_RESERVE(3);\n\tANDROID_KABI_RESERVE(4);\n\tANDROID_KABI_RESERVE(5);', '''#ifdef CONFIG_ACCESS_TOKENID
\tANDROID_KABI_USE(3, u64 token);
\tANDROID_KABI_USE(4, u64 ftoken);
#else
\tANDROID_KABI_RESERVE(3);
\tANDROID_KABI_RESERVE(4);
#endif
\tANDROID_KABI_RESERVE(5);''')
edit('kernel/fork.c', '\ttsk->wake_q.next = NULL;', '''\ttsk->wake_q.next = NULL;
#ifdef CONFIG_ACCESS_TOKENID
\t/* token is inherited by dup_task_struct; first-caller token is not. */
\ttsk->ftoken = 0;
#endif''')

edit('drivers/android/binder_internal.h', '\tenum binder_prio_state prio_state;\n};', '''\tenum binder_prio_state prio_state;
#ifdef CONFIG_ACCESS_TOKENID
\tstruct access_token hmos_tokens;
\tu64 hmos_sender_pid;
#endif
};''')
edit('drivers/android/binder_internal.h', '\tANDROID_OEM_DATA(1);\n};\n\n/**\n * struct binder_object', '''\tANDROID_OEM_DATA(1);
#ifdef CONFIG_ACCESS_TOKENID
\tu64 hmos_sender_token;
\tu64 hmos_first_token;
#endif
};

/**
 * struct binder_object''')
edit('include/uapi/linux/android/binder.h', '#define BINDER_FREEZE', '''/* OpenHarmony 5 token and sender-query ABI. */
struct binder_feature_set { __u64 feature_set; };
struct access_token {
\t__u64 sender_tokenid;
\t__u64 first_tokenid;
\t__u64 reserved[2];
};
struct binder_sender_info {
\tstruct access_token tokens;
\t__u64 sender_pid_nr;
};
#define BINDER_FEATURE_SET _IOWR('b', 30, struct binder_feature_set)
#define BINDER_GET_ACCESS_TOKEN _IOWR('b', 31, struct access_token)
#define BINDER_GET_SENDER_INFO _IOWR('b', 32, struct binder_sender_info)

#define BINDER_FREEZE''')
edit('drivers/android/binder.c', '#include <linux/fdtable.h>',
     '#include <linux/fdtable.h>\n#include <linux/hmos_compat.h>')
edit('drivers/android/binder.c', '\tt->sender_euid = task_euid(proc->tsk);', '''\tt->sender_euid = task_euid(proc->tsk);
#ifdef CONFIG_ACCESS_TOKENID
\tif (READ_ONCE(hmos_compat_enabled)) {
\t\tt->hmos_sender_token = READ_ONCE(current->token);
\t\tt->hmos_first_token = READ_ONCE(current->ftoken);
\t}
#endif''')
edit('drivers/android/binder.c', '\t\t\ttrd->sender_pid = 0;\n\t\t}', '''\t\t\ttrd->sender_pid = 0;
#ifdef CONFIG_ACCESS_TOKENID
\t\t\tif (READ_ONCE(hmos_compat_enabled))
\t\t\t\ttrd->sender_pid = t->from_pid;
#endif
\t\t}''')
edit('drivers/android/binder.c', '\t\tt->buffer->allow_user_free = 1;', '''\t\tt->buffer->allow_user_free = 1;
#ifdef CONFIG_ACCESS_TOKENID
\t\tif (READ_ONCE(hmos_compat_enabled)) {
\t\t\tbinder_inner_proc_lock(thread->proc);
\t\t\tthread->hmos_tokens.sender_tokenid = t->hmos_sender_token;
\t\t\tthread->hmos_tokens.first_tokenid = t->hmos_first_token;
\t\t\tthread->hmos_sender_pid = t->from_pid;
\t\t\tbinder_inner_proc_unlock(thread->proc);
\t\t}
#endif''')
edit('drivers/android/binder.c', '\tcase BINDER_GET_NODE_INFO_FOR_REF: {', '''#ifdef CONFIG_ACCESS_TOKENID
\tcase BINDER_FEATURE_SET: {
\t\tstruct binder_feature_set features = { .feature_set = 5 };
\t\tif (!READ_ONCE(hmos_compat_enabled)) { ret = -EINVAL; goto err; }
\t\tif (copy_to_user(ubuf, &features, sizeof(features))) {
\t\t\tret = -EFAULT;
\t\t\tgoto err;
\t\t}
\t\tbreak;
\t}
\tcase BINDER_GET_ACCESS_TOKEN:
\tcase BINDER_GET_SENDER_INFO: {
\t\tstruct binder_sender_info info = {};
\t\tsize_t info_size = cmd == BINDER_GET_ACCESS_TOKEN ?
\t\t\tsizeof(info.tokens) : sizeof(info);
\t\tif (!READ_ONCE(hmos_compat_enabled)) { ret = -EINVAL; goto err; }
\t\tbinder_inner_proc_lock(proc);
\t\tinfo.tokens = thread->hmos_tokens;
\t\tinfo.sender_pid_nr = thread->hmos_sender_pid;
\t\tbinder_inner_proc_unlock(proc);
\t\tif (copy_to_user(ubuf, &info, info_size)) {
\t\t\tret = -EFAULT;
\t\t\tgoto err;
\t\t}
\t\tbreak;
\t}
#endif
\tcase BINDER_GET_NODE_INFO_FOR_REF: {''')

write('arch/arm64/configs/hmos_dsu.config', '''# Additive stage-1 support; keep all Android GKI/vendor options.
CONFIG_ACCESS_TOKENID=y
CONFIG_DEVTMPFS=y
CONFIG_BLK_DEV_LOOP=y
CONFIG_EROFS_FS=y
''')

out = []
for name in sorted(set(changed)):
    original = BACKUP / name
    before = original.read_text() if original.exists() else ''
    out.extend(difflib.unified_diff(before.splitlines(True), (K / name).read_text().splitlines(True),
                                   fromfile='a/' + name if original.exists() else '/dev/null', tofile='b/' + name))
(ROOT / 'port/kernel/0001-hmos-dsu-token-binder-6.6.patch').write_text(''.join(out))
print(f'Prepared {len(set(changed))} files; originals in {BACKUP}')

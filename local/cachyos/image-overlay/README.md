# AD107 image overlay — unbooted, experimental

This directory is input to the separate parent image builder, **not a host
installation script**. Copy its `usr/` tree into the dedicated systemd dracut
image only. It must not be installed into the normal host root or stock image.
No gate execution, module loading, hardware probing, root operations or boot
has been performed while creating this overlay.

## Required image-builder contract

* Physically omit **all `nvidia*`, `nouveau`, `vfio_pci`, `vfio_pci_core`**
  modules from this image, including compressed variants. Do not rely on a
  blacklist alone. Reject a kernel with these binders built in. Audit other
  possible binders/loading entry points as well.
* Include the pinned `gpu_unlock` module and required firmware, but never
  force-load it or add `rd.driver.pre=gpu_unlock`, a modules-load entry or a
  udev/modprobe install hook. This service is the only intended loader.
* Include `/bin/sh`, `mkdir`, and `modprobe` plus their interpreter/library
  dependencies. Use dracut `--install` with resolved host paths, e.g.
  `$(command -v modprobe)` and `$(command -v mkdir)`, accounting for usr-merge.
  The gate resolves modprobe only in `/usr/sbin:/usr/bin:/sbin:/bin`.
  Other gate operations (`read`, `printf`, `test`, `command`) are shell builtins.
* Include all three drop-ins and the service (the Requires dependencies activate it; no separate activation symlink) at the exact paths shown. Requires +
  After on all consumers is deliberate: ordering alone is not failure
  propagation, nor is only blocking pre-udev sufficient for switch-root.
* Review the actual extracted image graph and emergency path for cycles and
  failure propagation. Static tests do not prove runtime graph correctness.
  Keep the separate stock boot path independent and unchanged.

## Gate behavior

The sole accepted opt-in tokens are each present **once** on `/proc/cmdline`:

```
gpu_unlock.targets=0000:01:00.0 gpu_unlock.ad107_experimental=1
```

Duplicate, conflicting, malformed or unknown `gpu_unlock.*` (also
`gpu-unlock.*`) tokens fail closed. `rd.break`, `rd.debug` and debug options
are neither required nor authorization. Quoting/escaping is not an alternate
accepted spelling. PCI identity is fixed to NVIDIA **10de:28a0**, the AD107M
function at 0000:01:00.0, not a generic desktop 4060. A bound function,
preloaded unlock module or known competing GPU binder causes refusal.

Atomic creation of `/run/ad107-experiment/attempted` happens before validation
or module loading, so even validation failure consumes the boot's invocation.
The marker is never removed. `systemctl restart` after success or failure must
fail rather than make another attempt; concurrent calls cannot both attempt.
Do not remove this marker, bypass dependencies, or manually load modules to
continue an unsuccessful experimental boot. Normal initrd `/run` is volatile
per boot and carried into real root; this is not a tamper-proof control against
an administrator who can change units, files or the running kernel.

The gate directly and synchronously runs modprobe once with explicit fixed
parameters, bypassing modprobe configuration/install hooks. Its zero exit alone
is insufficient: read-only sysfs `targets` must be `0000:01:00.0`, the bool
`ad107_experimental` must read **Y** (Linux canonical true representation), and
`ad107_result` must read **3**, each as an exact single-line value. Anything else
returns nonzero. There is no retry, unbind/unload, automatic reboot or poweroff.

`/run/ad107-experiment/result` and the journal are **diagnostics only**, never
an authorization token. The service never reads that record to authorize
anything. A second invocation preserves the previous record and logs refusal.
A missing or ATTEMPTING record may indicate abrupt death or a hang, not success.

## Dependencies, hangs and limits

The unit deliberately has `DefaultDependencies=no`, no sysinit Wants, and no
root/remount, udev, device or network dependency. In particular, it does not
order after systemd-remount-fs: the image must already provide `/proc`, `/sys`
and writable `/run` as initrd API filesystems before this execution point.
Review that assumption in the actual image; missing API filesystems fail closed.
There are no Condition directives that could skip the barrier as a success.

Both timeouts are **infinity**: a finite userspace timeout cannot safely cancel
kernel module init, firmware execution, DMA or a hung task. A hang may block
boot forever or hang the entire machine; emergency.target only helps after a
failure that actually returns. Killing the helper cannot undo hardware effects.
Another GPU/SSH is not a guarantee of recovery. No absolute safety, absence of
races, successful reset/cleanup, or cold-boot recovery is guaranteed. Scalar
result=3 is an observation of the pinned module's contract, not independent
proof that arbitrary kernel/firmware behavior is safe.

## Hardware-free checks

From the workspace, run `python3 -m unittest discover -s preparation/tests -p
 'test_image_overlay.py'`. The test only reads source and runs `sh -n`; it never
sources/executes the gate, invokes modprobe or mocks a host sysfs tree. No path
prefix/test bypass is shipped. Dynamic failure-injection and extracted-image
systemd graph tests remain required before considering an experimental boot.

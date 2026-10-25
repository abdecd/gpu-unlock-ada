# Exact 28a0 AD107M RTX 4060 Laptop owner report

## Scope and admission

This contribution adds only NVIDIA `10de:28a0` (RTX 4060 Laptop, AD107M) as an
**experimental opt-in**, not an AD107-family allowlist or universal laptop
support claim. It selects the existing pinned AD102-family assets and retains
all existing marker, required-permission, SEC2 HALT, selector, effective
readout and post-FLR gates. It changes neither firmware nor transaction logic.

`gpu_unlock.ad107_experimental` defaults to false. Both that flag and one
exact PCI BDF are required, for example on the tested machine:

```text
gpu_unlock.targets=0000:01:00.0 gpu_unlock.ad107_experimental=1
```

`targets=all`, lists, duplicate addresses, missing/wrong addresses and other
experimental flags do not admit this device. Neighboring IDs are not admitted.
The read-only `python3 tools/print_boot_option.py --exact28a0` helper optionally
includes this exact ID; without that option its existing candidate set is
unchanged. Confirm the address locally rather than copying this example.
The same flag name also overlaps PR #10; coordinate that overlap before merging,
rather than stacking two implementations or treating the name as wider support.

## Observed hardware and transaction

One physical MECHREVO Yaoshi15Pro laptop, chip `0x197000a1`, 8 GiB RTX 4060
Laptop at `0000:01:00.0`, Linux `7.3.0-4-cachyos`, NVIDIA `595.71.05`.
Two successful experiment boots were observed, separated by a return to the
original stock boot. These are not verified cold boots with EC power removal.

Both transaction excerpts show marker `0x67b00001`, required after-payload
permissions passing, SEC2 halted, SS0 `0x88888888` / SS1 `0x8`, full effective
readout before and after FLR, and successful module handoff. Some permissions
restore after FLR; the claim is selector/effective-rate persistence, not that
all permissions stay unlocked. The stock driver and CUDA ran afterward.
The RM getter reported `fmla32`, `imla2` and `imla4` as half rate (`1`) on the
returned stock boot, then full (`0`) on the repeat unlocked boot; all nine
reported fields were zero on both unlocked boots.

The local experimental source had an extra outcome diagnostic. This minimal
contribution deliberately omits it and local gate/result scripts; evidence is
based on transaction readbacks, driver getter and numerical/benchmark output,
not that diagnostic. Host mocks validate dispatch and failure gates, not
additional physical machines or an independently retested minimal build.

## Bounded instruction measurements

Best of three repeats, 5000 iterations, same cubin SHA-256, GPU UUID (redacted
in the evidence), driver and launch settings. FP16 and TF32 rates below are
TFLOP/s; unsigned INT4/INT32 is TOP/s.

| Mode | Returned stock | First unlocked | Repeat unlocked |
|---|---:|---:|---:|
| FP16 / FP32 accumulation | 29.114 | 57.996 | 58.005 |
| TF32 / FP32 accumulation | 16.308 | 32.488 | 29.004 |
| unsigned INT4 / INT32 | 257.945 | 259.415 | 259.429 |

Each mode checked 270336 all-one output cells with zero mismatches in all
three captures. FP16 was approximately 1.99× stock on both unlocked boots;
TF32 was approximately 1.99× then 1.78×. The lower repeat TF32 rate has no
isolated cause; this short sample alone does not establish a regression or
instability. INT4 was approximately unchanged (1.006×). These are
register-resident instruction issue rates, not application or GEMM speedups.
No BF16 throughput measurement was made.

The desktop was active with no fixed clock/power policy. External RTX 5060 Ti
presence differed: it was absent in the first unlocked enumeration and present
on stock return and the repeat; no cause was established. Separate boots,
clock ramping and this topology difference limit performance conclusions.

## Numerical checks and limitations

On each unlocked boot, a small cuBLAS validator compared FP16/FP32 and
BF16/FP32 against CPU output at 256×256×256 (seed 1), 64×96×128 (seed 2), and
127×65×95 (seed 3). All six cases had zero failures and `max_abs=0` on each
boot. These limited dyadic-input cases are numerical checks only, not BF16
throughput, exhaustive accuracy validation or matched stock GEMM timing.

No NVRM Xid, GPU-fallen-off or RmInitAdapter match was found in the captured
kernel logs. That bounded observation is not a guarantee of no faults.
Stock rollback was observed with the module absent and half-rate getter
fields restored. There is no claim of long-term stability, suspend/resume,
runtime-D3, EC-power-removal behavior, other laptop firmware compatibility or
whole-application gains. Other owners should retain a known-good recovery
boot and follow the existing testing workflow before considering routine use.

[Selected sanitized evidence](evidence/ada28a0/README.md) contains only relevant
transaction excerpts and benchmark/numerical output, not full host journals.

# Selected RTX 4060 Laptop owner evidence

One physical `10de:28a0` laptop, two observed successful experiment boots with
an original/stock boot between them. See the [report](../../ada-28a0-report.md)
for interpretation and limits. The stock-return measurement is the baseline
used in the report, not an earlier stock sample.

- `stock-return.json`: selected instruction benchmark and RM getter output
  after returning to the original boot without `gpu_unlock` loaded.
- `unlocked-first.json`, `unlocked-repeat.json`: the same outputs on each
  experiment boot.
- `*-transaction.txt`: selected payload, permission, selector, FLR and handoff
  lines, in original order, not full kernel journals.
- `*-numerical.txt`: all six small cuBLAS numerical cases for each unlocked boot.

Sanitization: GPU UUIDs replaced consistently by `GPU-REDACTED`; host log
prefixes (timestamps and hostname) removed. No command lines, boot/root UUIDs,
private host paths, binaries, firmware or full journals are included. Field
names and measurement values in the selected JSON are otherwise preserved.
The local experimental build had an additional outcome diagnostic; this is
not part of the proposed module and is not used as evidence of authorization
or safety. Its capture files are intentionally omitted.

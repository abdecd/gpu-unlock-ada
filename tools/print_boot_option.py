#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Print exact, supported NVIDIA PCI boot options without changing the host."""
import argparse
import re
import subprocess
import sys


def candidates(lspci_output: str, exact28a0: bool = False) -> list[tuple[str, str]]:
    found = []
    ids = "2684|2685|2705|2805" + ("|28a0" if exact28a0 else "")
    for line in lspci_output.splitlines():
        address = re.match(r"^([0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7])\s", line)
        device = re.search(rf"\[10de:({ids})\]", line, re.I)
        if address and device:
            found.append((address.group(1).lower(), device.group(1).lower()))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exact28a0", action="store_true",
                        help="include experimental exact 10de:28a0 RTX 4060 Laptop only")
    args = parser.parse_args()
    try:
        result = subprocess.run(["lspci", "-Dnn"], check=True, capture_output=True,
                                text=True, timeout=10)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"Could not read PCI devices: {error}. Install pciutils and retry.", file=sys.stderr)
        return 1
    found = candidates(result.stdout, args.exact28a0)
    if not found:
        extra = " or experimental RTX 4060 Laptop (10de:28a0)" if args.exact28a0 else ""
        print("No supported RTX 4090 (10de:2684), experimental RTX 4090 D "
              "(10de:2685), experimental RTX 4070 Ti SUPER (10de:2705) or "
              f"experimental RTX 4060 Ti 16GB (10de:2805){extra} was found.",
              file=sys.stderr)
        return 2
    for address, device in found:
        options = f"gpu_unlock.targets={address}"
        label = {"2684": "RTX 4090",
                 "2685": "RTX 4090 D (experimental)",
                 "2705": "RTX 4070 Ti SUPER (experimental)",
                 "2805": "RTX 4060 Ti 16GB (experimental)",
                 "28a0": "RTX 4060 Laptop (experimental; one machine tested)"}[device]
        if device == "2685":
            options += " gpu_unlock.rtx4090d_experimental=1"
        if device == "2705":
            options += " gpu_unlock.ad103_experimental=1"
        if device == "2805":
            options += " gpu_unlock.ad106_experimental=1"
        if device == "28a0":
            options += " gpu_unlock.ad107_experimental=1"
        print(f"{label} at {address} [10de:{device}]:")
        print(options)
        print()
    if len(found) > 1:
        print("Choose one exact card for the first cold test; do not combine addresses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

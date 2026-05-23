#!/usr/bin/env python3
"""Rough-place footprints into functional layout groups.

Uses kicad-python when available to prove IPC connectivity, then updates the
board file coordinates directly.  This keeps the operation deterministic even
when KiCad's GUI IPC session is not exposing board-document handlers.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


PLACEMENT_MM: dict[str, tuple[float, float, float | None]] = {
    # Input connector + input ESD/protection.
    "J1": (174.00, 92.00, -90.0),
    "D1": (167.20, 86.80, None),
    "D2": (167.20, 89.60, None),
    "U1": (177.30, 98.00, None),
    # CAN transceiver, decoupling, series/control resistors, logic test pads.
    "U2": (184.00, 96.00, None),
    "C1": (181.00, 91.20, 180.0),
    "C2": (181.00, 100.80, 180.0),
    "R1": (190.20, 88.50, 180.0),
    "R2": (190.20, 90.80, 180.0),
    "R3": (190.20, 93.10, 180.0),
    "R4": (184.30, 103.50, 180.0),
    "TP1": (181.00, 86.00, 180.0),
    "TP2": (184.00, 86.00, 180.0),
    "TP3": (187.00, 86.00, 180.0),
    "TP4": (190.00, 86.00, 180.0),
    "TP5": (193.00, 86.00, 180.0),
    "TP6": (196.00, 86.00, 180.0),
    # Status LEDs with current limiting resistors and FETs.
    "D3": (167.40, 101.70, 180.0),
    "R5": (170.40, 101.70, 180.0),
    "D4": (167.40, 104.00, 180.0),
    "R6": (170.40, 104.00, 180.0),
    "D5": (167.40, 106.30, 180.0),
    "R7": (170.40, 106.30, 180.0),
    "Q1": (174.00, 105.60, -90.0),
    "D6": (167.40, 108.60, 180.0),
    "R8": (170.40, 108.60, 180.0),
    "Q2": (177.00, 108.60, -90.0),
    # CAN-side termination/filter/switch cluster.
    "SW1": (194.00, 98.50, 180.0),
    "R9": (190.00, 96.00, -90.0),
    "R10": (190.00, 102.00, -90.0),
    "C3": (190.00, 99.00, 180.0),
    "TP7": (186.50, 105.50, 180.0),
    "TP8": (186.50, 93.00, 180.0),
    # Output connectors + local CAN ESD.
    "J2": (204.00, 92.00, 90.0),
    "D8": (200.00, 96.00, 180.0),
    "J3": (204.00, 102.20, -90.0),
    "D7": (200.00, 100.00, 180.0),
}


FOOTPRINT_START = re.compile(r'^\t\(footprint "', re.MULTILINE)
REF_RE = re.compile(r'\(property "Reference" "([^"]+)"')
AT_RE = re.compile(r'^(\t\t\(at )([^)]+)(\)\s*)$', re.MULTILINE)


def footprint_spans(text: str) -> list[tuple[int, int]]:
    starts = [m.start() for m in FOOTPRINT_START.finditer(text)]
    spans: list[tuple[int, int]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else text.rfind("\n\t(embedded_fonts")
        if end == -1:
            raise RuntimeError("Could not find end of final footprint block")
        spans.append((start, end))
    return spans


def update_footprint_at(block: str, x: float, y: float, rotation: float | None) -> str:
    match = AT_RE.search(block)
    if not match:
        raise RuntimeError("Footprint missing top-level (at ...) line")

    old_parts = match.group(2).split()
    angle = rotation if rotation is not None else (float(old_parts[2]) if len(old_parts) > 2 else None)
    parts = [f"{x:.3f}".rstrip("0").rstrip("."), f"{y:.3f}".rstrip("0").rstrip(".")]
    if angle is not None:
        parts.append(f"{angle:.3f}".rstrip("0").rstrip("."))

    return block[: match.start(2)] + " ".join(parts) + block[match.end(2) :]


def maybe_probe_kicad() -> None:
    try:
        from kipy import KiCad

        kicad = KiCad(timeout_ms=750)
        version = kicad.get_version()
        print(f"kicad-python IPC: connected to KiCad {version}")
    except Exception as exc:
        print(f"kicad-python IPC: unavailable ({type(exc).__name__}: {exc})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("--skip-ipc-probe", action="store_true")
    args = parser.parse_args()

    if not args.skip_ipc_probe:
        maybe_probe_kicad()

    text = args.board.read_text()
    spans = footprint_spans(text)
    replacements: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    for start, end in spans:
        block = text[start:end]
        ref_match = REF_RE.search(block)
        if not ref_match:
            continue
        ref = ref_match.group(1)
        if ref not in PLACEMENT_MM:
            continue
        seen.add(ref)
        replacements.append((start, end, update_footprint_at(block, *PLACEMENT_MM[ref])))

    missing = sorted(set(PLACEMENT_MM) - seen)
    if missing:
        raise RuntimeError(f"Expected refs not found: {', '.join(missing)}")

    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]

    args.board.write_text(text)
    print(f"updated {len(replacements)} footprints in {args.board}")


if __name__ == "__main__":
    main()

"""Walk-sheet fileIDs that Unity 6000.6.6f1 kept after the editor was closed and opened again."""

from __future__ import annotations

import sys
from pathlib import Path

TRIAL = Path(__file__).resolve().parents[1] / "trial"
sys.path.insert(0, str(TRIAL))

import contract as C  # noqa: E402

GUID = "a11ce0000000000000000000000a0001"
KEPT = {
    "walk_0": 7022111581176118319,
    "walk_1": 7860131210666100081,
    "walk_2": 147476393292304522,
    "walk_3": -2871211120335695017,
}


def check_fileids() -> str:
    rects = [(name, index * 16, 0, 16, 32) for index, name in enumerate(KEPT)]
    first = C.unity_meta(rects, 32, GUID)
    second = C.unity_meta(rects, 32, GUID)
    if first != second:
        raise SystemExit("meta drift")
    if "spriteMode: 2" not in first:
        raise SystemExit("spriteMode")
    disk = (TRIAL / "sprite_sheet" / "hero_sheet.png.meta").read_text(encoding="utf-8")
    for name, internal in KEPT.items():
        sprite_id, got = C._sprite_identity(f"{GUID}:{name}")
        if got != internal or f"internalID: {internal}" not in first:
            raise SystemExit(name)
        if f"{name}: {internal}" not in first or f"213: {internal}" not in first:
            raise SystemExit(name)
        if not sprite_id.endswith("0800000000000000"):
            raise SystemExit(sprite_id)
        if f"name: {name}" not in disk or f"internalID: {internal}" not in disk:
            raise SystemExit("disk " + name)
    return str(len(KEPT))


def main() -> None:
    count = check_fileids()
    print(f"PASS fileid_reopen {count}")
    print("ALL_PASS")


if __name__ == "__main__":
    main()

"""Write the capability inventory pumllint's trace reads (one id per line, name after a tab),
so `pumllint trace --pattern 'CAP-\\d+' --requirements caps.txt --fail-on-uncovered` over the
converted diagram corpus reports which capabilities have no process diagram. Approved
capabilities only, unless --all.

    python tools/inventory.py > caps.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from register import ROOT, load_register  # noqa: E402


def inventory(reg: dict, include_all: bool = False) -> list[tuple[str, str]]:
    return sorted((nid, n["name"]) for nid, n in reg["nodes"].items()
                  if n["_taxonomy"] == "capabilities" and n.get("kind") in ("capability", "sub_capability")
                  and (include_all or n.get("state") == "approved"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    for nid, name in inventory(load_register(a.root), a.all):
        print(f"{nid}\t{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

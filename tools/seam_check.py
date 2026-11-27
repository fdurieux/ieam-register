"""The seam check (decision 0025): what pumllint and aris2puml read and write, held against the
register's contracts. Standard library only; it never imports pumllint or aris2puml, it calls their
command lines and reads aris2puml's source. Run by `.github/workflows/seam.yml` on a schedule; never
a required check, and a red run blocks nothing.

    python tools/seam_check.py --aris2puml ../aris2puml \\
        --pumllint release=.venv-release/bin/pumllint --pumllint main=.venv-main/bin/pumllint \\
        --pumllint floor=.venv-floor/bin/pumllint --aris2puml-bin .venv-aris/bin/aris2puml
    python tools/seam_check.py --aris2puml ../aris2puml --print-floor   # the pumllint aris2puml pins

1. The inventory: `tools/inventory.py --all`, read by each pumllint's `trace --requirements`, yields
   every id the inventory wrote, none dropped, none added, none warned about.
2. aris2puml's ids: (a) the footer pattern in its conventions agrees with the id contract
   (`<PREFIX>-<4+ digits>`); (b) a footer aris2puml writes for each register process id is read back
   by `trace` under those conventions; (c) its report script reads the register id from the attribute
   `metamodel/sources.toml` `[system.aris]` `register_id_attribute` names, on the function definition
   (decision 0022 §4), read statically from `aris/export_epc.js`.
3. The floor: the pumllint release aris2puml's `check` extra pins is installed, and check 1 holds at it.

Exit 0 when every check holds, 1 when one does not, 2 on a usage or set-up error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_register import ID_RE  # noqa: E402
from inventory import inventory  # noqa: E402
from register import ROOT, load_register  # noqa: E402

DIGITS = r"\d{4,}"                       # the id contract's digits, as ID_RE states them
CONVENTIONS = Path("tests/fixtures/conventions.toml")   # aris2puml README: "that guide's configuration"
REPORT_SCRIPT = Path("aris/export_epc.js")
EDGE_IDS = ("PROC-10000",)               # ids the contract allows and the register does not yet hold
SHORT_IDS = ("PROC-123",)                # not ids: fewer than four digits
DEFINITION_CALLS = {"ObjDef", "ObjDefs", "ObjDefList", "SuperiorObjDefs"}
MODEL_CALLS = {"AssignedModels", "getSelectedModels", "Model", "ModelList"}
TIMEOUT = 300


class SetupError(Exception):
    pass


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    except (FileNotFoundError, PermissionError) as e:
        raise SetupError(f"cannot run {cmd[0]}: {e}") from None


def version_of(binary: str) -> str:
    p = run([binary, "--version"])
    return (p.stdout or p.stderr).strip() or f"exit {p.returncode}"


def git_head(path: Path) -> str:
    p = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else "unknown"


def result(name: str, ok: bool, lines: list[str]) -> dict:
    return {"check": name, "ok": ok, "lines": lines}


# -- check 1: the inventory, read by trace ---------------------------------------------------------

def read_trace(stdout: str, stderr: str, rc: int, expected: list[str]) -> tuple[bool, list[str]]:
    """Compare a `trace -f json` report with the ids written; True when none is dropped or added."""
    try:
        doc = json.loads(stdout)
        rows = doc["requirements"]
        read = [r["id"] for r in rows]
    except (ValueError, KeyError, TypeError):
        return False, [f"trace wrote no readable JSON (exit {rc}): {(stderr or stdout).strip()[:300]}"]
    dropped = [i for i in expected if i not in read]
    added = [i for i in read if i not in expected]
    uncovered = [r["id"] for r in rows if not r.get("covered") and r["id"] in expected]
    unknown = sorted({u.get("id", "?") for u in doc.get("unknownReferences", [])})
    warnings = [ln for ln in stderr.splitlines() if ln.startswith("warning:")]
    ok = rc == 0 and not (dropped or added or uncovered or unknown or warnings)
    lines = [f"{len(read) - len(added)} of {len(expected)} ids read, {len(dropped)} dropped, {len(added)} added"
             + (f", exit {rc}" if rc else "")]
    for label, ids in (("dropped", dropped), ("added", added), ("not read from the probe footer", uncovered),
                       ("unknown references", unknown)):
        if ids:
            lines.append(f"{label}: {', '.join(ids)}")
    lines += warnings
    return ok, lines


def check_inventory(label: str, binary: str, root: Path, work: Path) -> dict:
    inv = work / f"caps-{label}.txt"
    p = run([sys.executable, str(root / "tools" / "inventory.py"), "--all", "--root", str(root)])
    if p.returncode:
        raise SetupError(f"tools/inventory.py --all failed: {p.stderr.strip()}")
    inv.write_text(p.stdout, encoding="utf-8")
    expected = [nid for nid, _ in inventory(load_register(root), include_all=True)]
    d = work / f"probe-{label}"
    d.mkdir()
    (d / "probe.puml").write_text("@startuml probe\ntitle probe\nfooter " + " ".join(expected)
                                  + "\nstart\n:Probe;\nstop\n@enduml\n", encoding="utf-8")
    t = run([binary, "trace", str(d), "--pattern", f"CAP-{DIGITS}", "--requirements", str(inv), "-f", "json"])
    ok, lines = read_trace(t.stdout, t.stderr, t.returncode, expected)
    return result(f"1 {label}", ok, [f"{version_of(binary)}: " + lines[0]] + lines[1:])


def outside_inventory(root: Path) -> str:
    reg = load_register(root)
    inv = {nid for nid, _ in inventory(reg, include_all=True)}
    rest = sorted((nid, n.get("kind", "?")) for nid, n in reg["nodes"].items()
                  if nid.startswith("CAP-") and nid not in inv)
    if not rest:
        return "every CAP node is in the inventory"
    return (f"{len(inv)} of {len(inv) + len(rest)} CAP nodes in the inventory; outside it by kind: "
            + ", ".join(f"{nid} ({kind})" for nid, kind in rest))


# -- check 2: aris2puml's ids ----------------------------------------------------------------------

def conventions_pattern(aris: Path) -> str:
    path = aris / CONVENTIONS
    if not path.exists():
        raise SetupError(f"{CONVENTIONS} not found in {aris}")
    rules = tomllib.loads(path.read_text(encoding="utf-8")).get("rules", {})
    raw = rules.get("GEN007", rules.get("requirement-link"))
    pattern = raw.get("pattern") if isinstance(raw, dict) else None
    if not isinstance(pattern, str):
        raise SetupError(f"{CONVENTIONS} sets no requirement-link pattern")
    return pattern


def probe_pattern(pattern: str, ids: list[str]) -> tuple[bool, list[str]]:
    """Read `ARIS process <id>` with the pattern as trace does (finditer, group 0)."""
    rx = re.compile(pattern)
    wrong, short = [], []
    for i in list(ids) + list(EDGE_IDS):
        got = [m.group(0) for m in rx.finditer(f"ARIS process {i}")]
        if got != [i]:
            wrong.append(f"{i} read as {', '.join(got) or 'nothing'}")
    for i in SHORT_IDS:
        got = [m.group(0) for m in rx.finditer(f"ARIS process {i}")]
        if got:
            short.append(f"{i} (not an id) read as {', '.join(got)}")
    whole = sum(1 for i in ids if [m.group(0) for m in rx.finditer(f"ARIS process {i}")] == [i])
    lines = [f"{whole} of {len(ids)} register ids read whole; contract edge {', '.join(EDGE_IDS)}"]
    lines += wrong + short
    if wrong or short:
        lines.append(f"the contract reads PROC-{DIGITS}")
    return not (wrong or short), lines


def probe_document(ids: list[str]) -> dict:
    procs = []
    for n, pid in enumerate(ids):
        ref = ids[(n + 1) % len(ids)]
        procs.append({"version": 1, "process": {"id": pid, "name": f"Probe {n + 1}", "owner": "Seam"},
                      "lanes": [],
                      "nodes": [{"id": "e0", "kind": "event", "name": "Probe started"},
                                {"id": "f1", "kind": "function", "name": "Check probe"},
                                {"id": "p1", "kind": "interface", "name": "Hand over", "ref": ref},
                                {"id": "e1", "kind": "event", "name": "Probe ended"}],
                      "edges": [{"from": "e0", "to": "f1"}, {"from": "f1", "to": "p1"}, {"from": "p1", "to": "e1"}]})
    return {"version": 1, "processes": procs}


def check_footer(aris: Path, aris_bin: str, pumllint_bin: str, ids: list[str], work: Path) -> dict:
    src = work / "probe-aris.json"
    src.write_text(json.dumps(probe_document(ids), indent=1), encoding="utf-8")
    out = work / "probe-aris-out"
    c = run([aris_bin, str(src), "-o", str(out)])
    if c.returncode:
        return result("2b footer", False, [f"aris2puml exit {c.returncode}: {(c.stderr or c.stdout).strip()[:300]}"])
    inv = work / "procs.txt"
    inv.write_text("\n".join(ids) + "\n", encoding="utf-8")
    t = run([pumllint_bin, "trace", str(out), "-c", str(aris / CONVENTIONS), "--requirements", str(inv), "-f", "json"])
    ok, lines = read_trace(t.stdout, t.stderr, t.returncode, ids)
    return result("2b footer", ok, ["footer `ARIS process <id> — interfaces: <id>` for each register process id, "
                                     f"read by {version_of(pumllint_bin)}: " + lines[0]] + lines[1:])


def _last_call(expr: str) -> str | None:
    calls = re.findall(r"\.(\w+)\s*\(", expr)
    return calls[-1] if calls else None


def classify(expr: str, src: str, depth: int = 0) -> str:
    """'definition', 'model', 'occurrence' or 'unclassified', for a JS expression in the report script."""
    expr = expr.strip()
    last = _last_call(expr)
    if last in DEFINITION_CALLS:
        return "definition"
    if last in MODEL_CALLS:
        return "model"
    if last in ("ObjOccList", "ObjOcc"):
        return "occurrence"
    m = re.match(r"[A-Za-z_$][\w$]*", expr)
    if not m or depth > 4 or last is not None:
        return "unclassified"
    base = m.group(0)
    for b in re.finditer(rf"(?<![\w$.]){re.escape(base)}\s*=(?!=)\s*([^,;\n]+)", src):
        kind = classify(b.group(1), src, depth + 1)
        if kind != "unclassified":
            return kind
    for f in re.finditer(r"function\s+\w*\s*\(([^)]*)\)", src):
        if base in [p.strip() for p in f.group(1).split(",")]:
            low = base.lower()
            return "model" if "model" in low else "definition" if "def" in low else "unclassified"
    return "unclassified"


ATTR_RE = re.compile(r"attr\(\s*([^,]+?)\s*,\s*((?:Constants\.)?[A-Za-z_$][\w$]*)\s*\)")
GUID_RE = re.compile(r"\|\|\s*([^|;\n]+?)\.GUID\(\s*\)")


def function_body(name: str, src: str) -> str | None:
    """The body of `function name(...) { ... }` in the script, braces matched."""
    m = re.search(rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", src)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(src) and depth:
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        i += 1
    return src[m.end():i - 1]


def resolve_attribute(token: str, src: str) -> str | None:
    """`Constants.AT_ID`, or a name the script binds to one (`var REGISTER_ID_ATTRIBUTE = Constants.AT_ID`)."""
    if token.startswith("Constants."):
        return token[len("Constants."):]
    m = re.search(rf"(?<![\w$.]){re.escape(token)}\s*=(?!=)\s*Constants\.(\w+)", src)
    return m.group(1) if m else None


def read_id_expression(label: str, expr: str | None, src: str, attribute: str, expected_holder: str) -> tuple[bool, str]:
    if expr is None:
        return False, f"{label}: not found in {REPORT_SCRIPT}; read it by hand"
    shown, notes = f"`{expr}`", []
    if not ATTR_RE.search(expr):
        # One level of helper: `id: processId(model)` read through the function's body.
        call = re.fullmatch(r"\s*([A-Za-z_$][\w$]*)\s*\(.*\)\s*", expr)
        body = function_body(call.group(1), src) if call else None
        inner = re.search(r"attr\(.*?\.GUID\(\s*\)", body) if body else None
        if not inner:
            return False, f"{label}: `{expr}` reads no attribute directly; read it by hand"
        shown = f"`{expr}`, through `{inner.group(0)}` in {call.group(1)}()"
        last = [r.group(1) for r in re.finditer(r"\breturn\s+([^;\n]+?)\.GUID\(\s*\)\s*;", body)]
        for receiver in dict.fromkeys(last):
            kind = classify(receiver, src)
            if kind != "definition":
                notes.append(f"last resort `return {receiver}.GUID()` ({last.count(receiver)}x), {kind_phrase(kind)}"
                             + (", with a warning" if "warnings.push" in body else "")
                             + ", where no single function definition is reached; decision 0022 §4 names no target there")
        expr = inner.group(0)
    a = ATTR_RE.search(expr)
    g = GUID_RE.search(expr)
    holder, token = a.group(1), a.group(2)
    attr_name = resolve_attribute(token, src)
    kind = classify(holder, src)
    fallback = classify(g.group(1), src) if g else None
    ok = attr_name == attribute and kind == "definition" and fallback == "definition"
    named = attr_name if token.startswith("Constants.") else f"{token} = {attr_name or 'unresolved'}"
    agree = "agrees with" if attr_name == attribute else "differs from"
    said = (f"{label}: {shown} reads {named} ({agree} register_id_attribute {attribute}) on `{holder}`, "
            f"{kind_phrase(kind)}; GUID fallback "
            + (f"on `{g.group(1)}`, {kind_phrase(fallback)}" if g else "absent"))
    if notes:
        said += "; " + "; ".join(notes)
    if not ok:
        said += f". Decision 0022 §4: {expected_holder}, else that definition's GUID"
    return ok, said


def kind_phrase(kind: str | None) -> str:
    return {"definition": "a function definition", "model": "a model", "occurrence": "an occurrence"}.get(
        kind or "", "unclassified (read it by hand)")


def check_report_script(src: str, attribute: str) -> tuple[bool, list[str]]:
    proc = re.search(r"process\s*:\s*\{\s*id\s*:\s*([^\n]+?),?\s*$", src, re.M)
    ref = re.search(r"\bnode\.ref\s*=\s*([^;\n]+);", src)
    ok1, l1 = read_id_expression("process id", proc.group(1) if proc else None, src, attribute,
                                 "the attribute of the function definition the EPC is assigned to")
    ok2, l2 = read_id_expression("interface ref", ref.group(1) if ref else None, src, attribute,
                                 "the attribute of the interface occurrence's own definition")
    return ok1 and ok2, [l1, l2]


def register_id_attribute(root: Path) -> str:
    aris = load_register(root)["sources"].get("system", {}).get("aris", {})
    attribute = aris.get("register_id_attribute")
    if not isinstance(attribute, str):
        raise SetupError("metamodel/sources.toml [system.aris] names no register_id_attribute")
    return attribute


# -- check 3: the floor ----------------------------------------------------------------------------

def read_floor(pyproject_text: str) -> tuple[str, str]:
    """(the requirement as written, the floor version) from the `check` extra's pumllint pin."""
    extras = tomllib.loads(pyproject_text).get("project", {}).get("optional-dependencies", {})
    for req in extras.get("check", []):
        m = re.match(r"\s*pumllint\s*(?:\[[^\]]*\])?\s*(.*)$", req)
        if m:
            floor = re.search(r">=\s*([0-9][0-9.]*)", m.group(1))
            if not floor:
                raise SetupError(f"aris2puml's check extra pins {req!r}, with no >= floor")
            return req.strip(), floor.group(1)
    raise SetupError("aris2puml's pyproject.toml has no pumllint in [project.optional-dependencies] check")


def same_release(installed: str, floor: str) -> bool:
    m = re.search(r"(\d+(?:\.\d+)*)", installed)
    if not m:
        return False
    a = [int(x) for x in m.group(1).split(".")]
    b = [int(x) for x in floor.split(".")]
    n = max(len(a), len(b))
    return a + [0] * (n - len(a)) == b + [0] * (n - len(b))


# -- the run ---------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aris2puml", type=Path, required=True, help="a checkout of aris2puml (its source is read)")
    ap.add_argument("--pumllint", action="append", default=[], metavar="LABEL=BIN",
                    help="a pumllint command line; labels release, main and floor are the three the checks name")
    ap.add_argument("--aris2puml-bin", default="aris2puml", help="the aris2puml command line")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--print-floor", action="store_true", help="print the pumllint floor aris2puml pins, and exit")
    ap.add_argument("--json", type=Path, help="also write the results as JSON")
    a = ap.parse_args(argv)
    try:
        req, floor = read_floor((a.aris2puml / "pyproject.toml").read_text(encoding="utf-8"))
        if a.print_floor:
            print(floor)
            return 0
        bins = {}
        for spec in a.pumllint:
            label, sep, binary = spec.partition("=")
            if not sep or not binary:
                raise SetupError(f"--pumllint takes LABEL=BIN, not {spec!r}")
            bins[label] = binary
        if not bins:
            raise SetupError("no --pumllint given")
        return report(a, bins, req, floor)
    except (SetupError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def report(a, bins: dict, req: str, floor: str) -> int:
    root, aris = a.root.resolve(), a.aris2puml.resolve()
    results = []
    out = [f"seam check: register at {git_head(root)}, aris2puml at {git_head(aris)}"]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        out.append("check 1: tools/inventory.py --all, read by pumllint trace --requirements, pattern "
                   f"CAP-{DIGITS}")
        out.append(f"  {outside_inventory(root)}")
        for label, binary in bins.items():
            results.append(check_inventory(label, binary, root, work))
            out += _render(results[-1])

        out.append("check 2: aris2puml's ids, against the id contract and decision 0022")
        ids = sorted(n for n in load_register(root)["nodes"] if n.startswith("PROC-") and ID_RE.match(n))
        pattern = conventions_pattern(aris)
        ok, lines = probe_pattern(pattern, ids)
        results.append(result(f"2a pattern `{pattern}` ({CONVENTIONS})", ok, lines))
        out += _render(results[-1])
        reader = bins.get("release") or next(iter(bins.values()))
        results.append(check_footer(aris, a.aris2puml_bin, reader, ids, work))
        out += _render(results[-1])
        attribute = register_id_attribute(root)
        ok, lines = check_report_script((aris / REPORT_SCRIPT).read_text(encoding="utf-8"), attribute)
        results.append(result(f"2c report script {REPORT_SCRIPT}", ok, lines))
        out += _render(results[-1])

        out.append(f"check 3: the floor aris2puml pins, `{req}` (pyproject.toml, check extra)")
        one = next((r for r in results if r["check"] == "1 floor"), None)
        if one is None:
            results.append(result("3 floor", False, ["not run: no --pumllint floor=BIN given"]))
        else:
            installed = version_of(bins["floor"])
            at_floor = same_release(installed, floor)
            results.append(result("3 floor", at_floor and one["ok"], [
                f"installed {installed}, {'the floor' if at_floor else f'not the floor {floor}'}; check 1 at it "
                + ("holds" if one["ok"] else "fails")]))
        out += _render(results[-1])

    groups = {}
    for r in results:
        groups.setdefault(r["check"][0], []).append(r["ok"])
    red = [g for g, oks in groups.items() if not all(oks)]
    out.append(f"result: {len(groups) - len(red)} of {len(groups)} checks hold"
               + (f"; red: {', '.join(red)}" if red else ""))
    print("\n".join(out))
    if a.json:
        a.json.write_text(json.dumps({"results": results, "red": red}, indent=2) + "\n", encoding="utf-8")
    return 1 if red else 0


def _render(r: dict) -> list[str]:
    head = f"  {r['check']}  {'PASS' if r['ok'] else 'FAIL'}"
    return [head] + [f"      {ln}" for ln in r["lines"]]


if __name__ == "__main__":
    sys.exit(main())

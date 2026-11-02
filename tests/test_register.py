"""Standard-library tests: the register passes its own checks, and each check fires on a broken copy."""
from __future__ import annotations

import datetime as dt
import shutil
import sys
import tempfile
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_register  # noqa: E402
import impact  # noqa: E402
import inventory  # noqa: E402
import reconcile  # noqa: E402
from register import load_register, load_toml  # noqa: E402

TODAY = dt.date(2026, 10, 30)


def copy_register() -> Path:
    d = Path(tempfile.mkdtemp()) / "reg"
    shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns(".git", "__pycache__", "tests", "reports"))
    return d


class RegisterChecks(unittest.TestCase):
    def test_the_register_is_clean(self):
        f, summary = check_register.run(ROOT, today=TODAY)
        self.assertEqual([i for i in f.items if i["level"] == "error"], [], f.items)
        self.assertEqual(summary["nodes"], 56)   # 27 of the CargoQuote slice, 29 of the J-F slice (decisions 0005 and 0006)
        self.assertEqual(summary["C1"]["uncovered"], [])
        self.assertEqual(summary["C1"]["excepted"], 1)   # EXC-0001 on the touchpoint
        self.assertEqual(summary["C2"]["uncovered"], [])
        self.assertEqual(summary["C3"]["uncovered"], [])

    def test_dangling_link_is_an_error(self):
        d = copy_register()
        p = d / "relationships" / "requires.toml"
        p.write_text(p.read_text().replace('target = "CAP-0002"', 'target = "CAP-9999"'))
        f, _ = check_register.run(d, today=TODAY)
        self.assertTrue(any(i["check"] == "dangling" and "CAP-9999" in i["message"] for i in f.items))

    def test_deprecating_a_node_fails_its_approved_links(self):
        d = copy_register()
        p = d / "capabilities" / "CAP-0002.toml"
        p.write_text(p.read_text().replace('state = "approved"', 'state = "deprecated"'))
        f, _ = check_register.run(d, today=TODAY)
        hits = [i for i in f.items if i["check"] == "lifecycle" and "CAP-0002" in i["message"]]
        self.assertGreaterEqual(len(hits), 2)  # requires and realizes links reference it

    def test_cycle_and_wrong_parent_kind(self):
        d = copy_register()
        p = d / "capabilities" / "CAP-0001.toml"
        p.write_text(p.read_text().replace('kind = "capability_domain"', 'kind = "capability_domain"\nparent = "CAP-0002"'))
        f, _ = check_register.run(d, today=TODAY)
        self.assertTrue(any(i["check"] == "hierarchy" and "cycle" in i["message"] for i in f.items))

    def test_approval_without_record_fails(self):
        d = copy_register()
        p = d / "products" / "PRD-0002.toml"
        p.write_text(p.read_text().replace('record = "decisions/0002-pilot-slice-cargoquote.md"', 'record = "decisions/9999-missing.md"'))
        f, _ = check_register.run(d, today=TODAY)
        self.assertTrue(any(i["check"] == "approval" and "does not exist" in i["message"] for i in f.items))

    def test_glossary_forbids_synonyms(self):
        d = copy_register()
        p = d / "products" / "PRD-0002.toml"
        p.write_text(p.read_text().replace('name = "CargoQuote instant quote"', 'name = "CargoQuote instant quote, golden source"'))
        f, _ = check_register.run(d, today=TODAY)
        self.assertTrue(any(i["check"] == "glossary" for i in f.items))

    def test_expired_exception_stops_excusing(self):
        d = copy_register()
        f, summary = check_register.run(d, today=dt.date(2027, 3, 1))
        self.assertIn("JRN-0004", summary["C1"]["uncovered"])
        self.assertTrue(any(i["check"] == "exceptions" and "expired" in i["message"] for i in f.items))

    def test_coverage_c2_fires_without_a_realizing_process(self):
        d = copy_register()
        p = d / "relationships" / "realizes.toml"
        p.write_text(p.read_text().replace('target = "CAP-0002"', 'target = "CAP-0003"'))
        f, summary = check_register.run(d, today=TODAY)
        self.assertIn("CAP-0002", summary["C2"]["uncovered"])

    def test_impact_reaches_the_product_and_the_journey(self):
        reg = load_register(ROOT)
        reached = {e["to"] for e in impact.walk(reg, "APP-0002")}
        self.assertIn("PRD-0002", reached)
        self.assertIn("JRN-0002", reached)

    def test_inventory_lists_approved_capabilities(self):
        reg = load_register(ROOT)
        ids = [i for i, _ in inventory.inventory(reg)]
        self.assertEqual(ids, ["CAP-0002", "CAP-0003", "CAP-0004", "CAP-0007", "CAP-0008"])
        self.assertIn("CAP-0005", [i for i, _ in inventory.inventory(reg, include_all=True)])

    def test_reconcile_against_no_previous(self):
        d = copy_register()
        r = reconcile.reconcile(d / "exports" / "kit" / "2026-10-30", d)
        self.assertEqual(r["files"]["deleted"], [])
        self.assertEqual(len(r["files"]["added"]), 10)
        self.assertEqual(r["stale_nodes"], [])
        self.assertTrue((d / "exports" / "kit" / "2026-10-30" / "RECONCILE.json").exists())


if __name__ == "__main__":
    unittest.main()


class SecondSubject(unittest.TestCase):
    """The J-F data-load slice (decision 0005): its own source system and export, ids continuing
    the register's sequences, and the impact walk crossing it as it crosses CargoQuote's."""

    def test_the_slice_has_its_source_its_export_and_its_links(self):
        reg = load_register(ROOT)
        self.assertIn("jef_kit", reg["sources"]["system"])
        jef = {nid: n for nid, n in reg["nodes"].items() if (n.get("source") or {}).get("system") == "jef_kit"}
        self.assertEqual(len(jef), 29)   # 24 of decision 0005, one of them deprecated, and 5 of decision 0006
        self.assertTrue(all(n["state"] in ("approved", "deprecated") and re.search(r"000[56]-", n["approval"]["record"]) for n in jef.values()))
        self.assertEqual([nid for nid, n in jef.items() if n["state"] == "deprecated"], ["JRN-0008"])
        self.assertTrue(all(n["source"]["export"] == "exports/jef_kit/2026-11-01" for n in jef.values()))
        man = load_toml(ROOT / "exports" / "jef_kit" / "2026-11-01" / "MANIFEST.toml")
        self.assertEqual(len(man["files"]), 50)
        self.assertTrue(all(n["source"]["kit_path"] in man["files"] for n in jef.values()), "every node's kit path is in the export")
        links = [ln for rel in reg["relationships"].values() for ln in rel["links"] if ln.get("owner") == "ORG-0003"]
        self.assertEqual(len(links), 37)   # 28 of decision 0005, four of them deprecated, and 9 of decision 0006
        for ln in links:
            self.assertIn("exports/jef_kit/2026-11-01/MANIFEST.toml", ln["evidence"])
            self.assertTrue(any(e.startswith("jef_kit:") for e in ln["evidence"]), ln["id"])

    def test_impact_walks_the_slice(self):
        reg = load_register(ROOT)
        edges = impact.walk(reg, "APP-0005")
        reached = impact.reached(edges)
        self.assertIn("PROC-0006", reached)
        self.assertIn("PRD-0004", reached)
        self.assertIn("JRN-0011", reached)   # the upload step
        self.assertIn("PRD-0005", reached)
        # decision 0007: a withdrawn edge is reported and marked, not followed, not counted
        self.assertNotIn("JRN-0008", reached, "the deprecated step is not reached")
        withdrawn = {(e["to"], e["state"]) for e in edges if not e["live"]}
        self.assertIn(("JRN-0008", "deprecated"), withdrawn)
        self.assertIn(("PRD-0004", "deprecated"), withdrawn)   # REL-05002; PRD-0004 is still reached through PROC-0010
        self.assertTrue(all(e["state"] == "approved" for e in edges if e["live"]))

    def test_the_three_citations_of_decision_0007(self):
        reg = load_register(ROOT)
        by_id = {ln["id"]: ln for rel in reg["relationships"].values() for ln in rel["links"]}
        self.assertIn("jef_kit:requirements.json#JDL-058", by_id["REL-06008"]["evidence"])
        self.assertNotIn("jef_kit:requirements.json#JDL-072", by_id["REL-06008"]["evidence"])
        self.assertIn("jef_kit:requirements.json#JDL-108", by_id["REL-07007"]["evidence"])
        self.assertNotIn("jef_kit:requirements.json#JDL-113", by_id["REL-07007"]["evidence"])
        self.assertIn("jef_kit:requirements.json#JDL-156", by_id["REL-03005"]["evidence"])
        self.assertNotIn("jef_kit:requirements.json#JDL-150", by_id["REL-03005"]["evidence"])
        for lid in ("REL-06008", "REL-07007", "REL-03005"):
            self.assertTrue(by_id[lid]["approval"]["record"].endswith("0007-three-citations-re-read-and-the-walk-follows-approved-links.md"), lid)

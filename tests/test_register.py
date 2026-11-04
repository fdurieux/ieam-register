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
        self.assertEqual(summary["nodes"], 57)   # 28 of the CargoQuote slice (ORG-0004 by decision 0011), 29 of the J-F slice (decisions 0005 and 0006)
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

    def test_elicited_knowledge_needs_a_handle_a_date_a_record_and_a_shorter_review(self):
        """Decision 0008: a link resting on what a person said names an opaque handle, the date and
        the record of the answer, and is due for review within six months of that date."""
        d = copy_register()
        p = d / "relationships" / "realizes.toml"
        text = p.read_text()
        bad = text.replace('id = "REL-04001"', 'id = "REL-04001"\nelicited = { from = "Jane Doe", on = 2026-10-01, record = "captures/missing.toml" }', 1)
        p.write_text(bad)
        f, _ = check_register.run(d, today=TODAY)
        msgs = [i["message"] for i in f.items if i["check"] == "elicited"]
        self.assertTrue(any("not an opaque handle" in m for m in msgs), msgs)
        self.assertTrue(any("captures/missing.toml does not exist" in m for m in msgs), msgs)
        self.assertTrue(any("later than 2027-04-01" in m for m in msgs), msgs)
        good = text.replace('id = "REL-04001"', 'id = "REL-04001"\nelicited = { from = "employee-1", on = 2026-11-02, record = "decisions/0008-knowledge-a-person-gave.md" }', 1)
        p.write_text(good)
        f, _ = check_register.run(d, today=dt.date(2026, 11, 3))
        self.assertEqual([i for i in f.items if i["check"] == "elicited"], [])
        p.write_text(text.replace('id = "REL-04001"', 'id = "REL-04001"\nelicited = { from = "employee-1", on = 2026-11-02 }', 1))
        f, _ = check_register.run(d, today=dt.date(2026, 11, 3))
        self.assertTrue(any(i["check"] == "elicited" and "lacks record" in i["message"] for i in f.items))

    def test_handles_are_issued_and_a_capture_is_cited_by_its_id(self):
        """Decision 0009: from must be an issued handle, issued by the day the knowledge was given and
        not withdrawn; a record outside the register is capture:<id>; the list never holds a name."""
        d = copy_register()
        p = d / "relationships" / "realizes.toml"
        text = p.read_text()
        def run(el, today=dt.date(2026, 11, 3)):
            p.write_text(text.replace('id = "REL-04001"', 'id = "REL-04001"\nelicited = ' + el, 1))
            f, _ = check_register.run(d, today=today)
            return [i["message"] for i in f.items if i["check"] in ("elicited", "handles")]
        self.assertEqual(run('{ from = "employee-1", on = 2026-11-02, record = "capture:2026-11-02-ORG-0002-employee-1" }'), [])
        self.assertTrue(any("not an issued handle" in m for m in run('{ from = "john-doe", on = 2026-11-02, record = "capture:x" }')))
        self.assertTrue(any("not yet issued" in m for m in run('{ from = "employee-1", on = 2026-11-01, record = "capture:x" }')))
        self.assertTrue(any("cited as capture:<id>" in m for m in run('{ from = "employee-1", on = 2026-11-02, record = "instance:subjects/x.toml" }')))
        h = d / "people" / "handles.toml"
        h.write_text(h.read_text() + '\n[[handle]]\nhandle = "employee-9"\nname = "John Doe"\nunit = "ORG-0002"\nroles = ["rules"]\nissued = 2026-11-02\n')
        msgs = run('{ from = "employee-1", on = 2026-11-02, record = "capture:x" }')
        self.assertTrue(any("never a name" in m for m in msgs) and any("roles ['rules'] unknown" in m for m in msgs), msgs)

    def test_the_walk_starts_from_every_kind_something_rests_on(self):
        """Decision 0010: from a capability, an information entity, a product or a journey step the
        walk reaches what rests on it; only nodes with no links of their own (domains, portfolios)
        reach nothing; and direction keeps the answer specific: starts do not collapse to one set."""
        reg = load_register(ROOT)
        kinds = {"capability_domain", "capability", "sub_capability", "business_entity", "logical_entity",
                 "information_domain", "portfolio", "family", "product", "variant", "step", "touchpoint"}
        zero = sorted(nid for nid, n in reg["nodes"].items()
                      if n.get("state") == "approved" and n["kind"] in kinds - {"touchpoint"}
                      and not impact.reached(impact.walk(reg, nid)))
        self.assertEqual({reg["nodes"][z]["kind"] for z in zero}, {"capability_domain", "information_domain", "portfolio"}, zero)
        self.assertEqual(len(zero), 6)
        ent = impact.reached(impact.walk(reg, "ENT-0003"))
        self.assertIn("APP-0002", ent)            # manages, inverse: the application that manages the entity
        self.assertIn("PROC-0002", ent)           # crud, inverse: a process that reads or writes it
        self.assertEqual(impact.reached(impact.walk(reg, "CAP-0002")), {"PRD-0002", "PROC-0001", "JRN-0001"})
        self.assertIn("PROC-0004", impact.reached(impact.walk(reg, "JRN-0003")))   # is_supported_by, forward
        sets = {frozenset(impact.reached(impact.walk(reg, s))) for s in ("CAP-0002", "ENT-0003", "PRD-0002", "JRN-0003", "APP-0002")}
        self.assertGreaterEqual(len(sets), 4, "starts answer their own question; walking every link both ways would give one set")
        # owns and maps_to are never walk edges
        self.assertNotIn("owns", {r for spec in impact.FORWARD.values() for r, _ in spec})
        self.assertNotIn("maps_to", {r for spec in impact.FORWARD.values() for r, _ in spec})

    def test_the_realiser_walk_is_a_second_named_walk(self):
        """Decision 0012: from a capability, the processes that realise it and the
        applications that support them; the dependants walk stays the default and unchanged, and the
        two walks never meet on a capability of either slice."""
        reg = load_register(ROOT)
        self.assertEqual(impact.REALISERS, {"capabilities": [("realizes", False)], "processes": [("supports", False)]})
        self.assertIs(impact.WALKS["dependants"], impact.FORWARD)
        realisers = {c: impact.reached(impact.walk(reg, c, impact.REALISERS)) for c in
                     ("CAP-0002", "CAP-0003", "CAP-0004", "CAP-0007", "CAP-0008")}
        self.assertEqual(realisers, {"CAP-0002": {"PROC-0004", "APP-0003"}, "CAP-0003": {"PROC-0003", "APP-0004"},
                                     "CAP-0004": {"PROC-0002", "APP-0002"}, "CAP-0007": {"PROC-0007", "APP-0006", "APP-0008"},
                                     "CAP-0008": {"PROC-0008", "APP-0007"}})
        for c, got in realisers.items():
            self.assertFalse(got & impact.reached(impact.walk(reg, c)), c)
        # the three CargoQuote capabilities share one dependants answer; the realiser walk tells them apart
        self.assertEqual(len({frozenset(impact.reached(impact.walk(reg, c))) for c in ("CAP-0002", "CAP-0003", "CAP-0004")}), 1)
        self.assertEqual(len({frozenset(realisers[c]) for c in ("CAP-0002", "CAP-0003", "CAP-0004")}), 3)
        # decision 0007's rule holds: CAP-0005's only realizes link is proposed, reported and not followed
        edges = impact.walk(reg, "CAP-0005", impact.REALISERS)
        self.assertEqual([(e["to"], e["live"]) for e in edges], [("PROC-0005", False)])
        self.assertEqual(impact.walk(reg, "CAP-0001", impact.REALISERS), [])   # a domain: parent is not descended
        self.assertFalse({r for spec in impact.REALISERS.values() for r, _ in spec} & {"owns", "maps_to"})

    def test_the_walk_descends_parent_on_request(self):
        """Decision 0014: --children walks from the start and from every approved descendant, each by
        its own row; others are reported withdrawn and not walked; the union excludes the start and its
        descendants; off by default, walk() unchanged."""
        reg = load_register(ROOT)
        self.assertEqual(impact.walk(reg, "CAP-0001"), [])   # the default: parent is not descended
        parents = sorted({n["parent"] for n in reg["nodes"].values() if n.get("parent")})
        self.assertEqual(len(parents), 14)
        got = {p: impact.walk_children(reg, p) for p in parents}
        self.assertEqual({p: len(g["reached"]) for p, g in got.items()},
                         {"CAP-0001": 3, "CAP-0006": 8, "ENT-0001": 11, "ENT-0006": 16, "PRD-0001": 2, "PRD-0003": 6,
                          "APP-0001": 11, "APP-0005": 15, "PROC-0001": 7, "PROC-0006": 11, "JRN-0001": 6, "JRN-0005": 8,
                          "JRN-0002": 5, "PROC-0007": 10})
        self.assertTrue(all(g["reached"] for g in got.values()), "every parent reaches something with the option")
        self.assertEqual(got["CAP-0001"]["reached"], {"PRD-0002", "PROC-0001", "JRN-0001"})
        withdrawn = {d["id"] for g in got.values() for d in g["descendants"] if not d["live"]}
        self.assertEqual(withdrawn, {"CAP-0005", "ENT-0005", "PROC-0005", "JRN-0008"})
        for p, g in got.items():
            self.assertFalse({e["from"] for e in g["edges"]} & withdrawn, p)   # reported, not walked
            self.assertFalse(g["reached"] & ({p} | {d["id"] for d in g["descendants"]}), p)
        # decision 0016: JRN-0002 is not reached by its own walk, with or without the option
        self.assertNotIn("JRN-0002", impact.reached(impact.walk(reg, "JRN-0002")))
        self.assertNotIn("JRN-0002", got["JRN-0002"]["reached"])
        # each descendant by its own taxonomy's row of the walk chosen
        self.assertEqual(impact.walk_children(reg, "CAP-0001", impact.REALISERS)["reached"],
                         {"PROC-0002", "PROC-0003", "PROC-0004", "APP-0002", "APP-0003", "APP-0004"})

    def test_the_start_is_never_reached(self):
        """Decision 0016, point 2: the plain walk never counts its start; an edge back to it is reported
        and marked, not counted; 19 dependants starts lose themselves and nothing else; the realisers walk
        and the edges walked are unchanged."""
        reg = load_register(ROOT)
        changed = {}
        for nid in reg["nodes"]:
            edges = impact.walk(reg, nid)
            got = impact.reached(edges)
            self.assertNotIn(nid, got, nid)
            self.assertNotIn(nid, impact.reached(impact.walk(reg, nid, impact.REALISERS)), nid)
            self.assertFalse(any(e["to_start"] for e in impact.walk(reg, nid, impact.REALISERS)), nid)
            back = [e for e in edges if e["to_start"]]
            self.assertTrue(all(e["to"] == nid for e in back), nid)
            if any(e["live"] for e in back):
                self.assertEqual(got, {e["to"] for e in edges if e["live"]} - {nid}, nid)
                changed[nid] = len(got)
        self.assertEqual(changed, {"JRN-0001": 2, "JRN-0002": 5, "JRN-0003": 5, "JRN-0005": 2, "JRN-0006": 10,
                                   "JRN-0007": 7, "JRN-0009": 4, "JRN-0010": 4, "JRN-0011": 4, "PRD-0002": 2,
                                   "PRD-0004": 2, "PRD-0005": 4, "PROC-0001": 2, "PROC-0002": 5, "PROC-0004": 5,
                                   "PROC-0006": 4, "PROC-0007": 10, "PROC-0008": 7, "PROC-0010": 2})
        # the edge back is still reported: PRD-0002's walk meets JRN-0001 and PROC-0001 pointing back
        self.assertEqual(sorted(e["from"] for e in impact.walk(reg, "PRD-0002") if e["to_start"]), ["JRN-0001", "PROC-0001"])

    def test_the_descent_continues_below_a_withdrawn_descendant(self):
        """Decision 0016, point 1: on a copy where approved CAP-0002 sits below proposed CAP-0005,
        CAP-0005 is reported withdrawn and not walked, and CAP-0002 is still walked by its own row."""
        d = copy_register()
        p = d / "capabilities" / "CAP-0002.toml"
        p.write_text(p.read_text().replace('parent = "CAP-0001"', 'parent = "CAP-0005"'))
        reg = load_register(d)
        got = impact.walk_children(reg, "CAP-0001", impact.REALISERS)
        self.assertEqual([(x["id"], x["live"]) for x in got["descendants"]],
                         [("CAP-0003", True), ("CAP-0004", True), ("CAP-0005", False), ("CAP-0002", True)])   # depth first
        self.assertNotIn("CAP-0005", {e["from"] for e in got["edges"]})
        self.assertIn("CAP-0002", {e["from"] for e in got["edges"]})
        self.assertLessEqual({"PROC-0004", "APP-0003"}, got["reached"])   # what realises CAP-0002
        self.assertEqual(impact.walk_children(reg, "CAP-0005", impact.REALISERS)["reached"], {"PROC-0004", "APP-0003"})

    def test_an_approved_child_of_a_deprecated_parent_is_a_finding(self):
        """Decision 0015: approved child of a deprecated or retired parent an error, proposed or draft
        a warning, deprecated, retired or rejected none; nothing on the register as it stands."""
        def parent_findings(f):
            return [(i["level"], i["where"]) for i in f.items if i["check"] == "lifecycle" and "has parent" in i["message"]]
        f, _ = check_register.run(ROOT, today=TODAY)
        self.assertEqual(parent_findings(f), [])
        d = copy_register()
        p = d / "capabilities" / "CAP-0001.toml"
        p.write_text(p.read_text().replace('state = "approved"', 'state = "deprecated"'))
        f, _ = check_register.run(d, today=TODAY)
        self.assertEqual(sorted(parent_findings(f)), [("error", "capabilities/CAP-0002.toml"), ("error", "capabilities/CAP-0003.toml"),
                                                      ("error", "capabilities/CAP-0004.toml"), ("warning", "capabilities/CAP-0005.toml")])
        c = d / "capabilities" / "CAP-0002.toml"
        c.write_text(c.read_text().replace('state = "approved"', 'state = "deprecated"'))
        f, _ = check_register.run(d, today=TODAY)
        self.assertNotIn("capabilities/CAP-0002.toml", [w for _, w in parent_findings(f)])

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

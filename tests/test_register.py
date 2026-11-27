"""Standard-library tests: the register passes its own checks, and each check fires on a broken copy."""
from __future__ import annotations

import datetime as dt
import json
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
        self.assertEqual(summary["C4"]["uncovered"], [])

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

    def test_a_handle_may_record_its_holder_as_a_directory_identifier(self):
        """Decision 0021: person is optional; when present it is a directory identifier (a numeric
        id, a GUID, a principal name), never free text or a name. Synthetic values only."""
        d = copy_register()
        h = d / "people" / "handles.toml"
        text = h.read_text()
        def run(person_line):
            h.write_text(text + '\n[[handle]]\nhandle = "employee-9"\nunit = "ORG-0002"\nroles = ["gives"]\n'
                         'issued = 2026-11-02\n' + person_line)
            f, _ = check_register.run(d, today=TODAY)
            return [i["message"] for i in f.items if i["check"] == "handles"]
        self.assertEqual(run(""), [])   # absent: the holder is in the directory, or this is a synthetic role
        for valid in ("100234", "3f2504e0-4f89-11d3-9a0c-0305e82c3301", "u0042@directory.example",
                      "S-1-5-21-1004336348-1177238915-682003330-512"):
            self.assertEqual(run(f'person = "{valid}"\n'), [], valid)
        for invalid in ("Jane Doe", "jane.doe", "Doe", "jane doe@directory.example", ""):
            msgs = run(f'person = "{invalid}"\n')
            self.assertTrue(any("not a directory identifier" in m for m in msgs), (invalid, msgs))
        self.assertTrue(any("not a directory identifier" in m for m in run("person = 100234\n")))

    def test_one_person_holds_one_handle_per_unit_and_roles_at_a_time(self):
        """Decision 0021: a handle is one person in one role. Two live handles of one person with the
        same unit and roles are refused; a successor handle from the day of withdrawal, another
        unit, or other roles are not."""
        d = copy_register()
        h = d / "people" / "handles.toml"
        text = h.read_text()
        def run(*handles):
            extra = "".join(
                f'\n[[handle]]\nhandle = "{n}"\nunit = "{u}"\nroles = {r}\nissued = {i}\nperson = "100234"\n'
                + (f"withdrawn = {w}\n" if w else "") for n, u, r, i, w in handles)
            h.write_text(text + extra)
            f, _ = check_register.run(d, today=TODAY)
            return [i["message"] for i in f.items if i["check"] == "handles"]
        one = ("employee-8", "ORG-0002", '["gives"]', "2026-11-02", None)
        msgs = run(one, ("employee-9", "ORG-0002", '["gives"]', "2026-11-05", None))
        self.assertTrue(any("already holds employee-8" in m for m in msgs), msgs)
        msgs = run(("employee-8", "ORG-0002", '["gives"]', "2026-11-02", "2026-11-05"),
                   ("employee-9", "ORG-0002", '["gives"]', "2026-11-04", None))
        self.assertTrue(any("already holds employee-8" in m for m in msgs), msgs)
        self.assertEqual(run(("employee-8", "ORG-0002", '["gives"]', "2026-11-02", "2026-11-05"),
                             ("employee-9", "ORG-0002", '["gives"]', "2026-11-05", None)), [])
        self.assertEqual(run(one, ("employee-9", "ORG-0001", '["gives"]', "2026-11-02", None)), [])
        self.assertEqual(run(one, ("employee-9", "ORG-0002", '["gives", "approves"]', "2026-11-02", None)), [])

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

    def test_the_thread_walk_goes_from_a_step_down_to_its_data(self):
        """Decision 0018, part (a): from a step, the process that supports it, the capability it realises,
        the application that supports it and the information both use; one direction only, so no start
        reaches its whole slice and starts keep their own answers; walked both ways, the same relationship
        types collapse each start to its component."""
        reg = load_register(ROOT)
        self.assertEqual(impact.THREAD, {"journeys": [("is_supported_by", True)],
                                         "processes": [("realizes", True), ("supports", False), ("crud", True)],
                                         "applications": [("manages", True)]})
        self.assertIs(impact.WALKS["thread"], impact.THREAD)
        self.assertFalse({r for spec in impact.THREAD.values() for r, _ in spec} & {"owns", "maps_to"})
        thread = {s: impact.reached(impact.walk(reg, s, impact.THREAD)) for s in ("JRN-0002", "JRN-0003", "JRN-0006", "JRN-0007", "JRN-0009")}
        self.assertEqual(thread, {"JRN-0002": {"PROC-0002", "CAP-0004", "APP-0002", "ENT-0002", "ENT-0003"},
                                  "JRN-0003": {"PROC-0004", "CAP-0002", "APP-0003", "ENT-0003", "ENT-0004"},
                                  "JRN-0006": {"PROC-0007", "CAP-0007", "APP-0006", "APP-0008", "ENT-0008", "ENT-0009"},
                                  "JRN-0007": {"PROC-0008", "CAP-0008", "APP-0007", "ENT-0008"},
                                  "JRN-0009": {"PROC-0006", "APP-0005", "ENT-0007", "ENT-0010"}})
        # decision 0007's rule: JRN-0003's proposed link to PROC-0005 and PROC-0006's deprecated crud link are reported, not followed
        self.assertIn(("PROC-0005", False), [(e["to"], e["live"]) for e in impact.walk(reg, "JRN-0003", impact.THREAD)])
        self.assertIn(("ENT-0010", False), [(e["to"], e["live"]) for e in impact.walk(reg, "JRN-0009", impact.THREAD)])
        # parent adds starts, never steps (decision 0014): a journey reaches nothing alone, its steps' threads with --children
        self.assertEqual(impact.walk(reg, "JRN-0001", impact.THREAD), [])
        self.assertEqual(impact.walk_children(reg, "JRN-0001", impact.THREAD)["reached"],
                         thread["JRN-0002"] | thread["JRN-0003"])
        self.assertEqual(len(impact.walk_children(reg, "JRN-0005", impact.THREAD)["reached"]), 13)
        # the measure: zero-reach starts and reach against the slice
        approved = sorted(nid for nid, n in reg["nodes"].items() if n.get("state") == "approved")
        self.assertEqual(len(approved), 53)
        plain = {nid: impact.reached(impact.walk(reg, nid, impact.THREAD)) for nid in approved}
        children = {nid: impact.walk_children(reg, nid, impact.THREAD)["reached"] for nid in approved}
        self.assertEqual(sum(1 for r in plain.values() if not r), 33)
        self.assertEqual(sum(1 for r in children.values() if not r), 30)
        self.assertEqual(max(len(r) for r in plain.values()), 6)          # JRN-0006, of 29 J-F nodes
        self.assertEqual(max(len(r) for r in children.values()), 13)      # JRN-0005 with --children, of 29
        nonempty = [frozenset(r) for r in plain.values() if r]
        self.assertEqual((len(nonempty), len(set(nonempty))), (20, 17))
        # the same five relationship types walked both ways: every start reaches its whole component, five answers for 36 starts
        both = {"journeys": [("is_supported_by", True)], "capabilities": [("realizes", False)],
                "processes": [("is_supported_by", False), ("realizes", True), ("supports", False), ("crud", True)],
                "applications": [("supports", True), ("manages", True)], "information": [("crud", False), ("manages", False)]}
        comps = [frozenset(impact.reached(impact.walk(reg, nid, both)) | {nid}) for nid in approved if impact.reached(impact.walk(reg, nid, both))]
        self.assertEqual((len(comps), len(set(comps))), (36, 5))
        self.assertEqual(max(len(c) for c in comps), 12)

    def test_products_and_journeys_align_at_warning_level(self):
        """Decision 0018, part (b): A1 flags PRD-0002 (requires CAP-0003, which no step of JRN-0001 reaches),
        PRD-0004 (JRN-0005 reaches CAP-0008, not required) and PRD-0005 (no journey); warnings, never errors;
        each finding clears when the register is aligned on a copy."""
        def a1(f):
            return sorted((i["level"], i["where"], i["message"]) for i in f.items if i["check"] == "A1")
        f, summary = check_register.run(ROOT, today=TODAY)
        self.assertFalse(f.errors)
        self.assertEqual([(lvl, w) for lvl, w, _ in a1(f)], [("warning", "products/PRD-0002.toml"), ("warning", "products/PRD-0004.toml"),
                                                           ("warning", "products/PRD-0005.toml")])
        self.assertEqual(summary["A1"], {"denominator": 3, "aligned": [], "no_journey": ["PRD-0005"],
                                         "required_not_reached": [["PRD-0002", "CAP-0003"]],
                                         "reached_not_required": [["PRD-0004", "CAP-0008"]]})
        # on a copy: PRD-0004 requires CAP-0008; JRN-0002 is supported by PROC-0003 too; a journey concerns PRD-0005
        d = copy_register()
        r = d / "relationships" / "requires.toml"
        r.write_text(r.read_text() + '\n[[link]]\nid = "REL-99001"\nsource = "PRD-0004"\ntarget = "CAP-0008"\nstate = "draft"\n'
                     'rationale = "test"\nowner = "ORG-0003"\n')
        reg = load_register(d)
        self.assertEqual(check_register.check_alignment(reg, check_register.Findings())["reached_not_required"], [["PRD-0004", "CAP-0008"]])  # a draft link counts for nothing
        r.write_text(r.read_text().replace('state = "draft"\nrationale = "test"', 'state = "approved"\nrationale = "test"'))
        s = d / "relationships" / "is_supported_by.toml"
        s.write_text(s.read_text() + '\n[[link]]\nid = "REL-99002"\nsource = "JRN-0002"\ntarget = "PROC-0003"\nstate = "approved"\n'
                     'rationale = "test"\nowner = "ORG-0001"\n')
        c = d / "relationships" / "concerns.toml"
        c.write_text(c.read_text() + '\n[[link]]\nid = "REL-99003"\nsource = "JRN-0005"\ntarget = "PRD-0005"\nstate = "approved"\n'
                     'rationale = "test"\nowner = "ORG-0003"\n')
        got = check_register.check_alignment(load_register(d), check_register.Findings())
        self.assertEqual(got["no_journey"], [])
        self.assertEqual(got["required_not_reached"], [])
        self.assertEqual(got["reached_not_required"], [])
        self.assertEqual(got["aligned"], ["PRD-0002", "PRD-0004", "PRD-0005"])

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

    def test_coverage_c4_a_realising_process_is_supported_by_an_application(self):
        """Decision 0020: C4 covers 5 of 5 on the register. On a copy, a withdrawn supports link or a deprecated
        application leaves PROC-0004 uncovered, an error; a draft link covers nothing; an unexpired C4 exception
        excuses it and an expired one stops excusing; a process that realises nothing, or only a proposed
        capability, is outside the denominator."""
        def c4_errors(f):
            return [i["where"] for i in f.items if i["check"] == "C4"]
        def withdraw(path: Path, link_id: str):
            text = path.read_text()
            head, sep, rest = text.partition(f'id = "{link_id}"')
            path.write_text(head + sep + rest.replace('state = "approved"', 'state = "deprecated"', 1))
        f, summary = check_register.run(ROOT, today=TODAY)
        self.assertEqual(summary["C4"], {"denominator": 5, "covered": 5, "excepted": 0, "uncovered": []})
        self.assertEqual(c4_errors(f), [])
        # outside the denominator: PROC-0001, PROC-0006, PROC-0009, PROC-0010 realise nothing; PROC-0005 and CAP-0005 are proposed
        reg = load_register(ROOT)
        realizing = {ln["source"] for ln in reg["relationships"]["realizes"]["links"]}
        self.assertEqual(sorted(realizing), ["PROC-0002", "PROC-0003", "PROC-0004", "PROC-0005", "PROC-0007", "PROC-0008"])
        # a sunset without a replacement: TariffEngine's supports link to Price the quote withdrawn
        d = copy_register()
        sup = d / "relationships" / "supports.toml"
        withdraw(sup, "REL-06003")
        f, summary = check_register.run(d, today=TODAY)
        self.assertEqual(summary["C4"], {"denominator": 5, "covered": 4, "excepted": 0, "uncovered": ["PROC-0004"]})
        self.assertEqual(c4_errors(f), ["processes/PROC-0004.toml"])
        # a draft link from another application covers nothing
        sup.write_text(sup.read_text() + '\n[[link]]\nid = "REL-99010"\nsource = "APP-0002"\ntarget = "PROC-0004"\nstate = "draft"\n'
                       'rationale = "test"\nowner = "ORG-0002"\n')
        _, summary = check_register.run(d, today=TODAY)
        self.assertEqual(summary["C4"]["uncovered"], ["PROC-0004"])
        # a phase-out: an exception names the date by which a replacement supports the process
        (d / "exceptions" / "EXC-9001.toml").write_text(
            'id = "EXC-9001"\nrule = "C4"\nscope = ["PROC-0004"]\nrationale = "test: phase-out until the replacement supports pricing"\n'
            'approved = { by = "fdurieux", on = 2026-10-30, record = "decisions/0020-a-fourth-coverage-rule-a-realising-process-is-supported-by-an-application.md" }\n'
            'expires = 2027-03-31\n')
        f, summary = check_register.run(d, today=TODAY)
        self.assertEqual(summary["C4"], {"denominator": 5, "covered": 4, "excepted": 1, "uncovered": []})
        self.assertEqual(c4_errors(f), [])
        f, summary = check_register.run(d, today=dt.date(2027, 4, 1))
        self.assertEqual(summary["C4"]["uncovered"], ["PROC-0004"])
        self.assertTrue(any(i["check"] == "exceptions" and "EXC-9001" in i["where"] and "expired" in i["message"] for i in f.items))
        # a deprecated application supports nothing, though its link still reads approved (itself a lifecycle error)
        d = copy_register()
        a = d / "applications" / "APP-0003.toml"
        a.write_text(a.read_text().replace('state = "approved"', 'state = "deprecated"'))
        f, summary = check_register.run(d, today=TODAY)
        self.assertEqual(summary["C4"]["uncovered"], ["PROC-0004"])
        self.assertTrue(any(i["check"] == "lifecycle" and "APP-0003" in i["message"] for i in f.items))

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

    def test_inventory_output_is_a_plain_text_trace_inventory(self):
        # fixture of pumllint 0.35.0 trace's plain-text rule: strip; skip blank and `#` lines;
        # drop an inline `<whitespace>#` comment; an id left holding whitespace never matches.
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            inventory.main(["--all"])
        lines = buf.getvalue().splitlines()
        self.assertTrue(lines)
        for line in lines:
            s = line.strip()
            s = re.split(r"\s#", s, maxsplit=1)[0].strip()
            self.assertRegex(s, r"^CAP-\d{4,}$", line)

    def test_reconcile_against_no_previous(self):
        d = copy_register()
        r = reconcile.reconcile(d / "exports" / "kit" / "2026-10-30", d)
        self.assertEqual(r["files"]["deleted"], [])
        self.assertEqual(len(r["files"]["added"]), 10)
        self.assertEqual(r["stale_nodes"], [])
        self.assertEqual(r["unregistered"], [{"kit_path": "kit/links.toml", "name": "links.toml"},
                                             {"kit_path": "tests_input/acceptance.feature", "name": "acceptance.feature"}])
        self.assertTrue((d / "exports" / "kit" / "2026-10-30" / "RECONCILE.json").exists())

    def test_reconcile_lists_unregistered_ids(self):
        """Decision 0017: the export's ids no node carries, a finding; stale_nodes unchanged; counted in the summary."""
        d = copy_register()
        jef = reconcile.reconcile(d / "exports" / "jef_kit" / "2026-11-01", d)
        man = load_toml(d / "exports" / "jef_kit" / "2026-11-01" / "MANIFEST.toml")
        self.assertEqual(len(jef["unregistered"]), 35)
        self.assertTrue(all(e["name"] == man["ids"][e["kit_path"]] for e in jef["unregistered"]))
        self.assertIn({"kit_path": "CHANGES.md", "name": "CHANGES.md"}, jef["unregistered"])
        self.assertEqual(jef["stale_nodes"], [])
        self.assertEqual(reconcile.reconcile(d / "exports" / "kit" / "2026-10-30", d)["stale_nodes"], [])
        # a node removed from the copy moves its id into unregistered; reconcile writes no node
        before = sorted(p.relative_to(d).as_posix() for p in d.glob("*/*.toml"))
        (d / "applications" / "APP-0005.toml").unlink()   # the one node carrying uml/component.puml
        after = reconcile.reconcile(d / "exports" / "jef_kit" / "2026-11-01", d)
        self.assertIn({"kit_path": "uml/component.puml", "name": "component.puml"}, after["unregistered"])
        self.assertEqual(len(after["unregistered"]), 36)
        self.assertEqual(sorted(p.relative_to(d).as_posix() for p in d.glob("*/*.toml")), [b for b in before if b != "applications/APP-0005.toml"])
        _, summary = check_register.run(ROOT, today=TODAY)
        self.assertEqual(summary["exports"]["kit"], {"export": "exports/kit/2026-10-30", "denominator": 10, "registered": 8, "unregistered": 2})
        self.assertEqual(summary["exports"]["jef_kit"]["unregistered"], 35)
        self.assertEqual(summary["exports"]["jef_kit"]["denominator"], 50)


class InboundReferences(unittest.TestCase):
    """Decision 0023: an agent registry's usages cite a capability by id; the register reads them
    from the registry's export, warns per citation that does not rest on an approved capability,
    and reports the counts with their denominator. No node, no link."""
    AR = "exports/agent_registry/2026-11-27/MANIFEST.toml"

    def inbound(self, f):
        return [i for i in f.items if i["check"] == "inbound"]

    def test_the_synthetic_export_is_reported_with_its_denominator(self):
        f, summary = check_register.run(ROOT, today=TODAY)
        s = summary["inbound"]["agent_registry"]
        self.assertEqual({k: s[k] for k in ("export", "denominator", "citing", "approved", "not_yet_approved", "withdrawn", "no_node", "outside", "approved_cited", "approved_total")},
                         {"export": "exports/agent_registry/2026-11-27", "denominator": 4, "citing": 3, "approved": 1, "not_yet_approved": 1,
                          "withdrawn": 0, "no_node": 1, "outside": 0, "approved_cited": 1, "approved_total": 7})
        hits = self.inbound(f)
        self.assertEqual([i["level"] for i in hits], ["warning", "warning"], hits)
        self.assertEqual({i["where"] for i in hits}, {"capabilities/CAP-0005.toml", self.AR})
        self.assertTrue(any("prov-17" in i["message"] and "no node" in i["message"] for i in hits))
        self.assertTrue(any("CAP-0005" in i["message"] and "not yet approved" in i["message"] for i in hits))
        self.assertNotIn("agent_registry", summary["exports"], "a system that authors no node has no unregistered count")

    def test_a_deprecated_capability_moves_its_usage_to_withdrawn(self):
        d = copy_register()
        p = d / "capabilities" / "CAP-0003.toml"
        p.write_text(p.read_text().replace('state = "approved"', 'state = "deprecated"'))
        f, summary = check_register.run(d, today=TODAY)
        s = summary["inbound"]["agent_registry"]
        self.assertEqual((s["approved"], s["withdrawn"], s["approved_cited"], s["approved_total"]), (0, 1, 0, 6))
        at = [i for i in f.items if i["where"] == "capabilities/CAP-0003.toml" or "CAP-0003" in i["message"]]
        self.assertTrue(any(i["check"] == "inbound" and i["level"] == "warning" and "withdrawn" in i["message"]
                            and i["where"] == "capabilities/CAP-0003.toml" for i in at), at)
        self.assertTrue(any(i["check"] == "lifecycle" and i["level"] == "error" for i in at), "the approved links fail beside it")
        self.assertEqual([i for i in self.inbound(f) if i["level"] == "error"], [])

    def test_a_node_outside_the_cited_taxonomies_is_a_warning(self):
        d = copy_register()
        p = d / self.AR
        p.write_text(p.read_text().replace('"u-c51e90" = "prov-17"', '"u-c51e90" = "PRD-0002"'))
        f, summary = check_register.run(d, today=TODAY)
        self.assertTrue(any(i["where"] == "products/PRD-0002.toml" and i["level"] == "warning" for i in self.inbound(f)))
        self.assertEqual((summary["inbound"]["agent_registry"]["outside"], summary["inbound"]["agent_registry"]["no_node"]), (1, 0))

    def test_the_manifest_shape_is_an_error(self):
        d = copy_register()
        p = d / self.AR
        p.write_text(p.read_text() + '"u-0000aa" = "CAP-0002"\n')
        k = d / "exports" / "kit" / "2026-10-30" / "MANIFEST.toml"
        k.write_text(k.read_text() + '\n[cites]\n"kit/links.toml" = "CAP-0002"\n')
        f, _ = check_register.run(d, today=TODAY)
        errs = [i for i in self.inbound(f) if i["level"] == "error"]
        self.assertTrue(any(i["where"] == self.AR and "u-0000aa" in i["message"] and "[ids]" in i["message"] for i in errs), errs)
        self.assertTrue(any(i["where"] == "exports/kit/2026-10-30/MANIFEST.toml" and "no cites" in i["message"] for i in errs), errs)

    def test_no_node_may_name_the_agent_registry_as_its_source(self):
        d = copy_register()
        p = d / "capabilities" / "CAP-0005.toml"
        text = re.sub(r"(?ms)^\[source\].*?(?=^\[|\Z)", "", p.read_text())
        p.write_text(text + '\n[source]\nsystem = "agent_registry"\nusage_id = "u-8a04d7"\n')
        f, _ = check_register.run(d, today=TODAY)
        self.assertTrue(any(i["check"] == "sources" and i["where"] == "capabilities/CAP-0005.toml"
                            and "not authoritative" in i["message"] for i in f.errors), f.errors)

    def test_reconcile_lists_references_and_skips_stale_and_unregistered(self):
        d = copy_register()
        first = reconcile.reconcile(d / "exports" / "agent_registry" / "2026-11-27", d)
        self.assertEqual((first["stale_nodes"], first["unregistered"]), ([], []))
        self.assertEqual(len(first["references"]["added"]), 3)
        nxt = d / "exports" / "agent_registry" / "2026-12-04"
        nxt.mkdir()
        text = (d / self.AR).read_text().replace('previous = ""', 'previous = "exports/agent_registry/2026-11-27"')
        text = text.replace('"u-8a04d7" = "CAP-0005"', '"u-8a04d7" = "CAP-0004"').replace('"u-c51e90" = "prov-17"\n', "")
        (nxt / "MANIFEST.toml").write_text(text)
        r = reconcile.reconcile(nxt, d)
        self.assertEqual(r["references"], {"added": [], "changed": [{"usage_id": "u-8a04d7", "from": "CAP-0005", "to": "CAP-0004"}],
                                           "removed": [{"usage_id": "u-c51e90", "cites": "prov-17"}]})
        self.assertNotIn("references", reconcile.reconcile(d / "exports" / "kit" / "2026-10-30", d))
        _, summary = check_register.run(d, today=TODAY)
        self.assertEqual(summary["inbound"]["agent_registry"]["export"], "exports/agent_registry/2026-12-04")


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


def later_export(d: Path, system: str, date: str, ids: dict[str, str], previous: str = "") -> Path:
    """A synthetic export folder: a MANIFEST with the given [ids] and no files."""
    folder = d / "exports" / system / date
    folder.mkdir(parents=True)
    lines = [f"exported_on = {date}T00:00:00Z", f'source = "{system}"', 'source_version = "synthetic"',
             'tool = "tests"', 'tool_version = "0"', f'previous = "{previous}"', "", "[files]", "", "[ids]"]
    lines += [f'"{k}" = "{v}"' for k, v in ids.items()]
    (folder / "MANIFEST.toml").write_text("\n".join(lines) + "\n")
    return folder


def point(d: Path, path: str, old: str, new: str):
    p = d / path
    p.write_text(p.read_text().replace(old, new))


class NameCheck(unittest.TestCase):
    """Decision 0024 (issue #39): a node's name against the name the latest export of its system gives its id,
    where that system's export names concepts. GUIDs and names below are synthetic."""
    GUIDS = {"PROC-0002": "00000000-0000-4000-8000-000000000002", "PROC-0003": "00000000-0000-4000-8000-000000000003",
             "PROC-0004": "00000000-0000-4000-8000-000000000004", "PROC-0005": "00000000-0000-4000-8000-000000000005"}

    def _to_aris(self, d: Path, nid: str):
        p = d / "processes" / f"{nid}.toml"
        p.write_text(re.sub(r'system = "kit"\nkit_path = "[^"]*"', f'system = "aris"\naris_guid = "{self.GUIDS[nid]}"', p.read_text()))

    def _aris_copy(self) -> Path:
        """PROC-0002, 0004 and 0005 on aris; its export renames 0002's definition and no longer carries 0005's."""
        d = copy_register()
        for nid in ("PROC-0002", "PROC-0004", "PROC-0005"):
            self._to_aris(d, nid)
        later_export(d, "aris", "2026-11-20", {self.GUIDS["PROC-0004"]: "Price the quote",
                                               self.GUIDS["PROC-0002"]: "Validate the request",
                                               self.GUIDS["PROC-0005"]: "Notify the shipper"})
        later_export(d, "aris", "2026-12-01", {self.GUIDS["PROC-0004"]: "Price the quote",
                                               self.GUIDS["PROC-0002"]: "Check the request"},
                     previous="exports/aris/2026-11-20")
        return d

    def _for(self, f, nid):
        return [i for i in f.items if f"/{nid}.toml" in i["where"] and i["check"] in ("name", "stale")]

    def test_a_matching_name_gives_no_finding(self):
        f, summary = check_register.run(self._aris_copy(), today=TODAY)
        self.assertEqual(self._for(f, "PROC-0004"), [])
        self.assertEqual(summary["names"]["matched"], 1)

    def test_a_differing_name_names_the_node_both_names_and_the_folder(self):
        f, summary = check_register.run(self._aris_copy(), today=TODAY)
        hits = self._for(f, "PROC-0002")
        self.assertEqual([(i["level"], i["check"]) for i in hits], [(check_register.NAME_LEVEL, "name")])
        for part in ("Validate the request", "Check the request", self.GUIDS["PROC-0002"], "exports/aris/2026-12-01"):
            self.assertIn(part, hits[0]["message"])   # the latest folder by date, not the earlier one
        self.assertEqual(summary["names"]["differing"], [{"id": "PROC-0002", "name": "Validate the request",
                                                          "export_name": "Check the request", "export": "exports/aris/2026-12-01"}])

    def test_a_system_with_no_export_is_unchecked_and_counted(self):
        d = copy_register()
        self._to_aris(d, "PROC-0003")
        f, summary = check_register.run(d, today=TODAY)
        self.assertEqual(self._for(f, "PROC-0003"), [])
        self.assertEqual((summary["names"]["unchecked_no_export"], summary["names"]["denominator"]), (1, 57))
        later_export(d, "aris", "2026-12-01", {self.GUIDS["PROC-0003"]: "Screen the shipper"})
        _, summary = check_register.run(d, today=TODAY)
        self.assertEqual((summary["names"]["unchecked_no_export"], summary["names"]["matched"]), (0, 1))

    def test_a_vanished_id_is_stale_never_deleted_and_has_no_name_finding(self):
        d = self._aris_copy()
        f, summary = check_register.run(d, today=TODAY)
        hits = self._for(f, "PROC-0005")
        self.assertEqual([(i["level"], i["check"]) for i in hits], [("warning", "stale")])
        self.assertEqual(summary["names"]["stale"], [{"id": "PROC-0005", "aris_guid": self.GUIDS["PROC-0005"],
                                                      "export": "exports/aris/2026-12-01"}])
        self.assertIn('name = "Notify the shipper"', (d / "processes" / "PROC-0005.toml").read_text())

    def test_a_system_whose_export_names_documents_is_unchecked(self):
        """The kit systems' [ids] give each document its file name: counted unchecked, never a name finding."""
        f, summary = check_register.run(ROOT, today=TODAY)
        nm = summary["names"]
        self.assertEqual((nm["denominator"], nm["matched"], len(nm["differing"]), len(nm["stale"]),
                          nm["unchecked_no_export"], nm["unchecked_document"], nm["unchecked_part"]), (57, 0, 0, 0, 0, 57, 0))
        self.assertEqual([i for i in f.items if i["check"] in ("name", "stale")], [])
        # a system that declares no export_names is refused
        d = copy_register()
        point(d, "metamodel/sources.toml", 'export_names = "document"\n', "", )
        f, _ = check_register.run(d, today=TODAY)
        self.assertTrue(any(i["check"] == "sources" and "export_names" in i["message"] and i["level"] == "error" for i in f.items))


class SeamCheck(unittest.TestCase):
    """The seam check's readings (decision 0025), on synthetic inputs: no pumllint, no aris2puml."""

    TODAY_JS = """function exportModel(model) {
  var occs = model.ObjOccList();
  for (var i = 0; i < occs.length; i++) {
    var occ = occs[i], def = occ.ObjDef(), type = def.TypeNum();
      var linked = def.AssignedModels();
      if (linked.length > 0) node.ref = attr(linked[0], Constants.AT_ID) || linked[0].GUID();
  }
  var doc = {
    process: {
      id: attr(model, Constants.AT_ID) || model.GUID(),
      name: model.Name(-1),
"""

    def test_it_calls_the_command_lines_and_keeps_the_id_contract(self):
        import seam_check
        src = (ROOT / "tools" / "seam_check.py").read_text()
        self.assertIsNone(re.search(r"^\s*(import|from)\s+(pumllint|aris2puml)\b", src, re.M))
        self.assertIn(seam_check.DIGITS, check_register.ID_RE.pattern)

    def test_trace_output_dropped_added_and_warned(self):
        import seam_check
        doc = {"requirements": [{"id": "CAP-0002", "covered": True}, {"id": "CAP-0009", "covered": True}],
               "unknownReferences": [], "unlinkedDiagrams": [], "summary": {}}
        ok, lines = seam_check.read_trace(json.dumps(doc), "", 0, ["CAP-0002", "CAP-0003"])
        self.assertFalse(ok)
        self.assertIn("dropped: CAP-0003", lines)
        self.assertIn("added: CAP-0009", lines)
        ok, lines = seam_check.read_trace(json.dumps(doc), "warning: x.txt:1: requirement ID 'CAP-0002 x'", 0,
                                          ["CAP-0002", "CAP-0009"])
        self.assertFalse(ok)
        self.assertTrue(seam_check.read_trace(json.dumps(doc), "", 0, ["CAP-0002", "CAP-0009"])[0])
        self.assertFalse(seam_check.read_trace("not json", "boom", 2, ["CAP-0002"])[0])

    def test_the_footer_pattern_is_held_to_four_or_more_digits(self):
        import seam_check
        ids = ["PROC-0001", "PROC-0010"]
        ok, lines = seam_check.probe_pattern(r"PROC-\d{4}", ids)
        self.assertFalse(ok)
        self.assertIn("PROC-10000 read as PROC-1000", lines)
        self.assertTrue(seam_check.probe_pattern(r"PROC-\d{4,}", ids)[0])
        self.assertFalse(seam_check.probe_pattern(r"PROC-\d+", ids)[0])   # reads PROC-123, not an id

    def test_the_report_script_is_read_against_decision_0022(self):
        import seam_check
        ok, lines = seam_check.check_report_script(self.TODAY_JS, "AT_ID")
        self.assertFalse(ok)
        self.assertIn("on `model`, a model", lines[0])
        self.assertIn("on `linked[0]`, a model", lines[1])
        fixed = self.TODAY_JS.replace("attr(linked[0], Constants.AT_ID) || linked[0].GUID()",
                                      "attr(def, Constants.AT_ID) || def.GUID()")
        fixed = fixed.replace("  var doc = {", "  var fdef = model.SuperiorObjDefs()[0];\n  var doc = {")
        fixed = fixed.replace("attr(model, Constants.AT_ID) || model.GUID()", "attr(fdef, Constants.AT_ID) || fdef.GUID()")
        ok, lines = seam_check.check_report_script(fixed, "AT_ID")
        self.assertTrue(ok, lines)
        self.assertFalse(seam_check.check_report_script(fixed, "AT_REGISTER_ID")[0])
        helper = (self.TODAY_JS.replace("attr(linked[0], Constants.AT_ID) || linked[0].GUID()",
                                        "attr(def, REGISTER_ID_ATTRIBUTE) || def.GUID()")
                  .replace("attr(model, Constants.AT_ID) || model.GUID()", "processId(model)")
                  + "var REGISTER_ID_ATTRIBUTE = Constants.AT_ID;\n"
                  "function processId(model) {\n  var defs;\n  try { defs = model.SuperiorObjDefs(); }\n"
                  "  catch (e) { warnings.push(e); return model.GUID(); }\n"
                  "  for (var i = 0; i < defs.length; i++) {\n"
                  "    var id = attr(defs[i], REGISTER_ID_ATTRIBUTE) || defs[i].GUID();\n  }\n"
                  "  return model.GUID();\n}\n")
        ok, lines = seam_check.check_report_script(helper, "AT_ID")
        self.assertTrue(ok, lines)
        self.assertIn("in processId()", lines[0])
        self.assertIn("last resort `return model.GUID()` (2x), a model, with a warning", lines[0])
        self.assertFalse(seam_check.check_report_script(
            helper.replace("REGISTER_ID_ATTRIBUTE = Constants.AT_ID", "REGISTER_ID_ATTRIBUTE = Constants.AT_NAME"), "AT_ID")[0])
        ok, lines = seam_check.check_report_script("var doc = {};", "AT_ID")
        self.assertFalse(ok)
        self.assertIn("not found", lines[0])

    def test_the_floor_is_read_from_the_check_extra(self):
        import seam_check
        text = '[project]\nname = "x"\n[project.optional-dependencies]\ncheck = ["pumllint>=0.33"]\ntest = ["pytest>=7"]\n'
        self.assertEqual(seam_check.read_floor(text), ("pumllint>=0.33", "0.33"))
        self.assertTrue(seam_check.same_release("pumllint 0.33.0", "0.33"))
        self.assertFalse(seam_check.same_release("pumllint 0.35.0", "0.33"))
        with self.assertRaises(seam_check.SetupError):
            seam_check.read_floor('[project]\nname = "x"\n')

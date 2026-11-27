# 0024 — A name that differs from the latest export is a warning, and no exception excuses it

Date: 2026-11-27. State: proposed. Drafted by session_01HTAA1VMpofzhnMmGA5dXyy, dispatched by
session_01HTAA1UV2N6XGtCwCvVnB5t on fdurieux/ieam-register#39; a session never approves (decision 0019).
Supersedes: nothing. Sets the level of the name check that CLAUDE.md and METAMODEL.md have described since
decision 0001 and no code ran. Decisions 0001 (exports append-only, a vanished id `stale`), 0017
(`unregistered`), 0018 (A1, warning, no exception mechanism), 0020 (exceptions excuse coverage rules) and 0022
(an `aris` process node's name is its function definition's) stand.

## The question

`name` is the one field a node repeats from its source of record, "checked against the latest export, not
authored". `check_register.py` never opened an export's names. #39 asks for the check; the check changes what
passes, so its level needs a record: an error or a warning, and whether an exception can excuse it.

## Decision

1. **The check.** For each node whose `[source]` names a system with an id, `check_register.py` reads the
   latest export of that system (`exports/<system>/<date>/MANIFEST.toml`, latest by folder date) and compares
   the node's `name` with the name its `[ids]` gives the node's id (`kit_path`, `aris_guid`, `archi_id`,
   `edm_id`; for `aris`, the function definition's, decision 0022).
2. **A difference is a `name` warning,** naming the node, both names, the id and the export folder. It never
   fails the merge. No exception excuses it: `exceptions/` stays scoped to coverage rules, and a warning needs
   no excuse.
3. **A vanished id** (neither the id nor its document before `#` among the latest export's `[ids]`) is a
   `stale` warning, never a deletion, and gets no `name` finding. `reconcile.py`'s `stale_nodes` is unchanged.
4. **Unchecked, and counted.** A node whose system has no export folder yet, and a node whose id names a part
   (`<path>#<part>`) of a document the export carries only whole, are unchecked: the document's name is not the
   part's. The checker prints matched over checked, the differing and stale counts, and unchecked over every
   node with a `[source]`, as coverage is printed. `aris`, `archi` and `edm` are checked from their first
   folder; no node carries them today.
5. **The remedy is by hand, on the side that is wrong.** A rename in the source of record: set `name` to the
   export's in the pull request that lands the export. A wrong name in the source of record: fix it there; the
   next export, a new folder, closes the finding. Neither side is changed by a tool.

## Measured

On `main` at 686fba3 with this check: 57 nodes carry a `[source]` (28 `kit`, 29 `jef_kit`). 53 differ, 0 match,
0 are stale, 4 are unchecked as parts (CAP-0002, CAP-0003, CAP-0004 and ENT-0004, on
`contract/decision_table.md#DT-…`), 0 for want of an export. Every difference has one cause: the kit
manifests' `[ids]` give each document its file name (`"contract/spec.md" = "spec.md"`), written by the kit's
document list, and five nodes may point at one document. The register's names are the concepts'
("Freight quoting", "QuoteAPI"). The export is the side that is wrong for this check: it carries no name of
what a node points at. No node name is a typo. Under an error level, `main` would fail with 53 errors and no
pull request could fix them: the export is append-only, and setting 53 names to file names would make the
register wrong.

## Options

- (a) **Error, no exception.** The contract's literal reading. Fails `main` on the kit today (53 errors, none
  fixable); later, every pull request fails from the moment a rename lands in an export until a person edits
  the name.
- (b) **Error, excused by an exception.** A new rule id in `COVERAGE_RULES`, scoped exceptions with an
  `expires`. 53 nodes would need an approved exception now, renewed at each expiry, for a difference no one
  can remove; the exception mechanism (decision 0020) would carry a check that is not a coverage rule.
- (c) **Warning, no exception.** As A1 (decision 0018): reported every run, with its denominator, never
  failing. The kit's 53 stay visible; a rename shows on the first run after its export lands.
- (d) **Per-system level** in `sources.toml` (`name_check = "error" | "warning"`). A metamodel field for a
  distinction no export yet supports; the kit would sit at `warning` and the rest have no folder.

## Opportunity canvas

- **Problem:** the contract says `name` is checked; nothing checks it. A rename in ARIS would leave the
  register's name, the one field it repeats, silently wrong, and decision 0022's renamed definition
  (PROC-0004 in knowgov's fixture) would go unreported.
- **Who is served:** a reviewer of a pull request that lands an export; pumllint `trace`, whose inventory
  carries a node's `name` beside its id (`tools/inventory.py`); the maintainer, who reads one count per run.
- **Solution:** one comparison per node, reported as a warning with both names and the folder, the unchecked
  counted with their denominator.
- **What it costs:** one function and one printed line in `check_register.py`, four tests, a README section;
  53 warnings per run until the kit's exports carry names, which is a new export folder in pumllint's hands.
- **How we know it worked:** a renamed id in a later export prints one `name` warning naming both names; a
  vanished id prints one `stale` warning and no `name` warning; the counts add up to the denominator.

## Fit/gap

| it must | fit or gap |
|---|---|
| `name` checked against the latest export, not authored | fit: every node whose system has an export is compared, with the latest folder by date |
| a node file never copies a tool's attributes | fit: nothing is written to a node; the check reads only |
| exports append-only | fit: nothing writes an export; a fix is a new folder |
| a vanished id is `stale`, never a deletion | fit: a `stale` warning, no `name` warning, no file touched |
| coverage reported with its denominator and exceptions | fit: matched over checked, unchecked over all with a `[source]`; no exception exists for this check |
| exceptions excuse coverage rules and expire | fit: untouched, (b) refused |
| a difference blocks the content it concerns | gap, accepted: a warning does not block; a reviewer reads it. An error is revisited below |
| the kit's exports give names to check | gap: they give file names; 53 structural differences until a kit export carries names |
| a part of a document checked | gap, accepted: unchecked and counted until an export carries ids with parts |

## SWOT

- **Strengths:** the contract's sentence becomes true; `main` stays green on content that is right; the same
  check serves `aris` from its first folder with decision 0022's name; no new metamodel field.
- **Weaknesses:** 53 warnings on every run hide a real rename among structural ones; a warning can be merged
  past; a part is never checked.
- **Opportunities:** a kit export whose `[ids]` give the names of what nodes point at would turn the 53
  into matches without touching a node; once an export with real names lands, an error becomes measurable.
- **Threats:** reviewers learn to skip `name` lines; an export with names from another field than the
  one the register treats as `name` would differ on every node.

## Advice

Approve (c): a warning, no exception. The reasons:

- The one measurement available says an error fails `main` with 53 findings that no pull request can fix and
  that point at the export, not at the register.
- An exception excuses a gap someone owns and will close; these 53 belong to a tool outside the register, and
  (b) would make the exception mechanism carry a check that is not a coverage rule.
- A1 (decision 0018) set the precedent for a finding a reviewer reads and the merge does not gate.
- (d) adds a metamodel field before a second level has a use.

Revisit at the first `aris` export: if its names are the definitions' and every difference there is a rename
or a typo, supersede this record with one that makes a `name` difference an error for that system, measured
on that export.

## Built in this pull request

- `tools/check_register.py`: `check_names` (`NAME_LEVEL = "warning"`), `_latest_export` shared with
  `export_counts`; `summary["names"]` and one printed line.
- `tests/test_register.py`: `NameCheck`, four tests on synthetic folders (a match, a difference, a system with
  no export then its first `aris` folder, a vanished id); 33 tests.
- README "The checks", METAMODEL.md "Required fields", CLAUDE.md's test count.
- No node, link, export or exception changes. No matrix row and no relationship type moves.

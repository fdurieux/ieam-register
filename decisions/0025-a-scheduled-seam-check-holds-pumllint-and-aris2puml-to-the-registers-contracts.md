# 0025 — A scheduled seam check holds pumllint and aris2puml to the register's contracts, and blocks nothing

Date: 2026-11-27. State: proposed. Drafted by session_01HTAA1RBiiVNM48BPZ17B2e, dispatched by
session_01HTAA1UV2N6XGtCwCvVnB5t on fdurieux/ieam-register#46; a session never approves (decision 0019).
Supersedes: nothing. Adds a workflow and a tool; changes no node, link, export, metamodel field, relationship
type or glossary term. Decisions 0001 (ids, standard library only), 0019, 0022 (the definition carries the
register id, in `register_id_attribute`) and 0024 (the name check) stand. The pull request that settled the
inventory format, #41, stands.

## The question

The register fixed its side of three seams on 2026-11-27: the inventory `pumllint trace --requirements` reads
(#41), which ARIS function definition carries a process id and in which attribute (decision 0022), and the name
check (decision 0024). Nothing tells the register when pumllint or aris2puml drifts from them afterwards.
`tests/` holds trace's inventory format as a fixture, not pumllint itself, and the `register` workflow installs
nothing. Checking the other side means running it, and CLAUDE.md says no dependency is added without a decision
record: does installing pumllint and aris2puml to check them add one, and what does a red run mean?

## Decision

1. **A seam workflow, `.github/workflows/seam.yml`,** runs `tools/seam_check.py` daily, on `workflow_dispatch`,
   and on a pull request that touches `tools/inventory.py`, `metamodel/sources.toml` or the workflow itself.
2. **Three checks, each held against a contract the register recorded.**
   1. *The inventory.* `python tools/inventory.py --all`, read by `pumllint trace --pattern 'CAP-\d{4,}'
      --requirements` at the latest PyPI release and at `main`, yields exactly the ids the inventory wrote: none
      dropped, none added, no warning, each read from a probe footer. The denominator is the inventory's own:
      `capability` and `sub_capability` nodes in any state. The CAP nodes outside it (`capability_domain`) are
      counted by kind, never checked.
   2. *aris2puml's ids*, at its `main`:
      - (a) the `requirement-link` pattern of aris2puml's `tests/fixtures/conventions.toml`, the configuration its
        README hands adopters, reads each register process id whole, reads the contract's edge (`PROC-10000`,
        five digits) whole, and reads nothing in `PROC-123`. The contract is `ID_RE` in `check_register.py`:
        `<PREFIX>-<4+ digits>`;
      - (b) a footer aris2puml's command line writes for each register process id (`ARIS process <id>`, and the
        next id under `interfaces:`) is read back by the released `trace` under those conventions, none dropped
        or added;
      - (c) `aris/export_epc.js`, read as text, takes the process id and an interface's `ref` from the attribute
        `sources.toml` `[system.aris]` `register_id_attribute` names, on a function definition, with that
        definition's GUID as the fallback, as decision 0022 §4 states the target. An expression the reader
        cannot place is a failure that says "read it by hand", never a pass.
   3. *The floor.* The pumllint release aris2puml's `check` extra pins (`pyproject.toml`, `pumllint>=X`) is
      installed as `pumllint==X`, and check 1 holds at it.
3. **Not a dependency of the register's tools.** A dependency is what a register tool needs to run. pumllint and
   aris2puml are what the seam check checks, not what any register tool uses:
   - `check_register.py`, `inventory.py`, `reconcile.py`, `impact.py`, the tests and the `register` workflow
     install, import and call neither, and stay standard library only;
   - `seam_check.py` imports neither. It calls their command lines and reads aris2puml's source as text. Without
     them it stops with exit 2 and says which is missing. No other tool imports it. The tests exercise its readings
     on synthetic inputs, with neither installed;
   - the installs live in the seam job's own virtual environments, outside the checkout. The repository pins
     nothing: no requirements file, no lock, no extra;
   - an adopter's register runs none of it. Deleting the workflow leaves every register tool as it was.

   The precedent is aris2puml's `drift.yml`: a scheduled job installs pumllint's `main`, which aris2puml's own
   gate never does.
4. **Never required.** `seam` is not a required status check; the `register` workflow stays the gate, and a
   pull request merges on its green. A red seam run blocks no merge and opens nothing: no issue, no comment, no
   pull request in any repository.
5. **Who moves when it is red: the side that differs from the register's recorded contract.** The register is the
   driver: its contracts are the ones its decision records state.
   - Check 1 red at pumllint's release or `main`: pumllint's inventory reader moved, and pumllint fixes it, unless
     the register's pull request that turned it red changed `inventory.py`. That pull request runs the seam before
     merge, and its author fixes it, or records the new format in a decision first.
   - Check 2 red: aris2puml fixes its conventions, its footer or its report script.
   - Check 3 red: aris2puml raises its floor to a release check 1 holds at.
   - A contract the register means to change is changed by a decision record here, never by editing the check to
     pass.
   - As with `drift.yml`, a red run can also mean the other side's `main` is itself broken. The run says what it
     found; the maintainer reads it, and files the issue in the other repository by hand or asks a session to.
6. **The output says what it found**, and is written to the job's summary and to an uploaded `seam.json`: each
   check, PASS or FAIL, the version or commit read, and every id dropped, added or misread.

## Measured

`tools/seam_check.py` on the register at `1b4974c`, against pumllint 0.35.0 from PyPI, pumllint `main` at
`9205390` (it reports 0.35.0), pumllint 0.33.0 (the floor) and aris2puml `main` at `566cf6f`, on 2026-11-27:

- **Check 1 holds** at all three: 6 of 6 ids read, 0 dropped, 0 added, no warning. CAP-0001 and CAP-0006
  (`capability_domain`) are outside the inventory by its design: 6 of 8 CAP nodes.
- **Check 2 is red, on two of its three readings.**
  - (a) `PROC-\d{4}` reads all 10 register process ids (PROC-0001 to PROC-0010) whole, and reads `PROC-10000` as
    `PROC-1000`: an unanchored four-digit pattern silently names a different process once the register mints a
    five-digit id. Latent today; the contract allows it. The same pattern stands in pumllint's
    `docs/process-demo/conventions.toml` and `docs/business-processes.md`, which this check does not read.
  - (b) holds: 10 of 10 footers read back, interfaces included.
  - (c) fails, as decision 0022 recorded on approval: the process id is `attr(model, Constants.AT_ID) ||
    model.GUID()`, a model; the interface `ref` is `attr(linked[0], Constants.AT_ID) || linked[0].GUID()`, an
    assigned model. `AT_ID` agrees with `register_id_attribute`. aris2puml#52 is open for the process id.
- **Check 3 holds:** `pumllint>=0.33`, installed as 0.33.0; check 1 holds at it.

The register's checks are unchanged: 57 nodes, 65 links, 0 errors, 12 warnings.

## Options

- (a) **Nothing.** The contracts stay in decision records and test fixtures. Drift on the other side is found when
  a consumer breaks, as #38's divergence was found by reading code.
- (b) **The checks in the `register` workflow, required.** Every register merge then waits on two other
  repositories' `main` and on PyPI; a pumllint regression blocks a register change that did not cause it; the
  install becomes part of the gate, a dependency in all but name.
- (c) **A scheduled, non-required seam workflow in this repository** (the decision).
- (d) **The checks in pumllint's and aris2puml's own CI**, against a clone of the register. Each would carry a copy
  of the register's contracts; the register, which writes them, would not see the result. A later complement,
  not a replacement.
- (e) **Vendor pumllint's inventory reader into `tests/`.** A copy of the other side's code, which drifts from it
  as silently as the fixture does.

## Opportunity canvas

- **Problem:** three seams were settled on one day and nothing watches them. The inventory reader, aris2puml's
  footer pattern and its report script can each change in another repository without the register knowing.
- **Who is served:** the maintainer, who reads one daily run instead of three repositories' diffs; pumllint and
  aris2puml, told precisely which id their side dropped or misread; knowgov, which reads the same `AT_ID` on
  the same definitions (decision 0022) and gains a watch on the producer side; a register pull request that
  changes `inventory.py` or `sources.toml`, which sees the effect on the consumers before it merges.
- **Solution:** one standard-library script, three checks, one workflow on a schedule, red read and never gating.
- **What it costs:** one script and five tests here; one workflow; a daily job of a few minutes on a hosted runner;
  network reach to github.com and PyPI from that job; a red run to read while aris2puml#52 and the pattern stay
  open.
- **How we know it worked:** a change on either side that drops or misreads a register id turns the next
  scheduled run red, naming the id; the side that moved fixes it, and the next run is green without a change
  here.

## Fit/gap

| it must | fit or gap |
|---|---|
| standard library only, Python 3.11 or later, for the register's tools | fit: `seam_check.py` is standard library; the installs live in the job's environments (point 3) |
| no dependency without a decision record | fit: this record; and point 3 says why the CI-only install is not one |
| every change through a pull request, merged on the `register` workflow's green | fit: unchanged; `seam` is not required (point 4) |
| check 1: every CAP id the inventory writes is read, none dropped | fit, at the release, `main` and the floor. Gap, accepted: `capability_domain` nodes are outside the inventory by `inventory.py`'s design, counted, not checked |
| check 2: aris2puml's ids agree with `PROC-\d{4,}` and `register_id_attribute`, per decision 0022 as merged | fit: (a) and (b) run aris2puml's own pattern and command line; (c) reads its source. Gap, accepted: (c) is a static reading of JavaScript; an expression it cannot place fails with "read it by hand" |
| the report script has never run in ARIS | gap, accepted: (c) checks what the script would write, never what ARIS returns. No `mapping/matrix.toml` row moves, and no ARIS attribute or report call is asserted beyond what decision 0022 already records |
| check 3: aris2puml's floor works with the inventory | fit: the floor is installed exactly and check 1 runs at it |
| a red run blocks nothing, and the side that moved fixes it | fit: points 4 and 5 |
| aris2puml read at the version an adopter gets | gap, accepted: read at `main`, as #46 asks; aris2puml's tagged release is not read |
| the run reachable by an organisation's instance | gap, accepted: the job needs github.com and PyPI; an instance behind a restricted network decides its own seam |

## SWOT

- **Strengths:** the register finds drift on the day it happens, at the id that moved; the gate stays the
  register's own, standard library only; the first run already found a latent misread (`PROC-10000`) no test
  here or there exercised.
- **Weaknesses:** a check that is red on its first run (check 2, until aris2puml#52 and the pattern land) teaches
  readers to ignore it; (c) reads JavaScript with patterns, and a rewrite of the script can make it fail for the
  reader's sake, not the contract's; a red `main` on the other side reads the same as drift.
- **Opportunities:** knowgov's connector and pumllint's `docs/process-demo` copy of the pattern can join as further
  checks once a record says what they promise; a green check 2 after aris2puml#52 is the evidence the decision
  0022 build on that side asks for, short of a run in ARIS.
- **Threats:** pumllint or aris2puml changes shape faster than the reader follows, and the run is red for months;
  a session or adopter makes `seam` a required check, and the other repositories' `main` gates the register.

## Advice

Approve (c). The reasons:

- The register is where these contracts are written, so it is where their drift should surface; (d) would hide the
  result from the side that wrote the contract.
- (b) makes pumllint and aris2puml part of the register's gate in all but name; (c) keeps the gate standard
  library only and still runs the real command lines, which (e) and the fixture do not.
- The first run earns the workflow: check 2 (a) found that aris2puml's conventions would read a five-digit
  register id as another process, and (c) states the decision 0022 build still owed, from the source, not from a
  reading of it.
- Red today is the accurate state, not noise: aris2puml#52 is open, and the pattern is one character from
  agreeing (`PROC-\d{4,}`). Both are aris2puml's to move; the next green run shows they did.

Revisit when a fourth seam is added, or if check 2 (c) fails for the reader's sake more than once: then the
report script should state its id expression in a form a reader can check, a request to aris2puml, not a change
here.

## Built in this pull request

- `tools/seam_check.py`: the three checks; `--print-floor` for the workflow; text output, and `--json`.
- `.github/workflows/seam.yml`: daily at 05:41 UTC, `workflow_dispatch`, and pull requests touching
  `tools/inventory.py`, `metamodel/sources.toml` or the workflow; one virtual environment per command line.
- `tests/test_register.py`: `SeamCheck`, five tests on synthetic inputs (no pumllint, no aris2puml): no import of
  either and the id contract's digits; trace output dropped, added and warned; the footer pattern held to four or
  more digits; the report script read against decision 0022, today's shape and a definition-reading one; the
  floor read from the `check` extra; 45 tests with decision 0024's.
- README "The seam check"; CLAUDE.md's checks section and test count.
- No node, link, export, exception, matrix row, relationship type or glossary term changes.

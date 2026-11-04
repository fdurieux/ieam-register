# Working on ieam-register

## What this repository is

A public test case for keeping the identities, typed relationships and
approvals of an enterprise architecture in git, with the tools that author
the content (ARIS, Archi, the enterprise data model) staying its authors.
The content here is synthetic: the CargoQuote kit from pumllint's
governed-knowledge experiment. **No bank-related data, ever.** An
organisation's own instance is created from this structure inside its
private repositories; nothing of it comes back here.

The record it follows: pumllint `docs/ieam-register-proposal.md` (#239).
This repository's own record is `decisions/`: one numbered file per
decision, never edited after approval, superseded by a new one.

## Checks

```bash
python tools/check_register.py                      # the working tree; exit 1 on any error
python tools/check_register.py --previous origin/main   # plus lifecycle transitions against a ref
python -m unittest discover -s tests                # seventeen tests, standard library only
```

Both must pass. CI runs them on every pull request (with `--previous` set
to the base) and on `main`; a tag `v*` also writes `reports/<date>/`.
Standard library only, Python 3.11 or later (`tomllib`); no dependency
is added without a decision record.

## Pull requests

Every change goes through a pull request: open it, wait for the
`register` workflow, merge on green. A change that alters meaning (a
state to `approved` or `deprecated`, a new relationship type, a metamodel
field, a glossary term) needs a decision record in the same pull request
and is named in the approval's `record`.

A hosted session cannot push a tag: the owner publishes each `v*` Release in the GitHub UI on a
merge commit, typing the tag as new. When a merge is ready to be tagged, the session that merged it
hands the owner, in its reply, the tag, the target commit, a one-line title
(`vX.Y.Z — <what moved>`) and a Markdown description ready to paste. The description covers:
- what changed, in a few sentences;
- each decision record carried, with its pull requests;
- what is unchanged (links, relationship types, the glossary) where that matters;
- why it matters to a consumer such as knowgov;
- the checker's counts (nodes, links, errors) and the test count;
- the compare link to the previous tag.
It restates the decision records and never adds a claim they lack.

Two artifact pages are the maintainer's running view of this register, knowgov and pumllint:
the queue (https://claude.ai/code/artifact/a6e5007e-36f8-4a94-b3de-3ba2690512cc) and the
reconciliation (https://claude.ai/code/artifact/c3e39034-e727-430b-8170-8ca152ea9b80). A merged
pull request refreshes both in the same turn, without being asked. In the queue, that means the
link with a one-line what-and-why, plus any row whose state it changes (a decision proposed or
approved, a tag to publish). In the reconciliation's Record, it means a line when the merge bears
on the loops. A coordinating session, when one dispatches the work, writes the pages; its
sub-sessions report and never publish. The decision records are the record, and the pages quote
them. A session that cannot reach the pages says so.

## Things that are contracts, not details

- **Ids** are `<PREFIX>-<4+ digits>`, minted here, never reused, never
  encoding hierarchy or organisation. Prefixes: `CAP`, `PRD`, `JRN`,
  `PROC`, `APP`, `ENT`, `ORG`, `EXC`, `REL`. `CAP-` and `PROC-` are the
  ids pumllint's `trace` and aris2puml's footer already carry.
- **Hierarchy is the `parent` field**, never nested folders. One
  directory per taxonomy, one TOML file per node, file name equals id.
- **A node file never copies a tool's attributes.** It holds the
  register's id, kind, state, owner, links and a `[source]` pointer to
  the system of record; `name` is the one field it repeats, and it is
  checked against the latest export, not authored. The moment a file
  carries a field the tool owns, there are two records.
- **Approval is a file-state change**: `state = "approved"` with
  `approval = { by, on, record }`, both owners on a cross-domain link,
  the approver never the pull request's author. A merge records who
  changed the file; the approval block records who approved the content.
- **Lifecycle transitions** follow `metamodel/lifecycle.toml`; the
  checker diffs against the base and refuses a skipped step. Deprecating
  a node fails every approved link that references it; nothing is fixed
  automatically.
- **Exports are append-only**: `exports/<system>/<date>/` with a
  `MANIFEST.toml` (export time, source version, tool and version, the
  previous folder, sha256 per file, the ids carried) and a
  `RECONCILE.json` written by `tools/reconcile.py`. A later export is a
  new folder, never an overwrite. A node whose external id vanished is a
  `stale` finding, never a deletion.
- **`reports/` is derived**, written at a tag only, never edited by hand,
  never the record.
- **Support status starts at `unverified`** for every relationship type
  and every row of `mapping/matrix.toml`, and moves only with a test on a
  target installation and its evidence in the same pull request. No ARIS
  connection name is asserted without one.
- **Exceptions expire.** An exception past its `expires` date stops
  excusing and the coverage rule fires again.
- **Coverage is reported with its denominator and its exceptions**,
  never used as a percentage to pass.
- **The glossary applies** to every node `name`, link `rationale` and
  decision record: one approved term per concept, forbidden synonyms
  listed in `glossary/glossary.toml`.

## Registers

`README.md` is adopter-facing: name a concept before using it, say what a
command does and what the reader gets back. `METAMODEL.md`, this file,
`decisions/`, commit messages and pull request bodies are
maintainer-facing: terse, dense, symbols cited by name. British English.

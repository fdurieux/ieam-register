# ieam-register

A test case for one idea: keep the **identities, relationships and approvals** of an enterprise
architecture in git, while the tools that author the content (ARIS, Archi, the enterprise data
model) stay its authors. The six taxonomies of the IEAM proposal (capabilities, products and
services, customer journeys, business processes, applications and modules, information and data)
each get a directory; the typed relationships between them get a file each; approval is a
recorded change to a file, with who, when and which decision record says why.

**Everything here is synthetic.** The nodes describe the CargoQuote kit, a fictional freight
quoting service from [pumllint's governed-knowledge experiment](https://github.com/fdurieux/pumllint/tree/main/kg_experiment).
No bank-related data is stored in this repository; an organisation's own instance is created
from this structure inside its private repositories.

The proposal this follows: pumllint
[`docs/ieam-register-proposal.md`](https://github.com/fdurieux/pumllint/blob/main/docs/ieam-register-proposal.md).

The opportunity canvas, SWOT and a drawing of this repository:
[`docs/ieam-register-opportunity-canvas.html`](docs/ieam-register-opportunity-canvas.html)
(open the raw file in a browser; it is self-contained).

## What is where

| folder | holds | git is |
|---|---|---|
| `capabilities/ products/ journeys/ processes/ applications/ information/ organisation/` | one TOML file per node: id, kind, name, parent, state, owner, a pointer to the source of record, an approval | **authoritative** |
| `relationships/` | one file per relationship type: a type header (kinds, direction, inverse, cardinality per state, owner, evidence class, ARIS and Archi support status), then the links | **authoritative** |
| `metamodel/` `glossary/` `mapping/` `decisions/` `exceptions/` | the design contract, the approved terms, the tested mapping matrix, decision records, expiring exceptions | **authoritative** |
| `exports/<system>/<date>/` | a dated mirror of a source of record: a manifest of digests and ids, a reconciliation report | a mirror with provenance, never the record |
| `reports/<date>/` | coverage, impact and reconciliation summaries, written at a tag | derived, never the record |
| `tools/` | standard-library Python: the checker, reconcile, impact, inventory | |

The hierarchy inside a taxonomy is the `parent` field, never nested folders. Node ids are
`<PREFIX>-<4 digits>`: `CAP`, `PRD`, `JRN`, `PROC`, `APP`, `ENT`, `ORG`; links are `REL-…`.

## How to add a node

1. Copy a file of the same kind, give it the next free id, set `state = "draft"`.
2. Point `[source]` at the system of record and its id; write the `name` as that system has it.
3. Open a pull request. The checker runs: types, parent kind, cycles, duplicates, owner,
   glossary. A draft needs no approval.
4. Move it to `proposed`, then `approved` with an `[approval]` block naming the approver, the
   date and a decision record under `decisions/`. The checker refuses an approval without all
   three, and a state that skips a transition in `metamodel/lifecycle.toml`.

## How approval works

Approval is not a git feature. A node or link is approved when its file says
`state = "approved"` and carries `approval = { by, on, record }`; a cross-domain link needs both
owners. The pull request's merge records who changed the file; the approval block records who
approved the content. Deprecating a node fails the check on every approved link that still
references it; nothing is fixed automatically.

## The checks

```
python tools/check_register.py                      # the working tree
python tools/check_register.py --previous origin/main   # plus lifecycle transitions against a ref
python -m unittest discover -s tests
```

Errors fail the merge; warnings are reported. Three coverage rules carry exceptions:
C1, an approved journey step or touchpoint has a supporting process; C2, a capability an
approved product requires has a realising process; C3, a realising process names a diagram of
record. Coverage is always reported with its denominator and its exceptions; it is never a
percentage to pass.

## The questions the pilot answers

```
python tools/impact.py --from APP-0002     # which products and journeys does retiring QuoteAPI touch
python tools/check_register.py             # C1: journey steps without a process; C2: capabilities without a realising process
python tools/inventory.py > caps.txt       # the capability inventory for pumllint trace --fail-on-uncovered
```

## What is not here yet

No ARIS, Archi or EDM export route is tested. `exports/aris`, `exports/archi` and `exports/edm`
are empty, and every row of `mapping/matrix.toml` reads `unverified`. Those move only with a
test on a target installation and its evidence.

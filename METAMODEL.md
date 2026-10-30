# The metamodel, in prose

The design contract `metamodel/types.toml`, `lifecycle.toml` and `sources.toml` encode, for a
reader. Maintainer register.

**Node kinds.** Seven taxonomies, each with the IEAM's illustrative levels as kinds and an
allowed parent kind per level (`parent_of`). A taxonomy may use fewer levels; a kind with an
empty `parent_of` list is a root. The organisation taxonomy exists so that ownership is a link
(`owns`) and never a parent.

**Required fields.** Every node: `id`, `kind`, `name`, `state`, `owner`. Approved nodes add
`review_due` and `approval = { by, on, record }`. A `[source]` block names the system of record
and its id field (`aris_guid`, `archi_id`, `edm_id`, or `kit_path` in this test case) and the
export folder the name was checked against; a `diagram` field names the diagram of record for a
process (coverage rule C3).

**Relationship types.** Ten files under `relationships/`: `requires`, `concerns`,
`is_supported_by`, `realizes`, `delivers`, `supports`, `crud` (with `mode`), `manages`, `owns`,
`maps_to` (external target: the physical asset lives in the EDM). Each type header carries
source and target kinds, direction, inverse label, owner, evidence class, cardinality per
lifecycle state of the source, and the ARIS and Archi support status. The status values are the
IEAM's four plus `unverified`, the starting value, so an untested row cannot pass as native.

**Lifecycle.** `draft → proposed → approved → deprecated → retired`, `rejected` from `proposed`,
`draft` again from `rejected`, `approved` again from `deprecated`. The checker diffs states
against a git ref and refuses a skipped transition. Four eyes: the approver is not the author.

**What the register never holds.** The content of a node beyond its checked `name`: no
attributes copied from ARIS, Archi or the EDM. The moment a file carries a field the tool owns,
there are two records.

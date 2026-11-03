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

**Knowledge a person gave.** A link whose content rests on what a person said carries
`elicited = { from, on, record }`: an opaque handle (`types.toml` `[elicited]` `handle`, never a
name or an address), the date, and the path of the record of the answer. Such a link is due for
review within `lifecycle.toml` `[review.evidence]` `elicited` months (six) of `on`. Decision 0008;
knowgov's capture path writes the same three fields on the assertions it ingests.

**Issued handles.** `people/handles.toml` (`types.toml` `[elicited]` `issued`) lists the handles
the organisation has issued: handle, unit, roles (`gives`, `approves`, `closes`), issued and, once
retired, withdrawn; never a name. When it exists, `from` must be listed and live on `on`. A record
outside the register is `capture:<id>` (`external_record`), not resolved. The key from a handle to
a person is the organisation's directory. Decision 0009.

**What the register never holds.** The content of a node beyond its checked `name`: no
attributes copied from ARIS, Archi or the EDM. The moment a file carries a field the tool owns,
there are two records.

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
process (coverage rule C3). For ARIS, a process node's `aris_guid` is the GUID of its function's
definition, never an occurrence or a model; `diagram` is the GUID of the EPC model of record; the
register id rides on that definition in `sources.toml` `register_id_attribute` (`AT_ID` here), a
copy of the register's id that must agree with it (decision 0022).
The checker compares `name` with the name the latest export of the node's system (by folder date)
gives its id in `[ids]`: a difference is a `name` warning, an id the export no longer carries a `stale`
warning and no name finding, never a deletion; no exception excuses either. A node whose system has no
export, or whose `<path>#<part>` id names a part of a document the export carries whole, is unchecked
and counted (decision 0024, proposed).

**Relationship types.** Ten files under `relationships/`: `requires`, `concerns`,
`is_supported_by`, `realizes`, `delivers`, `supports`, `crud` (with `mode`), `manages`, `owns`,
`maps_to` (external target: the physical asset lives in the EDM). Each type header carries
source and target kinds, direction, inverse label, owner, evidence class, cardinality per
lifecycle state of the source, and the ARIS and Archi support status. The status values are the
IEAM's four plus `unverified`, the starting value, so an untested row cannot pass as native.

**Lifecycle.** `draft → proposed → approved → deprecated → retired`, `rejected` from `proposed`,
`draft` again from `rejected`, `approved` again from `deprecated`. The checker diffs states
against a git ref and refuses a skipped transition. Four eyes: the approver did not draft the change. For a pull request a session drafted, the session is the
author, not the account GitHub shows, and a session never approves (decision 0019).
An approved child of a deprecated or retired parent is a `lifecycle` error, a proposed or draft
one a warning (decision 0015).

**Coverage.** C1 to C3 are the README's. C4 (decision 0020): an approved process with an approved
`realizes` link to an approved capability is the target of an approved `supports` link from an approved
application or module, or in the scope of an unexpired exception of rule C4: a process manual by design,
or a phase-out whose `expires` is the date a replacement supports it. Both ends of both links approved, so
a deprecated application supports nothing.

**Knowledge a person gave.** A link whose content rests on what a person said carries
`elicited = { from, on, record }`: an opaque handle (`types.toml` `[elicited]` `handle`, never a
name or an address), the date, and the path of the record of the answer. Such a link is due for
review within `lifecycle.toml` `[review.evidence]` `elicited` months (six) of `on`. Decision 0008;
knowgov's capture path writes the same three fields on the assertions it ingests.

**Issued handles.** `people/handles.toml` (`types.toml` `[elicited]` `issued`) lists the handles
the organisation has issued: handle, unit, roles (`gives`, `approves`, `closes`), issued, an
optional `person` and, once retired, withdrawn; never a name. When it exists, `from` must be listed
and live on `on`. A record outside the register is `capture:<id>` (`external_record`), not resolved.
Decision 0009. A handle is one person in one role; `person` is the holder's directory identifier,
matching `[elicited]` `person`, never free text or a hand-typed address, and one `person` holds at
most one live handle per unit and set of roles (live: from `issued` to the day before `withdrawn`).
Where the holder is recorded instead (the private register or the directory) is the organisation's
choice; never a public repository. Decision 0021.

**The impact walk.** `tools/impact.py` follows approved links only, from the thing changed to
what rests on it (decisions 0007 and 0010): one row of `FORWARD` per start taxonomy, `owns` and
`maps_to` never walked, `parent` not descended by `walk`. A second, named walk, `--walk realisers`
(`REALISERS`, decision 0012): a capability to the processes that realise it and the
applications that support them; the default stays `dependants`.
`--children` (`walk_children`, decision 0014) also starts from every approved descendant by `parent`, each by its own row; others reported withdrawn; off by default.
The start is never among what a walk reaches, with or without `--children`: an edge back to it is reported, not counted; below a withdrawn descendant the descent continues to approved ones (decision 0016).
A third, named walk, `--walk thread` (`THREAD`, decision 0018): a step to its supporting process (`is_supported_by`), the process to what it realises, the applications that support it and the information it reads or writes (`realizes`, `supports` inverse, `crud`), an application to what it manages (`manages`); every step away from the journey.
Alignment rule A1 (`check_alignment`, decision 0018), warning only: an approved product with no approved journey; a capability it requires that its journeys' thread walk with `--children` does not reach; one reached that it does not require. Reported with its denominator; no exception mechanism.

**What the register never holds.** The content of a node beyond its checked `name`: no
attributes copied from ARIS, Archi or the EDM. The moment a file carries a field the tool owns,
there are two records.

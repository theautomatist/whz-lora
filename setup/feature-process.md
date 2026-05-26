# Feature Process

This file drives the feature process — adding, changing or removing a
feature while keeping the feature registry accurate. The registry is the
single source of truth for what the product does.

It runs two ways:

- Manually, via the `/feature` skill.
- Auto-proposed: when a PO request clearly adds, changes or removes a
  feature, the main session proposes it (see `CLAUDE.md`, Feature
  Lifecycle). Minor work — typo, small bugfix, refactor — stays a plain
  directive.

The project must already be onboarded — the concept paper and the seeded
feature registry must exist. If not, onboard first.

## Runbook

### Step 1 — Classify

The change: **add** a new feature, **change** an existing one, or **remove**
one.

### Step 2 — Feature interview

Clarify the feature in a short, focused interview, using the dialogue style
of the onboarding (`setup/interview.md`, "How each question is asked" —
options, "I need help deciding", draft-and-react). A handful of questions,
not a full onboarding.

- Add: what the feature does, its user-facing behavior, acceptance
  criteria, dependencies on other features, the interfaces and data it
  touches.
- Change: what changes and why; the effect on the feature's acceptance
  criteria and on anything that depends on it.
- Remove: why; what depends on it; deprecate first or remove immediately;
  any migration needed.

### Step 3 — Impact analysis

Check the registry: which other features does this touch through
dependencies? Surface conflicts and knock-on changes before building.

Also check team capability: does this feature introduce a domain the
current team is not equipped for — a first real UI, hardware, a regulated
area? If so, apply the "Extending the Team" procedure in `CLAUDE.md`; the
specialist is proposed here and signed off with the feature at Step 5.

### Step 4 — Registry draft

Create, update or mark-removed the feature entry, using the template below.

### Step 5 — PO sign-off

Present the drafted entry and the impact. The PO confirms before any build.

### Step 6 — Build

A feature add or a behavioural change is full work: create the directive —
a GitHub issue referencing the feature ID — and run the directive lifecycle
(`CLAUDE.md`). The feature entry is the directive's specification and the
Step 5 sign-off is its Gate 1, so the lifecycle is entered directly at
Build; intake, specification and Gate 1 are already satisfied. The issue is
self-contained — it links the feature entry, the research from Step 2 and
related ADRs. The registry entry links back to the directive.

A change with no code impact — a registry-text correction — has no build:
skip directly to Step 7.

### Step 7 — Registry sync

As the change is documented (the directive's Document step), update the
feature entry — status and history — so the registry matches reality. This
happens before Gate 2: a feature-affecting directive is not done until the
registry reflects it.

## The Feature Registry

### Layout — it grows with the project

- Few features: a single file, `docs/developer/features.md`.
- Past ~8 features: the process migrates to a folder
  `docs/developer/features/`, one file per feature, and updates the mkdocs
  navigation.
- Large: feature files are grouped into area subfolders, organically, once
  clear areas exist.

The feature process performs each migration automatically when a new
feature crosses the threshold. Onboarding seeds the registry directly in
the layout that fits the seeded count — more than eight seeded features
start in the folder layout.

### Status values

`proposed`, `active`, `deprecated`, `removed`. A removed feature keeps its
entry, marked `removed`, with the reason — the registry records what was
removed and why.

### Feature entry template

```
### F-NNNN — <name>

- Status: proposed | active | deprecated | removed
- Summary: <one or two sentences>
- Problem solved: <why it exists>
- User-facing behavior: <what the user can do>
- Acceptance criteria:
  - <testable statement>
- Dependencies: <other feature IDs, or none>
- Interfaces & data: <what it touches>
- Realised by: <for a product feature in a multi-repo main registry, the
  sub-repositories and their component features; otherwise n/a>
- Linked directives / ADRs: <issue numbers, ADR ids>
- History: <YYYY-MM-DD added; YYYY-MM-DD changed …>
```

## Two levels — multi-repository products

In a single-repository project, or in a sub-repository, registry entries
are **component features** — the full detail of what that codebase does.

In the **main repository** of a multi-repository product, entries are
**product features** — a capability as the user experiences it, listing
which sub-repositories realise it and linking to their component features.
The main registry indexes and coordinates; it does not duplicate the
sub-repositories' detail.

A feature spanning repositories starts as a product feature in the main
repository; the feature process then runs in each affected sub-repository
for its component part.

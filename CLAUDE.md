# Project — AI-Assisted Development

This project rests on a reusable base ("pillars"), identical across all
projects. Project-specific content is filled in; the pillars stay constant.

## First Run — Project Onboarding

Onboarding produces the concept paper at
`docs/developer/concept/concept-paper.md`. While its `Onboarding status` is
not `complete`, the project is not onboarded: before any other work, run the
`onboarding` skill (`/onboarding`). It is a funnel — it narrows the project
space cluster by cluster into the concept paper, then tunes this file and
the agents to the project. Once `complete`, skip this; the PO may re-run
`/onboarding` anytime.

## Guiding Principle: KISS

Keep It Simple — every process, workflow, data structure and document.
Prefer the simplest option that works. Add no agent, tool, layer or step
without a concrete need. Simplicity is the default; complexity must be
justified.

## The Five Pillars

| # | Pillar | Artifact |
|---|---|---|
| 1 | Process & Standards | this document |
| 2 | Documentation & Knowledge System | `docs/developer/`, `docs/user/`, `mkdocs.*.yml`, `export/` |
| 3 | AI Development Team | `.claude/agents/` |
| 4 | Quality Assurance | `.claude/settings.json`, `.claude/hooks/`, `.github/workflows/` |
| 5 | Infrastructure & Resources | `.mcp.json`, `infra/` |

## The Team

| Agent | Role | Model | Used in |
|---|---|---|---|
| `spec-analyst` | Analyst — turns a directive into a testable spec | Sonnet | Lifecycle step 2 |
| `implementer` | Builder — writes code and tests | Sonnet | Lifecycle step 5 |
| `reviewer` | Controller — reviews critically, read-only | Opus | Lifecycle step 5 |
| `research` | Researcher — focused per brief | Sonnet | as needed |

The main session leads: it plans, fans out agents, synthesizes results,
decides. Subagents cannot start subagents — all branching goes through the
main session.

### Extending the Team

The four agents above are the fixed base team — every project has them. A
project may also need a **specialist**: a UI/UX controller for a product
with a real interface, a domain researcher for hardware datasheets. The
base team is never changed; specialists are added on top.

A specialist is a specialization of one archetype and inherits its profile:

| Archetype | Base agent | Model | Tools | Writes code |
|---|---|---|---|---|
| Analyst | `spec-analyst` | Sonnet | read, web | no |
| Builder | `implementer` | Sonnet | read/write, Bash | yes |
| Controller | `reviewer` | Opus | read-only | no |
| Researcher | `research` | Sonnet | read, web, MCP | no |

Add a specialist only when all three hold — otherwise take the cheaper rung:

- Recurring — the need spans many directives. One-off → a `research` brief.
- Distinct competence — domain knowledge or judgment the base team lacks
  (UI/UX heuristics, datasheet analysis), not more of the same. Otherwise →
  a review dimension on `reviewer`, or guidance in an existing agent's prompt.
- Better persistent — a focused prompt with its own context window
  measurably beats instructing an existing agent.

The main session proposes the specialist; the PO signs off (a team change);
it is recorded as an ADR and added to the table in "The Team". This is
assessed at onboarding (interview theme 22) and whenever a feature
introduces a domain the team is not equipped for (feature process, Step 3).
A new specialist follows the structure of the existing agent files. A
specialist that stops earning its place is removed (KISS).

## The Directive Lifecycle

The Product Owner (PO) gives directives; the team specifies, builds,
verifies and documents them. Each directive runs these stages:

1. Intake & Triage — the PO brings a directive to the main session, the
   PO's single point of contact. The main session clarifies it in a short
   dialogue, classifies it (plain directive or feature; lightweight or
   full — see Triage), and records it as a GitHub issue. A feature switches
   to the feature process. The PO may also file a simple issue directly.
2. Specification — for a full task, `spec-analyst` writes a specification
   with explicit, testable acceptance criteria into the issue; for a
   lightweight task, the main session writes a one-line spec directly.
3. GATE 1 (PO) — the PO signs off the specification. No build before this.
4. Plan — the main session plans the build approach and creates the
   working branch and the draft pull request. Branch name mirrors the
   Conventional Commits type + the issue number (`feat/123-add-login`,
   `fix/124-typo`).
5. Build — `implementer` writes code and tests on the branch; the
   quickcheck hook runs; CI runs on each push; `reviewer` reviews and the
   main session posts the review report as a PR comment; `implementer`
   reworks BLOCKERs (from reviewer, CI or quickcheck). Repeat until no
   BLOCKERs remain — at most three rounds, then escalate. Lightweight
   directives skip the reviewer; the main session checks the diff itself.
6. Verify — check the result against the step-2 acceptance criteria. CI
   (GitHub Actions) must be green; the project's verification check (the
   method set at onboarding for its artifact type) confirms the build is
   sound.
7. Document — update developer documentation, and user documentation if the
   change is user-facing; write an ADR for architecture decisions.
8. GATE 2 (PO) — the PO approves the pull request (`gh pr review --approve`).
   Branch protection on main requires this before merge.
9. Close — the PR is squash-merged into main and closes the issue
   (`closes #N`); the merged branch is auto-deleted; the main session
   fills the issue's process log before closing.

Between Gate 1 and Gate 2 the team works autonomously: the main session
runs build, verification and documentation and returns to the PO only at
the two gates or to escalate.

### Triage

Triage happens at intake (step 1), before the specification:

- Lightweight (small bugfix, docs, one-liner): the main session writes the
  one-line spec itself; Gate 1 is a brief PO confirmation.
- Full (feature, architecture change, new dependency): run all steps, with
  `spec-analyst` writing the specification.

When in doubt, choose Full.

### Escalation

If a directive proves infeasible or a blocker cannot be cleared, work stops:
label the issue `blocked` and report to the PO with a summary and options.
Never silently lower quality to "finish".

### Status Labels

Each open directive issue carries one stage label, so progress is visible
at a glance:

- `spec` — Steps 2–3 (specification + Gate 1).
- `building` — Steps 4–5 (plan + build, the autonomous code phase).
- `verify` — Steps 6–7–8 (verify, document, Gate 2 PR review).
- `blocked` — replaces the current stage label on escalation; restored or
  advanced when work resumes.

The main session swaps the label at each transition (`gh issue edit
--remove-label X --add-label Y`). A closed issue is done — no stage label.
The labels are created during onboarding (Step 7).

## The Two Gates

Both gates belong to the PO and apply to every directive — for a
lightweight task as a brief confirmation, for a full task as a formal
sign-off:

- Gate 1 — Spec sign-off (issue checkbox): the PO confirms the
  specification matches intent before any code. The Definition of Ready.
- Gate 2 — Delivery acceptance (PR review approval): the PO approves the
  pull request. Branch protection on main enforces this. The Definition
  of Done.

## Feature Lifecycle

The feature registry (`docs/developer/features.md`, a `features/` folder
past ~8 features) is the single source of truth for what the product does.

When a PO request clearly adds, changes or removes a feature, propose the
feature process (the `/feature` skill) before treating it as a plain
directive. Minor work — typo, small bugfix, refactor — stays a plain
directive; the feature process is for capabilities.

It classifies the change (add / change / remove), clarifies it in a short
interview, analyses the impact on other features, drafts the registry
entry, takes PO sign-off, then hands the build to the directive lifecycle;
the registry is updated before Gate 2. Full runbook:
`setup/feature-process.md`.

## Core Principles

- KISS — see above; the overriding rule.
- Docs grow with the code. Record every notable architecture decision as an
  ADR in `docs/developer/decisions/` during step 7, not afterwards.
- Diagrams over prose. Flows, structures and timelines are Mermaid
  diagrams, not paragraphs.
- Control is separate from building. The reviewer has no write access; its
  findings go to the main session, which decides.
- Least privilege. Each agent only sees the tools in its capability profile.
- Self-contained directives. A directive issue links its specification,
  research findings, feature entry and related ADRs — the builder has
  everything. The builder does not re-research; it only looks up library
  and API documentation, via MCP servers or official docs.

## Commit Standards

Commits are uniform and reproducible — Conventional Commits:

```
<type>(<scope>): <short summary>
```

- Types: feat, fix, docs, refactor, test, chore, build.
- Summary in imperative mood, lower case, no trailing period, max 72 chars.
- One logical change per directive; the PR is squash-merged into main, so
  one main commit reflects the directive as a whole.
- Branch name mirrors the commit type plus the issue number — for example
  `feat/123-add-login`, `fix/124-typo-readme`.
- Reference the directive issue in commit bodies with `refs #N`; the PR
  squash-commit uses `closes #N`. Merged branches are auto-deleted.

A documented standard, not a separate agent — the implementer and main
session follow it directly (KISS).

## Research Budget

To cap cost when fanning out in parallel:

- at most 2 `research` agents in parallel per wave,
- at most 2 waves per question (scan broad, then go deep),
- every call gets one clear, focused brief.

Research findings the team will need are saved to `docs/developer/research/`
by the main session (the `research` agent is read-only), added to the
developer-docs navigation, and linked from the directive that uses them —
researched once.

## Documentation

Two separate sites, for two audiences:

- Developer documentation — `docs/developer/`, built with
  `mkdocs.developer.yml`. For contributors: concept, features, research,
  architecture, diagrams, decisions, onboarding.
- User documentation — `docs/user/`, built with `mkdocs.user.yml`. For end
  users: getting started, guides, FAQ. Plain language, no technical
  background assumed.

Web view: `mkdocs serve -f mkdocs.developer.yml` (or `mkdocs.user.yml`).
Export: `export/build.ps1` builds both sites.

## Definition of Done

A task is done when:

- automated local checks (the quickcheck hook) pass,
- the reviewer report has no open BLOCKER items (for full tasks),
- the acceptance criteria from the specification are all met,
- tests cover the change,
- the project's verification check passes (locally, until the GitLab
  move — see ADR-0017),
- for feature-affecting work, the feature registry reflects the change,
- developer and, if user-facing, user documentation are updated,
- Gate 2 (PO acceptance) has passed.

## Testing

Test at several levels, cheap and fast first (the test pyramid):

- Unit — a single piece in isolation.
- Integration — pieces working together, e.g. code and database.
- End-to-end — the whole system through its real interface.
- Verification check — the project's artifact-appropriate confirmation that
  the build is sound: a service deploys in a container and its main paths
  respond; a CLI installs and runs; a library imports and works; firmware
  builds and, where a rig exists, flashes and reports. The concrete method
  is set at onboarding and recorded in the concept paper.

Unit, integration and end-to-end tests run in ephemeral Docker containers —
every run clean and reproducible. The concrete levels and tools are decided
per project during onboarding.

**Until the project migrates from GitHub to self-hosted GitLab, verification
runs locally on the developer host, not in CI** — see ADR-0017. The
`.github/workflows/ci.yml` workflow stays in the repository as the future
basis for the GitLab CI port; it is not the gate. The verification evidence
for Gate 2 is the verbatim smoke-test output pasted into the pull-request
review.

## Releases

A release bundles accepted directives into a delivered version. Before
every release, the main session:

1. User-documentation walkthrough — in a fresh, clean environment (an empty
   Docker container where the artifact runs in one), with only the user
   documentation (`docs/user/`), set up and operate the software strictly
   by following it. Any step that is missing, ambiguous or needs an
   unstated assumption is a documentation gap to fix. This verifies the
   user documentation is correct and complete for a real, uninformed user.
2. Verification check — confirm the release artifact passes the project's
   verification check.
3. Version & changelog — bump the version (semantic versioning) and update
   `CHANGELOG.md`.

A release is done only when the user-documentation walkthrough has no open
gaps.

## Infrastructure & Guardrails

- Resource access only via the MCP layer or CLI behind permission rules —
  see `infra/README.md`.
- Agents work exclusively in the separate sandbox account, never in
  production.
- Test execution is isolated in ephemeral Docker containers.
- Credentials only via environment variables — never in an agent prompt or
  the repository.
- Tooling the project itself needs but does not exist (a custom MCP server,
  a CLI bridge to specialised hardware, an adapter for an uncommon
  interface) is a valid directive — built within the project, kept simple,
  integrated via `.mcp.json` and `infra/`. See `infra/README.md`, Extension
  Stages.

## Project-Specific

**Project**: whz-lora — selbst betriebene LoRaWAN-Basis an der WHZ für
Forschungs-Sensorik. Single-host Docker-Compose-Stack, Größe „Klein".
Vollständige Definition: `docs/developer/concept/concept-paper.md`.

### Stack & Layout

- **LoRaWAN Network Server**: ChirpStack v4 (siehe
  `docs/developer/decisions/adr-0001-lns-stack-chirpstack-v4.md`).
- **Begleitende Container** (alle aus dem offiziellen `chirpstack-docker`
  Compose abgeleitet): ChirpStack, ChirpStack Gateway Bridge (UDP),
  ChirpStack Gateway Bridge (Basics Station), Mosquitto, PostgreSQL,
  Redis, REST-API-Proxy.
- **Eigene Code-Anteile** (erwartet klein):
  - Geräte-Codecs in JavaScript (im LNS hinterlegt, separat versioniert).
  - Ein Smoke-Test-Skript (Python oder PowerShell) für den
    Verifikationscheck.
  - `.env.example` für Konfiguration.
- **Test-Container**: `chirpstack-simulator` (separates Image, im
  test-compose nachgeladen) zum Erzeugen synthetischer Uplinks.
- **Doku-Sprache**: Englisch (Developer und User).

### Verzeichnis-Layout (Soll-Zustand)

```
.
├─ docker-compose.yml          # Produktiv-Stack
├─ docker-compose.test.yml     # Smoke-Test-Overlay (Simulator)
├─ .env.example
├─ chirpstack/                 # ChirpStack-Konfig (region_eu868.toml, ...)
├─ mosquitto/                  # Mosquitto-Konfig + ACL
├─ codecs/                     # Device-Codecs (JS)
├─ scripts/smoke-test.ps1      # Verifikationscheck
└─ docs/                       # mkdocs-Sites (unverändert)
```

### Befehle

| Zweck | Befehl |
|---|---|
| Stack starten | `docker compose up -d` |
| Stack stoppen | `docker compose down` |
| Verifikationscheck (lokal) | `./scripts/smoke-test.ps1` |
| Doku-Build (Entwicklung) | `mkdocs serve -f mkdocs.developer.yml` |
| Doku-Build (Nutzer) | `mkdocs serve -f mkdocs.user.yml` |
| Doku-Export | `./export/build.ps1` |

Build/Lint-Schritte für eigenen Code (Codec-JS, Smoke-Test-Skript) liegen
in `.claude/hooks/quickcheck.ps1`. Die CI-Steps in
`.github/workflows/ci.yml` sind der Basisentwurf für den späteren
GitLab-Port (siehe ADR-0017) — aktuell ist die Verifikation lokal.

### Lokale Voraussetzungen (für den Verifikationscheck)

| Tool | Zweck |
|---|---|
| Docker Desktop für Windows | LNS-Stack-Laufzeit |
| Python 3.12+ | Smoke-Test (`scripts/smoke_test.py`) |
| Node.js 20+ | Codec-Unit-Tests (`node --test codecs/*.test.js`) |
| `gh` CLI | Issues, PRs, Labels |
| `pip install -r scripts/requirements-test.txt` | `chirpstack-api`, `paho-mqtt`, `cryptography` |

Für Bring-up echter Kerlink-Hardware zusätzlich (siehe
[ADR-0018](docs/developer/decisions/adr-0018.md) +
[user-doc](docs/user/kerlink-ifemtocell-bring-up.md)):

- Zwei Windows-Firewall-Regeln (UDP 1700 + ICMPv4), einmalig per
  elevated PowerShell.
- Ein USB-C-Datenkabel für den Gateway-Anschluss.

Der lokale Verifikationsablauf für eine Direktive:

```powershell
docker compose up -d --wait                    # Stack hochfahren
py -3.12 scripts/smoke_test.py                 # End-to-End-Smoke-Test
node --test codecs/*.test.js                   # Codec-Unit-Tests
docker compose down -v                         # sauberer Teardown
```

Erfolgs-Output des Smoke-Tests wird wörtlich in den PR-Review-Kommentar
geklebt — das ist die Gate-2-Evidenz.

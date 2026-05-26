# Project Template — AI-Assisted Development Base

A reusable template for projects built by an AI development team, steered by
a Product Owner. The PO gives directives; the team specifies, builds,
verifies and documents them. Every project rests on five strategically
identical pillars; only the project-specific content is filled in.

## Guiding Principle

KISS — Keep It Simple. The simplest option that works wins; complexity must
be justified. See `CLAUDE.md`.

## The Five Pillars

| # | Pillar | Artifact |
|---|---|---|
| 1 | Process & Standards | `CLAUDE.md` |
| 2 | Documentation & Knowledge System | `docs/developer/`, `docs/user/`, `mkdocs.*.yml` |
| 3 | AI Development Team | `.claude/agents/` |
| 4 | Quality Assurance | `.claude/settings.json`, `.claude/hooks/`, `.github/workflows/` |
| 5 | Infrastructure & Resources | `.mcp.json`, `infra/` |

## The Team

| Agent | Role | Model |
|---|---|---|
| `spec-analyst` | Analyst — turns a directive into a testable spec | Sonnet |
| `implementer` | Builder — writes code and tests | Sonnet |
| `reviewer` | Controller — reviews critically, read-only | Opus |
| `research` | Researcher — parallelizable, focused per brief | Sonnet |

Building and control are separated; the main session orchestrates. This
base team is fixed; projects add specialist agents (a UI/UX expert, a
domain researcher) when a domain earns one — see `CLAUDE.md`.

## The Directive Lifecycle

The PO brings each directive to the main session as a conversation. It runs
through the directive lifecycle: intake & triage (the main session
clarifies it and records a GitHub issue), specification, PO sign-off
(Gate 1), plan, build, verify, document, PO acceptance (Gate 2), close. Two
gates belong to the Product Owner; between them the team works
autonomously. Full details in `CLAUDE.md`.

## The Feature Lifecycle

The feature registry (`docs/developer/features.md`) is the single source of
truth for what the product does. When a request adds, changes or removes a
feature, the feature process (`/feature`) keeps the registry accurate and
hands the build to the directive lifecycle. Full details in `CLAUDE.md`.

## Multi-Repository Projects

A product may span several repositories — a main repository that
coordinates plus one sub-repository per independently deployable package.
Every repository is its own instance of this template. Full details in
`CLAUDE.md`.

## Prerequisites

Install once on the host before instantiating or running a project:

- Python 3 + pip — builds the documentation sites
- Node.js — MCP servers are launched via `npx`
- Docker — isolated, reproducible test runs
- git + GitHub CLI (`gh`) — the directive lifecycle (issues, CI, pull requests)

## Create a New Project

```powershell
.\scripts\init-project.ps1 -Name "MyProject" -Target "C:\Users\Carl\Projekte"
```

Then start Claude Code in the new project. On its first run it conducts the
onboarding interview (`setup/interview.md`) — it asks about the tech stack,
data structures, data flow and more, then tunes `CLAUDE.md`, the agents,
the hooks and CI to the project. You can also start or re-run it
deliberately at any time with the `/onboarding` command.

## View the Documentation

```powershell
pip install -r requirements.txt
mkdocs serve -f mkdocs.developer.yml   # developer docs
mkdocs serve -f mkdocs.user.yml        # user docs
.\export\build.ps1                     # builds both static sites
```

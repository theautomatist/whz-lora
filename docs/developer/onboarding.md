# Onboarding — How This Project Works

This page is the entry point for anyone joining the project. It explains
how work flows, so the work can be understood and continued by anyone.

## The Idea

The project is built by an AI development team, steered by a Product Owner
(PO). The PO gives directives; the team specifies, builds, verifies and
documents them. The whole setup rests on five pillars — see `CLAUDE.md`.

## The Team

- `spec-analyst` — turns a directive into a testable specification.
- `implementer` — writes code and tests.
- `reviewer` — reviews critically, read-only.
- `research` — gathers information on focused questions.

The main session is the team lead and orchestrates all of them.

## How Work Flows

The PO brings a directive to the main session — his single point of
contact — as a conversation. The directive then runs the lifecycle (see
`CLAUDE.md`): intake & triage (the main session clarifies it, classifies it
and records a GitHub issue), specification, PO sign-off (Gate 1), plan,
build, verify, document, PO acceptance (Gate 2), close. Two gates belong to
the PO — the spec sign-off before building and the delivery acceptance at
the end; between them the team works autonomously.

Work that adds, changes or removes a feature first runs the feature process
(the `/feature` skill): it keeps the feature registry — the single source
of truth for what the product does — accurate, then hands the build to the
directive lifecycle above.

A product may span several repositories (a main repository plus
sub-repositories). See `CLAUDE.md`, Multi-Repository Projects.

## Where Things Live

| You want… | Look in |
|---|---|
| The process and standards | `CLAUDE.md` |
| The onboarding interview | `setup/interview.md` |
| The project concept paper | `docs/developer/concept/concept-paper.md` |
| The feature registry | `docs/developer/features.md` |
| The feature process | `setup/feature-process.md` |
| The AI team definitions | `.claude/agents/` |
| Architecture decisions | `docs/developer/decisions/` |
| User-facing documentation | `docs/user/` |
| Infrastructure and access model | `infra/README.md` |
| Directives and their status | GitHub issues |

## Traceability

Each directive issue links to the commits and the pull request that
implement it (`closes #N`). To understand why something was built a
certain way, follow the issue and the related ADR.

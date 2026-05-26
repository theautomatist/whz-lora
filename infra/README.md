# Pillar 5 — Infrastructure & Resources

This pillar governs how the AI team accesses resources beyond the local
machine — version control, browser automation, cloud, pipelines, containers.

## The 3-Layer Access Model

Agents get capabilities, not keys.

| Layer | Function | Location |
|---|---|---|
| 1. MCP server | Wraps a resource behind clean tools; credentials live in the server | `.mcp.json` |
| 2. Tool scoping | Each agent lists exactly its allowed tools in the `tools:` frontmatter | `.claude/agents/*.md` |
| 3. Permissions | Allow/deny rules gate concrete commands | `.claude/settings.json` |

## Capability Profiles

| Agent | Local R/W | Web static | Web dynamic | Bash/CLI |
|---|:--:|:--:|:--:|:--:|
| `spec-analyst` | read-only | yes | - | - |
| `implementer` | yes | - | - | yes |
| `reviewer` | read-only | - | - | read-only |
| `research` | read-only | yes | yes (`browser` MCP) | - |

The hard boundary is the tool grant (Layer 2): a capability an agent must
not have is simply withheld from its `tools:` list. The read-only columns
above and the boundaries stated in each agent's prompt — for example the
`reviewer` running Bash "read-only" — are prompt-level constraints, not
technically enforced; the agent holds the full `Bash` tool. The real
safeguards are least privilege plus the sandbox account.

## Current Wiring

- GitHub — directive backlog (issues) and CI (Actions), accessed via the
  `gh` CLI behind permission rules. Traceability comes from issues linked
  to commits and pull requests (`closes #N`).
- browser — Playwright MCP (`.mcp.json`). Covers dynamic, JavaScript-heavy
  websites (replaces the originally considered Selenium grid). Used by the
  `research` agent. Launched via `npx`, so Node.js must be on the host.
- Cloud / pipelines — via their respective CLIs (`aws`, `gcloud`, `az`)
  behind permission rules. No custom MCP servers are built as long as
  ready-made solutions or CLIs are sufficient (KISS).
- Test isolation — ephemeral Docker containers, no VM pools.

## Guardrails

- All agent activity runs exclusively in the separate sandbox account.
- Destructive cloud operations are blocked per project under `deny` in
  `.claude/settings.json`.
- Credentials only via environment variables — never in the repo, never in
  an agent prompt.
- Start long-running infra jobs as background agents so the main session is
  not blocked.

## Open Items

- `.mcp.json` pins `@playwright/mcp@latest`. For a reproducible production
  setup, pin a tested version once one is verified.
- The `deny` list is a guardrail against accidents, not a security
  boundary: rules are pattern-based and tool-scoped — the `Bash` and
  `PowerShell` tools are gated by separate `Bash(...)` and `PowerShell(...)`
  rules, and a paraphrased command can slip a pattern. The real protection
  is least privilege and the sandbox account. Before granting real
  cloud-CLI access, add deny rules for destructive operations (delete,
  terminate, force) for every tool that can invoke them.
- Hooks and scripts are PowerShell (`.ps1`) — Windows-only. The CI workflow
  runs on Linux; keep stack checks defined in both places consistent, or
  provide a cross-platform hook.

## Extension Stages

- A custom MCP server is built only when a real gap remains that CLIs or
  ready-made MCP servers cannot close — and then with a clearly defined
  tool contract (tool names, parameters, error behavior).
- OpenProject (or a comparable PM tool) becomes worthwhile only when
  portfolio management across several projects and capital/cost tracking
  become a priority. Until then GitHub issues are sufficient (KISS).

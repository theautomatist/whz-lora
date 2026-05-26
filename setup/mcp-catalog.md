# MCP Catalog

A curated, stack-agnostic reference list of MCP (Model Context Protocol)
servers that have proved useful across projects. Onboarding consults it
first (`setup/interview.md`, theme 21) and goes beyond it only where it
does not cover the project's need.

Nothing in this catalog is auto-active. Each project picks what it needs
during onboarding; selected entries are wired into `.mcp.json` (and the
relevant agents' `tools:`). MCP servers that prove generally useful are
added back here so the knowledge compounds across projects.

The only MCP shipped active in the template is `browser` (Playwright).
Custom, project-specific MCP servers — built when no catalog entry or
ready-made server covers the need (a hardware bridge, an uncommon
interface) — are a valid directive in the regular lifecycle, see
`infra/README.md`, Extension Stages.

When adopting a server in `.mcp.json`, prefer pinning a tested version to
`@latest` for reproducibility (`infra/README.md`, Open Items).

## Entries

### browser — Playwright (shipped active)

- Purpose: dynamic, JavaScript-heavy websites; used by the `research` agent.
- Command: `npx -y @playwright/mcp@latest`
- Link: https://github.com/microsoft/playwright-mcp

### filesystem

- Purpose: structured access to a constrained set of filesystem paths
  outside the repository (for example a data directory or shared assets).
- Command: `npx -y @modelcontextprotocol/server-filesystem <path>`
- Link: https://github.com/modelcontextprotocol/servers

### fetch

- Purpose: HTTP fetch and simple web content retrieval as a tool.
- Command: `npx -y @modelcontextprotocol/server-fetch`
- Link: https://github.com/modelcontextprotocol/servers

### github

- Purpose: deeper, structured access to the GitHub API beyond the `gh` CLI
  (cross-repository queries, code search, richer attachments).
- Command: `npx -y @modelcontextprotocol/server-github`
- Link: https://github.com/modelcontextprotocol/servers

### sequential-thinking

- Purpose: explicit chain-of-thought scaffolding for hard reasoning tasks.
- Command: `npx -y @modelcontextprotocol/server-sequential-thinking`
- Link: https://github.com/modelcontextprotocol/servers

### postgres

- Purpose: query a PostgreSQL database safely (read-mostly by default).
- Command: `npx -y @modelcontextprotocol/server-postgres <connection-uri>`
- Link: https://github.com/modelcontextprotocol/servers

### sqlite

- Purpose: query a SQLite database file.
- Command: `npx -y @modelcontextprotocol/server-sqlite <path>`
- Link: https://github.com/modelcontextprotocol/servers

### memory

- Purpose: a small persistent knowledge graph the team can build up during
  long-running work.
- Command: `npx -y @modelcontextprotocol/server-memory`
- Link: https://github.com/modelcontextprotocol/servers

## Adding an entry

Use the format above: name as a `###` heading, three bullets — Purpose,
Command, Link. Keep Purpose to one line; the catalog earns its place by
being quick to scan.

# Project Onboarding Interview

This file drives the first-run interview. Onboarding is a funnel: the
project space starts unbounded and is narrowed — cluster by cluster,
question by question — into a complete concept paper at
`docs/developer/concept/concept-paper.md`. While that paper's `Onboarding
status` is not `complete`, onboarding runs or continues. After the funnel,
the main session tunes the project to the result.

Below: the runbook, then the question catalog.

## Runbook — how to run the interview, start to finish

### Step 1 — Kick off

Before asking anything, orient the PO in plain language:

- What this is — a guided interview that narrows the project into a concept
  paper.
- How it works — four rounds (the clusters); you confirm the result after
  each.
- It is interactive — every question is a small dialogue with options. One
  is always "I need help deciding": choose it and the main session
  researches the topic and returns with a plain-language explanation and a
  pros/cons table.
- You stay in control — pause and resume anytime, nothing is final until
  you confirm it, and you can revise earlier answers at any checkpoint.

### Step 2 — Project sizing

Ask one question first: small tool, medium application, or large system?
Calibrate the rest from the answer — how deep to go, which themes to cover
fully and which to touch lightly or skip (KISS) — and give the PO a rough
time expectation.

### Step 3 — Run the four narrowing rounds

For each cluster A, B, C, D, in order:

a. **Orient** — tell the PO where they are: "Round N of 4 — <cluster
   name>", and what is still open.
b. **Ask** the cluster's themes as dialogues — see "How each question is
   asked".
c. **Checkpoint** — synthesize: show before and after ("was open: … — now
   bounded to: …"), write the result into the matching concept-paper
   section, and ask the PO to confirm. The checkpoint is also a correction
   point — the PO may change anything, including earlier rounds.

Cluster D has two research-driven steps — theme 20 (tech-stack evaluation)
and theme 21 (setup recommendations). Before each, tell the PO the main
session will go research and return with a recommendation.

| Cluster | Concept-paper section |
|---|---|
| A — Foundation | 1. Foundation |
| B — Interfaces & Data | 2. Interfaces & Data |
| C — Operations & Quality | 3. Operations & Quality |
| D — Closing | 4. Infrastructure, Risks & Decisions |

If you are onboarding the **main repository** of a multi-repository
product, run clusters A and D (theme 20 self-excludes — the coordination
repo has no application stack) and skip the application-level themes of
clusters B and C — data structures, data flow, storage, detailed quality —
which belong to the sub-repositories. The deliverable is the manifest and
the split, not an application concept paper.

If the interview is paused, resume from the first cluster not yet narrowed
in the concept paper.

### Step 4 — Close and hand off

When all four rounds are confirmed:

1. Present the finished concept paper and set its `Onboarding status` to
   `complete`; confirm the `Project` field and set `Last updated`. The
   paper holds the converged project definition, including the co-developed
   data model and data-flow diagrams.
2. Seed the feature registry. First confirm the core feature list in the
   concept paper (section 1) — the named capabilities drawn from clusters A
   and B; draft it, have the PO confirm. Then create one registry entry per
   feature in `docs/developer/features.md` (see `setup/feature-process.md`).
   If more than eight features are seeded, apply the per-file folder layout
   (`docs/developer/features/`) from the start.
   For a multi-repository product, also create the manifest
   (`repositories.md`) and the list of sub-repositories. The PO instantiates
   each one by running `scripts/init-project.ps1` from the pristine
   template; the main session then pre-seeds its concept paper — inherited
   product context filled in, the parts specific to the sub-repository
   marked open, status `in progress`. Each sub-repository is then onboarded
   in its own instance, where `/onboarding` walks the funnel over the
   pre-seeded paper — see `CLAUDE.md`, Multi-Repository Projects.
3. Fill the "Project-Specific" section of `CLAUDE.md` — stack, layout,
   build/test/lint commands. Remove sections that do not apply — for a
   single-repository project, delete "Multi-Repository Projects" so
   `CLAUDE.md` stays lean.
4. Apply the accepted setup recommendations (theme 21) — wire MCP servers
   into `.mcp.json`, scaffold recommended skills under `.claude/skills/`,
   and give the PO a checklist for tools needing manual installation.
5. Tune the team — add project-specific guidance to the agent files,
   adjust their `tools:` or `model:` where warranted (including newly added
   MCP servers), add review dimensions to the `reviewer` if needed. If a
   shipped MCP server is not used by this project, remove it from
   `.mcp.json` and from every agent's `tools:`.
6. Configure the quality gates and tooling — fill
   `.claude/hooks/quickcheck.ps1` with the stack's real commands and its
   code file extensions (`$codeExtensions`), fill `.github/workflows/ci.yml`
   with the stack's real commands, create the test-container definition
   (Dockerfile / compose) for the isolated, reproducible test runs
   `CLAUDE.md` requires, and set the `language:` field in each mkdocs
   config to that site's documentation language (theme 18 — developer and
   user docs may differ).
7. Set up version control and repository policy — the project is already
   a fresh git repository (`init-project.ps1` runs `git init`). With the
   PO:
   - create the GitHub repository (`gh repo create`);
   - enable squash-merge and auto-delete of merged branches
     (`gh repo edit --enable-squash-merge --delete-branch-on-merge
     --enable-merge-commit=false --enable-rebase-merge=false`);
   - set branch protection on main via `gh api -X PUT
     /repos/{owner}/{repo}/branches/main/protection`: require a PR, require
     a passing CI run, forbid direct pushes;
   - create the labels (`gh label create`): `directive`, plus the
     lifecycle-stage labels `spec`, `building`, `verify`, and `blocked`.
8. Concept Audit — one focused team round before the project is committed.
   The main session fans out a parallel audit wave: `spec-analyst` reads
   the concept paper for ambiguity and gaps in the derivable acceptance
   criteria; `reviewer` audits the testing and verification-check strategy
   for feasibility; `research` re-checks the stack assumptions against
   current sources. Each returns brief questions and proposals. Synthesise
   them into a short list, present each item to the PO, and decide
   (clarify / change / accept / defer). Fold the resulting changes into the
   relevant artifacts (concept paper, feature registry, agent files); any
   architecture decisions surfaced are recorded as ADRs in the next step.
   One round only — a second round is a separate directive.
9. Record the architecture decisions, including the stack choice and any
   surfaced by the Concept Audit, as ADRs.
10. Commit and hand off — make a baseline commit of the onboarded project
    (`chore: complete project onboarding`). Tell the PO in plain language
    what was configured, and that Claude Code must be restarted so the wired
    MCP servers, scaffolded skills, tuned agents and updated `CLAUDE.md`
    take effect. Work then follows the directive lifecycle in `CLAUDE.md`.

## How each question is asked

Every question (a catalog bullet) is put to the PO as a dialogue — the PO
never answers unaided.

1. Ask with the AskUserQuestion tool.
   - Batch by default — group a theme's related questions into one dialogue
     (up to four). Never ask one tiny question at a time.
   - Discrete-choice questions — the realistic options plus an explicit
     "I need help deciding". The free-text field ("Other") is always
     available.
   - Yes/no questions — Yes / No / Unsure-maybe / I need help deciding.
   - Conceptual or open questions (the product, data structures,
     architecture) — do not ask for an answer cold. Draft a first proposal
     from what is known and let the PO react and correct. Reacting beats
     producing.

2. If the PO chooses "I need help deciding":
   a. Research the topic — the `research` agent or WebSearch — for the
      realistic options.
   b. Return with a short plain-language explanation and a pros/cons table.
   c. Re-ask with the researched options; the free-text field stays open.

   Keep research proportional (KISS): quick orientation for a small
   question, deeper work only where the decision is consequential.

3. Record the answer in the concept paper. Mark "help me decide" answers —
   they are less firm and may deserve a recheck.

## Ground rules

- KISS — skip themes that do not apply; go deep only where the project
  needs it. A small tool needs far less than a platform.
- Plain language — the PO may not be technical. Explain every technical
  term the moment it appears (ADR, CI, MCP, verification check, …).
- Do not re-ask — topics recur across themes (existing systems,
  authentication, data); build on the earlier answer.
- Co-develop artifacts — sketch data structures as Mermaid ER/class
  diagrams, draw the data flow, confirm the input/output contracts. Do not
  just collect answers.
- Note ADR-worthy decisions — when a theme reveals an architecture
  decision, note it for an ADR.

## Question Catalog

Four clusters, 22 themes (theme 20 runs only if the stack is still open).
The questions are prompts, not a rigid script — follow up wherever an answer
is thin. Themes 20 and 21 are research procedures, not question lists: the
main session researches and brings the result to the PO as a dialogue.

### Cluster A — Foundation

**1. Project Essence**
- What is the product, in one or two sentences?
- Which problem does it solve, and for whom?
- What does success look like? Which metrics show it?
- What is explicitly out of scope (non-goals)?

**2. Scope & Constraints**
- Are there deadlines, milestones or a fixed budget?
- Who works on the project besides the AI team?
- Are there regulatory or institutional constraints?
- Which existing systems must it integrate with or replace?

**3. Tech Stack — Constraints & Givens**
- Is a stack mandatory or already fixed? If so, which?
- Are any languages, frameworks or libraries mandated or forbidden?
- Does an existing system or integration dictate part of the stack?
- Which stacks does the team already know?
- Any preferences — and how firm are they?

This theme captures only the constraints. If the stack is fixed here,
theme 20 is skipped. If it is open, the actual choice is evaluated at the
end (theme 20), once the data, quality and infrastructure themes — which
strongly shape it — have been answered.

**4. Architecture**
- Architecture style — single application, services, serverless, library?
- What are the main components, and how do they relate?
- Any patterns the project should follow or avoid?
- One repository or several? A product splits into separate repositories
  only when it has genuinely separate, independently deployable packages —
  see `CLAUDE.md`, Multi-Repository Projects.
- If the stack is still open (theme 3), keep this conceptual; stack-specific
  detail is revisited in theme 22.

### Cluster B — Interfaces & Data

**5. Input & Output**
- What data or signals enter the system, and in which formats?
- What does the system produce, and in which formats?
- Who or what produces the inputs and consumes the outputs?

**6. Interfaces & Integrations**
- How is the system used — CLI, API, web UI, files, events?
- Which external APIs or third-party services are involved?
- Any external authentication providers or protocols (for example OAuth, SSO)?

**7. Data Structures**
- What are the core entities (the "nouns" of the domain)?
- Which attributes does each carry, and how do they relate?
- Co-develop one or more Mermaid ER/class diagrams with the PO.

**8. Data Flow**
- Trace the path of data: from which sources, through which steps, to
  which sinks?
- Where does data enter, where does it rest, where does it leave?
- Co-develop a Mermaid flow diagram.

**9. Data Processing**
- Which transformations or business rules act on the data?
- Batch, streaming, on-demand, or scheduled?
- Are there long-running or compute-heavy steps?

**10. Data Analysis**
- Which insights, metrics or reports must the system produce?
- Any statistical, analytical or machine-learning needs?
- Who consumes the analysis, and in which form?

**11. Data Storage & Persistence**
- Where does data live — which database(s), files, object storage?
- Are there caching needs?
- Retention, archival and backup expectations?

### Cluster C — Operations & Quality

**12. Users & Access**
- Which user roles exist, and what may each do?
- User authentication and authorization — how do roles map to permissions?
- Single-tenant or multi-tenant?

**13. Non-Functional Requirements**
- Expected load, data volume and growth?
- Latency, throughput and availability targets?

**14. Security & Privacy**
- Does the system handle personal or sensitive data?
- Which compliance rules apply (for example GDPR)?
- Where do secrets and credentials live? Known threat surfaces?

**15. Quality & Testing**
- What does "verified" mean for this project?
- Which test levels are expected — unit, integration, end-to-end?
- Any coverage or quality thresholds?
- What is the project's artifact type (service, CLI tool, library,
  firmware), and what is its verification check — the artifact-appropriate
  confirmation that a build is sound (see `CLAUDE.md`, Testing)?

**16. Deployment & Environments**
- Where does the system run — local, server, cloud?
- Which environments exist — dev, staging, production?
- Is it containerized? Which CI/CD targets?
- How are releases versioned and delivered?

### Cluster D — Closing

**17. Infrastructure Needs**
- Does the project need browser automation, cloud resources or VMs?
- Which MCP servers or CLIs must be wired in `.mcp.json` / permissions?
- Does the sandbox account need specific access?

Capture here only what the project already knows it needs; further MCP
servers, skills and tools are researched and recommended in theme 21.

**18. Documentation & Audiences**
- Who reads the developer documentation? Who reads the user documentation?
- In which language(s) should each be written?
- Any specific documents the audiences expect?
- Which setup and usage paths must the user documentation cover end to end
  (these become the release walkthrough)?

**19. Risks & Unknowns**
- What is still uncertain or undecided?
- What should the `research` agent investigate first — feeding the stack
  evaluation (theme 20) and the first directives?

**20. Tech Stack Evaluation & Decision** — only if theme 3 left the stack fully or partly open
- By now the data, processing, quality, deployment and infrastructure
  themes are answered; they strongly constrain the choice. The main session
  commissions the `research` agent to evaluate 2-4 candidate stacks against
  the rubric below, then presents a ranked recommendation for PO sign-off.
- Rubric — assess each candidate per dimension:
  - Project fit — how well it serves the requirements gathered above.
  - Implementation effort — how easy the project's specific features are.
  - Community size & knowledge availability — Stack Overflow activity,
    GitHub maturity, documentation quality, release cadence. A large,
    well-documented community means both the model and the research agent
    have far more to draw on.
  - Interface & library availability — are the SDKs and libraries for the
    project's required interfaces (theme 6) present, mature and maintained
    on this stack? Some interfaces are well-supported only on certain stacks.
  - Tooling & feedback quality — static typing, linters, clear error
    messages; a tight feedback loop makes implementation more reliable.
- Token-cost advisory — for each candidate, flag the expected effort. A
  stack with a smaller community or weaker documentation typically costs
  more tokens and more iteration to reach the same result. Present this to
  the PO as an advisory, not a hard score.
- Consult and update `setup/stack-knowledge.md` — the accumulated record of
  stack findings from earlier evaluations.
- Outcome: a ranked, evidence-backed recommendation, signed off by the PO,
  recorded as an ADR (the stack is the least-reversible decision).

In a multi-repository product the stack is chosen per sub-repository: this
theme runs in each sub-repository's own onboarding, and the main
(coordination) repository needs no application stack.

**21. Setup Recommendations** — research-driven, runs after the stack is decided
- With the stack and the full project profile known, the main session
  commissions the `research` agent to find what would measurably help this
  project — starting from `setup/mcp-catalog.md` (curated, stack-agnostic
  options) and going beyond it only where the catalog does not cover the
  need:
  - MCP servers — stack-appropriate tooling, for example a database MCP, a
    browser/testing MCP, or a container MCP for spinning up test
    environments.
  - Claude Code skills — reusable workflows worth adding for this project.
  - Tools — for example container-based test runners, linters, generators.
  - Build it ourselves — if no ready-made MCP server or CLI exists for a
    needed capability (a hardware bridge, an uncommon interface), proposing
    a project-built tool is a valid recommendation; accepted, it becomes a
    directive or feature in the regular lifecycle (see `infra/README.md`,
    Extension Stages).
- For each candidate, present in a dialogue: what it does, why it helps
  this project, the effort to add it, and any cost or credential needs.
  The PO accepts or declines each ("I need help deciding" stays available).
- Accepted items are applied in Step 4 of the runbook: MCP servers wired
  into `.mcp.json`, skills scaffolded under `.claude/skills/`, a setup
  checklist for anything the PO must install manually, and "build it
  ourselves" items earmarked as early directives (filed once the GitHub
  repository exists — Step 4 sub-step 7).
- Record the findings in `setup/stack-knowledge.md`, and add new MCP servers
  that proved generally useful to `setup/mcp-catalog.md` so recommendations
  compound across projects.

**22. Team Tuning**
- Given all the above — the chosen stack and the accepted setup
  recommendations — do any agents need project-specific guidance, different
  tools or a different model?
- Does the data model or architecture need a brief stack-specific revisit?
- Does the project need a specialist agent beyond the base team — a UI/UX
  controller, a domain researcher, a security-auditor? Apply the "Extending
  the Team" procedure in `CLAUDE.md`; default to no unless it clearly earns
  its place.

## The Concept Paper

The funnel produces one document: `docs/developer/concept/concept-paper.md`.
It ships as a skeleton — every section open, `Onboarding status`
`not started`. The interview narrows it cluster by cluster; each checkpoint
fills the matching section. When the PO confirms the finished paper, the
status becomes `complete`.

The status field is the onboarding signal: while not `complete`, first-run
onboarding runs or continues (see `CLAUDE.md`) — this handles an
interrupted, partially filled paper correctly.

<#
.SYNOPSIS
  Instantiates a new project from this template.

.DESCRIPTION
  Copies the pristine template, strips template-only artifacts (the
  template's own design ADRs, the generated site, git history, local build
  caches), names the project, and initialises a fresh git repository.
  Afterwards the new project is ready for its first Claude Code run, which
  conducts the onboarding interview.

  Runs only from the pristine template (the source must carry the
  `.template-marker` file) — never from an already-instantiated project.

.EXAMPLE
  .\scripts\init-project.ps1 -Name "MentorAI" -Target "C:\Users\Carl\Projekte"
#>
param(
    [Parameter(Mandatory)][string]$Name,
    [string]$Target = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot
$path   = Join-Path $Target $Name

if (-not (Test-Path (Join-Path $source ".template-marker"))) {
    throw "Source is not the pristine template (no .template-marker found): $source`nInstantiate only from the pristine template, never from an already-instantiated project."
}
if (Test-Path $path) {
    throw "Target folder already exists: $path"
}

# Read the template version from the marker so it can be recorded in the
# new project's concept paper.
$markerText      = Get-Content (Join-Path $source ".template-marker") -Raw
$versionMatch    = [regex]::Match($markerText, '(?m)^Template version:\s*(\S+)')
$templateVersion = if ($versionMatch.Success) { $versionMatch.Groups[1].Value } else { "unknown" }

# Write UTF-8 without a BOM - keeps mkdocs/PyYAML and git diffs clean.
function Write-Utf8NoBom([string]$File, [string]$Content) {
    [System.IO.File]::WriteAllText($File, $Content, (New-Object System.Text.UTF8Encoding $false))
}

Write-Host "Creating new project: $path" -ForegroundColor Cyan
Copy-Item -Path $source -Destination $path -Recurse

# 1. Remove generated/local artifacts and the template marker. The marker
#    is intentionally not carried over - an instantiated project must not
#    pose as a template source.
foreach ($item in @("site", ".git", ".venv", "node_modules", ".template-marker")) {
    $artifact = Join-Path $path $item
    if (Test-Path $artifact) { Remove-Item $artifact -Recurse -Force }
}
Get-ChildItem $path -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem $path -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
    Remove-Item -Force

# 2. Reset the decision log. ADR-0001..00NN record the design of the
#    template itself; they stay in the template repository and must not
#    pose as the new project's own architecture decisions. The project's
#    first real ADR is a genuine adr-0001.
$decisions = Join-Path $path "docs/developer/decisions"
Get-ChildItem $decisions -Filter "adr-0*.md" | Remove-Item -Force
Write-Utf8NoBom (Join-Path $decisions "index.md") @'
# Architecture Decision Records (ADR)

Every notable architecture decision is recorded as an ADR - during the
documentation step of the directive lifecycle, not afterwards.

## How To

1. Copy `adr-template.md`, number it sequentially (`adr-NNNN.md`).
2. Fill it in and add it to the navigation (`mkdocs.developer.yml`).
3. If a decision is later replaced, set the old ADR's status to
   "Superseded" and link to the new one.

## List

No architecture decisions recorded yet.
'@

# 3. Drop the template ADRs from the developer-docs navigation.
$devCfg  = Join-Path $path "mkdocs.developer.yml"
$navKept = Get-Content $devCfg | Where-Object { $_ -notmatch '^\s+- ADR-\d{4}:' }
Write-Utf8NoBom $devCfg (($navKept -join "`n") + "`n")

# 4. Name the project: mkdocs site names, CLAUDE.md title, concept paper.
$siteNames = @{
    "mkdocs.developer.yml" = "$Name - Developer Documentation"
    "mkdocs.user.yml"      = "$Name - User Documentation"
}
foreach ($cfg in $siteNames.Keys) {
    $file = Join-Path $path $cfg
    $text = (Get-Content $file -Raw) -replace '(?m)^site_name:.*', "site_name: $($siteNames[$cfg])"
    Write-Utf8NoBom $file $text
}

# CLAUDE.md title - replace only the first line, never any later heading.
$claude      = Join-Path $path "CLAUDE.md"
$claudeLines = Get-Content $claude
if ($claudeLines.Count -gt 0 -and $claudeLines[0] -match '^# ') {
    $claudeLines[0] = "# $Name - AI-Assisted Development"
}
Write-Utf8NoBom $claude (($claudeLines -join "`n") + "`n")

$concept     = Join-Path $path "docs/developer/concept/concept-paper.md"
$conceptText = (Get-Content $concept -Raw) `
    -replace '(?m)^- Project:.*', "- Project: $Name" `
    -replace '(?m)^- Template version:.*', "- Template version: $templateVersion"
Write-Utf8NoBom $concept $conceptText

# 5. Replace the template README with a concise project README.
$readme = @'
# __NAME__

Built by an AI development team steered by a Product Owner, on the
AI-assisted development template. The PO gives directives; the team
specifies, builds, verifies and documents them. See `CLAUDE.md` for the
process, the team and the directive lifecycle.

## Status

Not yet onboarded. On the first Claude Code run the onboarding interview
(`setup/interview.md`) narrows the project into a concept paper and tunes
the template to it. You can also run it deliberately with `/onboarding`.

## Prerequisites

- Python 3 + pip - documentation builds
- Node.js - MCP servers launched via `npx`
- Docker - isolated, reproducible test runs
- git + GitHub CLI (`gh`) - the directive lifecycle (issues, CI, PRs)

## View the Documentation

```powershell
pip install -r requirements.txt
mkdocs serve -f mkdocs.developer.yml   # developer docs
mkdocs serve -f mkdocs.user.yml        # user docs
.\export\build.ps1                     # builds both static sites
```
'@
Write-Utf8NoBom (Join-Path $path "README.md") ($readme -replace '__NAME__', $Name)

# 6. Initialise a fresh git repository - the directive lifecycle needs one.
git -C $path init --quiet

Write-Host "Done. Next steps:" -ForegroundColor Green
Write-Host "  1. cd `"$path`""
Write-Host "  2. Ensure the prerequisites are installed (see README.md)."
Write-Host "  3. Create the GitHub repository:  gh repo create"
Write-Host "  4. Start Claude Code. On first run it conducts the onboarding"
Write-Host "     interview (setup/interview.md) and tunes the project -"
Write-Host "     stack, agents, hooks, CI - and creates the lifecycle labels."

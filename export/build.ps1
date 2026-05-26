# Builds both documentation sites (developer + user) as static websites.
# Prerequisite:  pip install -r requirements.txt

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    Write-Host "Building developer documentation..." -ForegroundColor Cyan
    mkdocs build --strict -f mkdocs.developer.yml --site-dir site/developer

    Write-Host "Building user documentation..." -ForegroundColor Cyan
    mkdocs build --strict -f mkdocs.user.yml --site-dir site/user

    Write-Host "Done:" -ForegroundColor Green
    Write-Host "  $root\site\developer\index.html"
    Write-Host "  $root\site\user\index.html"
}
finally {
    Pop-Location
}

# --- PDF export ---
# Working path: mkdocs-exporter renders pages via a browser; Mermaid
# diagrams work out of the box.
#   pip install mkdocs-exporter   and enable the plugin in the mkdocs files.
#
# Extension stage (print-quality look): Markdown -> Typst -> PDF.
#   NOTE: Typst does not render Mermaid natively. Diagrams must be
#   pre-rendered to SVG/PNG in a preceding step. Only adopt this once the
#   mkdocs-exporter PDF look is demonstrably insufficient.

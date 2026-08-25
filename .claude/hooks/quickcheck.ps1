# Quick-check hook (Pillar 4) - runs after every Edit/Write.
#
# IMPORTANT: put only FAST checks here - lint, typecheck, affected tests.
# The full test suite belongs at the cycle's phase boundaries, NOT in this
# hook (otherwise every edit becomes painfully slow).
#
# The hook also fires for documentation edits. To avoid running code checks
# after a docs-only change, list the project's code file extensions in
# $codeExtensions below; the hook then exits early for anything else.
#
# Configure the stack-specific command per project, for example:
#   npm run lint
#   ruff check .
#   dotnet build --no-restore
#
# The hook must exit with code 0 while there are no blockers.
# Until something is configured it is a no-op.

# Code file extensions for this project - whz-lora is a Docker-Compose-
# based LoRaWAN setup with a small own-code footprint (configs + codecs
# + smoke tests).
$codeExtensions = @(".yml", ".yaml", ".toml", ".json", ".js", ".ps1", ".py")

# The harness passes the tool call as JSON on stdin; extract the file path.
$payload  = [Console]::In.ReadToEnd()
$filePath = $null
if ($payload.Trim()) {
    try { $filePath = ($payload | ConvertFrom-Json).tool_input.file_path } catch {}
}

if ($codeExtensions.Count -gt 0 -and $filePath) {
    $ext = [System.IO.Path]::GetExtension($filePath)
    if ($codeExtensions -notcontains $ext) {
        exit 0   # not a code file - skip the checks
    }
}

$ext = if ($filePath) { [System.IO.Path]::GetExtension($filePath) } else { "" }

switch ($ext) {
    { @(".yml", ".yaml") -contains $_ } {
        # YAML: if it's a compose file, validate via docker; otherwise skip.
        $name = [System.IO.Path]::GetFileName($filePath)
        if ($name -match '^docker-compose(\..+)?\.ya?ml$') {
            if (Get-Command docker -ErrorAction SilentlyContinue) {
                $envFile = if (Test-Path .env) { ".env" } elseif (Test-Path .env.example) { ".env.example" } else { $null }
                if ($envFile) {
                    docker compose --env-file $envFile -f $filePath config -q 2>&1 | Out-Host
                } else {
                    docker compose -f $filePath config -q 2>&1 | Out-Host
                }
                exit $LASTEXITCODE
            }
        }
        exit 0
    }
    ".json" {
        try {
            Get-Content -Raw $filePath | ConvertFrom-Json -ErrorAction Stop | Out-Null
            exit 0
        } catch {
            Write-Host "[quickcheck] JSON parse error in ${filePath}: $_"
            exit 1
        }
    }
    ".js" {
        if (Get-Command node -ErrorAction SilentlyContinue) {
            node --check $filePath 2>&1 | Out-Host
            exit $LASTEXITCODE
        }
        exit 0
    }
    ".py" {
        if (Get-Command python -ErrorAction SilentlyContinue) {
            python -m py_compile $filePath 2>&1 | Out-Host
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }

        # Cockpit ships its own pytest suite: stdlib + sqlite + a temp-file
        # DB per test, no Docker, no network, ~500 tests in well under a
        # minute (see cockpit/README.md#tests). Run it on every cockpit/
        # edit so it can't silently stop running again (it used to run
        # only when someone remembered). Prefers the repo's .venv-cockpit;
        # falls back to the ambient `python`. Missing test dependencies
        # (cockpit/requirements-dev.txt not installed) is a warning, not a
        # hook failure — quickcheck must stay usable without that venv.
        if ($filePath -match '[\\/]cockpit[\\/]') {
            $venvPython = Join-Path (Get-Location) ".venv-cockpit/Scripts/python.exe"
            $pyExe = if (Test-Path $venvPython) {
                $venvPython
            } elseif (Get-Command python -ErrorAction SilentlyContinue) {
                "python"
            } else {
                $null
            }

            if ($null -eq $pyExe) {
                Write-Host "[quickcheck] WARNING: no Python interpreter found - skipping cockpit/tests."
                exit 0
            }

            & $pyExe -c "import pytest, httpx" 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[quickcheck] WARNING: cockpit test dependencies (pytest/httpx) not installed for $pyExe - skipping cockpit/tests. Install with: pip install -r cockpit/requirements-dev.txt"
                exit 0
            }

            & $pyExe -m pytest cockpit/tests -q 2>&1 | Out-Host
            exit $LASTEXITCODE
        }

        exit 0
    }
    ".ps1" {
        $errors = $null
        [System.Management.Automation.PSParser]::Tokenize(
            (Get-Content -Raw $filePath), [ref] $errors) | Out-Null
        if ($errors -and $errors.Count -gt 0) {
            $errors | ForEach-Object { Write-Host $_ }
            exit 1
        }
        exit 0
    }
    default {
        exit 0
    }
}

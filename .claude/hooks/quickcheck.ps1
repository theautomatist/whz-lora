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

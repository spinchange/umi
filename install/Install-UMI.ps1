Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$jsonClients = @(
    @{
        Name = "Claude Desktop"
        ConfigPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
        ClientDir = Join-Path $env:APPDATA "Claude"
        Kind = "json"
    },
    @{
        Name = "Cursor"
        ConfigPath = Join-Path $env:USERPROFILE ".cursor\mcp.json"
        ClientDir = Join-Path $env:USERPROFILE ".cursor"
        Kind = "json"
    },
    @{
        Name = "Windsurf"
        ConfigPath = Join-Path $env:USERPROFILE ".codeium\windsurf\mcp_config.json"
        ClientDir = Join-Path $env:USERPROFILE ".codeium\windsurf"
        Kind = "json"
    },
    @{
        Name = "Cline"
        ConfigPath = Join-Path $env:USERPROFILE ".vscode\globalStorage\saoudrizwan.claude-dev\cline_mcp_settings.json"
        ClientDir = Join-Path $env:USERPROFILE ".vscode\globalStorage\saoudrizwan.claude-dev"
        Kind = "json"
    }
)

$tomlClients = @(
    @{
        Name = "Codex CLI"
        ConfigPath = Join-Path $env:USERPROFILE ".codex\config.toml"
        ClientDir = Join-Path $env:USERPROFILE ".codex"
        Kind = "toml"
    }
)

$allClients = @($jsonClients + $tomlClients)

function Get-PythonCommand {
    $candidates = @(
        @{ Command = "python"; Arguments = @() },
        @{ Command = "py"; Arguments = @("-3") }
    )

    foreach ($candidate in $candidates) {
        if (Get-Command $candidate.Command -ErrorAction SilentlyContinue) {
            try {
                & $candidate.Command @($candidate.Arguments + @("-c", "import sys; print(sys.version)")) *> $null
                if ($LASTEXITCODE -eq 0) {
                    return $candidate
                }
            } catch {
            }
        }
    }

    throw "Python 3 was not found. Install Python 3.10+ and rerun this script."
}

function Ensure-UmiInstalled {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Python
    )

    & $Python.Command @($Python.Arguments + @("-c", "from importlib import metadata; print(metadata.version('umi-mcp'))")) *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "umi-mcp is not installed for the detected Python. Installing with pip..."
    & $Python.Command @($Python.Arguments + @("-m", "pip", "install", "umi-mcp"))
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install umi-mcp."
    }
}

function Merge-UmiConfig {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Python,
        [Parameter(Mandatory = $true)]
        [ValidateSet("json", "toml")]
        [string]$Kind,
        [Parameter(Mandatory = $true)]
        [string]$ConfigPath
    )

    $script = @'
import json
import os
import re
import sys
import tempfile

ENTRY = {"command": "python", "args": ["-m", "umi_mcp"]}


def read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def atomic_write(path: str, text: str) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".umi-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def update_json(path: str) -> str:
    raw = read_text(path)
    if raw.strip():
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("JSON config root must be an object.")
    else:
        data = {}

    mcp_servers = data.get("mcpServers")
    if mcp_servers is None:
        mcp_servers = {}
        data["mcpServers"] = mcp_servers
    elif not isinstance(mcp_servers, dict):
        raise TypeError('JSON config field "mcpServers" must be an object.')

    if "umi" in mcp_servers:
        return "already configured"

    mcp_servers["umi"] = ENTRY
    atomic_write(path, json.dumps(data, indent=2) + "\n")
    return "configured"


def load_toml_module():
    try:
        import tomllib  # type: ignore
        return tomllib
    except ModuleNotFoundError:
        try:
            import tomli  # type: ignore
            return tomli
        except ModuleNotFoundError:
            return None


def update_toml(path: str) -> str:
    raw = read_text(path)
    if re.search(r"(?m)^\s*\[\s*mcp_servers\.umi\s*\]\s*$", raw):
        return "already configured"

    toml_module = load_toml_module()
    if toml_module and raw.strip():
        toml_module.loads(raw)

    block = '[mcp_servers.umi]\ncommand = "python"\nargs = ["-m", "umi_mcp"]'
    merged = f"{raw.rstrip()}\n\n{block}\n" if raw.strip() else f"{block}\n"

    if toml_module:
        toml_module.loads(merged)

    atomic_write(path, merged)
    return "configured"


def main() -> int:
    kind = sys.argv[1]
    path = sys.argv[2]
    if kind == "json":
        result = update_json(path)
    elif kind == "toml":
        result = update_toml(path)
    else:
        raise ValueError(f"Unsupported config kind: {kind}")
    print(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
'@

    $output = $script | & $Python.Command @($Python.Arguments + @("-", $Kind, $ConfigPath)) 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    return ($output | Select-Object -Last 1).Trim()
}

$python = Get-PythonCommand
Ensure-UmiInstalled -Python $python

$found = [System.Collections.Generic.List[string]]::new()
$configured = [System.Collections.Generic.List[string]]::new()
$skipped = [System.Collections.Generic.List[string]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

foreach ($client in $allClients) {
    $hasConfig = Test-Path $client.ConfigPath
    $hasDirectory = Test-Path $client.ClientDir

    if (-not $hasConfig -and -not $hasDirectory) {
        continue
    }

    $found.Add($client.Name) | Out-Null

    try {
        $result = Merge-UmiConfig -Python $python -Kind $client.Kind -ConfigPath $client.ConfigPath
        if ($result -eq "configured") {
            $configured.Add($client.Name) | Out-Null
        } elseif ($result -eq "already configured") {
            $skipped.Add("$($client.Name) (already configured)") | Out-Null
        } else {
            $errors.Add("$($client.Name): unexpected result '$result'") | Out-Null
        }
    } catch {
        $errors.Add("$($client.Name): $($_.Exception.Message)") | Out-Null
    }
}

Write-Host ""
Write-Host "UMI installer summary"
Write-Host "Found clients: $($found.Count)"
foreach ($item in $found) {
    Write-Host "  - $item"
}

Write-Host "Configured: $($configured.Count)"
foreach ($item in $configured) {
    Write-Host "  - $item"
}

Write-Host "Skipped: $($skipped.Count)"
foreach ($item in $skipped) {
    Write-Host "  - $item"
}

if ($errors.Count -gt 0) {
    Write-Host "Errors: $($errors.Count)"
    foreach ($item in $errors) {
        Write-Host "  - $item"
    }
    Write-Host ""
    Write-Host "Restart any configured clients to load UMI."
    exit 1
}

Write-Host ""
Write-Host "Restart any configured clients to load UMI."

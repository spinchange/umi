# UMI — Universal Machine Interface

[![Tests](https://github.com/spinchange/umi/actions/workflows/test.yml/badge.svg)](https://github.com/spinchange/umi/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/spinchange/umi/graph/badge.svg)](https://codecov.io/gh/spinchange/umi)
[![License](https://img.shields.io/github/license/spinchange/umi)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/umi-mcp/)
[![Platform](https://img.shields.io/badge/platform-windows%20|%20linux%20|%20macos-lightgrey)]()
[![MCP](https://img.shields.io/badge/MCP-compatible-purple)](https://modelcontextprotocol.io)

**A Python MCP server for local machine inspection from MCP-compatible AI clients.**

UMI is currently functional, but it is **not performance-ready** for the fast "what is wrong with this machine right now?" workflow. Core calls work, but response times can still be materially slower than native tools like Task Manager, Resource Monitor, or Event Viewer.

If you need instant triage on Windows today, use native system tools first. UMI is best treated as an experimental MCP integration layer while the fast path is rebuilt.

---

## Current Status

- Core MCP calls are working again: `get_umi_uptime`, `get_umi_disk`, `get_umi_process`
- A new narrow fast path exists: `get_umi_fast_triage`
- The broader composite/summary direction has been intentionally pulled back
- The next intended milestone is a **fast triage** path that returns in a few seconds, not a rich observability layer

This repository remains public because the implementation is real and usable, but the current state should be read as **functional recovery baseline**, not polished product.

---

## What it does

UMI runs as a local [Model Context Protocol](https://modelcontextprotocol.io) server. Once installed, compatible AI clients can call its tools to query your system and reason about what they find.

```
You: "Is anything on this machine worth worrying about?"

AI: "C: is at 75% capacity, RAM is 87% used (866 MB free of 8 GB),
     and the Claude Desktop service has crashed 3 times in the last
     week according to the event log. Everything else looks normal."
```

That is the intended interaction model, but it is not yet a reliable performance claim. At the moment, UMI should be evaluated as an experimental MCP server, not as a faster replacement for native system tools.

---

## Tools

| Tool | What it returns |
|------|----------------|
| `get_umi_uptime` | Hostname, OS, architecture, boot time, uptime, CPU count, RAM, **current CPU and memory utilization**, swap usage, load averages |
| `get_umi_disk` | Mounted volumes — capacity, used/free, filesystem, **I/O counters** (reads, writes, bytes, time) |
| `get_umi_network` | Network interfaces — IPs, MAC, speed, status, **bytes/packets sent and received**, errors, drops |
| `get_umi_process` | Running processes sorted by CPU — filterable by name or limited to top N |
| `get_umi_service` | System services — Windows Services, systemd units, launchd agents — with status and start type |
| `get_umi_user` | Local user accounts — groups, admin status, home directory |
| `get_umi_events` | Recent system log entries — Windows Event Log, journald, macOS unified log — filterable by level and source |
| `get_umi_fast_triage` | Small fast snapshot for operator triage — overall CPU, memory pressure, top disks, top CPU-time processes, top memory processes |

All tools return structured JSON conforming to the [UMI schemas](./schema/). Data is cross-platform and normalized — the same property names and types regardless of OS.

---

## Supported clients

UMI works with any MCP-compatible AI client:

| Client | Notes |
|--------|-------|
| **Claude Desktop** | `claude_desktop_config.json` |
| **Cursor** | MCP settings in `.cursor/mcp.json` |
| **Windsurf** | MCP settings in config |
| **Cline** | `cline_mcp_settings.json` |
| **Continue** | VS Code / JetBrains extension |
| **VS Code Copilot** | Agent Mode with MCP (GA July 2025) |
| **Codex CLI** | `~/.codex/config.toml` |
| **Qwen Code** | MCP settings in config |

> **Note on coding assistants:** Tools like Cursor and Codex can already run shell commands directly, so UMI is less essential there. It's most useful in **chat-oriented clients** (Claude Desktop, etc.) that don't have shell access by default.

---

## Install

Requires Python 3.10+ and pip.

```bash
pip install umi-mcp
```

### Auto-installers

UMI includes installers that will:

- ensure `umi-mcp` is installed for your active Python
- detect supported AI clients already present on the machine
- merge the `umi` MCP entry into each client config without overwriting other settings
- skip clients that already have a `umi` entry

Run the installer for your platform:

```powershell
./install/Install-UMI.ps1
```

```bash
./install/install-umi.sh
```

The installer checks these client config locations and creates the config file when the client directory exists but the file does not:

| Client | Config path |
|--------|-------------|
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Linux) | `~/.config/Claude/claude_desktop_config.json` |
| Codex CLI | `~/.codex/config.toml` |
| Cursor | `~/.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| Cline | `~/.vscode/globalStorage/saoudrizwan.claude-dev/cline_mcp_settings.json` |

Restart any configured clients after the installer finishes.

### Manual configuration

If you prefer to configure a client yourself, add the UMI MCP entry below.

### Claude Desktop

Add to `claude_desktop_config.json`:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "umi": {
      "command": "python",
      "args": ["-m", "umi_mcp"]
    }
  }
}
```

Restart Claude Desktop. Check **Settings → Developer** to confirm UMI is listed.

### Other clients

The pattern is the same for all MCP clients — point the client at `python -m umi_mcp`. Check your client's MCP documentation for config file location and format.

---

## Platform support

| OS | Status |
|----|--------|
| Windows 10/11 | Functional, performance work in progress |
| Linux (systemd) | Functional, less exercised |
| macOS 13+ | Functional, less exercised |

The MCP server uses [psutil](https://psutil.readthedocs.io/) for cross-platform system queries and falls back gracefully where platform-specific data isn't available (returning `null` rather than erroring).

---

## Schemas

The JSON schemas in [`/schema`](./schema/) define the exact shape of every tool's output. They follow a few strict rules:

- **PascalCase, full words** — `UsedPercent`, `MemoryBytes`, `IsAdmin`. No abbreviations.
- **Flat objects** — one level deep. No nested structures.
- **Constrained enums** — every enum includes `Unknown` as a fallback. Values never surprise you.
- **Bytes as integers** — always raw bytes. The consumer decides how to display (GB, TB, etc.).
- **ISO 8601 timestamps** — all times are machine-parseable strings with timezone.
- **Null over absent** — optional fields always appear in output as `null`, never missing entirely.

These schemas are implementation-agnostic. The PowerShell module in [`/powershell`](./powershell/) is a reference implementation. Python, Go, Rust — anything that outputs conforming JSON is UMI-compatible.

---

## PowerShell reference implementation

A PowerShell 7 module is included for Windows users who want to use UMI outside of MCP, or pipe data between scripts and agents.

```powershell
Import-Module ./powershell/UMI/UMI.psd1

Get-UmiDisk | Where-Object UsedPercent -gt 80
Get-UmiProcess -Top 5
Get-UmiUptime -AsJson
```

```powershell
# Run tests (requires Pester 5+)
Invoke-Pester ./powershell/Tests/UMI.Tests.ps1
```

---

## Tests

```bash
pip install pytest pytest-cov
pytest mcp-server/tests/ --cov=umi_mcp --cov-report=term-missing
```

76 tests covering all 7 tools across Windows, Linux, and macOS paths — including subprocess failure modes, null-field handling, platform branching, and entry point wiring. 100% statement coverage.

---

## Known Limitations

### Performance and operator workflow

UMI is currently too slow for the strict "faster than opening Task Manager" standard.
That is a meaningful limitation, not just a polish issue.

The project drifted toward richer MCP summaries and cross-platform enrichment before
locking down a truly fast baseline. The current reset direction is:

- keep the core local inspection tools working
- avoid broad composite endpoints for now
- rebuild around a narrow fast-triage path with a target response time of a few seconds

Until that work is done, native OS tools remain the better choice for immediate triage.

### Windows: virtual/cloud-mounted drives may report identical disk stats

On Windows, virtual drives (e.g. Google Drive, OneDrive, network shares) are
sometimes backed by the same underlying volume. When this happens,
`get_umi_disk` may return two entries with identical `TotalBytes`, `UsedBytes`,
and `FreeBytes`. This is a Windows API limitation — `psutil` sees the same
physical volume through two mount points. I/O counters for virtual drives will
also be `null` for the same reason.

A future fix will add a `VolumeSerial` or `DeviceId` field to allow callers to
detect and deduplicate aliased volumes. Tracked in
[#fix/disk-virtual-drive-disambiguation](https://github.com/spinchange/umi/issues).

---

## Contributing

The most useful contributions right now:

- **New platforms or edge cases** — ZFS, NixOS, unusual hardware, BSD variants
- **Schema feedback** — missing fields, naming that isn't obvious, type mismatches
- **Alternative implementations** — Go, Rust, or Bash modules conforming to the schemas
- **Client compatibility reports** — does it work with a client not listed above?

File an issue or open a PR.

---

## Reset Direction

The next useful version of UMI should probably be much smaller:

- top CPU processes
- top memory processes
- overall CPU and memory pressure
- disk free/used percentage
- recent critical or error events

That reset has started with `get_umi_fast_triage`, which is intentionally much narrower than the older composite direction.

If that fast path cannot reliably beat or closely match the feel of opening a native
system monitor, then the design should be reconsidered before layering on more features.

---

## License

MIT

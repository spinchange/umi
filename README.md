# UMI — Universal Machine Interface

**A Python MCP server that gives AI assistants live awareness of the machine they're running on.**

Ask your AI assistant how much disk space is left, what's using the most memory, or whether any services have crashed recently — and get a real answer, not a suggested command to run yourself.

---

## What it does

UMI runs as a local [Model Context Protocol](https://modelcontextprotocol.io) server. Once installed, compatible AI clients can call its tools to query your system and reason about what they find.

```
You: "Is anything on this machine worth worrying about?"

AI: "C: is at 75% capacity, RAM is 87% used (866 MB free of 8 GB),
     and the Claude Desktop service has crashed 3 times in the last
     week according to the event log. Everything else looks normal."
```

That response required no commands, no copy-pasting, and no prompting the user to open Task Manager. The AI queried the machine directly, assembled the picture, and answered in plain language.

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
pip install git+https://github.com/spinchange/umi.git#subdirectory=mcp-server
```

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
| Windows 10/11 | Full support |
| Linux (systemd) | Full support |
| macOS 13+ | Full support |

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
python -m unittest discover -s mcp-server/tests -v
```

---

## Contributing

The most useful contributions right now:

- **New platforms or edge cases** — ZFS, NixOS, unusual hardware, BSD variants
- **Schema feedback** — missing fields, naming that isn't obvious, type mismatches
- **Alternative implementations** — Go, Rust, or Bash modules conforming to the schemas
- **Client compatibility reports** — does it work with a client not listed above?

File an issue or open a PR.

---

## License

MIT

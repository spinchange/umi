# umi-mcp

A Python MCP server that gives AI assistants live awareness of the machine they're running on.

Install it, point your AI client at it, and ask questions like "what's using the most memory?" or "have there been any service crashes recently?" — and get real answers.

## Install

```bash
pip install umi-mcp
```

## Configure (Claude Desktop)

Add to your `claude_desktop_config.json`:

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

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Restart Claude Desktop. Check **Settings → Developer** to confirm UMI is connected.

## Tools

- `get_umi_uptime` — hostname, OS, arch, CPU%, memory utilization, swap, load averages
- `get_umi_disk` — volumes, capacity, usage, filesystem, I/O counters
- `get_umi_network` — interfaces, IPs, MAC, speed, bytes sent/received, errors
- `get_umi_process` — running processes by CPU, filterable by name or top N
- `get_umi_service` — Windows Services / systemd / launchd, with status
- `get_umi_user` — local accounts, groups, admin status
- `get_umi_events` — Windows Event Log / journald / macOS unified log, filterable by level

Works on Windows, Linux, and macOS.

## Full documentation

[github.com/spinchange/umi](https://github.com/spinchange/umi)

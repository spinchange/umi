# UMI — Universal Machine Interface

**An open schema for how AI agents query and understand machines.**

UMI defines a standard set of object schemas for common system information — disk, network, processes, uptime, users — so that any tool, script, or AI agent can ask a machine about itself and get a predictable, structured answer regardless of operating system.

The PowerShell module in this repo is the **reference implementation**. The schemas are the product.

---

## The Problem

When an AI agent needs to check disk space, it currently has to:

1. Guess the OS
2. Pick the right command (`df -h` vs `Get-Volume` vs `diskutil`)
3. Parse inconsistent text output
4. Hope the column order hasn't changed between distros

Every agent, in every conversation, solves this from scratch. If two agents need to hand off data to each other, they're playing telephone with unstructured text.

## The Solution

UMI defines **what the answer should look like** — a JSON schema for each system concept. Then it provides a PowerShell 7 module that implements those schemas cross-platform.

```powershell
# Same command. Same output shape. Any OS.
Get-UmiDisk | Where-Object UsedPercent -gt 80

# Hand it to another agent as clean JSON
Get-UmiUptime -AsJson | clip
```

An agent receiving UMI output doesn't parse — it **reads**. Property names are self-documenting. Types are explicit. Enums are constrained.

## Schemas

The schemas live in [`/schema`](./schema/) as JSON Schema (2020-12) files:

| Schema | File | What it describes |
|--------|------|-------------------|
| **Disk** | `disk.schema.json` | Mounted volumes — capacity, usage, filesystem |
| **Network** | `network.schema.json` | Network interfaces — IPs, MACs, DNS, link state |
| **Process** | `process.schema.json` | Running processes — CPU, memory, owner, status |
| **Uptime** | `uptime.schema.json` | System identity — hostname, OS, architecture, boot time |
| **User** | `user.schema.json` | Local accounts — groups, admin status, home directory |

These schemas are **implementation-agnostic**. You can implement them in Python, Rust, Go, Bash — anything that outputs conforming JSON.

## PowerShell Reference Implementation

### Requirements

- PowerShell 7.0+ (install: https://aka.ms/powershell)
- Works on Windows, Linux, and macOS

### Install

```powershell
# From the repo
git clone https://github.com/spinchange/umi.git
Import-Module ./umi/powershell/UMI/UMI.psd1

# Verify
Test-UmiEnvironment
```

### Commands

| Command | Description |
|---------|-------------|
| `Get-UmiDisk` | Disk/volume usage |
| `Get-UmiNetwork` | Network interfaces |
| `Get-UmiProcess` | Running processes |
| `Get-UmiUptime` | System identity & uptime |
| `Get-UmiUser` | Local user accounts |
| `Test-UmiEnvironment` | Validate your system can run UMI |

### Common Parameters

Every `Get-Umi*` command supports:

- **`-AsJson`** — Output as a JSON string instead of PowerShell objects. Ideal for piping to files, APIs, or other agents.

### Examples

```powershell
# Am I running low on disk space?
Get-UmiDisk | Where-Object UsedPercent -gt 90

# What's eating my CPU?
Get-UmiProcess -Top 5

# Quick system fingerprint for an agent
Get-UmiUptime -AsJson

# All admin users on this machine
Get-UmiUser | Where-Object IsAdmin -eq $true

# Which network interface has an IP?
Get-UmiNetwork | Where-Object IPv4Address -ne $null
```

### Testing

```powershell
# Requires Pester 5+
Install-Module Pester -Force -SkipPublisherCheck
Invoke-Pester ./powershell/Tests/UMI.Tests.ps1
```

## For Agent / LLM Developers

UMI is designed to be consumed by AI agents. Key design decisions:

- **Flat objects** — no deep nesting. Every property is one level deep.
- **Self-documenting names** — `UsedPercent`, `MemoryBytes`, `IsAdmin`. No abbreviations, no codes.
- **Constrained enums** — `Status` is always one of `Running|Sleeping|Stopped|Zombie|Idle|Unknown`. Never a surprise value.
- **Bytes as integers** — always raw bytes. The agent decides how to display (GB, GiB, TB). No pre-formatted strings in data fields.
- **ISO 8601 timestamps** — all times are machine-parseable strings.
- **Null over absent** — optional properties return `null`, never missing keys. Agents don't need try/catch for missing fields.

### Example: Agent-to-Agent Handoff

```
Agent 1 runs: Get-UmiProcess -Top 5 -AsJson
Agent 1 passes JSON to Agent 2
Agent 2 parses with zero ambiguity — property names and types are guaranteed
Agent 2 acts on the data (alert, remediate, report)
```

No regex. No "which column was CPU again?" No "does this distro put PID first or second?"

## Implementing the Schema in Other Languages

The schemas in `/schema` are standard JSON Schema. To create a conforming implementation:

1. Read the `.schema.json` for the object type you're implementing
2. Query the OS using whatever native method your language supports
3. Output a JSON object matching the schema — same property names, same types, same enum values

A Python implementation might look like:

```python
import psutil, json

def get_umi_disk():
    disks = []
    for part in psutil.disk_partitions():
        usage = psutil.disk_usage(part.mountpoint)
        disks.append({
            "DeviceName": part.device,
            "MountPoint": part.mountpoint,
            "FileSystem": part.fstype.upper(),
            "TotalBytes": usage.total,
            "UsedBytes": usage.used,
            "FreeBytes": usage.free,
            "UsedPercent": round(usage.percent, 1),
            "IsRemovable": False,
            "Label": None
        })
    return json.dumps(disks, indent=2)
```

If the output conforms to the schema, it's UMI-compatible. The language doesn't matter.

## Contributing

This project is in early development. The most valuable contributions right now:

1. **Schema feedback** — Are the property names obvious? Are we missing critical fields?
2. **Edge case reports** — "Get-UmiDisk doesn't handle ZFS on FreeBSD" — great, file an issue.
3. **Alternative implementations** — Python, Rust, Go implementations of the schemas.
4. **Agent integration stories** — How are you using UMI with your AI tooling?

## License

MIT

## Links

- Schema spec: [`/schema`](./schema/)
- PowerShell module: [`/powershell`](./powershell/)
- Project site: [spinchange.github.io/umi](https://spinchange.github.io/umi)

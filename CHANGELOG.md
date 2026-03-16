# Changelog

## [0.1.0] — 2026-03-16

Initial release.

### MCP server (`mcp-server/`)

- `get_umi_uptime` — hostname, OS, architecture, boot time, uptime, CPU count, total RAM, current CPU utilization, memory utilization, swap usage, load averages (Linux/macOS)
- `get_umi_disk` — mounted volumes with capacity, usage, filesystem type, and I/O counters (reads, writes, bytes, time); Windows maps drive letters to physical disks
- `get_umi_network` — network interfaces with IPs, MAC, speed, status, and cumulative I/O counters (bytes, packets, errors, drops)
- `get_umi_process` — running processes sorted by CPU, filterable by name or limited to top N
- `get_umi_service` — system services (Windows Services, systemd, launchd) with status, start type, binary path
- `get_umi_user` — local user accounts with UID, home directory, shell, groups, admin status
- `get_umi_events` — recent system log entries from Windows Event Log, Linux journald, or macOS unified log; filterable by level, source, and count; messages truncated at 500 characters
- Cross-platform: Windows 10/11, Linux, macOS

### Schemas (`schema/`)

Seven JSON Schema (2020-12) definitions: disk, network, process, uptime, user, service, events

### PowerShell reference implementation (`powershell/`)

PowerShell 7 module with `Get-UmiDisk`, `Get-UmiNetwork`, `Get-UmiProcess`, `Get-UmiUptime`, `Get-UmiUser`, `Get-UmiService`, `Test-UmiEnvironment`; 30 Pester tests

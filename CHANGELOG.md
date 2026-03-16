# Changelog

## [0.2.0] — 2026-03-16

### MCP server — bug fixes

- **`get_umi_events`**: Windows event timestamps were always `null` — PowerShell's `ConvertTo-Json` serializes `DateTime` as `/Date(ms)/`; `_parse_timestamp` now handles this format
- **`get_umi_uptime`**: `PowerShellVersion` was hardcoded `null`; now queries `$PSVersionTable.PSVersion` on Windows
- **`get_umi_uptime`**: `LoadAverage` fields returned `0.0` on Windows (psutil emulates but starts at zero); now returns `null` on Windows
- **`get_umi_process`**: `System Idle Process` reported 500%+ CPU on Windows; now filtered from results
- **`get_umi_process`**: All per-process `CpuPercent` values were `0.0` — the global `psutil.cpu_percent(interval=0.5)` call primed the system counter but not per-process counters; replaced with a proper two-pass sampling approach (prime each process individually, sleep 0.5s, read delta)
- **`get_umi_disk`**: `Label` field was hardcoded `null`; now populated from `Get-Volume` on Windows

### MCP server — new

- **`get_umi_summary`**: Composite snapshot of machine health in a single call — system identity, CPU/memory utilization, disk aggregates (total, used, most-full partition), top CPU and memory processes, recent error count with configurable lookback window, last event metadata. Designed by Gemini, flat 22-field schema.

### MCP server — improvements

- Tool descriptions improved throughout: valid enum values documented (`level`, `status`), bytes-to-GB divisor noted for disk, CPU multi-core behavior documented for process

### Known limitations

- Virtual/cloud-mounted drives (Google Drive, OneDrive) may report identical disk stats and null I/O counters — same underlying volume, two mount points. `VolumeSerial` field planned to allow deduplication.

### Roadmap (from live AI session feedback)

- `get_umi_gpu` — GPU model, VRAM total/used, utilization, temperature; high value for local LLM inference workloads
- `get_umi_installed` — installed software list, searchable; enables bloatware audits, version checks, dependency verification
- `get_umi_env` — environment variables (PATH, PYTHONPATH, etc.); critical for debugging shell/Python pathing issues
- `get_umi_scheduled` — Windows Task Scheduler entries; useful for understanding periodic resource consumers
- `get_umi_filesystem` — directory listing with file sizes for a given path
- Historical snapshots — time-series CPU/memory over configurable window; requires background collection

---

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

# UMI Envelope Contract

Every UMI endpoint returns a JSON **object**, never a bare array. All responses include standard envelope fields alongside domain data.

## Envelope Fields

| Field | Type | Present on |
|-------|------|------------|
| `SchemaVersion` | string | All endpoints |
| `GeneratedAt` | ISO 8601 string | All endpoints |
| `CollectionTimeMs` | float (ms, 1 decimal) | Simple endpoints |
| `Count` | integer | Array endpoints |
| `Items` | array | Array endpoints |
| `Timing` | object | Aggregate endpoints |

### `CollectionTimeMs` vs `Timing`

**Simple endpoints** (`get_umi_disk`, `get_umi_network`, `get_umi_process`, `get_umi_uptime`, `get_umi_user`, `get_umi_service`, `get_umi_events`, `get_umi_process_trends`) include a single `CollectionTimeMs` field at the envelope level. This measures only the time spent inside the underlying data collector (e.g. the psutil call, or the PowerShell subprocess). It does not include serialisation or MCP framing overhead.

**Aggregate endpoints** (`get_umi_summary`, `get_umi_event_summary`, `get_umi_recent_changes`, `get_umi_service_health`, `get_umi_triage_bundle`) call multiple collectors. They expose a `Timing` object with per-collector breakdowns and a `TotalMs` field:

```json
{
  "Timing": {
    "UptimeMs": 12.3,
    "ProcessMs": 620.1,
    "DiskMs": 8.4,
    "ServiceMs": 45.2,
    "EventsMs": 180.0,
    "TotalMs": 866.0
  }
}
```

`TotalMs` includes all collector time plus in-process aggregation. The sum of per-collector fields may be slightly less than `TotalMs` due to Python-side grouping work between calls.

Not all per-collector keys appear in every aggregate endpoint — only the collectors that endpoint actually calls are included.

## Response Shapes

### Array endpoints

`get_umi_disk`, `get_umi_network`, `get_umi_process`, `get_umi_user`, `get_umi_service`, `get_umi_events`

```json
{
  "SchemaVersion": "1",
  "GeneratedAt": "2026-03-17T10:00:00+00:00",
  "Count": 2,
  "Items": [
    { "ProcessName": "chrome", "CpuPercent": 45.2, "..." : "..." },
    { "ProcessName": "python", "CpuPercent": 12.1, "..." : "..." }
  ]
}
```

### Flat object endpoints

`get_umi_uptime`, `get_umi_summary`

`SchemaVersion` and `GeneratedAt` are merged at the top level alongside domain fields:

```json
{
  "SchemaVersion": "1",
  "GeneratedAt": "2026-03-17T10:00:00+00:00",
  "Hostname": "my-machine",
  "OS": "Windows",
  "UptimeSeconds": 86400,
  "..."  : "..."
}
```

### Aggregate endpoints

`get_umi_event_summary`, `get_umi_recent_changes`

These have their own documented shapes. See each endpoint's docstring or the sections below.

**`get_umi_event_summary`:**
```json
{
  "SchemaVersion": "1",
  "GeneratedAt": "...",
  "LookbackHours": 24,
  "Level": "Warning",
  "Count": 3,
  "Groups": [
    {
      "Source": "Service Control Manager",
      "EventId": 7034,
      "Level": "Error",
      "Count": 8,
      "FirstSeen": "2026-03-16T08:00:00+00:00",
      "LastSeen":  "2026-03-16T11:45:00+00:00",
      "SampleMessage": "The Print Spooler service terminated unexpectedly.",
      "Classification": "actionable"
    }
  ],
  "Timing": { "EventsMs": 180.0, "TotalMs": 182.1 }
}
```

`Classification` values: `"noise"` (safe to suppress), `"watch"` (worth noting), `"actionable"` (requires attention). Classification is assigned per group based on known noisy event IDs/sources and severity heuristics — see `_classify_event()` in `server.py` for the full rule set.

**`get_umi_recent_changes`:**
```json
{
  "SchemaVersion": "1",
  "GeneratedAt": "...",
  "LookbackHours": 4,
  "Hostname": "my-machine",
  "Highlights": [
    "Process spikes: chrome, python",
    "Storage C: at 91.0% used"
  ],
  "Changes": {
    "ProcessSpikes":  [ { "ProcessName": "chrome", "CpuPercent": 82.1, "MemoryBytes": 2100000000, "Reasons": ["HighCpu", "HighMemory"] } ],
    "ServiceCrashes": [ { "ServiceName": "spooler", "DisplayName": "Print Spooler", "Status": "Stopped" } ],
    "BurstEvents":    [ { "Source": "Disk", "EventId": 51, "Level": "Error", "Count": 12, "SampleMessage": "..." } ],
    "StorageAlerts":  [ { "DeviceName": "C:", "MountPoint": "C:\\", "UsedPercent": 91.0, "FreeBytes": 9000000 } ]
  },
  "Timing": { "UptimeMs": 12.1, "ProcessMs": 620.0, "DiskMs": 8.2, "ServiceMs": 45.0, "EventsMs": 180.0, "TotalMs": 866.0 }
}
```

## Null Semantics

UMI uses a strict three-way distinction:

| Value | Meaning |
|-------|---------|
| `null` | Supported but unavailable — the OS supports this field, but the value could not be determined at query time |
| `[]` | Supported and queried, but no items were found |
| *(omitted)* | Not part of this endpoint or schema version |

**Examples:**
- `"LoadAverage1m": null` on Windows — Windows has no load average concept
- `"DnsServers": []` — DNS servers are supported but could not be discovered
- `"BurstEvents": []` — no repeated event sources found in the window

Agents should treat `null` as "unknown/unavailable" and `[]` as "confirmed empty". A missing field means the endpoint does not surface that concept.

## Migration Guide: pre-envelope → v0.2

Array endpoints previously returned a bare list. Consumers need one change:

```python
# Before (pre-envelope):
for item in result:
    process(item)

# After (v0.2+):
for item in result["Items"]:
    process(item)
```

A forward-compatible pattern that handles both formats:

```python
items = result["Items"] if isinstance(result, dict) else result
for item in items:
    process(item)
```

`Count` equals `len(result["Items"])` and is provided for cheap size checks without iterating `Items`.

## Field Semantics Notes

### Level normalization (events endpoints)

The `Level` field is normalized across all platforms to one of five canonical values:
`Critical`, `Error`, `Warning`, `Information`, `Verbose`. Platform sources:

| Platform | Raw value → Level |
|----------|-------------------|
| Windows | EventLog level int: 1→Critical, 2→Error, 3→Warning, 4→Information, 5→Verbose |
| Linux | journald PRIORITY: 0-2→Critical, 3→Error, 4→Warning, 5-6→Information, 7→Verbose |
| macOS | messageType: fault→Critical, error→Error, default→Warning |

An unmapped raw value becomes `Unknown`. The string `"Info"` is accepted as an alias for `"Information"` when passed as a filter parameter.

### CpuPercent (process endpoints)

`CpuPercent` is a delta measurement sampled over a ~0.5s interval per process. On multi-core systems it can exceed 100 (e.g. 800% on an 8-core machine at full single-thread utilisation is normal). It is not a point-in-time reading and will be 0.0 for processes that started during the sampling window.

`get_umi_process_trends` uses two such samples separated by ~1.5s and reports the delta between them. This is a short-window trend, not long-horizon history.

### IsRemovable (disk endpoint)

`IsRemovable` is a heuristic:
- All platforms: `True` if the filesystem type is `iso9660`, `udf`, or `cdfs`, or if mount options include `cdrom` or `removable`
- Linux only: authoritative sysfs read from `/sys/class/block/<dev>/removable` (value `1` = removable) as a secondary check

On Windows, psutil does not expose a reliable removable flag; the heuristic relies solely on filesystem type and mount options. USB drives formatted as NTFS may not be detected as removable.

### Service endpoint scale (Windows)

`get_umi_service()` defaults to `verbosity="summary"` (4 fields: ServiceName, DisplayName, Status, StartType). On Windows this still returns 200+ items. For further reduction:
- Use `only_non_microsoft=True` to drop OS-owned services (typically ~70% of Windows services)
- Use `top=N` to hard-cap the result set
- Use `get_umi_triage_bundle()` or `get_umi_service_health()` for pre-filtered views
- Use `verbosity="full"` only for explicit drill-down on a specific service

## Platform Notes

### DNS servers (network endpoint)

`DnsServers` is populated per-interface on **Windows** (via `Get-DnsClientServerAddress`). On **Linux** and **macOS** the same system-wide resolver list is applied to all Up interfaces — per-interface DNS is not yet distinguished on those platforms.

On Linux systems running **systemd-resolved** (common on Ubuntu, Debian, Fedora), `/etc/resolv.conf` typically points to a local stub (`127.0.0.53`). UMI automatically reads from `/run/systemd/resolve/resolv.conf` first to surface the real upstream resolvers. If only stub addresses are found they are returned as-is.

### Default gateway and route metadata (network endpoint)

`DefaultGateway` is assigned to the interface identified as the system's lowest-metric default route. All other interfaces get `null`. When a VPN is active it may become the default route interface; the physical interface's `DefaultGateway` will then be `null` until the VPN disconnects.

`IsDefaultRoute` is `true` for the same interface that holds `DefaultGateway`, and `false` for all others. It is provided as a boolean convenience to avoid a null-check on `DefaultGateway`.

`RouteMetric` reflects the route metric of the default route and is populated only on the default-route interface (all others get `null`). Platform availability:

| Platform | Source | Notes |
|----------|--------|-------|
| Windows | `Get-NetRoute RouteMetric` | Reliable; typically 25–50 for physical, higher for virtual |
| Linux | `ip route show default metric` field | Available when `metric` appears in the route line |
| macOS | Not available | Always `null` — `route -n get default` does not expose a numeric metric |

`IsVpn` is `true` when `InterfaceType == "Tunnel"` (interface name starts with `tun`, `tap`, or `vpn`). This is a name-based heuristic; some VPN clients use non-standard names and will not be detected.

## Process Trends (short-window sampled)

`get_umi_process_trends` performs two CPU/memory snapshots ~1.5 s apart and reports delta fields (`CpuDeltaPercent`, `MemoryDeltaBytes`) and a `Trend` label (`Increasing` / `Decreasing` / `Stable`).

**This is a short-window point-in-time sample, not long-horizon historical trending.** A single call reflects what changed in the last ~1.5 seconds. Use it to catch runaway processes or memory leaks in progress, not to reason about hour-long growth patterns. The endpoint takes approximately 2.5 s to complete (two CPU sampling passes of 0.5 s each, plus 1.5 s inter-sample sleep).

Trend thresholds: CPU delta > 5% OR memory delta > 50 MB → `Increasing`; CPU delta < −5% → `Decreasing`; otherwise `Stable`.

## `get_umi_triage_bundle` cache semantics

Results are cached for **30 seconds**. Check `GeneratedAt` to determine data freshness. Agents that need the most current snapshot can call individual endpoints instead.

## SchemaVersion

- Current value: `"1"`
- Adding optional envelope fields or new endpoints stays at `"1"`
- Breaking changes to the envelope structure (e.g., renaming `Items`, changing `Count` semantics) would increment to `"2"`
- Tool-level schema changes (new fields on disk/process/etc.) follow the per-schema versioning documented in `SCHEMA_DESIGN.md`

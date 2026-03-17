# UMI Envelope Contract

Every UMI endpoint returns a JSON **object**, never a bare array. All responses include standard envelope fields alongside domain data.

## Envelope Fields

| Field | Type | Present on |
|-------|------|------------|
| `SchemaVersion` | string | All endpoints |
| `GeneratedAt` | ISO 8601 string | All endpoints |
| `Count` | integer | Array endpoints |
| `Items` | array | Array endpoints |

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
      "SampleMessage": "The Print Spooler service terminated unexpectedly."
    }
  ]
}
```

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
  }
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

## SchemaVersion

- Current value: `"1"`
- Adding optional envelope fields or new endpoints stays at `"1"`
- Breaking changes to the envelope structure (e.g., renaming `Items`, changing `Count` semantics) would increment to `"2"`
- Tool-level schema changes (new fields on disk/process/etc.) follow the per-schema versioning documented in `SCHEMA_DESIGN.md`

import platform
import re
import time

from mcp.server.fastmcp import FastMCP
from datetime import datetime, timedelta, timezone

from .tools.disk import get_disk
from .tools.events import get_events
from .tools.network import get_network
from .tools.process import get_process
from .tools.uptime import get_uptime
from .tools.user import get_user
from .tools.service import get_service

mcp = FastMCP("umi")

_SCHEMA_VERSION = "1"

# Summary-mode field sets for verbosity="summary".
# These are the minimum fields an agent needs to triage each resource type.
_PROCESS_SUMMARY_FIELDS = frozenset({"ProcessName", "ProcessId", "CpuPercent", "MemoryBytes", "Status", "User"})
_SERVICE_SUMMARY_FIELDS = frozenset({"ServiceName", "DisplayName", "Status", "StartType"})
_EVENTS_SUMMARY_FIELDS  = frozenset({"Timestamp", "Level", "Source", "Message"})

_LEVEL_ORDER = {
    "Critical": 0,
    "Error": 1,
    "Warning": 2,
    "Information": 3,
    "Verbose": 4,
    "Unknown": 5,
}

# --- Issue #13: noise classification ---

# Windows event IDs known to be high-volume operational noise with no action required.
_KNOWN_NOISE_IDS = frozenset({
    10016,  # DistributedCOM: DCOM permission error (nearly always benign)
    4202,   # WLAN AutoConfig: disconnected from network
    1014,   # DNS Client: name resolution timeout (transient)
    642,    # Audit policy change (routine)
    5605,   # Windows backup: shadow copy noise
})
# Source name substrings (lowercased) that are structurally noisy on most Windows systems.
_KNOWN_NOISE_SOURCES = frozenset({"distributedcom", "wlan-autoconfig", "wlan autoconfig"})


def _classify_event(
    source: "str | None",
    event_id: "int | None",
    level: "str | None",
    count: int,
) -> str:
    """Return 'noise', 'watch', or 'actionable' for an event group.

    noise      — Known high-volume operational noise; safe to suppress in dashboards.
    actionable — Critical/Error severity, OR fires ≥10 times in the window.
    watch      — Everything else (Warning-level, moderate count).
    """
    src_lower = (source or "").lower()
    if event_id in _KNOWN_NOISE_IDS or any(n in src_lower for n in _KNOWN_NOISE_SOURCES):
        return "noise"
    level_rank = _LEVEL_ORDER.get(level or "Unknown", 5)
    if level_rank <= 1 or count >= 10:
        return "actionable"
    return "watch"


def _is_microsoft_service(svc: dict) -> bool:
    """Heuristic: True if the service binary lives under a Windows system directory.

    Used to implement the only_non_microsoft filter on get_umi_service.
    On Linux/macOS this always returns False (all services are non-Microsoft).
    """
    path = (svc.get("BinaryPath") or "").lower().replace('"', "").strip()
    if not path:
        return False
    return (
        "\\windows\\" in path
        or path.startswith("c:\\windows")
        or path.startswith("%systemroot%")
        or "\\microsoft shared\\" in path
    )


def _apply_verbosity(items: list[dict], verbosity: str, summary_fields: frozenset) -> list[dict]:
    """Strip items to summary_fields when verbosity='summary'. No-op for 'full'."""
    if verbosity == "summary":
        return [{k: v for k, v in item.items() if k in summary_fields} for item in items]
    return items


def _wrap(data: "dict | list", collection_time_ms: "float | None" = None) -> dict:
    """Wrap a tool result in the standard UMI response envelope.

    Array results become: {SchemaVersion, GeneratedAt, Count, Items: [...]}.
    Dict results get SchemaVersion and GeneratedAt merged at the top level.
    CollectionTimeMs (ms, 1 decimal) is included when provided.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    if isinstance(data, list):
        result = {
            "SchemaVersion": _SCHEMA_VERSION,
            "GeneratedAt": now,
            "Count": len(data),
            "Items": data,
        }
    else:
        result = {
            "SchemaVersion": _SCHEMA_VERSION,
            "GeneratedAt": now,
            **data,
        }
    if collection_time_ms is not None:
        result["CollectionTimeMs"] = round(collection_time_ms, 1)
    return result


# --- Issue #14: TTL cache for triage_bundle ---

_TRIAGE_CACHE_TTL = 30.0  # seconds
_triage_cache: dict = {"result": None, "expires_at": 0.0}


@mcp.tool()
def get_umi_disk() -> dict:
    """
    Returns all mounted disk volumes with capacity and usage statistics.
    Use this to check which drives exist, their total size, how much is used
    and free, filesystem type, and mount point. Each volume is one object in Items.
    Bytes fields: divide by 1073741824 for GB.
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs, Count, and Items array.
    """
    t0 = time.perf_counter()
    data = get_disk()
    return _wrap(data, collection_time_ms=(time.perf_counter() - t0) * 1000)


@mcp.tool()
def get_umi_network(include_down: bool = False) -> dict:
    """
    Returns network interfaces with IP addresses, MAC address, interface type,
    link speed, and status. By default only returns interfaces that are Up.
    Set include_down=true to include inactive interfaces.
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs, Count, and Items array.
    """
    t0 = time.perf_counter()
    data = get_network(include_down=include_down)
    return _wrap(data, collection_time_ms=(time.perf_counter() - t0) * 1000)


@mcp.tool()
def get_umi_process(
    name: str = None,
    top: int = None,
    verbosity: str = "full",
    only_user_processes: bool = False,
) -> dict:
    """
    Returns running processes sorted by CPU usage descending.
    Use name to filter by process name substring (e.g. name="python").
    Use top to limit results (e.g. top=10 for the 10 most CPU-intensive processes).
    Set only_user_processes=true to exclude System-owned processes (kernel, SYSTEM account, root).
    MemoryBytes is resident set size. CpuPercent may exceed 100 on multi-core systems.
    Full mode fields include: ProcessName, ProcessId, ParentProcessId, ParentProcessName,
    CpuPercent, MemoryBytes, MemoryPercent, Status, User, ProcessType, ExecutablePath,
    Publisher (null in v1), ServiceName (null in v1), StartTime, CommandLine, ThreadCount.
    ProcessType is a heuristic classification ('System' or 'User'), not an OS-native truth
    field. It is inferred from PID (<=4 = System) and username (SYSTEM, root, etc.).
    verbosity="summary" returns only: ProcessName, ProcessId, CpuPercent, MemoryBytes, Status, User.
    verbosity="full" (default) returns all fields.
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs, Count, and Items array.
    """
    t0 = time.perf_counter()
    data = get_process(name=name, top=top)
    elapsed = (time.perf_counter() - t0) * 1000
    if only_user_processes:
        data = [p for p in data if p.get("ProcessType") == "User"]
    return _wrap(_apply_verbosity(data, verbosity, _PROCESS_SUMMARY_FIELDS), collection_time_ms=elapsed)


@mcp.tool()
def get_umi_uptime() -> dict:
    """
    Returns system identity and uptime: hostname, OS family (Windows/Linux/macOS),
    OS version string, CPU architecture, boot timestamp, seconds since boot,
    human-readable uptime, logical CPU count, and total installed RAM in bytes.
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs alongside all uptime fields.
    """
    t0 = time.perf_counter()
    data = get_uptime()
    elapsed = (time.perf_counter() - t0) * 1000
    result = _wrap(data)
    result["CollectionTimeMs"] = round(elapsed, 1)
    return result


@mcp.tool()
def get_umi_user(current_only: bool = False) -> dict:
    """
    Returns local user accounts with username, user ID, home directory, shell,
    group memberships, and admin status. Set current_only=true to return only
    the user running the current session.
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs, Count, and Items array.
    """
    t0 = time.perf_counter()
    data = get_user(current_only=current_only)
    return _wrap(data, collection_time_ms=(time.perf_counter() - t0) * 1000)


@mcp.tool()
def get_umi_service(
    name: str = None,
    status: str = None,
    top: int = None,
    verbosity: str = "summary",
    only_non_microsoft: bool = False,
) -> dict:
    """
    Returns system services: Windows Services, systemd units, or launchd agents
    depending on the host OS. Optionally filter by name substring or by status
    (Running, Stopped, Degraded, Starting, Stopping, Paused).
    Set only_non_microsoft=true to exclude services whose BinaryPath is under
    Windows system directories (C:/Windows/, %SystemRoot%). This filter is
    Windows-meaningful only — on Linux and macOS all services pass through unchanged.
    On Windows the unfiltered list can exceed 200 entries; use top or
    only_non_microsoft to keep the response token-efficient.
    Use top to limit the number of returned services.
    verbosity="summary" (default) returns only: ServiceName, DisplayName, Status, StartType.
    verbosity="full" returns all fields: Description, User, ProcessId, BinaryPath,
    UptimeSeconds, ExitCode, Publisher (null in v1).
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs, Count, and Items array.
    """
    t0 = time.perf_counter()
    data = get_service(name=name, status=status)
    if only_non_microsoft:
        data = [s for s in data if not _is_microsoft_service(s)]
    if top is not None:
        data = data[:top]
    elapsed = (time.perf_counter() - t0) * 1000
    return _wrap(_apply_verbosity(data, verbosity, _SERVICE_SUMMARY_FIELDS), collection_time_ms=elapsed)


@mcp.tool()
def get_umi_summary(error_lookback_hours: int = 24) -> dict:
    """
    Provides a high-level health and utilization snapshot of the local
    system. Aggregates critical metrics from uptime, storage, processes,
    and event logs into a single flat response. Use this for rapid
    situational awareness and initial triage before employing specialized
    diagnostic tools. Valid events_level values for error counting:
    Info, Warning, Error, Critical.
    Response includes Timing with per-collector and TotalMs breakdowns.
    """
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    uptime_data = get_uptime()
    uptime_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    disk_data = get_disk()
    disk_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    process_data = get_process()
    process_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    events_data = get_events(level="Error", last_n=500)
    events_ms = (time.perf_counter() - t0) * 1000

    total_memory_bytes = uptime_data.get("TotalMemoryBytes")
    memory_used_bytes = uptime_data.get("MemoryUsedBytes")
    if total_memory_bytes and total_memory_bytes > 0:
        memory_used_percent = round((memory_used_bytes / total_memory_bytes) * 100, 1)
    else:
        memory_used_percent = None

    total_disk_bytes = sum(d.get("TotalBytes", 0) for d in disk_data)
    used_disk_bytes = sum(d.get("UsedBytes", 0) for d in disk_data)
    max_disk_used_percent = max((d.get("UsedPercent") for d in disk_data), default=None)

    if process_data:
        top_cpu_process_name = process_data[0].get("ProcessName")
        top_cpu_process_id = process_data[0].get("ProcessId")
        top_memory_process = max(process_data, key=lambda p: p.get("MemoryBytes") or 0)
        top_memory_process_name = top_memory_process.get("ProcessName")
        top_memory_process_bytes = top_memory_process.get("MemoryBytes")
    else:
        top_cpu_process_name = None
        top_cpu_process_id = None
        top_memory_process_name = None
        top_memory_process_bytes = None

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=error_lookback_hours)
    recent = [
        event for event in events_data
        if event.get("Timestamp")
        and datetime.fromisoformat(event["Timestamp"]) >= cutoff
    ]

    last_event = events_data[0] if events_data else None

    total_ms = (time.perf_counter() - t_total) * 1000

    return {
        "SchemaVersion": _SCHEMA_VERSION,
        "GeneratedAt": datetime.now(tz=timezone.utc).isoformat(),
        "Hostname": uptime_data.get("Hostname"),
        "OS": uptime_data.get("OS"),
        "OSVersion": uptime_data.get("OSVersion"),
        "Architecture": uptime_data.get("Architecture"),
        "UptimeSeconds": uptime_data.get("UptimeSeconds"),
        "CpuCount": uptime_data.get("CpuCount"),
        "CpuUtilizationPercent": uptime_data.get("CpuPercentOverall"),
        "TotalMemoryBytes": total_memory_bytes,
        "MemoryUsedBytes": memory_used_bytes,
        "MemoryUsedPercent": memory_used_percent,
        "LoadAverageOneMinute": uptime_data.get("LoadAverage1m"),
        "TotalDiskBytes": total_disk_bytes,
        "UsedDiskBytes": used_disk_bytes,
        "MaxDiskUsedPercent": max_disk_used_percent,
        "TopCpuProcessName": top_cpu_process_name,
        "TopCpuProcessId": top_cpu_process_id,
        "TopMemoryProcessName": top_memory_process_name,
        "TopMemoryProcessBytes": top_memory_process_bytes,
        "RecentErrorCount": len(recent),
        "LastEventTimestamp": last_event.get("Timestamp") if last_event else None,
        "LastEventLevel": last_event.get("Level") if last_event else None,
        "LastEventMessage": last_event.get("Message") if last_event else None,
        "Timing": {
            "UptimeMs": round(uptime_ms, 1),
            "DiskMs": round(disk_ms, 1),
            "ProcessMs": round(process_ms, 1),
            "EventsMs": round(events_ms, 1),
            "TotalMs": round(total_ms, 1),
        },
    }


@mcp.tool()
def get_umi_events(level: str = "Error", source: str = None, last_n: int = 20, verbosity: str = "full") -> dict:
    """
    Returns recent system events/log entries normalized across Windows Event Log,
    Linux journald, and macOS unified logging. Filter by severity level, optional
    source substring, and limit the number of returned entries with last_n.
    Valid level values: Info, Warning, Error, Critical (default: Error).
    Message is truncated to 500 characters.
    verbosity="summary" returns only: Timestamp, Level, Source, Message.
    verbosity="full" (default) returns all fields including LogName, EventId, User, MachineName, etc.
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs, Count, and Items array.
    """
    t0 = time.perf_counter()
    data = get_events(level=level, source=source, last_n=last_n)
    elapsed = (time.perf_counter() - t0) * 1000
    return _wrap(_apply_verbosity(data, verbosity, _EVENTS_SUMMARY_FIELDS), collection_time_ms=elapsed)


@mcp.tool()
def get_umi_event_summary(
    lookback_hours: int = 24,
    level: str = "Warning",
    top: int = 20,
) -> dict:
    """
    Returns events grouped by source and event ID for quick triage.
    Aggregates repeated events into counts rather than dumping raw floods.
    Use lookback_hours to control the time window (default: 24).
    Use level to set minimum severity (default: Warning).
    Use top to cap the number of groups returned (default: 20).
    Groups are sorted by Count descending, then by severity.
    Each group includes FirstSeen, LastSeen, SampleMessage, and Classification
    ('noise' / 'watch' / 'actionable').
    Response includes SchemaVersion, GeneratedAt, LookbackHours, Count, Groups, and Timing.
    """
    t_total = time.perf_counter()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
    t0 = time.perf_counter()
    raw = get_events(level=level, last_n=500)
    events_ms = (time.perf_counter() - t0) * 1000

    in_window = []
    for event in raw:
        ts = event.get("Timestamp")
        if ts:
            try:
                if datetime.fromisoformat(ts) >= cutoff:
                    in_window.append(event)
            except ValueError:
                pass

    groups: dict = {}
    for event in in_window:
        key = (event.get("Source"), event.get("EventId"), event.get("Level"))
        if key not in groups:
            groups[key] = {
                "Source": event.get("Source"),
                "EventId": event.get("EventId"),
                "Level": event.get("Level"),
                "Count": 0,
                "FirstSeen": event.get("Timestamp"),
                "LastSeen": event.get("Timestamp"),
                "SampleMessage": event.get("Message"),
            }
        g = groups[key]
        g["Count"] += 1
        ts = event.get("Timestamp")
        if ts:
            if g["FirstSeen"] is None or ts < g["FirstSeen"]:
                g["FirstSeen"] = ts
            if g["LastSeen"] is None or ts > g["LastSeen"]:
                g["LastSeen"] = ts

    # Attach noise classification to each group
    for g in groups.values():
        g["Classification"] = _classify_event(g["Source"], g["EventId"], g["Level"], g["Count"])

    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (-g["Count"], _LEVEL_ORDER.get(g.get("Level") or "Unknown", 5)),
    )[:top]

    total_ms = (time.perf_counter() - t_total) * 1000

    return {
        "SchemaVersion": _SCHEMA_VERSION,
        "GeneratedAt": datetime.now(tz=timezone.utc).isoformat(),
        "LookbackHours": lookback_hours,
        "Level": level,
        "Count": len(sorted_groups),
        "Groups": list(sorted_groups),
        "Timing": {
            "EventsMs": round(events_ms, 1),
            "TotalMs": round(total_ms, 1),
        },
    }


@mcp.tool()
def get_umi_recent_changes(lookback_hours: int = 4) -> dict:
    """
    Returns a compact snapshot of what is noteworthy right now, plus burst events
    from the last N hours. Use Highlights for a ready-to-read text summary.
    Note: ProcessSpikes, ServiceCrashes, and StorageAlerts are current point-in-time
    snapshots — they do not filter by lookback_hours. Only BurstEvents (repeated
    warnings/errors) are windowed to the lookback period.
    Changes.ProcessSpikes: processes exceeding 50% CPU or 1 GB resident memory.
    Changes.ServiceCrashes: Automatic-start services currently Stopped or Degraded.
    Changes.BurstEvents: event sources that fired 3+ times in the lookback window.
    Changes.StorageAlerts: volumes at or above 85% used.
    Response includes SchemaVersion, GeneratedAt, LookbackHours, Hostname, Highlights,
    Changes, and Timing with per-collector and TotalMs breakdowns.
    """
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    uptime_data = get_uptime()
    uptime_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    process_data = get_process()
    process_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    disk_data = get_disk()
    disk_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    try:
        service_data = get_service()
    except Exception:
        service_data = []
    service_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    raw_events = get_events(level="Warning", last_n=500)
    events_ms = (time.perf_counter() - t0) * 1000

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)

    _CPU_SPIKE_THRESHOLD = 50.0
    _MEMORY_SPIKE_BYTES = 1_000_000_000
    _BURST_THRESHOLD = 3
    _STORAGE_THRESHOLD = 85.0

    process_spikes = []
    for p in process_data:
        reasons = []
        if (p.get("CpuPercent") or 0) > _CPU_SPIKE_THRESHOLD:
            reasons.append("HighCpu")
        if (p.get("MemoryBytes") or 0) > _MEMORY_SPIKE_BYTES:
            reasons.append("HighMemory")
        if reasons:
            process_spikes.append({
                "ProcessName": p.get("ProcessName"),
                "ProcessId": p.get("ProcessId"),
                "CpuPercent": p.get("CpuPercent"),
                "MemoryBytes": p.get("MemoryBytes"),
                "Reasons": reasons,
            })

    service_crashes = [
        {
            "ServiceName": s.get("ServiceName"),
            "DisplayName": s.get("DisplayName"),
            "Status": s.get("Status"),
        }
        for s in service_data
        if s.get("StartType") == "Automatic" and s.get("Status") in ("Stopped", "Degraded")
    ]

    event_groups: dict = {}
    for event in raw_events:
        ts = event.get("Timestamp")
        if not ts:
            continue
        try:
            if datetime.fromisoformat(ts) < cutoff:
                continue
        except ValueError:
            continue
        key = (event.get("Source"), event.get("EventId"), event.get("Level"))
        if key not in event_groups:
            event_groups[key] = {
                "Source": event.get("Source"),
                "EventId": event.get("EventId"),
                "Level": event.get("Level"),
                "Count": 0,
                "SampleMessage": event.get("Message"),
            }
        event_groups[key]["Count"] += 1

    burst_events = sorted(
        [g for g in event_groups.values() if g["Count"] >= _BURST_THRESHOLD],
        key=lambda g: -g["Count"],
    )

    storage_alerts = [
        {
            "DeviceName": d.get("DeviceName"),
            "MountPoint": d.get("MountPoint"),
            "UsedPercent": d.get("UsedPercent"),
            "FreeBytes": d.get("FreeBytes"),
        }
        for d in disk_data
        if (d.get("UsedPercent") or 0) >= _STORAGE_THRESHOLD
    ]

    highlights = []
    if process_spikes:
        names = ", ".join(p["ProcessName"] for p in process_spikes[:3])
        suffix = f" (+{len(process_spikes) - 3} more)" if len(process_spikes) > 3 else ""
        highlights.append(f"Process spikes: {names}{suffix}")
    if service_crashes:
        names = ", ".join(s["ServiceName"] for s in service_crashes[:3])
        suffix = f" (+{len(service_crashes) - 3} more)" if len(service_crashes) > 3 else ""
        highlights.append(f"Stopped automatic services: {names}{suffix}")
    if burst_events:
        sources = ", ".join(g["Source"] or "unknown" for g in burst_events[:3])
        highlights.append(f"Burst events from: {sources}")
    for alert in storage_alerts:
        label = alert["DeviceName"] or alert["MountPoint"] or "unknown"
        highlights.append(f"Storage {label} at {alert['UsedPercent']}% used")
    if not highlights:
        highlights.append("No significant changes detected.")

    total_ms = (time.perf_counter() - t_total) * 1000

    return {
        "SchemaVersion": _SCHEMA_VERSION,
        "GeneratedAt": datetime.now(tz=timezone.utc).isoformat(),
        "LookbackHours": lookback_hours,
        "Hostname": uptime_data.get("Hostname"),
        "Highlights": highlights,
        "Changes": {
            "ProcessSpikes": process_spikes,
            "ServiceCrashes": service_crashes,
            "BurstEvents": burst_events,
            "StorageAlerts": storage_alerts,
        },
        "Timing": {
            "UptimeMs": round(uptime_ms, 1),
            "ProcessMs": round(process_ms, 1),
            "DiskMs": round(disk_ms, 1),
            "ServiceMs": round(service_ms, 1),
            "EventsMs": round(events_ms, 1),
            "TotalMs": round(total_ms, 1),
        },
    }


# --- Windows SCM event patterns for service health correlation ---
_SCM_CRASH_RE = re.compile(
    r"The (.+?) service terminated unexpectedly|"
    r"The (.+?) service has terminated with the following error",
    re.IGNORECASE,
)
_SCM_STATE_RE = re.compile(
    r"The (.+?) service entered the (\w+) state",
    re.IGNORECASE,
)
_STATUS_PRIORITY = {"Stopped": 0, "Degraded": 1, "Starting": 2, "Stopping": 2, "Paused": 2, "Running": 3, "Unknown": 4}


@mcp.tool()
def get_umi_service_health(
    lookback_hours: int = 24,
    only_degraded: bool = False,
    top: int = 20,
) -> dict:
    """
    Returns service health enriched with crash and restart counts from event logs.
    On Windows, correlates each service against Service Control Manager events
    (EventId 7034/7031 = crash, EventId 7036 = state change) within the lookback window.
    On Linux and macOS, CrashCount and RestartCount are null (not available from journald
    without per-service queries).
    Use only_degraded=true to return only services that are Stopped, Degraded, or have crashes.
    Use top to cap results (default 20, sorted by health status then crash count).
    Each service record includes: ServiceName, DisplayName, Status, StartType, IsHealthy,
    CrashCount, RestartCount, LastCrash, LastStateChange.
    Response includes SchemaVersion, GeneratedAt, LookbackHours, Count, Services, and Timing.
    """
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    service_data = get_service()
    service_ms = (time.perf_counter() - t0) * 1000

    is_windows = platform.system() == "Windows"

    # On Windows, pull SCM events and parse crash/restart history.
    # On other platforms, event correlation is not available.
    service_events: dict[str, dict] = {}
    events_ms = 0.0
    if is_windows:
        t0 = time.perf_counter()
        raw_events = get_events(level="Warning", source="Service Control Manager", last_n=500)
        events_ms = (time.perf_counter() - t0) * 1000

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)

        for event in raw_events:
            ts = event.get("Timestamp")
            if not ts:
                continue
            try:
                if datetime.fromisoformat(ts) < cutoff:
                    continue
            except ValueError:
                continue

            msg = event.get("Message") or ""

            crash_match = _SCM_CRASH_RE.search(msg)
            if crash_match:
                svc_name = (crash_match.group(1) or crash_match.group(2) or "").strip().lower()
                if svc_name:
                    rec = service_events.setdefault(svc_name, {"crashes": [], "state_changes": []})
                    rec["crashes"].append({"Timestamp": ts, "Message": event.get("Message")})
                continue

            state_match = _SCM_STATE_RE.search(msg)
            if state_match:
                svc_name = state_match.group(1).strip().lower()
                state = state_match.group(2).strip()
                rec = service_events.setdefault(svc_name, {"crashes": [], "state_changes": []})
                rec["state_changes"].append({"Timestamp": ts, "State": state})

    health_records = []
    for svc in service_data:
        svc_name = svc.get("ServiceName") or ""
        display_name = svc.get("DisplayName") or svc_name

        # Try to match by ServiceName, then DisplayName
        rec = (
            service_events.get(svc_name.lower())
            or service_events.get(display_name.lower())
            or {"crashes": [], "state_changes": []}
        )

        crashes = rec["crashes"]
        state_changes = rec["state_changes"]

        crash_count = len(crashes) if is_windows else None
        restart_count = (
            sum(1 for sc in state_changes if sc["State"].lower() == "running")
            if is_windows else None
        )
        last_crash = (
            max((c["Timestamp"] for c in crashes if c["Timestamp"]), default=None)
            if crashes else None
        )
        last_state_change = (
            max((sc["Timestamp"] for sc in state_changes if sc["Timestamp"]), default=None)
            if state_changes else None
        )

        status = svc.get("Status")
        is_healthy = status == "Running" and (crash_count or 0) == 0

        health_records.append({
            "ServiceName": svc_name,
            "DisplayName": display_name,
            "Status": status,
            "StartType": svc.get("StartType"),
            "IsHealthy": is_healthy,
            "CrashCount": crash_count,
            "RestartCount": restart_count,
            "LastCrash": last_crash,
            "LastStateChange": last_state_change,
        })

    if only_degraded:
        health_records = [
            r for r in health_records
            if not r["IsHealthy"] or (r["CrashCount"] or 0) > 0
        ]

    health_records.sort(key=lambda r: (
        _STATUS_PRIORITY.get(r["Status"] or "Unknown", 4),
        -(r["CrashCount"] or 0),
    ))
    health_records = health_records[:top]

    total_ms = (time.perf_counter() - t_total) * 1000

    return {
        "SchemaVersion": _SCHEMA_VERSION,
        "GeneratedAt": datetime.now(tz=timezone.utc).isoformat(),
        "LookbackHours": lookback_hours,
        "Count": len(health_records),
        "Services": health_records,
        "Timing": {
            "ServiceMs": round(service_ms, 1),
            "EventsMs": round(events_ms, 1),
            "TotalMs": round(total_ms, 1),
        },
    }


@mcp.tool()
def get_umi_triage_bundle() -> dict:
    """
    One-call triage entrypoint. Returns everything needed to answer
    'what is wrong right now?' without chaining multiple tool calls.
    Combines: system identity, resource utilization, top 10 CPU processes
    (summary fields), grouped recent errors (last 4h), stopped/degraded
    automatic services, and storage alerts.
    Use Highlights for a ready-to-read text summary.
    TopEvents include Classification ('noise'/'watch'/'actionable') for filtering.
    Results are cached for 30 seconds — check GeneratedAt for data freshness.
    This is the recommended first call for agent-driven system diagnosis.
    Response includes SchemaVersion, GeneratedAt, Hostname, OS, UptimeSeconds,
    CpuPercent, MemoryUsedPercent, LoadAverage1m, Highlights, TopProcesses,
    StorageAlerts, StoppedServices, TopEvents, and Timing.
    """
    now_ts = time.monotonic()
    if _triage_cache["result"] is not None and now_ts < _triage_cache["expires_at"]:
        return _triage_cache["result"]

    t_total = time.perf_counter()

    t0 = time.perf_counter()
    uptime_data = get_uptime()
    uptime_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    process_data = get_process(top=10)
    process_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    disk_data = get_disk()
    disk_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    try:
        service_data = get_service()
    except Exception:
        service_data = []
    service_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    events_data = get_events(level="Warning", last_n=200)
    events_ms = (time.perf_counter() - t0) * 1000

    total_memory = uptime_data.get("TotalMemoryBytes")
    used_memory = uptime_data.get("MemoryUsedBytes")
    memory_pct = round((used_memory / total_memory) * 100, 1) if total_memory else None

    top_processes = _apply_verbosity(process_data, "summary", _PROCESS_SUMMARY_FIELDS)

    _STORAGE_THRESHOLD = 85.0
    storage_alerts = [
        {
            "DeviceName": d.get("DeviceName"),
            "MountPoint": d.get("MountPoint"),
            "UsedPercent": d.get("UsedPercent"),
            "FreeBytes": d.get("FreeBytes"),
        }
        for d in disk_data
        if (d.get("UsedPercent") or 0) >= _STORAGE_THRESHOLD
    ]

    stopped_services = [
        {
            "ServiceName": s.get("ServiceName"),
            "DisplayName": s.get("DisplayName"),
            "Status": s.get("Status"),
        }
        for s in service_data
        if s.get("StartType") == "Automatic" and s.get("Status") in ("Stopped", "Degraded")
    ][:10]  # Cap at 10 to keep triage bundle token-efficient

    # Group events from the last 4 hours
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=4)
    event_groups: dict = {}
    for event in events_data:
        ts = event.get("Timestamp")
        if not ts:
            continue
        try:
            if datetime.fromisoformat(ts) < cutoff:
                continue
        except ValueError:
            continue
        key = (event.get("Source"), event.get("EventId"), event.get("Level"))
        if key not in event_groups:
            event_groups[key] = {
                "Source": event.get("Source"),
                "Level": event.get("Level"),
                "Count": 0,
                "SampleMessage": event.get("Message"),
            }
        event_groups[key]["Count"] += 1

    # Attach classification before sorting
    for key, g in event_groups.items():
        event_id = key[1]  # EventId from the grouping key
        g["Classification"] = _classify_event(g["Source"], event_id, g["Level"], g["Count"])

    top_events = sorted(event_groups.values(), key=lambda g: (
        _LEVEL_ORDER.get(g.get("Level") or "Unknown", 5),
        -g["Count"],
    ))[:10]

    highlights: list[str] = []
    cpu_pct = uptime_data.get("CpuPercentOverall")
    if cpu_pct is not None and cpu_pct > 80:
        highlights.append(f"High system CPU: {cpu_pct}%")
    if memory_pct is not None and memory_pct > 85:
        highlights.append(f"High memory usage: {memory_pct}%")
    for alert in storage_alerts:
        label = alert["DeviceName"] or alert["MountPoint"] or "unknown"
        highlights.append(f"Storage {label} at {alert['UsedPercent']}% used")
    if stopped_services:
        names = ", ".join(s["ServiceName"] for s in stopped_services[:3])
        suffix = f" (+{len(stopped_services) - 3} more)" if len(stopped_services) > 3 else ""
        highlights.append(f"Stopped automatic services: {names}{suffix}")
    if top_events:
        e = top_events[0]
        preview = (e["SampleMessage"] or "")[:80]
        highlights.append(f"Top event: {e['Source'] or 'unknown'} ({e['Count']}x) — {preview}")
    if not highlights:
        highlights.append("No significant issues detected.")

    total_ms = (time.perf_counter() - t_total) * 1000

    result = {
        "SchemaVersion": _SCHEMA_VERSION,
        "GeneratedAt": datetime.now(tz=timezone.utc).isoformat(),
        "Hostname": uptime_data.get("Hostname"),
        "OS": uptime_data.get("OS"),
        "UptimeSeconds": uptime_data.get("UptimeSeconds"),
        "CpuPercent": uptime_data.get("CpuPercentOverall"),
        "MemoryUsedPercent": memory_pct,
        "LoadAverage1m": uptime_data.get("LoadAverage1m"),
        "Highlights": highlights,
        "TopProcesses": top_processes,
        "StorageAlerts": storage_alerts,
        "StoppedServices": stopped_services,
        "TopEvents": top_events,
        "Timing": {
            "UptimeMs": round(uptime_ms, 1),
            "ProcessMs": round(process_ms, 1),
            "DiskMs": round(disk_ms, 1),
            "ServiceMs": round(service_ms, 1),
            "EventsMs": round(events_ms, 1),
            "TotalMs": round(total_ms, 1),
        },
    }

    _triage_cache["result"] = result
    _triage_cache["expires_at"] = time.monotonic() + _TRIAGE_CACHE_TTL
    return result


# --- Issue #7: Process trends ---

_TRENDS_SORT_KEYS = {
    "cpu_avg": lambda t: -t["CpuAvgPercent"],
    "cpu_max": lambda t: -t["CpuMaxPercent"],
    "mem_avg": lambda t: -t["MemoryAvgBytes"],
    "mem_max": lambda t: -t["MemoryMaxBytes"],
}
_TRENDS_SLEEP = 1.5  # seconds between samples
_TRENDS_CPU_DELTA_THRESHOLD = 5.0    # % change to count as Increasing/Decreasing
_TRENDS_MEM_DELTA_THRESHOLD = 50_000_000  # 50 MB change to count as Increasing


@mcp.tool()
def get_umi_process_trends(top: int = 10, sort: str = "cpu_avg") -> dict:
    """
    Returns CPU and memory trends for processes by sampling twice with a ~1.5s gap.
    Processes that appear in both samples are matched by ProcessId and compared.
    Fields per process: ProcessName, ProcessId, CpuAvgPercent, CpuMaxPercent,
    CpuDeltaPercent, MemoryAvgBytes, MemoryMaxBytes, MemoryDeltaBytes, Trend.
    Trend: 'Increasing' (CPU delta >5% or memory delta >50MB), 'Decreasing'
    (CPU delta < -5%), or 'Stable'.
    sort: 'cpu_avg' (default), 'cpu_max', 'mem_avg', 'mem_max'.
    top: cap returned results (default 10).
    Note: this call takes ~2.5s minimum due to two CPU sampling passes.
    Response includes SchemaVersion, GeneratedAt, CollectionTimeMs, Count, and Items array.
    """
    t_total = time.perf_counter()

    snap1 = get_process()
    time.sleep(_TRENDS_SLEEP)
    snap2 = get_process()

    by_pid: dict[int, dict] = {
        p["ProcessId"]: p
        for p in snap1
        if p.get("ProcessId") is not None
    }

    trends = []
    for p2 in snap2:
        pid = p2.get("ProcessId")
        p1 = by_pid.get(pid)
        if p1 is None:
            continue  # process appeared between samples — skip

        cpu1 = p1.get("CpuPercent") or 0.0
        cpu2 = p2.get("CpuPercent") or 0.0
        mem1 = p1.get("MemoryBytes") or 0
        mem2 = p2.get("MemoryBytes") or 0

        cpu_delta = round(cpu2 - cpu1, 2)
        mem_delta = mem2 - mem1

        if cpu_delta > _TRENDS_CPU_DELTA_THRESHOLD or mem_delta > _TRENDS_MEM_DELTA_THRESHOLD:
            trend = "Increasing"
        elif cpu_delta < -_TRENDS_CPU_DELTA_THRESHOLD:
            trend = "Decreasing"
        else:
            trend = "Stable"

        trends.append({
            "ProcessName": p2.get("ProcessName"),
            "ProcessId": pid,
            "CpuAvgPercent": round((cpu1 + cpu2) / 2, 2),
            "CpuMaxPercent": round(max(cpu1, cpu2), 2),
            "CpuDeltaPercent": cpu_delta,
            "MemoryAvgBytes": (mem1 + mem2) // 2,
            "MemoryMaxBytes": max(mem1, mem2),
            "MemoryDeltaBytes": mem_delta,
            "Trend": trend,
        })

    key_fn = _TRENDS_SORT_KEYS.get(sort, _TRENDS_SORT_KEYS["cpu_avg"])
    trends.sort(key=key_fn)
    trends = trends[:top]

    elapsed = (time.perf_counter() - t_total) * 1000
    return _wrap(trends, collection_time_ms=elapsed)

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


@mcp.tool()
def get_umi_disk() -> list[dict]:
    """
    Returns all mounted disk volumes with capacity and usage statistics.
    Use this to check which drives exist, their total size, how much is used
    and free, filesystem type, and mount point. Each volume is one object.
    Bytes fields: divide by 1073741824 for GB.
    """
    return get_disk()


@mcp.tool()
def get_umi_network(include_down: bool = False) -> list[dict]:
    """
    Returns network interfaces with IP addresses, MAC address, interface type,
    link speed, and status. By default only returns interfaces that are Up.
    Set include_down=true to include inactive interfaces.
    """
    return get_network(include_down=include_down)


@mcp.tool()
def get_umi_process(name: str = None, top: int = None) -> list[dict]:
    """
    Returns running processes sorted by CPU usage descending.
    Use name to filter by process name substring (e.g. name="python").
    Use top to limit results (e.g. top=10 for the 10 most CPU-intensive processes).
    MemoryBytes is resident set size. CpuPercent may exceed 100 on multi-core systems.
    """
    return get_process(name=name, top=top)


@mcp.tool()
def get_umi_uptime() -> dict:
    """
    Returns system identity and uptime: hostname, OS family (Windows/Linux/macOS),
    OS version string, CPU architecture, boot timestamp, seconds since boot,
    human-readable uptime, logical CPU count, and total installed RAM in bytes.
    """
    return get_uptime()


@mcp.tool()
def get_umi_user(current_only: bool = False) -> list[dict]:
    """
    Returns local user accounts with username, user ID, home directory, shell,
    group memberships, and admin status. Set current_only=true to return only
    the user running the current session.
    """
    return get_user(current_only=current_only)


@mcp.tool()
def get_umi_service(name: str = None, status: str = None) -> list[dict]:
    """
    Returns system services: Windows Services, systemd units, or launchd agents
    depending on the host OS. Optionally filter by name substring or by status
    (Running, Stopped, Degraded, Starting, Stopping, Paused).
    """
    return get_service(name=name, status=status)


@mcp.tool()
def get_umi_summary(error_lookback_hours: int = 24) -> dict:
    """
    Provides a high-level health and utilization snapshot of the local
    system. Aggregates critical metrics from uptime, storage, processes,
    and event logs into a single flat response. Use this for rapid
    situational awareness and initial triage before employing specialized
    diagnostic tools. Valid events_level values for error counting:
    Info, Warning, Error, Critical.
    """
    uptime_data = get_uptime()
    disk_data = get_disk()
    process_data = get_process()
    events_data = get_events(level="Error", last_n=500)

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

    return {
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
    }


@mcp.tool()
def get_umi_events(level: str = "Error", source: str = None, last_n: int = 20) -> list[dict]:
    """
    Returns recent system events/log entries normalized across Windows Event Log,
    Linux journald, and macOS unified logging. Filter by severity level, optional
    source substring, and limit the number of returned entries with last_n.
    Valid level values: Info, Warning, Error, Critical (default: Error).
    Message is truncated to 500 characters.
    """
    return get_events(level=level, source=source, last_n=last_n)

import psutil
from datetime import datetime, timezone

STATUS_MAP = {
    psutil.STATUS_RUNNING: "Running",
    psutil.STATUS_SLEEPING: "Sleeping",
    psutil.STATUS_DISK_SLEEP: "Sleeping",
    psutil.STATUS_STOPPED: "Stopped",
    psutil.STATUS_ZOMBIE: "Zombie",
    psutil.STATUS_IDLE: "Idle",
    psutil.STATUS_DEAD: "Stopped",
    psutil.STATUS_WAKING: "Running",
    psutil.STATUS_PARKED: "Sleeping",
}

ATTRS = [
    "pid", "name", "ppid", "cpu_percent", "memory_info",
    "memory_percent", "status", "username", "create_time",
    "cmdline", "num_threads",
]


def get_process(name: str = None, top: int = None) -> list[dict]:
    results = []

    for proc in psutil.process_iter(ATTRS, ad_value=None):
        info = proc.info
        if not info.get("name"):
            continue
        if name and name.lower() not in info["name"].lower():
            continue

        mem_bytes = info["memory_info"].rss if info["memory_info"] else 0

        start_time = None
        if info["create_time"]:
            try:
                start_time = datetime.fromtimestamp(
                    info["create_time"], tz=timezone.utc
                ).isoformat()
            except (OSError, ValueError, OverflowError):
                pass

        cmdline = " ".join(info["cmdline"]) if info["cmdline"] else None
        status = STATUS_MAP.get(info.get("status", ""), "Unknown")

        results.append({
            "ProcessName": info["name"],
            "ProcessId": info["pid"],
            "ParentProcessId": info["ppid"],
            "CpuPercent": round(info["cpu_percent"] or 0.0, 1),
            "MemoryBytes": mem_bytes,
            "MemoryPercent": round(info["memory_percent"], 1) if info["memory_percent"] else None,
            "Status": status,
            "User": info["username"],
            "StartTime": start_time,
            "CommandLine": cmdline,
            "ThreadCount": info["num_threads"],
        })

    results.sort(key=lambda p: p["CpuPercent"], reverse=True)

    if top:
        results = results[:top]

    return results

import platform
import time
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
    "pid", "name", "ppid", "memory_info",
    "memory_percent", "status", "username", "create_time",
    "cmdline", "num_threads", "exe",
]

CPU_SAMPLE_INTERVAL = 0.5

# Usernames that indicate a kernel or OS-owned process on Windows and Unix.
_SYSTEM_USERNAMES = frozenset({
    "system",
    "nt authority\\system",
    "nt authority\\network service",
    "nt authority\\local service",
    "local service",
    "network service",
    "root",
})


def _classify_process_type(username: "str | None", pid: int) -> str:
    """Return 'System' for kernel/OS-owned processes; 'User' for everything else."""
    if pid <= 4:
        return "System"
    if (username or "").lower() in _SYSTEM_USERNAMES:
        return "System"
    return "User"


def get_process(name: str = None, top: int = None) -> list[dict]:
    is_windows = platform.system() == "Windows"

    # Pass 1: collect processes and prime per-process cpu_percent baseline
    procs = []
    for proc in psutil.process_iter(ATTRS, ad_value=None):
        info = proc.info
        if not info.get("name"):
            continue
        if name and name.lower() not in info["name"].lower():
            continue
        if is_windows and info["name"] == "System Idle Process":
            continue
        try:
            proc.cpu_percent()  # Prime — first call always returns 0.0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        procs.append((proc, info))

    # Build PID→name map from the full collected list for ParentProcessName lookup
    pid_to_name: dict[int, str] = {
        info["pid"]: info["name"]
        for _, info in procs
        if info.get("pid") is not None and info.get("name")
    }

    # Wait for the measurement interval
    time.sleep(CPU_SAMPLE_INTERVAL)

    # Pass 2: read accurate cpu_percent for each primed process
    results = []
    for proc, info in procs:
        try:
            cpu = proc.cpu_percent()  # Accurate delta since pass 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            cpu = 0.0

        # ExecutablePath — may raise AccessDenied on system processes
        try:
            exe_path = info.get("exe") or None
        except Exception:
            exe_path = None

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
        username = info["username"]
        pid = info["pid"]
        ppid = info.get("ppid")

        results.append({
            "ProcessName": info["name"],
            "ProcessId": pid,
            "ParentProcessId": ppid,
            "ParentProcessName": pid_to_name.get(ppid) if ppid is not None else None,
            "CpuPercent": round(cpu, 1),
            "MemoryBytes": mem_bytes,
            "MemoryPercent": round(info["memory_percent"], 1) if info["memory_percent"] else None,
            "Status": status,
            "User": username,
            "ProcessType": _classify_process_type(username, pid),
            "ExecutablePath": exe_path,
            "Publisher": None,   # v1: populated in a future Windows enrichment pass
            "ServiceName": None, # v1: populated in a future Windows enrichment pass
            "StartTime": start_time,
            "CommandLine": cmdline,
            "ThreadCount": info["num_threads"],
        })

    results.sort(key=lambda p: p["CpuPercent"], reverse=True)

    if top:
        results = results[:top]

    return results

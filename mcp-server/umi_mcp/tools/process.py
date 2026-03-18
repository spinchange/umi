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

LIGHT_ATTRS = ["pid", "name", "cpu_times"]

CPU_SAMPLE_INTERVAL = 0.5
MIN_CANDIDATE_COUNT = 24
CPU_CANDIDATE_MULTIPLIER = 4


def _get_process_details(proc: psutil.Process) -> dict:
    try:
        info = proc.as_dict(
            attrs=[
                "ppid", "memory_info", "memory_percent", "status",
                "username", "create_time", "num_threads", "cmdline",
            ],
            ad_value=None,
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return {
            "ParentProcessId": None,
            "MemoryBytes": 0,
            "MemoryPercent": None,
            "Status": "Unknown",
            "User": None,
            "StartTime": None,
            "CommandLine": None,
            "ThreadCount": None,
        }

    start_time = None
    if info.get("create_time"):
        try:
            start_time = datetime.fromtimestamp(
                info["create_time"], tz=timezone.utc
            ).isoformat()
        except (OSError, ValueError, OverflowError):
            pass

    mem_info = info.get("memory_info")
    cmdline = " ".join(info["cmdline"]) if info.get("cmdline") else None
    status = STATUS_MAP.get(info.get("status", ""), "Unknown")

    return {
        "ParentProcessId": info.get("ppid"),
        "MemoryBytes": mem_info.rss if mem_info else 0,
        "MemoryPercent": round(info["memory_percent"], 1) if info.get("memory_percent") else None,
        "Status": status,
        "User": info.get("username"),
        "StartTime": start_time,
        "CommandLine": cmdline,
        "ThreadCount": info.get("num_threads"),
    }


def get_process(name: str = None, top: int = None, include_command_line: bool = True) -> list[dict]:
    is_windows = platform.system() == "Windows"

    # Pass 1: collect lightweight process data and rank by cumulative CPU time.
    # We only do live cpu_percent sampling for a bounded candidate set.
    procs = []
    for proc in psutil.process_iter(LIGHT_ATTRS, ad_value=None):
        info = proc.info
        if not info.get("name"):
            continue
        if name and name.lower() not in info["name"].lower():
            continue
        if is_windows and info["name"] == "System Idle Process":
            continue
        cpu_times = info.get("cpu_times")
        cpu_total = (cpu_times.user + cpu_times.system) if cpu_times else 0.0
        procs.append((proc, info, cpu_total))

    results = []
    for proc, info, cpu_total in procs:
        results.append({
            "ProcessName": info["name"],
            "ProcessId": info["pid"],
            "ParentProcessId": None,
            "CpuPercent": 0.0,
            "MemoryBytes": 0,
            "MemoryPercent": None,
            "Status": "Unknown",
            "User": None,
            "StartTime": None,
            "CommandLine": None,
            "ThreadCount": None,
            "_cpu_total": cpu_total,
            "_proc": proc,
        })

    results.sort(key=lambda p: p["_cpu_total"], reverse=True)

    candidate_count = min(
        len(results),
        max(MIN_CANDIDATE_COUNT, (top or MIN_CANDIDATE_COUNT) * CPU_CANDIDATE_MULTIPLIER),
    )
    candidates = results[:candidate_count]

    for result in candidates:
        try:
            result["_proc"].cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(CPU_SAMPLE_INTERVAL)

    for result in candidates:
        try:
            cpu = result["_proc"].cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            cpu = 0.0
        result["CpuPercent"] = round(cpu, 1)

    results.sort(key=lambda p: (p["CpuPercent"], p["_cpu_total"]), reverse=True)

    if top:
        results = results[:top]

    for result in results:
        details = _get_process_details(result["_proc"])
        result.update(details)

    if not include_command_line:
        for result in results:
            result["CommandLine"] = None

    for result in results:
        result.pop("_proc", None)

    return results

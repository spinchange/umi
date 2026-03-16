import platform
import socket
import subprocess
import psutil
from datetime import datetime, timezone

OS_MAP = {"Windows": "Windows", "Linux": "Linux", "Darwin": "macOS"}

ARCH_MAP = {
    "AMD64": "x64", "x86_64": "x64",
    "x86": "x86", "i386": "x86", "i686": "x86",
    "ARM64": "ARM64", "aarch64": "ARM64",
    "armv7l": "ARM", "arm": "ARM",
}


def _get_powershell_version(os_name: str) -> str | None:
    if os_name != "Windows":
        return None

    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$PSVersionTable.PSVersion.ToString()",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError:
        return None

    version = (out.stdout or "").strip()
    return version or None


def get_uptime() -> dict:
    boot_ts = psutil.boot_time()
    boot_dt = datetime.fromtimestamp(boot_ts, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    uptime_secs = int((now - boot_dt).total_seconds())

    days = uptime_secs // 86400
    hours = (uptime_secs % 86400) // 3600
    minutes = (uptime_secs % 3600) // 60

    os_name = platform.system()

    if os_name == "Darwin":
        os_version = platform.mac_ver()[0]
    elif os_name == "Windows":
        os_version = platform.version()
    else:
        try:
            import distro
            os_version = f"{distro.name()} {distro.version()}"
        except ImportError:
            os_version = platform.release()

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu_percent = psutil.cpu_percent(interval=0.5)
    if os_name == "Windows":
        load_avg = None
    else:
        load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else None
    powershell_version = _get_powershell_version(os_name)

    return {
        "Hostname": socket.gethostname(),
        "OS": OS_MAP.get(os_name, os_name),
        "OSVersion": os_version,
        "Architecture": ARCH_MAP.get(platform.machine(), platform.machine()),
        "BootTime": boot_dt.isoformat(),
        "UptimeSeconds": uptime_secs,
        "UptimeHuman": f"{days}d {hours}h {minutes}m",
        "CpuCount": psutil.cpu_count(logical=True),
        "TotalMemoryBytes": mem.total,
        "CpuPercentOverall": round(cpu_percent, 1),
        "MemoryUsedBytes": mem.used,
        "MemoryAvailableBytes": mem.available,
        "SwapTotalBytes": swap.total,
        "SwapUsedBytes": swap.used,
        "LoadAverage1m": round(load_avg[0], 2) if load_avg else None,
        "LoadAverage5m": round(load_avg[1], 2) if load_avg else None,
        "LoadAverage15m": round(load_avg[2], 2) if load_avg else None,
        "PowerShellVersion": powershell_version,
    }

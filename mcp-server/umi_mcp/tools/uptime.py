import platform
import socket
import psutil
from datetime import datetime, timezone

OS_MAP = {"Windows": "Windows", "Linux": "Linux", "Darwin": "macOS"}

ARCH_MAP = {
    "AMD64": "x64", "x86_64": "x64",
    "x86": "x86", "i386": "x86", "i686": "x86",
    "ARM64": "ARM64", "aarch64": "ARM64",
    "armv7l": "ARM", "arm": "ARM",
}


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

    return {
        "Hostname": socket.gethostname(),
        "OS": OS_MAP.get(os_name, os_name),
        "OSVersion": os_version,
        "Architecture": ARCH_MAP.get(platform.machine(), platform.machine()),
        "BootTime": boot_dt.isoformat(),
        "UptimeSeconds": uptime_secs,
        "UptimeHuman": f"{days}d {hours}h {minutes}m",
        "CpuCount": psutil.cpu_count(logical=True),
        "TotalMemoryBytes": psutil.virtual_memory().total,
        "PowerShellVersion": None,
    }

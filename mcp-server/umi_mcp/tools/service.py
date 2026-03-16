import json
import platform
import subprocess


def get_service(name: str = None, status: str = None) -> list[dict]:
    os_name = platform.system()
    if os_name == "Windows":
        return _get_services_windows(name, status)
    elif os_name == "Linux":
        return _get_services_linux(name, status)
    elif os_name == "Darwin":
        return _get_services_macos(name, status)
    return []


def _matches(value: str, filter_str: str) -> bool:
    return filter_str is None or filter_str.lower() in value.lower()


def _get_services_windows(name_filter, status_filter) -> list[dict]:
    results = []
    STATUS_MAP = {0: "Unknown", 1: "Stopped", 2: "Starting", 3: "Stopping",
                  4: "Running", 5: "Unknown", 6: "Paused", 7: "Paused"}
    START_MAP = {0: "Unknown", 1: "OnDemand", 2: "Automatic", 3: "Manual",
                 4: "Disabled", 5: "Delayed"}

    ps_cmd = (
        "Get-WmiObject Win32_Service | "
        "Select-Object Name,DisplayName,Description,State,StartMode,StartName,ProcessId,PathName,ExitCode | "
        "ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30,
        )
        services = json.loads(out.stdout)
        if isinstance(services, dict):
            services = [services]

        STATE_STR = {
            "running": "Running", "stopped": "Stopped", "paused": "Paused",
            "start pending": "Starting", "stop pending": "Stopping",
            "pause pending": "Paused", "continue pending": "Starting",
        }
        START_STR = {
            "auto": "Automatic", "manual": "Manual", "disabled": "Disabled",
            "delayed-auto": "Delayed",
        }

        for svc in services:
            sname = svc.get("Name", "")
            if not _matches(sname, name_filter):
                continue

            status_str = STATE_STR.get((svc.get("State") or "").lower(), "Unknown")
            if not _matches(status_str, status_filter):
                continue

            results.append({
                "ServiceName": sname,
                "DisplayName": svc.get("DisplayName"),
                "Description": svc.get("Description") or None,
                "Status": status_str,
                "StartType": START_STR.get((svc.get("StartMode") or "").lower(), "Unknown"),
                "User": svc.get("StartName") or None,
                "ProcessId": svc.get("ProcessId") or None,
                "BinaryPath": svc.get("PathName") or None,
                "UptimeSeconds": None,
                "ExitCode": svc.get("ExitCode"),
            })
    except Exception:
        pass

    return results


def _get_services_linux(name_filter, status_filter) -> list[dict]:
    results = []

    try:
        out = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all",
             "--output=json", "--no-pager"],
            capture_output=True, text=True, timeout=30,
        )
        units = json.loads(out.stdout)

        STATE_MAP = {
            "active": "Running", "inactive": "Stopped", "failed": "Degraded",
            "activating": "Starting", "deactivating": "Stopping", "reloading": "Running",
        }

        for unit in units:
            unit_name = unit.get("unit", "")
            if not unit_name.endswith(".service"):
                continue
            sname = unit_name[:-8]

            if not _matches(sname, name_filter):
                continue

            status_str = STATE_MAP.get(unit.get("active", "").lower(), "Unknown")
            if not _matches(status_str, status_filter):
                continue

            results.append({
                "ServiceName": sname,
                "DisplayName": unit.get("description") or sname,
                "Description": None,
                "Status": status_str,
                "StartType": "Unknown",
                "User": None,
                "ProcessId": None,
                "BinaryPath": None,
                "UptimeSeconds": None,
                "ExitCode": None,
            })
    except Exception:
        pass

    return results


def _get_services_macos(name_filter, status_filter) -> list[dict]:
    results = []

    try:
        out = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=30,
        )
        for line in out.stdout.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            pid_str, _, label = parts[0], parts[1], parts[2]

            if not _matches(label, name_filter):
                continue

            is_running = pid_str.strip() != "-"
            status_str = "Running" if is_running else "Stopped"

            if not _matches(status_str, status_filter):
                continue

            results.append({
                "ServiceName": label,
                "DisplayName": label,
                "Description": None,
                "Status": status_str,
                "StartType": "Unknown",
                "User": None,
                "ProcessId": int(pid_str) if is_running else None,
                "BinaryPath": None,
                "UptimeSeconds": None,
                "ExitCode": None,
            })
    except Exception:
        pass

    return results

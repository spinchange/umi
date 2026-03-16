import json
import platform
import subprocess
from datetime import datetime, timezone


MAX_MESSAGE_LENGTH = 500
COMMAND_TIMEOUT_SECONDS = 30
WINDOWS_LEVEL_MAP = {
    "Critical": 1,
    "Error": 2,
    "Warning": 3,
    "Information": 4,
    "Verbose": 5,
}
LINUX_LEVEL_MAP = {
    "Emergency": "emerg",
    "Alert": "alert",
    "Critical": "crit",
    "Error": "err",
    "Warning": "warning",
    "Notice": "notice",
    "Information": "info",
    "Info": "info",
    "Debug": "debug",
}
LINUX_PRIORITY_LABELS = {
    "0": "Emergency",
    "1": "Alert",
    "2": "Critical",
    "3": "Error",
    "4": "Warning",
    "5": "Notice",
    "6": "Information",
    "7": "Debug",
}
MACOS_LEVEL_MAP = {
    "fault": "Critical",
    "error": "Error",
    "default": "Information",
    "info": "Information",
    "debug": "Debug",
}


def _truncate_message(message: str | None) -> str | None:
    if message is None:
        return None
    cleaned = " ".join(str(message).split())
    if len(cleaned) <= MAX_MESSAGE_LENGTH:
        return cleaned
    return cleaned[: MAX_MESSAGE_LENGTH - 3] + "..."


def _parse_timestamp(value) -> str | None:
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text) / 1_000_000, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None

    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f%z")
        except ValueError:
            try:
                parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S%z")
            except ValueError:
                return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _normalize_event(timestamp, level, source, event_id, message) -> dict:
    if isinstance(event_id, str) and event_id.isdigit():
        event_id = int(event_id)

    return {
        "Timestamp": _parse_timestamp(timestamp),
        "Level": level or "Unknown",
        "Source": source or None,
        "EventId": event_id if isinstance(event_id, int) else None,
        "Message": _truncate_message(message),
    }


def get_events(level: str = "Error", source: str = None, last_n: int = 20) -> list[dict]:
    requested = max(int(last_n or 20), 1)
    os_name = platform.system()

    if os_name == "Windows":
        return _get_events_windows(level, source, requested)
    if os_name == "Linux":
        return _get_events_linux(level, source, requested)
    if os_name == "Darwin":
        return _get_events_macos(level, source, requested)
    return []


def _get_events_windows(level: str, source: str | None, last_n: int) -> list[dict]:
    ps_level = WINDOWS_LEVEL_MAP.get(level, WINDOWS_LEVEL_MAP["Error"])
    scan_limit = min(max(last_n * 10, 100), 1000)
    source_clause = ""
    if source:
        escaped_source = source.replace("'", "''")
        source_clause = (
            f" | Where-Object {{ $_.ProviderName -like '*{escaped_source}*' }}"
        )

    ps_cmd = (
        "$events = Get-WinEvent "
        f"-FilterHashtable @{{ LogName=@('Application','System'); Level={ps_level} }} "
        f"-MaxEvents {scan_limit} -ErrorAction SilentlyContinue"
        f"{source_clause}; "
        f"$events | Select-Object -First {last_n} "
        "| Select-Object TimeCreated, LevelDisplayName, ProviderName, Id, Message "
        "| ConvertTo-Json -Compress"
    )

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError:
        return []

    if out.returncode != 0 or not out.stdout.strip():
        return []

    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = [data]

    return [
        _normalize_event(
            item.get("TimeCreated"),
            item.get("LevelDisplayName"),
            item.get("ProviderName"),
            item.get("Id"),
            item.get("Message"),
        )
        for item in data
    ]


def _get_events_linux(level: str, source: str | None, last_n: int) -> list[dict]:
    priority = LINUX_LEVEL_MAP.get(level, LINUX_LEVEL_MAP["Error"])
    scan_limit = min(max(last_n * 10, 100), 2000)

    try:
        out = subprocess.run(
            [
                "journalctl",
                "--no-pager",
                "--output",
                "json",
                "--priority",
                priority,
                "-n",
                str(scan_limit),
            ],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError:
        return []

    if out.returncode != 0:
        return []

    source_filter = source.lower() if source else None
    results = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_source = (
            item.get("SYSLOG_IDENTIFIER")
            or item.get("_SYSTEMD_UNIT")
            or item.get("_COMM")
            or item.get("_EXE")
        )
        if source_filter and source_filter not in str(event_source or "").lower():
            continue

        results.append(
            _normalize_event(
                item.get("__REALTIME_TIMESTAMP"),
                LINUX_PRIORITY_LABELS.get(str(item.get("PRIORITY")), level),
                event_source,
                None,
                item.get("MESSAGE"),
            )
        )
        if len(results) >= last_n:
            break

    return results


def _get_events_macos(level: str, source: str | None, last_n: int) -> list[dict]:
    scan_limit = min(max(last_n * 10, 100), 1000)

    try:
        out = subprocess.run(
            [
                "log",
                "show",
                "--style",
                "json",
                "--last",
                "1d",
            ],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError:
        return []

    if out.returncode != 0:
        return []

    level_filter = level.lower()
    source_filter = source.lower() if source else None
    collected = []

    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        raw_level = str(item.get("messageType") or item.get("level") or "default").lower()
        normalized_level = MACOS_LEVEL_MAP.get(raw_level, raw_level.title())
        if level_filter and normalized_level.lower() != level_filter:
            continue

        event_source = (
            item.get("subsystem")
            or item.get("processImagePath")
            or item.get("senderImagePath")
            or item.get("process")
        )
        if source_filter and source_filter not in str(event_source or "").lower():
            continue

        collected.append(
            _normalize_event(
                item.get("timestamp"),
                normalized_level,
                event_source,
                item.get("eventIdentifier"),
                item.get("eventMessage") or item.get("message"),
            )
        )

    return collected[-last_n:]

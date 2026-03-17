import json
import os
import platform
import re
import subprocess

import psutil

_NETWORK_FS = {"smb", "cifs", "nfs", "nfs4", "afpfs", "davfs", "sshfs", "fuse.sshfs", "ncpfs", "afs"}
_REMOVABLE_FS = {"iso9660", "udf", "cdfs", "udf"}
_VIRTUAL_FS = {"tmpfs", "ramfs", "zfs", "fuse", "fuseblk"}

PSEUDO_FS = {
    "tmpfs", "devtmpfs", "proc", "sysfs", "devpts", "cgroup", "cgroup2",
    "overlay", "shm", "udev", "squashfs", "efivarfs", "bpf", "tracefs",
    "debugfs", "securityfs", "pstore", "hugetlbfs", "mqueue", "configfs",
    "fusectl", "fuse.gvfsd-fuse", "autofs", "nsfs",
}

PSEUDO_MOUNTS = ("/proc", "/sys", "/dev", "/run", "/snap")
WINDOWS_IO_TIMEOUT_SECONDS = 10
IO_FIELD_NAMES = (
    "ReadCount",
    "WriteCount",
    "ReadBytes",
    "WriteBytes",
    "ReadTimeMs",
    "WriteTimeMs",
)


def _classify_volume_type(part) -> str:
    opts = (getattr(part, "opts", "") or "").lower()
    fstype = (part.fstype or "").lower()
    device = (part.device or "").lower()

    if fstype in _NETWORK_FS or "remote" in opts:
        return "Network"
    if fstype in _REMOVABLE_FS or "cdrom" in opts:
        return "Removable"
    if "removable" in opts:
        return "Removable"
    if fstype in _VIRTUAL_FS or device.startswith("zfs"):
        return "Virtual"
    return "Fixed"


def _is_removable(part) -> bool:
    opts = (getattr(part, "opts", "") or "").lower()
    fstype = (part.fstype or "").lower()
    return "cdrom" in opts or "removable" in opts or fstype in _REMOVABLE_FS


def _null_io_fields() -> dict:
    return {name: None for name in IO_FIELD_NAMES}


def _normalize_windows_drive(value: str | None) -> str | None:
    if not value:
        return None
    drive = value.strip().rstrip("\\/")
    if len(drive) >= 2 and drive[1] == ":":
        return f"{drive[0].upper()}:\\"
    return None


def _load_windows_drive_map() -> dict[str, str]:
    ps_cmd = (
        "Get-Partition | "
        "Where-Object DriveLetter | "
        "Select-Object DriveLetter, DiskNumber | "
        "ConvertTo-Json -Compress"
    )

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=WINDOWS_IO_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError:
        return {}

    if out.returncode != 0 or not out.stdout.strip():
        return {}

    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}

    if isinstance(data, dict):
        data = [data]

    mapping: dict[str, str] = {}
    for entry in data:
        drive_letter = entry.get("DriveLetter")
        disk_number = entry.get("DiskNumber")
        if not drive_letter or disk_number is None:
            continue
        mapping[f"{str(drive_letter).upper()}:\\"] = f"PhysicalDrive{disk_number}"

    return mapping


def _load_windows_label_map() -> dict[str, str | None]:
    ps_cmd = (
        "Get-Volume | "
        "Where-Object { $_.DriveLetter } | "
        "Select-Object DriveLetter, FileSystemLabel | "
        "ConvertTo-Json -Compress"
    )

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=WINDOWS_IO_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError:
        return {}

    if out.returncode != 0 or not out.stdout.strip():
        return {}

    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}

    if isinstance(data, dict):
        data = [data]

    mapping: dict[str, str | None] = {}
    for entry in data:
        drive_letter = entry.get("DriveLetter")
        if not drive_letter:
            continue
        label = entry.get("FileSystemLabel") or None
        mapping[f"{str(drive_letter).upper()}:\\"] = label

    return mapping


def _device_candidates(device_name: str | None, mount_point: str | None) -> list[str]:
    candidates: list[str] = []
    for raw in (device_name, mount_point):
        if not raw:
            continue
        if platform.system() == "Windows":
            drive = _normalize_windows_drive(raw)
            if drive:
                candidates.append(drive)
            continue

        base = os.path.basename(raw.rstrip("/")) or raw.rstrip("/")
        if base.startswith("/dev/"):
            base = base[5:]
        if base:
            candidates.append(base)

            if re.match(r"^nvme\d+n\d+p\d+$", base):
                candidates.append(re.sub(r"p\d+$", "", base))
            elif re.match(r"^mmcblk\d+p\d+$", base):
                candidates.append(re.sub(r"p\d+$", "", base))
            elif re.match(r"^disk\d+s\d+$", base):
                candidates.append(re.sub(r"s\d+$", "", base))
            elif re.match(r"^[a-z]+\d+$", base):
                candidates.append(re.sub(r"\d+$", "", base))

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def _resolve_io_counter(
    part,
    io_counters: dict,
    windows_drive_map: dict[str, str],
):
    if platform.system() == "Windows":
        drive = _normalize_windows_drive(part.device) or _normalize_windows_drive(part.mountpoint)
        if drive:
            physical_name = windows_drive_map.get(drive)
            if physical_name and physical_name in io_counters:
                return io_counters[physical_name]

    for candidate in _device_candidates(part.device, part.mountpoint):
        if candidate in io_counters:
            return io_counters[candidate]

    return None


def _extract_io_fields(io_counter) -> dict:
    if io_counter is None:
        return _null_io_fields()

    return {
        "ReadCount": getattr(io_counter, "read_count", None),
        "WriteCount": getattr(io_counter, "write_count", None),
        "ReadBytes": getattr(io_counter, "read_bytes", None),
        "WriteBytes": getattr(io_counter, "write_bytes", None),
        "ReadTimeMs": getattr(io_counter, "read_time", None),
        "WriteTimeMs": getattr(io_counter, "write_time", None),
    }


def get_disk() -> list[dict]:
    io_counters = psutil.disk_io_counters(perdisk=True) or {}
    is_windows = platform.system() == "Windows"
    windows_drive_map = _load_windows_drive_map() if is_windows else {}
    windows_label_map = _load_windows_label_map() if is_windows else {}
    results = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype.lower() in PSEUDO_FS:
            continue
        if any(part.mountpoint.startswith(m) for m in PSEUDO_MOUNTS):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue

        used_pct = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0.0
        io_counter = _resolve_io_counter(part, io_counters, windows_drive_map)

        if is_windows:
            drive_key = _normalize_windows_drive(part.device) or _normalize_windows_drive(part.mountpoint)
            label = windows_label_map.get(drive_key) if drive_key else None
        else:
            label = None

        results.append({
            "DeviceName": part.device,
            "MountPoint": part.mountpoint,
            "FileSystem": part.fstype.upper() if part.fstype else "Unknown",
            "VolumeType": _classify_volume_type(part),
            "TotalBytes": usage.total,
            "UsedBytes": usage.used,
            "FreeBytes": usage.free,
            "UsedPercent": used_pct,
            "IsRemovable": _is_removable(part),
            "Label": label,
            **_extract_io_fields(io_counter),
        })

    return results

import psutil

PSEUDO_FS = {
    "tmpfs", "devtmpfs", "proc", "sysfs", "devpts", "cgroup", "cgroup2",
    "overlay", "shm", "udev", "squashfs", "efivarfs", "bpf", "tracefs",
    "debugfs", "securityfs", "pstore", "hugetlbfs", "mqueue", "configfs",
    "fusectl", "fuse.gvfsd-fuse", "autofs", "nsfs",
}

PSEUDO_MOUNTS = ("/proc", "/sys", "/dev", "/run", "/snap")


def get_disk() -> list[dict]:
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

        results.append({
            "DeviceName": part.device,
            "MountPoint": part.mountpoint,
            "FileSystem": part.fstype.upper() if part.fstype else "Unknown",
            "TotalBytes": usage.total,
            "UsedBytes": usage.used,
            "FreeBytes": usage.free,
            "UsedPercent": used_pct,
            "IsRemovable": False,
            "Label": None,
        })

    return results

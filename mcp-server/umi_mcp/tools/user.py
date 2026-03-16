import os
import platform


def get_user(current_only: bool = False) -> list[dict]:
    if platform.system() == "Windows":
        return _get_users_windows(current_only)
    return _get_users_unix(current_only)


def _get_users_windows(current_only: bool) -> list[dict]:
    import ctypes
    current_username = os.environ.get("USERNAME", "")
    is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

    entry = {
        "Username": current_username,
        "UserId": os.environ.get("USERSID"),
        "FullName": None,
        "HomeDirectory": os.path.expanduser("~"),
        "Shell": None,
        "IsCurrentUser": True,
        "IsAdmin": is_admin,
        "IsEnabled": None,
        "Groups": [],
        "LastLogin": None,
    }

    return [entry]


def _get_users_unix(current_only: bool) -> list[dict]:
    import pwd
    import grp

    current_uid = os.getuid()
    current_username = pwd.getpwuid(current_uid).pw_name
    is_linux = platform.system() == "Linux"
    min_uid = 1000 if is_linux else 500

    results = []

    try:
        all_pw = pwd.getpwall()
    except Exception:
        all_pw = [pwd.getpwuid(current_uid)]

    all_groups = grp.getgrall()

    for pw in all_pw:
        if pw.pw_uid < min_uid and pw.pw_uid != 0 and pw.pw_uid != current_uid:
            continue
        if current_only and pw.pw_name != current_username:
            continue

        is_current = pw.pw_name == current_username
        is_admin = pw.pw_uid == 0

        groups = [g.gr_name for g in all_groups if pw.pw_name in g.gr_mem]
        try:
            primary = grp.getgrgid(pw.pw_gid).gr_name
            if primary not in groups:
                groups.insert(0, primary)
        except KeyError:
            pass

        if not is_admin and any(g in groups for g in ("sudo", "wheel", "admin")):
            is_admin = True

        full_name = pw.pw_gecos.split(",")[0] if pw.pw_gecos else None

        results.append({
            "Username": pw.pw_name,
            "UserId": pw.pw_uid,
            "FullName": full_name or None,
            "HomeDirectory": pw.pw_dir or None,
            "Shell": pw.pw_shell or None,
            "IsCurrentUser": is_current,
            "IsAdmin": is_admin,
            "IsEnabled": None,
            "Groups": groups,
            "LastLogin": None,
        })

    return results

import json
import platform
import re
import socket
import struct
import subprocess

import psutil

_GATEWAY_TIMEOUT = 5
_DNS_TIMEOUT = 5


def _load_default_gateway_windows() -> tuple[str | None, str | None]:
    """Return (gateway_ip, interface_alias) for the lowest-metric default route."""
    ps_cmd = (
        "Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
        "| Sort-Object RouteMetric | Select-Object -First 1 "
        "| Select-Object NextHop, InterfaceAlias | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=_GATEWAY_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if out.returncode != 0 or not out.stdout.strip():
        return None, None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None, None
    gw = data.get("NextHop")
    iface = data.get("InterfaceAlias")
    if gw and gw not in ("", "0.0.0.0", "::"):
        return gw, iface
    return None, None


def _load_dns_servers_windows() -> dict[str, list[str]]:
    """Return {interface_alias: [dns_ip, ...]} for all IPv4-configured interfaces."""
    ps_cmd = (
        "Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue "
        "| Where-Object { $_.ServerAddresses } "
        "| Select-Object InterfaceAlias, @{N='Servers';E={[string[]]$_.ServerAddresses}} "
        "| ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=_DNS_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        data = [data]
    result: dict[str, list[str]] = {}
    for entry in data:
        alias = entry.get("InterfaceAlias")
        servers = entry.get("Servers") or []
        if alias and servers:
            if isinstance(servers, str):
                servers = [servers]
            result[alias] = list(servers)
    return result


def _load_default_gateway_linux() -> tuple[str | None, str | None]:
    """Return (gateway_ip, interface_name) from the default IPv4 route."""
    try:
        out = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=_GATEWAY_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "default" and parts[1] == "via":
            gw = parts[2]
            iface = None
            if "dev" in parts:
                idx = parts.index("dev")
                if idx + 1 < len(parts):
                    iface = parts[idx + 1]
            return gw, iface
    return None, None


def _load_dns_servers_resolv() -> list[str]:
    """Parse nameserver lines from resolv.conf.

    On systemd-resolved systems /etc/resolv.conf points to a local stub
    (127.0.0.53). We try the real upstream resolver file first.
    """
    _STUB_ADDRS = {"127.0.0.1", "127.0.0.53", "::1"}

    for path in ("/run/systemd/resolve/resolv.conf", "/etc/resolv.conf"):
        try:
            with open(path) as f:
                content = f.read()
        except (OSError, subprocess.TimeoutExpired):
            continue
        servers = re.findall(r"^nameserver\s+(\S+)", content, re.MULTILINE)
        real = [s for s in servers if s not in _STUB_ADDRS]
        if real:
            return real
        if servers:
            return servers  # all stubs — return them rather than nothing

    return []


def _load_default_gateway_macos() -> tuple[str | None, str | None]:
    """Return (gateway_ip, interface_name) from macOS routing table."""
    try:
        out = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True, timeout=_GATEWAY_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    gw = None
    iface = None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("gateway:"):
            gw = line.split(":", 1)[1].strip()
        elif line.startswith("interface:"):
            iface = line.split(":", 1)[1].strip()
    return gw, iface


def _load_dns_servers_scutil() -> list[str]:
    """Parse nameservers from macOS scutil --dns output."""
    try:
        out = subprocess.run(
            ["scutil", "--dns"],
            capture_output=True, text=True, timeout=_DNS_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    servers = re.findall(r"nameserver\[\d+\]\s*:\s*(\S+)", out.stdout)
    seen: set[str] = set()
    unique: list[str] = []
    for s in servers:
        if s not in seen:
            unique.append(s)
            seen.add(s)
    return unique


def _load_network_extras() -> tuple[str | None, str | None, dict[str, list[str]] | list[str]]:
    """Return (gateway_ip, default_iface, dns_info) for the current OS.

    dns_info is either a dict {iface_alias: [servers]} (Windows) or
    a flat list[str] of system-wide DNS servers (Linux/macOS).
    """
    os_name = platform.system()
    if os_name == "Windows":
        gw, iface = _load_default_gateway_windows()
        dns = _load_dns_servers_windows()
        return gw, iface, dns
    if os_name == "Linux":
        gw, iface = _load_default_gateway_linux()
        dns = _load_dns_servers_resolv()
        return gw, iface, dns
    if os_name == "Darwin":
        gw, iface = _load_default_gateway_macos()
        dns = _load_dns_servers_scutil()
        return gw, iface, dns
    return None, None, []


def _prefix_to_mask(prefix_len: int) -> str:
    mask = (0xFFFFFFFF >> (32 - prefix_len)) << (32 - prefix_len)
    return socket.inet_ntoa(struct.pack(">I", mask))


def _classify_interface(name: str) -> str:
    n = name.lower()
    if n.startswith("lo") or n == "loopback":
        return "Loopback"
    if any(n.startswith(p) for p in ("eth", "en", "eno", "ens", "enp")):
        return "Ethernet"
    if any(n.startswith(p) for p in ("wlan", "wi-fi", "wifi", "wl", "wlp")):
        return "WiFi"
    if any(n.startswith(p) for p in ("tun", "tap", "vpn")):
        return "Tunnel"
    if any(n.startswith(p) for p in ("veth", "docker", "br-", "virbr", "vbox")):
        return "Virtual"
    return "Unknown"


def get_network(include_down: bool = False) -> list[dict]:
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io_counters = psutil.net_io_counters(pernic=True)

    default_gw, default_iface, dns_info = _load_network_extras()
    # dns_info is either dict{alias: servers} (Windows) or list[str] (Linux/macOS)
    system_dns: list[str] = dns_info if isinstance(dns_info, list) else []

    results = []

    for iface_name, addr_list in addrs.items():
        stat = stats.get(iface_name)
        is_up = stat.isup if stat else False

        if not include_down and not is_up:
            continue

        ipv4 = None
        ipv6 = None
        mac = None
        subnet_mask = None

        for addr in addr_list:
            if addr.family == socket.AF_INET:
                ipv4 = addr.address
                if addr.netmask:
                    subnet_mask = addr.netmask
                elif hasattr(addr, "prefixlen") and addr.prefixlen:
                    subnet_mask = _prefix_to_mask(addr.prefixlen)
            elif addr.family == socket.AF_INET6:
                candidate = addr.address.split("%")[0]
                if not candidate.startswith("fe80") and ipv6 is None:
                    ipv6 = candidate
            elif addr.family == psutil.AF_LINK:
                raw = addr.address.replace("-", ":").upper()
                if raw and raw not in ("00:00:00:00:00:00", ""):
                    mac = raw

        io = io_counters.get(iface_name)

        # Gateway: assign to the default-route interface; null for all others
        gateway = default_gw if iface_name == default_iface else None

        # DNS: per-interface on Windows; system-wide on Linux/macOS (all Up interfaces)
        if isinstance(dns_info, dict):
            dns_servers = dns_info.get(iface_name, [])
        else:
            dns_servers = system_dns if is_up else []

        results.append({
            "InterfaceName": iface_name,
            "InterfaceType": _classify_interface(iface_name),
            "Status": "Up" if is_up else "Down",
            "IPv4Address": ipv4,
            "IPv6Address": ipv6,
            "SubnetMask": subnet_mask,
            "DefaultGateway": gateway,
            "MacAddress": mac,
            "SpeedMbps": stat.speed if stat and stat.speed > 0 else None,
            "DnsServers": dns_servers,
            "BytesSent": io.bytes_sent if io else None,
            "BytesReceived": io.bytes_recv if io else None,
            "PacketsSent": io.packets_sent if io else None,
            "PacketsReceived": io.packets_recv if io else None,
            "ErrorsIn": io.errin if io else None,
            "ErrorsOut": io.errout if io else None,
            "DropsIn": io.dropin if io else None,
            "DropsOut": io.dropout if io else None,
        })

    return results

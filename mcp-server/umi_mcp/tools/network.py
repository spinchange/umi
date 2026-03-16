import socket
import struct
import psutil


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

        results.append({
            "InterfaceName": iface_name,
            "InterfaceType": _classify_interface(iface_name),
            "Status": "Up" if is_up else "Down",
            "IPv4Address": ipv4,
            "IPv6Address": ipv6,
            "SubnetMask": subnet_mask,
            "DefaultGateway": None,
            "MacAddress": mac,
            "SpeedMbps": stat.speed if stat and stat.speed > 0 else None,
            "DnsServers": [],
        })

    return results

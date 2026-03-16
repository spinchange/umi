from mcp.server.fastmcp import FastMCP

from .tools.disk import get_disk
from .tools.events import get_events
from .tools.network import get_network
from .tools.process import get_process
from .tools.uptime import get_uptime
from .tools.user import get_user
from .tools.service import get_service

mcp = FastMCP("umi")


@mcp.tool()
def get_umi_disk() -> list[dict]:
    """
    Returns all mounted disk volumes with capacity and usage statistics.
    Use this to check which drives exist, their total size, how much is used
    and free, filesystem type, and mount point. Each volume is one object.
    Bytes fields: divide by 1073741824 for GB.
    """
    return get_disk()


@mcp.tool()
def get_umi_network(include_down: bool = False) -> list[dict]:
    """
    Returns network interfaces with IP addresses, MAC address, interface type,
    link speed, and status. By default only returns interfaces that are Up.
    Set include_down=true to include inactive interfaces.
    """
    return get_network(include_down=include_down)


@mcp.tool()
def get_umi_process(name: str = None, top: int = None) -> list[dict]:
    """
    Returns running processes sorted by CPU usage descending.
    Use name to filter by process name substring (e.g. name="python").
    Use top to limit results (e.g. top=10 for the 10 most CPU-intensive processes).
    MemoryBytes is resident set size. CpuPercent may exceed 100 on multi-core systems.
    """
    return get_process(name=name, top=top)


@mcp.tool()
def get_umi_uptime() -> dict:
    """
    Returns system identity and uptime: hostname, OS family (Windows/Linux/macOS),
    OS version string, CPU architecture, boot timestamp, seconds since boot,
    human-readable uptime, logical CPU count, and total installed RAM in bytes.
    """
    return get_uptime()


@mcp.tool()
def get_umi_user(current_only: bool = False) -> list[dict]:
    """
    Returns local user accounts with username, user ID, home directory, shell,
    group memberships, and admin status. Set current_only=true to return only
    the user running the current session.
    """
    return get_user(current_only=current_only)


@mcp.tool()
def get_umi_service(name: str = None, status: str = None) -> list[dict]:
    """
    Returns system services: Windows Services, systemd units, or launchd agents
    depending on the host OS. Optionally filter by name substring or by status
    (Running, Stopped, Degraded, Starting, Stopping, Paused).
    """
    return get_service(name=name, status=status)


@mcp.tool()
def get_umi_events(level: str = "Error", source: str = None, last_n: int = 20) -> list[dict]:
    """
    Returns recent system events/log entries normalized across Windows Event Log,
    Linux journald, and macOS unified logging. Filter by severity level, optional
    source substring, and limit the number of returned entries with last_n.
    Message is truncated to 500 characters.
    """
    return get_events(level=level, source=source, last_n=last_n)

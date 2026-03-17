import json
import runpy
import unittest
import socket
import psutil
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

from umi_mcp.server import (
    get_umi_disk,
    get_umi_network,
    get_umi_process,
    get_umi_uptime,
    get_umi_user,
    get_umi_service,
    get_umi_summary,
    get_umi_event_summary,
    get_umi_recent_changes,
)
from umi_mcp.tools import disk, uptime, network, process, service, user, events


class UptimeToolTests(unittest.TestCase):
    @patch("umi_mcp.tools.uptime.subprocess.run")
    @patch("umi_mcp.tools.uptime.socket.gethostname", return_value="test-host")
    @patch("umi_mcp.tools.uptime.platform.machine", return_value="x86_64")
    @patch("umi_mcp.tools.uptime.psutil.cpu_count", return_value=8)
    @patch("umi_mcp.tools.uptime.psutil.cpu_percent", return_value=10.5)
    @patch("umi_mcp.tools.uptime.psutil.swap_memory")
    @patch("umi_mcp.tools.uptime.psutil.virtual_memory")
    @patch("umi_mcp.tools.uptime.psutil.boot_time", return_value=1710590400.0)
    @patch("umi_mcp.tools.uptime.datetime")
    @patch("umi_mcp.tools.uptime.platform.system", return_value="Windows")
    @patch("umi_mcp.tools.uptime.platform.version", return_value="10.0.19045")
    @patch("umi_mcp.tools.uptime.psutil.getloadavg", return_value=None, create=True)
    def test_uptime_windows(
        self,
        _mock_load,
        _mock_version,
        _mock_system,
        mock_datetime,
        _mock_boot_time,
        mock_virtual_memory,
        mock_swap_memory,
        _mock_cpu_percent,
        _mock_cpu_count,
        _mock_machine,
        _mock_hostname,
        mock_subprocess_run,
    ):
        # Mocking datetime.now and datetime.fromtimestamp
        mock_now = datetime(2024, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        mock_boot = datetime(2024, 3, 16, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromtimestamp.return_value = mock_boot

        mock_virtual_memory.return_value = SimpleNamespace(total=16000, used=8000, available=8000)
        mock_swap_memory.return_value = SimpleNamespace(total=4000, used=1000)
        mock_subprocess_run.return_value = SimpleNamespace(stdout="7.4.6\n")

        result = uptime.get_uptime()

        self.assertEqual(result["Hostname"], "test-host")
        self.assertEqual(result["OS"], "Windows")
        self.assertEqual(result["OSVersion"], "10.0.19045")
        self.assertEqual(result["Architecture"], "x64")
        self.assertEqual(result["UptimeSeconds"], 3600)
        self.assertEqual(result["UptimeHuman"], "0d 1h 0m")
        self.assertEqual(result["TotalMemoryBytes"], 16000)
        self.assertIsNone(result["LoadAverage1m"])
        self.assertIsNone(result["LoadAverage5m"])
        self.assertIsNone(result["LoadAverage15m"])
        self.assertEqual(result["PowerShellVersion"], "7.4.6")
        _mock_load.assert_not_called()

    @patch("umi_mcp.tools.uptime.subprocess.run")
    @patch("umi_mcp.tools.uptime.psutil.getloadavg", return_value=(1.0, 0.5, 0.2), create=True)
    @patch("umi_mcp.tools.uptime.platform.mac_ver", return_value=("14.4", ("", "", ""), ""))
    @patch("umi_mcp.tools.uptime.platform.system", return_value="Darwin")
    @patch("umi_mcp.tools.uptime.psutil.boot_time", return_value=1710590400.0)
    @patch("umi_mcp.tools.uptime.datetime")
    @patch("umi_mcp.tools.uptime.psutil.virtual_memory")
    @patch("umi_mcp.tools.uptime.psutil.swap_memory")
    def test_uptime_macos_with_load(
        self,
        mock_swap,
        mock_virt,
        mock_datetime,
        _boot,
        _sys,
        _mac_ver,
        _load,
        mock_subprocess_run,
    ):
        mock_now = datetime(2024, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        mock_boot = datetime(2024, 3, 16, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromtimestamp.return_value = mock_boot
        mock_virt.return_value = SimpleNamespace(total=16000, used=8000, available=8000)
        mock_swap.return_value = SimpleNamespace(total=4000, used=1000)

        result = uptime.get_uptime()

        self.assertEqual(result["OS"], "macOS")
        self.assertEqual(result["OSVersion"], "14.4")
        self.assertEqual(result["LoadAverage1m"], 1.0)
        self.assertEqual(result["LoadAverage5m"], 0.5)
        self.assertEqual(result["LoadAverage15m"], 0.2)
        self.assertIsNone(result["PowerShellVersion"])
        mock_subprocess_run.assert_not_called()


class NetworkToolTests(unittest.TestCase):
    @patch("umi_mcp.tools.network.psutil.net_io_counters")
    @patch("umi_mcp.tools.network.psutil.net_if_stats")
    @patch("umi_mcp.tools.network.psutil.net_if_addrs")
    def test_get_network_filtering_and_classification(self, mock_addrs, mock_stats, mock_io):
        mock_addrs.return_value = {
            "lo": [
                SimpleNamespace(family=socket.AF_INET, address="127.0.0.1", netmask="255.0.0.0"),
            ],
            "eth0": [
                SimpleNamespace(family=socket.AF_INET, address="192.168.1.10", netmask="255.255.255.0"),
                SimpleNamespace(family=socket.AF_INET6, address="fe80::1%eth0", netmask=None),
                SimpleNamespace(family=socket.AF_INET6, address="2001:db8::1", netmask=None),
                SimpleNamespace(family=psutil.AF_LINK, address="00-11-22-33-44-55"),
            ],
            "wlan0": [
                SimpleNamespace(family=socket.AF_INET, address="10.0.0.5", netmask="255.255.255.0"),
            ]
        }
        mock_stats.return_value = {
            "lo": SimpleNamespace(isup=True, speed=0),
            "eth0": SimpleNamespace(isup=True, speed=1000),
            "wlan0": SimpleNamespace(isup=False, speed=300),
        }
        mock_io.return_value = {
            "eth0": SimpleNamespace(bytes_sent=100, bytes_recv=200, packets_sent=10, packets_recv=20, errin=0, errout=0, dropin=0, dropout=0)
        }

        # Test include_down=False
        result = network.get_network(include_down=False)
        self.assertEqual(len(result), 2)  # lo and eth0
        
        eth0 = next(r for r in result if r["InterfaceName"] == "eth0")
        self.assertEqual(eth0["InterfaceType"], "Ethernet")
        self.assertEqual(eth0["Status"], "Up")
        self.assertEqual(eth0["IPv4Address"], "192.168.1.10")
        self.assertEqual(eth0["IPv6Address"], "2001:db8::1")
        self.assertEqual(eth0["MacAddress"], "00:11:22:33:44:55")
        self.assertEqual(eth0["BytesSent"], 100)
        self.assertEqual(eth0["SpeedMbps"], 1000)

        lo = next(r for r in result if r["InterfaceName"] == "lo")
        self.assertEqual(lo["InterfaceType"], "Loopback")
        self.assertIsNone(lo["BytesSent"])

        # Test include_down=True
        result_all = network.get_network(include_down=True)
        self.assertEqual(len(result_all), 3)
        wlan0 = next(r for r in result_all if r["InterfaceName"] == "wlan0")
        self.assertEqual(wlan0["Status"], "Down")
        self.assertEqual(wlan0["InterfaceType"], "WiFi")


class ProcessToolTests(unittest.TestCase):
    @patch("umi_mcp.tools.process.time.sleep")
    @patch("umi_mcp.tools.process.psutil.process_iter")
    def test_get_process_filtering_and_top(self, mock_iter, _sleep):
        proc_python = MagicMock(info={
            "pid": 101, "name": "python.exe", "ppid": 100,
            "memory_info": SimpleNamespace(rss=1024), "memory_percent": 1.0,
            "status": psutil.STATUS_RUNNING, "username": "user1",
            "create_time": 1710590400.0, "cmdline": ["python", "app.py"], "num_threads": 2,
        })
        proc_python.cpu_percent.return_value = 5.0

        proc_chrome = MagicMock(info={
            "pid": 102, "name": "chrome.exe", "ppid": 100,
            "memory_info": SimpleNamespace(rss=2048), "memory_percent": 2.0,
            "status": psutil.STATUS_SLEEPING, "username": "user1",
            "create_time": 1710590401.0, "cmdline": ["chrome", "--tabs"], "num_threads": 10,
        })
        proc_chrome.cpu_percent.return_value = 15.0

        proc_bash = MagicMock(info={
            "pid": 103, "name": "bash", "ppid": 100,
            "memory_info": SimpleNamespace(rss=512), "memory_percent": 0.5,
            "status": psutil.STATUS_IDLE, "username": "user1",
            "create_time": 1710590402.0, "cmdline": ["bash"], "num_threads": 1,
        })
        proc_bash.cpu_percent.return_value = 0.0

        mock_iter.return_value = [proc_python, proc_chrome, proc_bash]

        # Test all processes, sorted by CPU desc
        result = process.get_process()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["ProcessName"], "chrome.exe")
        self.assertEqual(result[1]["ProcessName"], "python.exe")
        self.assertEqual(result[2]["ProcessName"], "bash")
        self.assertEqual(result[0]["Status"], "Sleeping")

        # Test filtering by name
        result_py = process.get_process(name="python")
        self.assertEqual(len(result_py), 1)
        self.assertEqual(result_py[0]["ProcessName"], "python.exe")

        # Test top
        result_top = process.get_process(top=1)
        self.assertEqual(len(result_top), 1)
        self.assertEqual(result_top[0]["ProcessName"], "chrome.exe")


class ServiceToolTests(unittest.TestCase):
    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Windows")
    def test_get_service_windows(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {
                    "Name": "TestSvc", "DisplayName": "Test Service", "Description": "A test",
                    "State": "Running", "StartMode": "Auto", "StartName": "LocalSystem",
                    "ProcessId": 1234, "PathName": "C:\\test.exe", "ExitCode": 0
                }
            ])
        )
        result = service.get_service(name="test")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "TestSvc")
        self.assertEqual(result[0]["Status"], "Running")
        self.assertEqual(result[0]["StartType"], "Automatic")

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Linux")
    def test_get_service_linux(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {
                    "unit": "ssh.service", "description": "SSH Daemon",
                    "active": "active", "sub": "running"
                },
                {
                    "unit": "cron.service", "description": "Cron Daemon",
                    "active": "inactive", "sub": "dead"
                }
            ])
        )
        result = service.get_service(status="Running")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "ssh")
        self.assertEqual(result[0]["Status"], "Running")

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Darwin")
    def test_get_service_macos(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout="pid\tstatus\tlabel\n123\t0\tcom.apple.test\n-\t0\tcom.apple.stopped"
        )
        result = service.get_service()
        self.assertEqual(len(result), 2)
        running = next(r for r in result if r["ServiceName"] == "com.apple.test")
        self.assertEqual(running["Status"], "Running")
        self.assertEqual(running["ProcessId"], 123)
        stopped = next(r for r in result if r["ServiceName"] == "com.apple.stopped")
        self.assertEqual(stopped["Status"], "Stopped")
        self.assertIsNone(stopped["ProcessId"])


class UserToolTests(unittest.TestCase):
    @patch("umi_mcp.tools.user.platform.system", return_value="Windows")
    def test_get_user_windows(self, _sys):
        mock_ctypes = MagicMock()
        mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = 1
        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch.dict("umi_mcp.tools.user.os.environ", {"USERNAME": "testuser", "USERSID": "S-1-5-21-123"}):
                result = user.get_user()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Username"], "testuser")
        self.assertEqual(result[0]["UserId"], "S-1-5-21-123")
        self.assertTrue(result[0]["IsAdmin"])

    @patch("umi_mcp.tools.user.platform.system", return_value="Linux")
    def test_get_user_unix(self, _sys):
        mock_pwd = MagicMock()
        mock_grp = MagicMock()
        
        # We must mock sys.modules because the tool does 'import pwd' internally
        with patch.dict("sys.modules", {"pwd": mock_pwd, "grp": mock_grp}):
            with patch("umi_mcp.tools.user.os.getuid", return_value=1000, create=True):
                mock_pwd.getpwuid.return_value = SimpleNamespace(pw_name="user1", pw_uid=1000, pw_gid=1000, pw_gecos="User One", pw_dir="/home/user1", pw_shell="/bin/bash")
                mock_pwd.getpwall.return_value = [
                    SimpleNamespace(pw_name="root", pw_uid=0, pw_gid=0, pw_gecos="root", pw_dir="/root", pw_shell="/bin/bash"),
                    SimpleNamespace(pw_name="user1", pw_uid=1000, pw_gid=1000, pw_gecos="User One", pw_dir="/home/user1", pw_shell="/bin/bash"),
                    SimpleNamespace(pw_name="nobody", pw_uid=65534, pw_gid=65534, pw_gecos="nobody", pw_dir="/", pw_shell="/sbin/nologin"),
                ]
                mock_grp.getgrall.return_value = [
                    SimpleNamespace(gr_name="sudo", gr_mem=["user1"]),
                    SimpleNamespace(gr_name="root", gr_mem=["root"]),
                ]
                mock_grp.getgrgid.return_value = SimpleNamespace(gr_name="user1")

                result = user.get_user(current_only=False)
                self.assertEqual(len(result), 3)
                
                root = next(r for r in result if r["Username"] == "root")
                self.assertTrue(root["IsAdmin"])
                
                user1 = next(r for r in result if r["Username"] == "user1")
                self.assertTrue(user1["IsCurrentUser"])
                self.assertTrue(user1["IsAdmin"])
                self.assertIn("sudo", user1["Groups"])

                result_current = user.get_user(current_only=True)
                self.assertEqual(len(result_current), 1)
                self.assertEqual(result_current[0]["Username"], "user1")


class UptimeLinuxToolTests(unittest.TestCase):
    def _base_patches(self):
        """Return a list of common patches shared by both Linux uptime tests."""
        return [
            patch("umi_mcp.tools.uptime.platform.system", return_value="Linux"),
            patch("umi_mcp.tools.uptime.platform.machine", return_value="x86_64"),
            patch("umi_mcp.tools.uptime.socket.gethostname", return_value="linux-host"),
            patch("umi_mcp.tools.uptime.psutil.boot_time", return_value=1710590400.0),
            patch("umi_mcp.tools.uptime.psutil.cpu_count", return_value=4),
            patch("umi_mcp.tools.uptime.psutil.cpu_percent", return_value=5.0),
            patch("umi_mcp.tools.uptime.psutil.getloadavg", return_value=(0.5, 0.4, 0.3)),
            patch(
                "umi_mcp.tools.uptime.psutil.virtual_memory",
                return_value=SimpleNamespace(total=8000, used=4000, available=4000),
            ),
            patch(
                "umi_mcp.tools.uptime.psutil.swap_memory",
                return_value=SimpleNamespace(total=2000, used=500),
            ),
            patch(
                "umi_mcp.tools.uptime.datetime",
                **{
                    "now.return_value": datetime(2024, 3, 16, 13, 0, 0, tzinfo=timezone.utc),
                    "fromtimestamp.return_value": datetime(2024, 3, 16, 12, 0, 0, tzinfo=timezone.utc),
                },
            ),
        ]

    def test_uptime_linux_with_distro(self):
        mock_distro = MagicMock()
        mock_distro.name.return_value = "Ubuntu"
        mock_distro.version.return_value = "22.04"

        patches = self._base_patches()
        with patch.dict(sys.modules, {"distro": mock_distro}):
            with ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                result = uptime.get_uptime()

        self.assertEqual(result["OS"], "Linux")
        self.assertEqual(result["OSVersion"], "Ubuntu 22.04")
        self.assertEqual(result["Hostname"], "linux-host")
        self.assertEqual(result["LoadAverage1m"], 0.5)

    def test_uptime_linux_distro_import_error_falls_back_to_platform_release(self):
        patches = self._base_patches()
        patches.append(
            patch("umi_mcp.tools.uptime.platform.release", return_value="5.15.0-generic")
        )

        with patch.dict(sys.modules, {"distro": None}):
            with ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                result = uptime.get_uptime()

        self.assertEqual(result["OS"], "Linux")
        self.assertEqual(result["OSVersion"], "5.15.0-generic")


class ServerToolRegistrationTests(unittest.TestCase):
    def _assert_envelope(self, result):
        """Assert that result is a properly-shaped UMI response envelope."""
        self.assertIsInstance(result, dict)
        self.assertEqual(result["SchemaVersion"], "1")
        self.assertIn("GeneratedAt", result)

    def _assert_array_envelope(self, result, expected_items):
        """Assert array-style envelope with Items and Count."""
        self._assert_envelope(result)
        self.assertEqual(result["Count"], len(expected_items))
        self.assertEqual(result["Items"], expected_items)

    @patch("umi_mcp.server.get_disk", return_value=[{"MountPoint": "/"}])
    def test_server_exposes_disk_tool(self, mock_fn):
        result = get_umi_disk()
        self._assert_array_envelope(result, [{"MountPoint": "/"}])
        mock_fn.assert_called_once_with()

    @patch("umi_mcp.server.get_network", return_value=[{"InterfaceName": "eth0"}])
    def test_server_exposes_network_tool(self, mock_fn):
        result = get_umi_network(include_down=True)
        self._assert_array_envelope(result, [{"InterfaceName": "eth0"}])
        mock_fn.assert_called_once_with(include_down=True)

    @patch("umi_mcp.server.get_process", return_value=[{"ProcessName": "python"}])
    def test_server_exposes_process_tool(self, mock_fn):
        result = get_umi_process(name="python", top=5)
        self._assert_array_envelope(result, [{"ProcessName": "python"}])
        mock_fn.assert_called_once_with(name="python", top=5)

    @patch("umi_mcp.server.get_uptime", return_value={"Hostname": "host1"})
    def test_server_exposes_uptime_tool(self, mock_fn):
        result = get_umi_uptime()
        self._assert_envelope(result)
        self.assertEqual(result["Hostname"], "host1")
        mock_fn.assert_called_once_with()

    @patch("umi_mcp.server.get_user", return_value=[{"Username": "alice"}])
    def test_server_exposes_user_tool(self, mock_fn):
        result = get_umi_user(current_only=True)
        self._assert_array_envelope(result, [{"Username": "alice"}])
        mock_fn.assert_called_once_with(current_only=True)

    @patch("umi_mcp.server.get_service", return_value=[{"ServiceName": "sshd"}])
    def test_server_exposes_service_tool(self, mock_fn):
        result = get_umi_service(name="ssh", status="Running")
        self._assert_array_envelope(result, [{"ServiceName": "sshd"}])
        mock_fn.assert_called_once_with(name="ssh", status="Running")

    @patch("umi_mcp.server.get_events", return_value=[])
    @patch("umi_mcp.server.get_process", return_value=[])
    @patch("umi_mcp.server.get_disk", return_value=[])
    @patch("umi_mcp.server.get_uptime", return_value={"Hostname": "host1"})
    def test_server_exposes_summary_tool(self, mock_uptime, mock_disk, mock_process, mock_events):
        result = get_umi_summary()
        self._assert_envelope(result)
        mock_uptime.assert_called_once_with()
        mock_disk.assert_called_once_with()
        mock_process.assert_called_once_with()
        self.assertTrue(mock_events.called)


_UPTIME = {
    "Hostname": "testhost", "OS": "Windows", "OSVersion": "10.0.19045",
    "Architecture": "x64", "UptimeSeconds": 3600, "CpuCount": 8,
    "CpuPercentOverall": 12.5, "TotalMemoryBytes": 16_000_000_000,
    "MemoryUsedBytes": 8_000_000_000, "MemoryAvailableBytes": 8_000_000_000,
    "LoadAverage1m": None,
}
_DISKS = [
    {"TotalBytes": 500_000_000_000, "UsedBytes": 200_000_000_000, "UsedPercent": 40.0},
    {"TotalBytes": 1_000_000_000_000, "UsedBytes": 900_000_000_000, "UsedPercent": 90.0},
]
_PROCESSES = [
    {"ProcessName": "chrome",  "ProcessId": 100, "CpuPercent": 45.0, "MemoryBytes": 500_000_000},
    {"ProcessName": "python",  "ProcessId": 200, "CpuPercent": 10.0, "MemoryBytes": 2_000_000_000},
    {"ProcessName": "svchost", "ProcessId": 300, "CpuPercent":  2.0, "MemoryBytes": 100_000_000},
]
# Two events — one recent (within 24h of mock now), one old
_NOW = datetime(2026, 3, 16, 12, 0, 0, tzinfo=timezone.utc)
_EVENTS = [
    {"Timestamp": "2026-03-16T11:00:00+00:00", "Level": "Error",   "Message": "Recent error"},
    {"Timestamp": "2026-03-14T08:00:00+00:00", "Level": "Warning", "Message": "Old warning"},
]


class SummaryToolTests(unittest.TestCase):

    def _call(self, uptime=None, disks=None, processes=None, events=None, **kwargs):
        with patch("umi_mcp.server.get_uptime",  return_value=_UPTIME if uptime is None else uptime), \
             patch("umi_mcp.server.get_disk",    return_value=_DISKS if disks is None else disks), \
             patch("umi_mcp.server.get_process", return_value=_PROCESSES if processes is None else processes), \
             patch("umi_mcp.server.get_events",  return_value=_EVENTS if events is None else events), \
             patch("umi_mcp.server.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.timezone = timezone
            return get_umi_summary(**kwargs)

    # --- shape ---

    def test_returns_dict(self):
        self.assertIsInstance(self._call(), dict)

    def test_all_required_fields_present(self):
        result = self._call()
        expected = [
            "Hostname", "OS", "OSVersion", "Architecture",
            "UptimeSeconds", "CpuCount", "CpuUtilizationPercent",
            "TotalMemoryBytes", "MemoryUsedBytes", "MemoryUsedPercent",
            "LoadAverageOneMinute",
            "TotalDiskBytes", "UsedDiskBytes", "MaxDiskUsedPercent",
            "TopCpuProcessName", "TopCpuProcessId",
            "TopMemoryProcessName", "TopMemoryProcessBytes",
            "RecentErrorCount", "LastEventTimestamp", "LastEventLevel", "LastEventMessage",
        ]
        for field in expected:
            self.assertIn(field, result, msg=f"Missing field: {field}")

    # --- identity fields from uptime ---

    def test_identity_fields_from_uptime(self):
        result = self._call()
        self.assertEqual(result["Hostname"],      "testhost")
        self.assertEqual(result["OS"],            "Windows")
        self.assertEqual(result["OSVersion"],     "10.0.19045")
        self.assertEqual(result["Architecture"],  "x64")
        self.assertEqual(result["UptimeSeconds"], 3600)
        self.assertEqual(result["CpuCount"],      8)

    def test_cpu_utilization_from_uptime_cpu_percent_overall(self):
        result = self._call()
        self.assertEqual(result["CpuUtilizationPercent"], 12.5)

    def test_memory_fields_from_uptime(self):
        result = self._call()
        self.assertEqual(result["TotalMemoryBytes"], 16_000_000_000)
        self.assertEqual(result["MemoryUsedBytes"],   8_000_000_000)

    def test_memory_used_percent_computed(self):
        result = self._call()
        self.assertAlmostEqual(result["MemoryUsedPercent"], 50.0, places=1)

    def test_load_average_from_uptime(self):
        result = self._call()
        self.assertIsNone(result["LoadAverageOneMinute"])

    # --- disk aggregation ---

    def test_total_disk_bytes_is_sum(self):
        result = self._call()
        self.assertEqual(result["TotalDiskBytes"], 1_500_000_000_000)

    def test_used_disk_bytes_is_sum(self):
        result = self._call()
        self.assertEqual(result["UsedDiskBytes"], 1_100_000_000_000)

    def test_max_disk_used_percent_is_highest_partition(self):
        result = self._call()
        self.assertEqual(result["MaxDiskUsedPercent"], 90.0)

    def test_empty_disks_produce_zero_totals(self):
        result = self._call(disks=[])
        self.assertEqual(result["TotalDiskBytes"], 0)
        self.assertEqual(result["UsedDiskBytes"],  0)
        self.assertIsNone(result["MaxDiskUsedPercent"])

    # --- process leaders ---

    def test_top_cpu_process_is_first_in_sorted_list(self):
        result = self._call()
        # _PROCESSES already sorted by CPU desc; chrome is first
        self.assertEqual(result["TopCpuProcessName"], "chrome")
        self.assertEqual(result["TopCpuProcessId"],   100)

    def test_top_memory_process_is_highest_memory_bytes(self):
        result = self._call()
        # python has the highest MemoryBytes
        self.assertEqual(result["TopMemoryProcessName"],  "python")
        self.assertEqual(result["TopMemoryProcessBytes"], 2_000_000_000)

    def test_empty_processes_produce_null_leaders(self):
        result = self._call(processes=[])
        self.assertIsNone(result["TopCpuProcessName"])
        self.assertIsNone(result["TopCpuProcessId"])
        self.assertIsNone(result["TopMemoryProcessName"])
        self.assertIsNone(result["TopMemoryProcessBytes"])

    # --- events ---

    def test_recent_error_count_filters_by_lookback_window(self):
        # _NOW = 2026-03-16T12:00:00Z; first event is 1h old (in window),
        # second is 52h old (outside 24h window)
        result = self._call()
        self.assertEqual(result["RecentErrorCount"], 1)

    def test_last_event_fields_from_most_recent_event(self):
        result = self._call()
        self.assertEqual(result["LastEventTimestamp"], "2026-03-16T11:00:00+00:00")
        self.assertEqual(result["LastEventLevel"],     "Error")
        self.assertEqual(result["LastEventMessage"],   "Recent error")

    def test_null_timestamp_events_excluded_from_recent_count(self):
        events = [{"Timestamp": None, "Level": "Error", "Message": "no ts"}]
        result = self._call(events=events)
        self.assertEqual(result["RecentErrorCount"], 0)

    def test_empty_events_produce_null_last_event_fields(self):
        result = self._call(events=[])
        self.assertEqual(result["RecentErrorCount"],  0)
        self.assertIsNone(result["LastEventTimestamp"])
        self.assertIsNone(result["LastEventLevel"])
        self.assertIsNone(result["LastEventMessage"])

    def test_custom_error_lookback_hours(self):
        # With 72h lookback both events should be counted
        result = self._call(error_lookback_hours=72)
        self.assertEqual(result["RecentErrorCount"], 2)

    # --- memory edge cases ---

    def test_zero_total_memory_does_not_crash(self):
        uptime = {**_UPTIME, "TotalMemoryBytes": 0, "MemoryUsedBytes": 0}
        result = self._call(uptime=uptime)
        self.assertIsNone(result["MemoryUsedPercent"])


class DiskToolExtendedCoverageTests(unittest.TestCase):
    @patch("umi_mcp.tools.disk.psutil.disk_io_counters")
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_get_disk_linux_filters_pseudo_filesystems(
        self,
        _mock_system,
        mock_partitions,
        mock_usage,
        mock_io_counters,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="tmpfs", mountpoint="/run", fstype="tmpfs"),
            SimpleNamespace(device="devtmpfs", mountpoint="/dev", fstype="devtmpfs"),
            SimpleNamespace(device="/dev/loop0", mountpoint="/snap/core", fstype="squashfs"),
            SimpleNamespace(device="/dev/sda1", mountpoint="/", fstype="ext4"),
            SimpleNamespace(device="/dev/sdb1", mountpoint="/data", fstype="xfs"),
        ]
        mock_usage.side_effect = [
            SimpleNamespace(total=1000, used=250, free=750),
            SimpleNamespace(total=2000, used=1000, free=1000),
        ]
        mock_io_counters.return_value = {
            "sda": SimpleNamespace(
                read_count=1,
                write_count=2,
                read_bytes=3,
                write_bytes=4,
                read_time=5,
                write_time=6,
            ),
            "sdb": SimpleNamespace(
                read_count=7,
                write_count=8,
                read_bytes=9,
                write_bytes=10,
                read_time=11,
                write_time=12,
            ),
        }

        result = disk.get_disk()

        self.assertEqual(len(result), 2)
        self.assertEqual([entry["MountPoint"] for entry in result], ["/", "/data"])
        self.assertEqual(result[0]["FileSystem"], "EXT4")
        self.assertEqual(result[1]["FileSystem"], "XFS")
        self.assertEqual(result[0]["ReadBytes"], 3)
        self.assertEqual(result[1]["WriteBytes"], 10)

    @patch("umi_mcp.tools.disk.psutil.disk_io_counters")
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Darwin")
    def test_get_disk_macos_filters_pseudo_filesystems(
        self,
        _mock_system,
        mock_partitions,
        mock_usage,
        mock_io_counters,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="map auto_home", mountpoint="/System/Volumes/Data/home", fstype="autofs"),
            SimpleNamespace(device="/dev/disk3s1", mountpoint="/", fstype="apfs"),
            SimpleNamespace(device="/dev/disk4s2", mountpoint="/Volumes/External", fstype="hfs"),
        ]
        mock_usage.side_effect = [
            SimpleNamespace(total=5000, used=2000, free=3000),
            SimpleNamespace(total=4000, used=1000, free=3000),
        ]
        mock_io_counters.return_value = {
            "disk3": SimpleNamespace(
                read_count=10,
                write_count=20,
                read_bytes=30,
                write_bytes=40,
                read_time=50,
                write_time=60,
            ),
            "disk4": SimpleNamespace(
                read_count=11,
                write_count=21,
                read_bytes=31,
                write_bytes=41,
                read_time=51,
                write_time=61,
            ),
        }

        result = disk.get_disk()

        self.assertEqual(len(result), 2)
        self.assertEqual([entry["MountPoint"] for entry in result], ["/", "/Volumes/External"])
        self.assertEqual(result[0]["FileSystem"], "APFS")
        self.assertEqual(result[1]["FileSystem"], "HFS")
        self.assertEqual(result[0]["ReadTimeMs"], 50)
        self.assertEqual(result[1]["WriteTimeMs"], 61)

    @patch("umi_mcp.tools.disk.psutil.disk_io_counters", return_value={})
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_get_disk_skips_permission_error_partition_only(
        self,
        _mock_system,
        mock_partitions,
        mock_usage,
        _mock_io_counters,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="/dev/sda1", mountpoint="/", fstype="ext4"),
            SimpleNamespace(device="/dev/sdb1", mountpoint="/restricted", fstype="ext4"),
            SimpleNamespace(device="/dev/sdc1", mountpoint="/data", fstype="ext4"),
        ]

        def usage_for_mount(mountpoint):
            if mountpoint == "/restricted":
                raise PermissionError("denied")
            if mountpoint == "/":
                return SimpleNamespace(total=1000, used=100, free=900)
            return SimpleNamespace(total=2000, used=500, free=1500)

        mock_usage.side_effect = usage_for_mount

        result = disk.get_disk()

        self.assertEqual(len(result), 2)
        self.assertEqual([entry["MountPoint"] for entry in result], ["/", "/data"])

    @patch("umi_mcp.tools.disk.psutil.disk_io_counters")
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_get_disk_io_none_keeps_null_keys(
        self,
        _mock_system,
        mock_partitions,
        mock_usage,
        mock_io_counters,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="/dev/sda1", mountpoint="/", fstype="ext4")
        ]
        mock_usage.return_value = SimpleNamespace(total=1000, used=500, free=500)
        mock_io_counters.return_value = {"sda": None}

        result = disk.get_disk()

        self.assertEqual(len(result), 1)
        for field in (
            "ReadCount",
            "WriteCount",
            "ReadBytes",
            "WriteBytes",
            "ReadTimeMs",
            "WriteTimeMs",
        ):
            self.assertIn(field, result[0])
            self.assertIsNone(result[0][field])

    @patch("umi_mcp.tools.disk._load_windows_label_map", return_value={"C:\\": "System"})
    @patch("umi_mcp.tools.disk._load_windows_drive_map", return_value={})
    @patch("umi_mcp.tools.disk.psutil.disk_io_counters", return_value={})
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Windows")
    def test_get_disk_windows_populates_label_from_label_map(
        self,
        _mock_system,
        mock_partitions,
        mock_usage,
        _mock_io_counters,
        _mock_drive_map,
        _mock_label_map,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="C:\\", mountpoint="C:\\", fstype="NTFS")
        ]
        mock_usage.return_value = SimpleNamespace(total=1000, used=500, free=500)

        result = disk.get_disk()

        self.assertEqual(len(result), 1)
        self.assertIn("Label", result[0])
        self.assertEqual(result[0]["Label"], "System")

    @patch("umi_mcp.tools.disk._load_windows_label_map", return_value={"C:\\": None})
    @patch("umi_mcp.tools.disk._load_windows_drive_map", return_value={})
    @patch("umi_mcp.tools.disk.psutil.disk_io_counters", return_value={})
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Windows")
    def test_get_disk_windows_keeps_null_label_key(
        self,
        _mock_system,
        mock_partitions,
        mock_usage,
        _mock_io_counters,
        _mock_drive_map,
        _mock_label_map,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="C:\\", mountpoint="C:\\", fstype="NTFS")
        ]
        mock_usage.return_value = SimpleNamespace(total=1000, used=500, free=500)

        result = disk.get_disk()

        self.assertEqual(len(result), 1)
        self.assertIn("Label", result[0])
        self.assertIsNone(result[0]["Label"])


class ServiceToolExtendedCoverageTests(unittest.TestCase):
    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Windows")
    def test_get_service_windows_returns_empty_on_nonzero_exit(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")

        result = service.get_service()

        self.assertEqual(result, [])

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Windows")
    def test_get_service_windows_filters_by_status(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                [
                    {"Name": "SvcRunning", "State": "Running", "StartMode": "Auto"},
                    {"Name": "SvcStopped", "State": "Stopped", "StartMode": "Manual"},
                ]
            ),
        )

        result = service.get_service(status="Running")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "SvcRunning")
        self.assertEqual(result[0]["Status"], "Running")
        self.assertIn("DisplayName", result[0])
        self.assertIsNone(result[0]["DisplayName"])

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Linux")
    def test_get_service_linux_returns_empty_on_subprocess_failure(self, _sys, mock_run):
        mock_run.side_effect = OSError("systemctl unavailable")

        result = service.get_service()

        self.assertEqual(result, [])

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Darwin")
    def test_get_service_macos_filters_by_status(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout="pid\tstatus\tlabel\n123\t0\tcom.apple.running\n-\t0\tcom.apple.stopped",
        )

        running = service.get_service(status="Running")
        stopped = service.get_service(status="Stopped")

        self.assertEqual(running, [
            {
                "ServiceName": "com.apple.running",
                "DisplayName": "com.apple.running",
                "Description": None,
                "Status": "Running",
                "StartType": "Unknown",
                "User": None,
                "ProcessId": 123,
                "BinaryPath": None,
                "UptimeSeconds": None,
                "ExitCode": None,
            }
        ])
        self.assertEqual(stopped, [
            {
                "ServiceName": "com.apple.stopped",
                "DisplayName": "com.apple.stopped",
                "Description": None,
                "Status": "Stopped",
                "StartType": "Unknown",
                "User": None,
                "ProcessId": None,
                "BinaryPath": None,
                "UptimeSeconds": None,
                "ExitCode": None,
            }
        ])


class EventsHelperTests(unittest.TestCase):
    def test_normalize_event_string_event_id_coerced_to_int(self):
        # _normalize_event is defensive: if event_id arrives as a digit string
        # (no current caller produces this, but the schema promises an int) it
        # should be coerced so EventId is an int, not a string (line 94)
        result = events._normalize_event(None, "Error", "src", "42", "msg")
        self.assertEqual(result["EventId"], 42)
        self.assertIsInstance(result["EventId"], int)

    def test_truncate_message_none(self):
        self.assertIsNone(events._truncate_message(None))

    def test_parse_timestamp_none_or_empty(self):
        self.assertIsNone(events._parse_timestamp(None))
        self.assertIsNone(events._parse_timestamp(""))
        self.assertIsNone(events._parse_timestamp("   "))

    def test_parse_timestamp_numeric(self):
        # Numeric (int/float)
        ts = events._parse_timestamp(1710590400.0)
        self.assertEqual(ts, "2024-03-16T12:00:00+00:00")

        # Digit string (microseconds)
        ts_str = events._parse_timestamp("1710590400000000")
        self.assertEqual(ts_str, "2024-03-16T12:00:00+00:00")

        # Overflow on int/float path (line 62-63)
        self.assertIsNone(events._parse_timestamp(1e30))

        # Overflow on digit-string path (lines 72-73): value is all digits but
        # int(value) / 1_000_000 still overflows datetime.fromtimestamp
        self.assertIsNone(events._parse_timestamp("9" * 30))

    def test_parse_timestamp_formats(self):
        # ISO with Z
        self.assertEqual(events._parse_timestamp("2024-03-16T12:00:00Z"), "2024-03-16T12:00:00+00:00")
        
        # ISO with space (supported by fromisoformat)
        self.assertEqual(events._parse_timestamp("2024-03-16 12:00:00"), "2024-03-16T12:00:00+00:00")

        # Fallback formats
        self.assertEqual(events._parse_timestamp("2024-03-16 12:00:00.000+0000"), "2024-03-16T12:00:00+00:00")
        self.assertEqual(events._parse_timestamp("2024-03-16 12:00:00+0000"), "2024-03-16T12:00:00+00:00")
        
        # PowerShell ConvertTo-Json /Date(ms)/ format
        self.assertEqual(events._parse_timestamp("/Date(1710590400000)/"), "2024-03-16T12:00:00+00:00")
        # With timezone offset suffix (also emitted by some PS versions)
        self.assertEqual(events._parse_timestamp("/Date(1710590400000+0000)/"), "2024-03-16T12:00:00+00:00")
        # Malformed — should return None
        self.assertIsNone(events._parse_timestamp("/Date()/"))

        # Invalid
        self.assertIsNone(events._parse_timestamp("invalid date"))


class EventsToolExtendedTests(unittest.TestCase):
    @patch("umi_mcp.tools.events.platform.system", return_value="FreeBSD")
    def test_get_events_unknown_platform(self, _sys):
        self.assertEqual(events.get_events(), [])

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Windows")
    def test_info_alias_passes_level_4_to_windows(self, _sys, mock_run):
        # "Info" must normalize to "Information" (level 4), not fall back to Error (level 2)
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")
        events.get_events(level="Info")
        cmd = mock_run.call_args[0][0]
        ps_cmd = " ".join(cmd)
        self.assertIn("Level=4", ps_cmd)
        self.assertNotIn("Level=2", ps_cmd)

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Linux")
    def test_info_alias_passes_info_priority_to_linux(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")
        events.get_events(level="Info")
        cmd = mock_run.call_args[0][0]
        self.assertIn("info", cmd)

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Windows")
    def test_get_events_windows_edge_cases(self, _sys, mock_run):
        # OSError
        mock_run.side_effect = OSError("Access denied")
        self.assertEqual(events.get_events(), [])

        # Non-zero returncode
        mock_run.side_effect = None
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")
        self.assertEqual(events.get_events(), [])

        # Empty stdout
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="  ")
        self.assertEqual(events.get_events(), [])

        # JSONDecodeError
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="invalid json")
        self.assertEqual(events.get_events(), [])

        # Single dict response
        mock_run.return_value = SimpleNamespace(
            returncode=0, 
            stdout=json.dumps({"Id": 1, "Message": "single"})
        )
        res = events.get_events()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["EventId"], 1)

        # Source filter escaping
        events.get_events(source="O'Reilly")
        args, kwargs = mock_run.call_args
        cmd = args[0][-1]
        self.assertIn("O''Reilly", cmd)

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Windows")
    def test_get_events_windows_missing_fields(self, _sys, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0, 
            stdout=json.dumps([{"Message": "only message"}])
        )
        res = events.get_events()
        self.assertEqual(len(res), 1)
        self.assertIsNone(res[0]["EventId"])
        self.assertIsNone(res[0]["Source"])
        self.assertIsNone(res[0]["Timestamp"])
        self.assertEqual(res[0]["Level"], "Unknown")

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Linux")
    def test_get_events_linux_edge_cases(self, _sys, mock_run):
        # OSError
        mock_run.side_effect = OSError("cmd not found")
        self.assertEqual(events.get_events(), [])

        # Non-zero returncode
        mock_run.side_effect = None
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")
        self.assertEqual(events.get_events(), [])

        # Empty lines and malformed JSON lines
        lines = [
            "",
            json.dumps({"MESSAGE": "ok", "PRIORITY": "3"}),
            "not json",
            json.dumps({"MESSAGE": "ok2", "PRIORITY": "3"}),
        ]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="\n".join(lines))
        res = events.get_events(last_n=10)
        self.assertEqual(len(res), 2)

        # last_n break reached mid-iteration
        lines_many = [json.dumps({"MESSAGE": f"msg{i}", "PRIORITY": "3"}) for i in range(5)]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="\n".join(lines_many))
        res_limited = events.get_events(last_n=2)
        self.assertEqual(len(res_limited), 2)
        self.assertEqual(res_limited[1]["Message"], "msg1")

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Darwin")
    def test_get_events_macos_edge_cases(self, _sys, mock_run):
        # OSError
        mock_run.side_effect = OSError("crash")
        self.assertEqual(events.get_events(), [])

        # Non-zero returncode
        mock_run.side_effect = None
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")
        self.assertEqual(events.get_events(), [])

        # Empty/malformed lines
        lines = [
            "  ",
            json.dumps({"eventMessage": "ok", "messageType": "error"}),
            "{bad json",
        ]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="\n".join(lines))
        res = events.get_events(level="Error")
        self.assertEqual(len(res), 1)

        # Level filter mismatch
        lines_mixed = [
            json.dumps({"eventMessage": "err", "messageType": "error"}),
            json.dumps({"eventMessage": "info", "messageType": "info"}),
        ]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="\n".join(lines_mixed))
        res_err = events.get_events(level="Error")
        self.assertEqual(len(res_err), 1)
        self.assertEqual(res_err[0]["Message"], "err")

        # Source filter mismatch
        lines_src = [
            json.dumps({"eventMessage": "a", "messageType": "error", "subsystem": "com.apple.a"}),
            json.dumps({"eventMessage": "b", "messageType": "error", "subsystem": "com.apple.b"}),
        ]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="\n".join(lines_src))
        res_src = events.get_events(source="apple.a")
        self.assertEqual(len(res_src), 1)
        self.assertEqual(res_src[0]["Source"], "com.apple.a")


class DiskHelpersTests(unittest.TestCase):
    # _normalize_windows_drive
    def test_normalize_windows_drive_falsy_returns_none(self):
        self.assertIsNone(disk._normalize_windows_drive(None))
        self.assertIsNone(disk._normalize_windows_drive(""))

    def test_normalize_windows_drive_non_drive_format_returns_none(self):
        self.assertIsNone(disk._normalize_windows_drive("notadrive"))
        self.assertIsNone(disk._normalize_windows_drive("/dev/sda1"))

    def test_normalize_windows_drive_valid_formats(self):
        self.assertEqual(disk._normalize_windows_drive("C:\\"), "C:\\")
        self.assertEqual(disk._normalize_windows_drive("D:\\path\\to\\dir"), "D:\\")

    # _load_windows_drive_map error paths
    @patch("umi_mcp.tools.disk.subprocess.run", side_effect=OSError("no powershell"))
    def test_load_windows_drive_map_oserror_returns_empty(self, _):
        self.assertEqual(disk._load_windows_drive_map(), {})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_drive_map_bad_returncode_returns_empty(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")
        self.assertEqual(disk._load_windows_drive_map(), {})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_drive_map_bad_json_returns_empty(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="not json {{")
        self.assertEqual(disk._load_windows_drive_map(), {})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_drive_map_single_dict_response(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"DriveLetter": "C", "DiskNumber": 0}),
        )
        self.assertEqual(disk._load_windows_drive_map(), {"C:\\": "PhysicalDrive0"})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_drive_map_missing_fields_skipped(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {"DriveLetter": None, "DiskNumber": 0},
                {"DriveLetter": "D", "DiskNumber": 1},
            ]),
        )
        self.assertEqual(disk._load_windows_drive_map(), {"D:\\": "PhysicalDrive1"})

    # _load_windows_label_map error paths
    @patch("umi_mcp.tools.disk.subprocess.run", side_effect=OSError("no powershell"))
    def test_load_windows_label_map_oserror_returns_empty(self, _):
        self.assertEqual(disk._load_windows_label_map(), {})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_label_map_bad_returncode_returns_empty(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="")
        self.assertEqual(disk._load_windows_label_map(), {})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_label_map_bad_json_returns_empty(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="not json {{")
        self.assertEqual(disk._load_windows_label_map(), {})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_label_map_single_dict_response(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"DriveLetter": "C", "FileSystemLabel": "System"}),
        )
        self.assertEqual(disk._load_windows_label_map(), {"C:\\": "System"})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_label_map_missing_drive_letter_skipped(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {"DriveLetter": None, "FileSystemLabel": "Ignored"},
                {"DriveLetter": "D", "FileSystemLabel": "Data"},
            ]),
        )
        self.assertEqual(disk._load_windows_label_map(), {"D:\\": "Data"})

    @patch("umi_mcp.tools.disk.subprocess.run")
    def test_load_windows_label_map_empty_label_stored_as_none(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"DriveLetter": "C", "FileSystemLabel": ""}),
        )
        self.assertEqual(disk._load_windows_label_map(), {"C:\\": None})

    # _device_candidates
    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_device_candidates_dev_prefix_stripped(self, _):
        result = disk._device_candidates("/dev/sda1", None)
        self.assertIn("sda1", result)
        self.assertIn("sda", result)

    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_device_candidates_nvme_parent_added(self, _):
        result = disk._device_candidates("/dev/nvme0n1p1", None)
        self.assertIn("nvme0n1p1", result)
        self.assertIn("nvme0n1", result)

    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_device_candidates_mmcblk_parent_added(self, _):
        result = disk._device_candidates("/dev/mmcblk0p1", None)
        self.assertIn("mmcblk0p1", result)
        self.assertIn("mmcblk0", result)

    @patch("umi_mcp.tools.disk.platform.system", return_value="Windows")
    def test_device_candidates_windows_normalizes_drive(self, _):
        result = disk._device_candidates("C:\\", "C:\\")
        self.assertEqual(result, ["C:\\"])

    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_device_candidates_falsy_raw_skipped(self, _):
        self.assertEqual(disk._device_candidates(None, None), [])

    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    @patch("umi_mcp.tools.disk.os.path.basename", return_value="")
    def test_device_candidates_basename_empty_falls_back_to_raw_and_strips_dev_prefix(self, _, __):
        # basename returns "" → base = raw.rstrip("/") = "/dev/sda1" → stripped to "sda1"
        result = disk._device_candidates("/dev/sda1", None)
        self.assertIn("sda1", result)

    # get_disk pseudo mountpoint filter (PSEUDO_MOUNTS)
    @patch("umi_mcp.tools.disk.psutil.disk_io_counters", return_value={})
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_get_disk_filters_pseudo_mount_points(self, _, mock_parts, mock_usage, __):
        mock_parts.return_value = [
            SimpleNamespace(device="nfsd", mountpoint="/proc/fs/nfsd", fstype="nfsd"),
            SimpleNamespace(device="/dev/sda1", mountpoint="/", fstype="ext4"),
        ]
        mock_usage.return_value = SimpleNamespace(total=1000, used=100, free=900)
        result = disk.get_disk()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["MountPoint"], "/")


class NetworkHelpersTests(unittest.TestCase):
    def test_prefix_to_mask(self):
        self.assertEqual(network._prefix_to_mask(8), "255.0.0.0")
        self.assertEqual(network._prefix_to_mask(16), "255.255.0.0")
        self.assertEqual(network._prefix_to_mask(24), "255.255.255.0")

    def test_classify_interface_tunnel(self):
        for name in ("tun0", "tap1", "vpn0"):
            self.assertEqual(network._classify_interface(name), "Tunnel", name)

    def test_classify_interface_virtual(self):
        for name in ("docker0", "veth0abc", "br-abc123", "virbr0", "vbox0"):
            self.assertEqual(network._classify_interface(name), "Virtual", name)

    def test_classify_interface_unknown(self):
        self.assertEqual(network._classify_interface("zzz999"), "Unknown")

    @patch("umi_mcp.tools.network.psutil.net_io_counters", return_value={})
    @patch("umi_mcp.tools.network.psutil.net_if_stats")
    @patch("umi_mcp.tools.network.psutil.net_if_addrs")
    def test_subnet_mask_derived_from_prefixlen(self, mock_addrs, mock_stats, _):
        mock_addrs.return_value = {
            "eth0": [SimpleNamespace(
                family=socket.AF_INET, address="10.0.0.1",
                netmask=None, prefixlen=24,
            )]
        }
        mock_stats.return_value = {"eth0": SimpleNamespace(isup=True, speed=1000)}
        result = network.get_network()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["SubnetMask"], "255.255.255.0")


class ProcessEdgeCaseTests(unittest.TestCase):
    @patch("umi_mcp.tools.process.time.sleep")
    @patch("umi_mcp.tools.process.psutil.process_iter")
    def test_nameless_process_is_skipped(self, mock_iter, _sleep):
        mock_iter.return_value = [
            MagicMock(info={
                "pid": 1, "name": None, "ppid": 0,
                "memory_info": None, "memory_percent": None,
                "status": psutil.STATUS_RUNNING, "username": "root",
                "create_time": 1.0, "cmdline": [], "num_threads": 1,
            }),
            MagicMock(info={
                "pid": 2, "name": "real_proc", "ppid": 1,
                "memory_info": SimpleNamespace(rss=512), "memory_percent": 0.1,
                "status": psutil.STATUS_RUNNING, "username": "user",
                "create_time": 1.0, "cmdline": ["real"], "num_threads": 1,
            }),
        ]
        result = process.get_process()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ProcessName"], "real_proc")

    @patch("umi_mcp.tools.process.time.sleep")
    @patch("umi_mcp.tools.process.psutil.process_iter")
    def test_create_time_overflow_produces_null_start_time(self, mock_iter, _sleep):
        mock_iter.return_value = [
            MagicMock(info={
                "pid": 1, "name": "proc", "ppid": 0,
                "memory_info": SimpleNamespace(rss=512), "memory_percent": 0.1,
                "status": psutil.STATUS_RUNNING, "username": "user",
                "create_time": 1e300, "cmdline": None, "num_threads": 1,
            }),
        ]
        result = process.get_process()
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["StartTime"])
        self.assertIsNone(result[0]["CommandLine"])

    @patch("umi_mcp.tools.process.time.sleep")
    @patch("umi_mcp.tools.process.psutil.process_iter")
    @patch("umi_mcp.tools.process.platform.system")
    def test_system_idle_process_skipped_only_on_windows(self, mock_system, mock_iter, _sleep):
        proc_idle = MagicMock(info={
            "pid": 0, "name": "System Idle Process", "ppid": 0,
            "memory_info": SimpleNamespace(rss=0), "memory_percent": 0.0,
            "status": psutil.STATUS_RUNNING, "username": "SYSTEM",
            "create_time": 1.0, "cmdline": [], "num_threads": 4,
        })
        proc_idle.cpu_percent.return_value = 50.0

        proc_real = MagicMock(info={
            "pid": 1, "name": "real_proc", "ppid": 0,
            "memory_info": SimpleNamespace(rss=512), "memory_percent": 0.1,
            "status": psutil.STATUS_RUNNING, "username": "user",
            "create_time": 1.0, "cmdline": ["real"], "num_threads": 1,
        })
        proc_real.cpu_percent.return_value = 5.0

        mock_iter.return_value = [proc_idle, proc_real]

        mock_system.return_value = "Windows"
        windows_result = process.get_process()
        self.assertEqual([p["ProcessName"] for p in windows_result], ["real_proc"])

        mock_system.return_value = "Linux"
        linux_result = process.get_process()
        # System Idle Process has higher CPU so sorts first
        self.assertEqual(
            [p["ProcessName"] for p in linux_result],
            ["System Idle Process", "real_proc"],
        )


class ServiceAdditionalEdgeCaseTests(unittest.TestCase):
    @patch("umi_mcp.tools.service.platform.system", return_value="FreeBSD")
    def test_unknown_platform_returns_empty(self, _):
        self.assertEqual(service.get_service(), [])

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Windows")
    def test_windows_single_dict_response_not_list(self, _, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"Name": "OnlyOne", "State": "Running", "StartMode": "Auto"}),
        )
        result = service.get_service()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "OnlyOne")

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Windows")
    def test_windows_name_filter_excludes_non_matching(self, _, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {"Name": "TargetService", "State": "Running", "StartMode": "Auto"},
                {"Name": "OtherService", "State": "Running", "StartMode": "Auto"},
            ]),
        )
        result = service.get_service(name="Target")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "TargetService")

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Linux")
    def test_linux_non_service_units_skipped(self, _, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {"unit": "ssh.service", "description": "SSH", "active": "active", "sub": "running"},
                {"unit": "dev-sda.device", "description": "Disk", "active": "active", "sub": "plugged"},
                {"unit": "network.mount", "description": "Mount", "active": "active", "sub": "mounted"},
            ]),
        )
        result = service.get_service()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "ssh")

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Linux")
    def test_linux_name_filter_excludes_non_matching(self, _, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {"unit": "ssh.service", "description": "SSH", "active": "active", "sub": "running"},
                {"unit": "cron.service", "description": "Cron", "active": "active", "sub": "running"},
            ]),
        )
        result = service.get_service(name="cron")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "cron")

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Darwin")
    def test_macos_short_line_skipped(self, _, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout="pid\tstatus\tlabel\n123\tshortline\n-\t0\tcom.apple.ok",
        )
        result = service.get_service()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "com.apple.ok")

    @patch("umi_mcp.tools.service.subprocess.run")
    @patch("umi_mcp.tools.service.platform.system", return_value="Darwin")
    def test_macos_name_filter_excludes_non_matching(self, _, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout="pid\tstatus\tlabel\n123\t0\tcom.apple.target\n-\t0\tcom.other",
        )
        result = service.get_service(name="apple.target")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ServiceName"], "com.apple.target")

    @patch("umi_mcp.tools.service.subprocess.run", side_effect=OSError("unavailable"))
    @patch("umi_mcp.tools.service.platform.system", return_value="Darwin")
    def test_macos_exception_returns_empty(self, _, __):
        self.assertEqual(service.get_service(), [])


class UserAdditionalEdgeCaseTests(unittest.TestCase):
    def _unix_context(self, mock_pwd, mock_grp):
        """Return a context manager that injects pwd/grp mocks into sys.modules."""
        return ExitStack()

    def _run_unix(self, mock_pwd, mock_grp, **kwargs):
        """Call user.get_user() with pwd/grp injected into sys.modules."""
        with patch.dict(sys.modules, {"pwd": mock_pwd, "grp": mock_grp}):
            with patch("umi_mcp.tools.user.platform.system", return_value="Linux"):
                with patch("umi_mcp.tools.user.os.getuid", return_value=1000, create=True):
                    return user.get_user(**kwargs)

    def test_getpwall_failure_falls_back_to_current_user(self):
        mock_pwd = MagicMock()
        mock_grp = MagicMock()
        current = SimpleNamespace(
            pw_name="user1", pw_uid=1000, pw_gid=1000,
            pw_gecos="User One", pw_dir="/home/user1", pw_shell="/bin/bash",
        )
        mock_pwd.getpwuid.return_value = current
        mock_pwd.getpwall.side_effect = Exception("not supported")
        mock_grp.getgrall.return_value = []
        mock_grp.getgrgid.return_value = SimpleNamespace(gr_name="user1")

        result = self._run_unix(mock_pwd, mock_grp)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Username"], "user1")

    def test_low_uid_users_filtered_out(self):
        mock_pwd = MagicMock()
        mock_grp = MagicMock()
        current = SimpleNamespace(
            pw_name="user1", pw_uid=1000, pw_gid=1000,
            pw_gecos="", pw_dir="/home/user1", pw_shell="/bin/bash",
        )
        daemon = SimpleNamespace(
            pw_name="daemon", pw_uid=2, pw_gid=2,
            pw_gecos="", pw_dir="/usr/sbin", pw_shell="/usr/sbin/nologin",
        )
        mock_pwd.getpwuid.return_value = current
        mock_pwd.getpwall.return_value = [daemon, current]
        mock_grp.getgrall.return_value = []
        mock_grp.getgrgid.return_value = SimpleNamespace(gr_name="user1")

        result = self._run_unix(mock_pwd, mock_grp)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Username"], "user1")

    def test_grgid_keyerror_skipped_gracefully(self):
        mock_pwd = MagicMock()
        mock_grp = MagicMock()
        current = SimpleNamespace(
            pw_name="user1", pw_uid=1000, pw_gid=9999,
            pw_gecos="", pw_dir="/home/user1", pw_shell="/bin/bash",
        )
        mock_pwd.getpwuid.return_value = current
        mock_pwd.getpwall.return_value = [current]
        mock_grp.getgrall.return_value = []
        mock_grp.getgrgid.side_effect = KeyError("9999")

        result = self._run_unix(mock_pwd, mock_grp)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Groups"], [])


class MainEntryPointTests(unittest.TestCase):
    @patch("umi_mcp.__main__.mcp.run")
    def test_main_calls_mcp_run(self, mock_run):
        from umi_mcp.__main__ import main
        main()
        mock_run.assert_called_once_with()

    def test_module_dunder_main_calls_main(self):
        # runpy re-executes the module in a fresh namespace, so we can't patch
        # the name 'main' there — instead patch mcp.run on the shared server
        # object (imported from the already-cached umi_mcp.server module).
        sys.modules.pop("umi_mcp.__main__", None)
        with patch("umi_mcp.server.mcp.run") as mock_run:
            runpy.run_module("umi_mcp", run_name="__main__", alter_sys=True)
        mock_run.assert_called_once_with()


_NOW_RC = datetime(2026, 3, 16, 12, 0, 0, tzinfo=timezone.utc)

_PROCESSES_RC = [
    {"ProcessName": "chrome",  "ProcessId": 10, "CpuPercent": 80.0, "MemoryBytes": 2_000_000_000},
    {"ProcessName": "idle",    "ProcessId": 20, "CpuPercent": 1.0,  "MemoryBytes": 50_000_000},
]
_SERVICES_RC = [
    {"ServiceName": "svcA", "DisplayName": "Service A", "Status": "Stopped",  "StartType": "Automatic"},
    {"ServiceName": "svcB", "DisplayName": "Service B", "Status": "Running",  "StartType": "Automatic"},
    {"ServiceName": "svcC", "DisplayName": "Service C", "Status": "Degraded", "StartType": "Automatic"},
    {"ServiceName": "svcD", "DisplayName": "Service D", "Status": "Stopped",  "StartType": "Manual"},
]
_DISKS_RC = [
    {"DeviceName": "C:", "MountPoint": "C:\\", "UsedPercent": 90.0, "FreeBytes": 10_000_000},
    {"DeviceName": "D:", "MountPoint": "D:\\", "UsedPercent": 50.0, "FreeBytes": 500_000_000},
]
_UPTIME_RC = {"Hostname": "testhost"}


class EventSummaryToolTests(unittest.TestCase):
    """Tests for get_umi_event_summary (Issue #5)."""

    def _call(self, raw_events=None, now=None, **kwargs):
        if raw_events is None:
            raw_events = []
        mock_now = now or _NOW_RC
        with patch("umi_mcp.server.get_events", return_value=raw_events), \
             patch("umi_mcp.server.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.timezone = timezone
            return get_umi_event_summary(**kwargs)

    def test_returns_dict_with_envelope(self):
        result = self._call()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["SchemaVersion"], "1")
        self.assertIn("GeneratedAt", result)

    def test_required_shape_fields(self):
        result = self._call()
        for field in ("LookbackHours", "Level", "Count", "Groups"):
            self.assertIn(field, result, msg=f"Missing: {field}")

    def test_empty_events_yields_zero_groups(self):
        result = self._call()
        self.assertEqual(result["Count"], 0)
        self.assertEqual(result["Groups"], [])

    def test_single_event_creates_one_group(self):
        events = [
            {"Timestamp": "2026-03-16T11:00:00+00:00", "Level": "Error",
             "Source": "Disk", "EventId": 51, "Message": "disk error"},
        ]
        result = self._call(raw_events=events)
        self.assertEqual(result["Count"], 1)
        g = result["Groups"][0]
        self.assertEqual(g["Source"], "Disk")
        self.assertEqual(g["EventId"], 51)
        self.assertEqual(g["Count"], 1)
        self.assertEqual(g["SampleMessage"], "disk error")

    def test_repeated_events_are_grouped(self):
        events = [
            {"Timestamp": "2026-03-16T11:00:00+00:00", "Level": "Error",
             "Source": "Disk", "EventId": 51, "Message": "disk error"},
            {"Timestamp": "2026-03-16T10:00:00+00:00", "Level": "Error",
             "Source": "Disk", "EventId": 51, "Message": "disk error again"},
        ]
        result = self._call(raw_events=events)
        self.assertEqual(result["Count"], 1)
        self.assertEqual(result["Groups"][0]["Count"], 2)

    def test_groups_sorted_by_count_descending(self):
        events = [
            {"Timestamp": "2026-03-16T11:00:00+00:00", "Level": "Warning",
             "Source": "A", "EventId": 1, "Message": "msg"},
            {"Timestamp": "2026-03-16T11:00:00+00:00", "Level": "Error",
             "Source": "B", "EventId": 2, "Message": "msg"},
            {"Timestamp": "2026-03-16T10:00:00+00:00", "Level": "Error",
             "Source": "B", "EventId": 2, "Message": "msg"},
        ]
        result = self._call(raw_events=events)
        self.assertEqual(result["Groups"][0]["Source"], "B")
        self.assertEqual(result["Groups"][0]["Count"], 2)

    def test_events_outside_window_excluded(self):
        events = [
            {"Timestamp": "2026-03-14T10:00:00+00:00", "Level": "Error",
             "Source": "Old", "EventId": 1, "Message": "old"},
            {"Timestamp": "2026-03-16T11:00:00+00:00", "Level": "Error",
             "Source": "Recent", "EventId": 2, "Message": "recent"},
        ]
        result = self._call(raw_events=events, lookback_hours=24)
        self.assertEqual(result["Count"], 1)
        self.assertEqual(result["Groups"][0]["Source"], "Recent")

    def test_top_limits_groups_returned(self):
        events = [
            {"Timestamp": "2026-03-16T11:00:00+00:00", "Level": "Error",
             "Source": f"src{i}", "EventId": i, "Message": f"msg{i}"}
            for i in range(10)
        ]
        result = self._call(raw_events=events, top=3)
        self.assertEqual(result["Count"], 3)
        self.assertEqual(len(result["Groups"]), 3)

    def test_default_lookback_and_level_in_response(self):
        result = self._call()
        self.assertEqual(result["LookbackHours"], 24)
        self.assertEqual(result["Level"], "Warning")


class RecentChangesToolTests(unittest.TestCase):
    """Tests for get_umi_recent_changes (Issue #11)."""

    def _call(self, uptime=None, processes=None, disks=None, services=None,
              events=None, now=None, **kwargs):
        mock_now = now or _NOW_RC
        with patch("umi_mcp.server.get_uptime",  return_value=_UPTIME_RC if uptime is None else uptime), \
             patch("umi_mcp.server.get_process", return_value=_PROCESSES_RC if processes is None else processes), \
             patch("umi_mcp.server.get_disk",    return_value=_DISKS_RC if disks is None else disks), \
             patch("umi_mcp.server.get_service", return_value=_SERVICES_RC if services is None else services), \
             patch("umi_mcp.server.get_events",  return_value=[] if events is None else events), \
             patch("umi_mcp.server.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.timezone = timezone
            return get_umi_recent_changes(**kwargs)

    def test_returns_dict_with_envelope(self):
        result = self._call()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["SchemaVersion"], "1")
        self.assertIn("GeneratedAt", result)

    def test_required_shape_fields(self):
        result = self._call()
        for field in ("LookbackHours", "Hostname", "Highlights", "Changes"):
            self.assertIn(field, result, msg=f"Missing: {field}")
        for bucket in ("ProcessSpikes", "ServiceCrashes", "BurstEvents", "StorageAlerts"):
            self.assertIn(bucket, result["Changes"], msg=f"Missing Changes.{bucket}")

    def test_default_lookback_hours(self):
        result = self._call()
        self.assertEqual(result["LookbackHours"], 4)

    def test_hostname_from_uptime(self):
        result = self._call()
        self.assertEqual(result["Hostname"], "testhost")

    def test_process_spike_high_cpu(self):
        # chrome has 80% CPU > 50 threshold
        result = self._call()
        spikes = result["Changes"]["ProcessSpikes"]
        spike_names = [p["ProcessName"] for p in spikes]
        self.assertIn("chrome", spike_names)

    def test_process_spike_high_memory(self):
        # chrome has 2GB > 1GB threshold
        result = self._call()
        spikes = result["Changes"]["ProcessSpikes"]
        chrome_spike = next(p for p in spikes if p["ProcessName"] == "chrome")
        self.assertIn("HighMemory", chrome_spike["Reasons"])

    def test_idle_process_not_spiked(self):
        result = self._call()
        spikes = result["Changes"]["ProcessSpikes"]
        self.assertNotIn("idle", [p["ProcessName"] for p in spikes])

    def test_service_crashes_only_automatic_stopped_degraded(self):
        result = self._call()
        crashes = result["Changes"]["ServiceCrashes"]
        crash_names = {s["ServiceName"] for s in crashes}
        # svcA (Automatic+Stopped) and svcC (Automatic+Degraded) should be included
        self.assertIn("svcA", crash_names)
        self.assertIn("svcC", crash_names)
        # svcB (Running) and svcD (Manual+Stopped) should not be included
        self.assertNotIn("svcB", crash_names)
        self.assertNotIn("svcD", crash_names)

    def test_storage_alerts_above_threshold(self):
        result = self._call()
        alerts = result["Changes"]["StorageAlerts"]
        alert_devices = [a["DeviceName"] for a in alerts]
        self.assertIn("C:", alert_devices)
        self.assertNotIn("D:", alert_devices)

    def test_burst_events_grouped_by_source(self):
        # 3 identical events should trigger burst threshold
        ts = "2026-03-16T11:30:00+00:00"
        events = [
            {"Timestamp": ts, "Source": "SomeSource", "EventId": 100,
             "Level": "Warning", "Message": "burst"}
        ] * 3
        result = self._call(events=events)
        bursts = result["Changes"]["BurstEvents"]
        self.assertEqual(len(bursts), 1)
        self.assertEqual(bursts[0]["Source"], "SomeSource")
        self.assertEqual(bursts[0]["Count"], 3)

    def test_highlights_non_empty(self):
        result = self._call()
        self.assertIsInstance(result["Highlights"], list)
        self.assertGreater(len(result["Highlights"]), 0)

    def test_highlights_all_clear_when_no_issues(self):
        result = self._call(
            processes=[{"ProcessName": "idle", "ProcessId": 1, "CpuPercent": 0.1, "MemoryBytes": 10_000}],
            services=[{"ServiceName": "svcB", "DisplayName": "B", "Status": "Running", "StartType": "Automatic"}],
            disks=[{"DeviceName": "C:", "MountPoint": "C:\\", "UsedPercent": 50.0, "FreeBytes": 500_000_000}],
            events=[],
        )
        self.assertEqual(result["Highlights"], ["No significant changes detected."])

    def test_highlights_mentions_spike_process(self):
        result = self._call()
        combined = " ".join(result["Highlights"])
        self.assertIn("chrome", combined)

    def test_service_exception_falls_back_to_empty_crashes(self):
        with patch("umi_mcp.server.get_uptime",  return_value=_UPTIME_RC), \
             patch("umi_mcp.server.get_process", return_value=[]), \
             patch("umi_mcp.server.get_disk",    return_value=[]), \
             patch("umi_mcp.server.get_service", side_effect=PermissionError("access denied")), \
             patch("umi_mcp.server.get_events",  return_value=[]), \
             patch("umi_mcp.server.datetime") as mock_dt:
            mock_dt.now.return_value = _NOW_RC
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.timezone = timezone
            result = get_umi_recent_changes()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["Changes"]["ServiceCrashes"], [])

    def test_storage_alert_highlight_uses_mountpoint_when_devicename_none(self):
        disks = [{"DeviceName": None, "MountPoint": "/mnt/data",
                  "UsedPercent": 91.0, "FreeBytes": 1_000_000}]
        result = self._call(disks=disks, processes=[], services=[])
        combined = " ".join(result["Highlights"])
        self.assertIn("/mnt/data", combined)
        self.assertNotIn("None", combined)


if __name__ == "__main__":
    unittest.main()

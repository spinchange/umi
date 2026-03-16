import json
import unittest
import socket
import psutil
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from umi_mcp.tools import uptime, network, process, service, user


class UptimeToolTests(unittest.TestCase):
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
    ):
        # Mocking datetime.now and datetime.fromtimestamp
        mock_now = datetime(2024, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        mock_boot = datetime(2024, 3, 16, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromtimestamp.return_value = mock_boot

        mock_virtual_memory.return_value = SimpleNamespace(total=16000, used=8000, available=8000)
        mock_swap_memory.return_value = SimpleNamespace(total=4000, used=1000)

        result = uptime.get_uptime()

        self.assertEqual(result["Hostname"], "test-host")
        self.assertEqual(result["OS"], "Windows")
        self.assertEqual(result["OSVersion"], "10.0.19045")
        self.assertEqual(result["Architecture"], "x64")
        self.assertEqual(result["UptimeSeconds"], 3600)
        self.assertEqual(result["UptimeHuman"], "0d 1h 0m")
        self.assertEqual(result["TotalMemoryBytes"], 16000)
        self.assertIsNone(result["LoadAverage1m"])

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
    @patch("umi_mcp.tools.process.psutil.process_iter")
    @patch("umi_mcp.tools.process.psutil.cpu_percent")
    def test_get_process_filtering_and_top(self, _mock_cpu, mock_iter):
        mock_iter.return_value = [
            MagicMock(info={
                "pid": 101, "name": "python.exe", "ppid": 100, "cpu_percent": 5.0,
                "memory_info": SimpleNamespace(rss=1024), "memory_percent": 1.0,
                "status": psutil.STATUS_RUNNING, "username": "user1",
                "create_time": 1710590400.0, "cmdline": ["python", "app.py"], "num_threads": 2
            }),
            MagicMock(info={
                "pid": 102, "name": "chrome.exe", "ppid": 100, "cpu_percent": 15.0,
                "memory_info": SimpleNamespace(rss=2048), "memory_percent": 2.0,
                "status": psutil.STATUS_SLEEPING, "username": "user1",
                "create_time": 1710590401.0, "cmdline": ["chrome", "--tabs"], "num_threads": 10
            }),
            MagicMock(info={
                "pid": 103, "name": "bash", "ppid": 100, "cpu_percent": 0.0,
                "memory_info": SimpleNamespace(rss=512), "memory_percent": 0.5,
                "status": psutil.STATUS_IDLE, "username": "user1",
                "create_time": 1710590402.0, "cmdline": ["bash"], "num_threads": 1
            }),
        ]

        # Test all processes, sorted by CPU
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
    @patch.dict("umi_mcp.tools.user.os.environ", {"USERNAME": "testuser", "USERSID": "S-1-5-21-123"})
    @patch("umi_mcp.tools.user.platform.system", return_value="Windows")
    def test_get_user_windows(self, _sys):
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1, create=True):
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


if __name__ == "__main__":
    unittest.main()

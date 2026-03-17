import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from umi_mcp.server import get_umi_events
from umi_mcp.tools import disk, events


class DiskToolTests(unittest.TestCase):
    @patch("umi_mcp.tools.disk.subprocess.run")
    @patch("umi_mcp.tools.disk.psutil.disk_io_counters")
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Windows")
    def test_windows_disk_io_maps_drive_to_physical_disk(
        self,
        _platform_system,
        mock_partitions,
        mock_usage,
        mock_io_counters,
        mock_subprocess_run,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="C:\\", mountpoint="C:\\", fstype="NTFS")
        ]
        mock_usage.return_value = SimpleNamespace(total=1000, used=250, free=750)
        mock_io_counters.return_value = {
            "PhysicalDrive0": SimpleNamespace(
                read_count=10,
                write_count=20,
                read_bytes=100,
                write_bytes=200,
                read_time=30,
                write_time=40,
            )
        }
        mock_subprocess_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"DriveLetter": "C", "DiskNumber": 0}]),
        )

        result = disk.get_disk()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ReadCount"], 10)
        self.assertEqual(result[0]["WriteCount"], 20)
        self.assertEqual(result[0]["ReadBytes"], 100)
        self.assertEqual(result[0]["WriteBytes"], 200)
        self.assertEqual(result[0]["ReadTimeMs"], 30)
        self.assertEqual(result[0]["WriteTimeMs"], 40)

    @patch("umi_mcp.tools.disk.psutil.disk_io_counters", return_value={})
    @patch("umi_mcp.tools.disk.psutil.disk_usage")
    @patch("umi_mcp.tools.disk.psutil.disk_partitions")
    @patch("umi_mcp.tools.disk.platform.system", return_value="Linux")
    def test_disk_io_fields_are_null_when_counters_unavailable(
        self,
        _platform_system,
        mock_partitions,
        mock_usage,
        _mock_io_counters,
    ):
        mock_partitions.return_value = [
            SimpleNamespace(device="/dev/sda1", mountpoint="/", fstype="ext4")
        ]
        mock_usage.return_value = SimpleNamespace(total=1000, used=500, free=500)

        result = disk.get_disk()

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["ReadCount"])
        self.assertIsNone(result[0]["WriteCount"])
        self.assertIsNone(result[0]["ReadBytes"])
        self.assertIsNone(result[0]["WriteBytes"])
        self.assertIsNone(result[0]["ReadTimeMs"])
        self.assertIsNone(result[0]["WriteTimeMs"])


class EventsToolTests(unittest.TestCase):
    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Windows")
    def test_windows_events_normalize_and_truncate(self, _platform_system, mock_run):
        long_message = "x" * 700
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "TimeCreated": "2026-03-16T12:00:00Z",
                        "LevelDisplayName": "Error",
                        "ProviderName": "Disk",
                        "Id": 51,
                        "Message": long_message,
                    }
                ]
            ),
        )

        result = events.get_events()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Level"], "Error")
        self.assertEqual(result[0]["Source"], "Disk")
        self.assertEqual(result[0]["EventId"], 51)
        self.assertEqual(len(result[0]["Message"]), 500)
        self.assertTrue(result[0]["Message"].endswith("..."))

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Linux")
    def test_linux_events_filter_source_and_parse_timestamp(self, _platform_system, mock_run):
        lines = [
            json.dumps(
                {
                    "__REALTIME_TIMESTAMP": "1710590400000000",
                    "PRIORITY": "3",
                    "SYSLOG_IDENTIFIER": "sshd",
                    "MESSAGE": "Failed password",
                }
            ),
            json.dumps(
                {
                    "__REALTIME_TIMESTAMP": "1710590401000000",
                    "PRIORITY": "3",
                    "SYSLOG_IDENTIFIER": "cron",
                    "MESSAGE": "Ignored",
                }
            ),
        ]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="\n".join(lines))

        result = events.get_events(level="Error", source="ssh", last_n=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Source"], "sshd")
        self.assertEqual(result[0]["Level"], "Error")
        self.assertEqual(result[0]["Message"], "Failed password")
        self.assertTrue(result[0]["Timestamp"].startswith("2024-03-16T"))

    @patch("umi_mcp.tools.events.subprocess.run")
    @patch("umi_mcp.tools.events.platform.system", return_value="Darwin")
    def test_macos_events_parse_and_keep_last_n(self, _platform_system, mock_run):
        lines = [
            json.dumps(
                {
                    "timestamp": "2026-03-16 10:00:00.000000+0000",
                    "messageType": "error",
                    "subsystem": "com.apple.first",
                    "eventMessage": "first",
                }
            ),
            json.dumps(
                {
                    "timestamp": "2026-03-16 11:00:00.000000+0000",
                    "messageType": "error",
                    "subsystem": "com.apple.second",
                    "eventMessage": "second",
                }
            ),
        ]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="\n".join(lines))

        result = events.get_events(level="Error", last_n=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Source"], "com.apple.second")
        self.assertEqual(result[0]["Message"], "second")

    @patch("umi_mcp.server.get_events", return_value=[{"Level": "Error"}])
    def test_server_exposes_events_tool(self, mock_get_events):
        result = get_umi_events(level="Error", source="Disk", last_n=3)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["SchemaVersion"], "1")
        self.assertIn("GeneratedAt", result)
        self.assertEqual(result["Count"], 1)
        self.assertEqual(result["Items"], [{"Level": "Error"}])
        mock_get_events.assert_called_once_with(level="Error", source="Disk", last_n=3)


if __name__ == "__main__":
    unittest.main()

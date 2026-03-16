# Example: Conversational system health check

This is a real Claude Desktop conversation with UMI installed and connected.

---

**User:** Give me a health summary of this machine.

**Claude:** Here's the current state of Luna:

**Identity**
- Windows 11 (10.0.26200), x64
- 8 logical CPU cores, 8 GB RAM
- Running for 5 days, 2 hours since last reboot

**Resources**
- CPU: 58% utilized
- Memory: 7.1 GB used / 866 MB available (87% — getting tight)
- Swap: 3.5 GB of 20 GB in use

**Disk**
- C:\ — 75.4% used (NTFS, 234 GB total)
- G:\ — 76.7% used (Google Drive)

**Network**
- Wi-Fi: 10.0.0.39, Up — 2.5 GB sent / 8.7 GB received since boot

**Recent errors**
- The Claude Desktop service has terminated unexpectedly 3 times this week
- One .NET Runtime initialization failure

**Overall:** The machine is healthy but memory pressure is notable. The Claude Desktop service crashes are worth investigating — check the event log for exit code details.

---

**User:** What's causing the memory pressure?

**Claude:** The top memory consumers right now:

1. `msedgewebview2.exe` — 1.2 GB (multiple instances, likely Claude Desktop's embedded browser)
2. `chrome.exe` — 890 MB
3. `python.exe` — 340 MB
4. `Code.exe` — 280 MB

The WebView2 processes are the main culprit — that's the rendering engine Claude Desktop uses. With 8 GB total and these processes running, you're consistently near the ceiling. Closing Chrome or restarting Claude Desktop would recover the most headroom quickly.

---

**User:** Is the SSH service running?

**Claude:** No — `sshd` is not present in the Windows Services list. OpenSSH Server isn't installed on this machine. If you want to enable remote SSH access, you can install it via Settings → Optional Features → OpenSSH Server.

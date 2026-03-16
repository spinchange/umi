function Get-UmiUptime {
    <#
    .SYNOPSIS
        Returns system identity and uptime as a UMI-schema object.
    .DESCRIPTION
        Cross-platform system summary. Returns hostname, OS, architecture,
        boot time, and uptime conforming to the UMI Uptime schema.
    .PARAMETER AsJson
        Output as JSON string.
    .EXAMPLE
        Get-UmiUptime
        Quick system fingerprint — same shape on any OS.
    .EXAMPLE
        (Get-UmiUptime).UptimeSeconds / 86400
        Days since last reboot, cross-platform.
    .LINK
        https://github.com/spinchange/umi
    #>
    [CmdletBinding()]
    param(
        [switch]$AsJson
    )

    $hostname = [System.Net.Dns]::GetHostName()
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    $normArch = switch ($arch) {
        'X64'   { 'x64'   }
        'Arm64' { 'ARM64' }
        'X86'   { 'x86'   }
        'Arm'   { 'ARM'   }
        default { $arch   }
    }
    $cpuCount = [Environment]::ProcessorCount
    $psVersion = $PSVersionTable.PSVersion.ToString()

    $os        = Get-UmiPlatform
    $osVersion = ''
    $bootTime  = $null
    $totalMem  = [long]0

    if ($IsWindows) {
        try {
            $cim = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
            $osVersion = $cim.Version
            $bootTime  = $cim.LastBootUpTime
            $totalMem  = [long]$cim.TotalVisibleMemorySize * 1024
        } catch {
            $osVersion = [System.Environment]::OSVersion.Version.ToString()
        }
    }
    elseif ($IsLinux) {
        # Get distro info
        if (Test-Path /etc/os-release) {
            $osRelease = Get-Content /etc/os-release -ErrorAction SilentlyContinue |
                ConvertFrom-StringData -ErrorAction SilentlyContinue
            $osVersion = ($osRelease.PRETTY_NAME ?? $osRelease.NAME ?? 'Linux') -replace '"', ''
        } else {
            $osVersion = 'Linux'
        }
        # Boot time from /proc/stat
        $uptimeSec = $null
        if (Test-Path /proc/uptime) {
            $raw = (Get-Content /proc/uptime).Split(' ')[0]
            $uptimeSec = [double]$raw
            $bootTime = (Get-Date).AddSeconds(-$uptimeSec)
        }
        # Total memory
        $memLine = Get-Content /proc/meminfo -ErrorAction SilentlyContinue | Where-Object { $_ -match '^MemTotal' }
        if ($memLine -match '(\d+)') { $totalMem = [long]$Matches[1] * 1024 }
    }
    elseif ($IsMacOS) {
        $osVersion = (& sw_vers -productVersion 2>/dev/null) ?? 'macOS'
        # Boot time via sysctl
        try {
            $kernBoot = & sysctl -n kern.boottime 2>/dev/null
            if ($kernBoot -match 'sec\s*=\s*(\d+)') {
                $bootEpoch = [long]$Matches[1]
                $bootTime = [DateTimeOffset]::FromUnixTimeSeconds($bootEpoch).LocalDateTime
            }
        } catch {}
        # Total memory
        try {
            $memStr = & sysctl -n hw.memsize 2>/dev/null
            $totalMem = [long]$memStr
        } catch {}
    }

    # Calculate uptime
    $uptimeSeconds = 0
    if ($bootTime) {
        $uptimeSeconds = [int]((Get-Date) - $bootTime).TotalSeconds
    }
    $days  = [Math]::Floor($uptimeSeconds / 86400)
    $hours = [Math]::Floor(($uptimeSeconds % 86400) / 3600)
    $mins  = [Math]::Floor(($uptimeSeconds % 3600) / 60)
    $uptimeHuman = "${days}d ${hours}h ${mins}m"

    $result = [PSCustomObject]@{
        PSTypeName        = 'UMI.Uptime'
        Hostname          = $hostname
        OS                = $os
        OSVersion         = $osVersion
        Architecture      = $normArch
        BootTime          = if ($bootTime) { $bootTime.ToString('o') } else { $null }
        UptimeSeconds     = $uptimeSeconds
        UptimeHuman       = $uptimeHuman
        CpuCount          = $cpuCount
        TotalMemoryBytes  = $totalMem
        PowerShellVersion = $psVersion
    }

    if ($AsJson) {
        return ($result | ConvertTo-Json -Depth 3)
    }
    return $result
}

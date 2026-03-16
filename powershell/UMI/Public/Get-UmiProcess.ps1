function Get-UmiProcess {
    <#
    .SYNOPSIS
        Returns running process information as UMI-schema objects.
    .DESCRIPTION
        Cross-platform process query. Returns one object per process,
        conforming to the UMI Process schema (process.schema.json).
    .PARAMETER Name
        Filter by process name (supports wildcards).
    .PARAMETER Top
        Return only the top N processes by CPU usage.
    .PARAMETER AsJson
        Output as JSON string.
    .EXAMPLE
        Get-UmiProcess -Top 10
        Top 10 CPU consumers. Works identically on any OS.
    .EXAMPLE
        Get-UmiProcess -Name 'chrome*' | Measure-Object MemoryBytes -Sum
        Total memory used by Chrome across all its processes.
    .LINK
        https://github.com/spinchange/umi
    #>
    [CmdletBinding()]
    param(
        [string]$Name,
        [int]$Top,
        [switch]$AsJson
    )

    $results = @()

    if ($IsWindows) {
        try {
            $procs = try {
                Get-Process -IncludeUserName -ErrorAction Stop
            } catch {
                Get-Process -ErrorAction Stop
            }
            $totalMem = (Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize * 1024  # bytes

            foreach ($p in $procs) {
                $startTime = try { $p.StartTime.ToString('o') } catch { $null }

                $results += [PSCustomObject]@{
                    PSTypeName      = 'UMI.Process'
                    ProcessName     = $p.ProcessName
                    ProcessId       = $p.Id
                    ParentProcessId = $null  # Requires CIM query per-process, skipped for perf
                    CpuPercent      = [Math]::Round($p.CPU, 1)
                    MemoryBytes     = [long]$p.WorkingSet64
                    MemoryPercent   = if ($totalMem -gt 0) { [Math]::Round(($p.WorkingSet64 / $totalMem) * 100, 1) } else { $null }
                    Status          = if ($p.Responding) { 'Running' } else { 'Unknown' }
                    User            = if ($p.PSObject.Properties['UserName']) { $p.UserName } else { $null }
                    StartTime       = $startTime
                    CommandLine     = $null
                    ThreadCount     = $p.Threads.Count
                }
            }

            # Attempt to fill ParentProcessId and CommandLine from CIM.
            try {
                $cimProcs = Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId, CommandLine -ErrorAction Stop
                $cimCache = @{}
                foreach ($cp in $cimProcs) {
                    $cimCache[$cp.ProcessId] = @{
                        Cmd  = $cp.CommandLine
                        Ppid = $cp.ParentProcessId
                    }
                }
                foreach ($r in $results) {
                    if ($cimCache.ContainsKey($r.ProcessId)) {
                        $r.CommandLine = $cimCache[$r.ProcessId].Cmd
                        $r.ParentProcessId = $cimCache[$r.ProcessId].Ppid
                    }
                }
            } catch {
                # Non-elevated: ParentProcessId and CommandLine stay null — that's fine
            }
        } catch {
            Write-Error "Get-UmiProcess [Windows]: $_"
        }
    }
    else {
        # Linux and macOS
        try {
            $psOutput = & ps -eo pid,ppid,user,%cpu,%mem,stat,lstart,comm,args --no-headers 2>/dev/null
            if (-not $psOutput) {
                # macOS ps doesn't support all the same flags
                $psOutput = & ps -eo pid,ppid,user,%cpu,%mem,stat,comm -c 2>/dev/null | Select-Object -Skip 1
            }

            $totalMem = $null
            if ($IsLinux) {
                $memLine = Get-Content /proc/meminfo -ErrorAction SilentlyContinue | Where-Object { $_ -match '^MemTotal' }
                if ($memLine -match '(\d+)') { $totalMem = [long]$Matches[1] * 1024 }
            }

            foreach ($line in $psOutput) {
                $line = $line.Trim()
                if ([string]::IsNullOrWhiteSpace($line)) { continue }

                # Parse carefully — args field can contain spaces
                $parts = $line -split '\s+', 7
                if ($parts.Count -lt 7) { continue }

                $statusChar = $parts[5][0]
                $status = switch ($statusChar) {
                    'R' { 'Running'  }
                    'S' { 'Sleeping' }
                    'T' { 'Stopped'  }
                    'Z' { 'Zombie'   }
                    'I' { 'Idle'     }
                    'D' { 'Sleeping' }
                    default { 'Unknown' }
                }

                $cpuPct = [double]$parts[3]
                $memPct = [double]$parts[4]
                $memBytes = if ($totalMem -and $memPct -gt 0) {
                    [long]($totalMem * $memPct / 100)
                } else { [long]0 }
                $processId = [int]$parts[0]
                $threadCount = $null

                if ($IsLinux) {
                    $procStatus = Get-Content "/proc/$processId/status" -ErrorAction SilentlyContinue
                    foreach ($statusLine in $procStatus) {
                        if ($statusLine -match '^Threads:\s+(\d+)') {
                            $threadCount = [int]$Matches[1]
                            break
                        }
                    }
                }

                $results += [PSCustomObject]@{
                    PSTypeName      = 'UMI.Process'
                    ProcessName     = $parts[6] -replace '.*/(.+)$', '$1'  # strip path
                    ProcessId       = $processId
                    ParentProcessId = [int]$parts[1]
                    CpuPercent      = $cpuPct
                    MemoryBytes     = $memBytes
                    MemoryPercent   = $memPct
                    Status          = $status
                    User            = $parts[2]
                    StartTime       = $null  # lstart parsing is complex; omitted for v0.1
                    CommandLine     = $parts[6]
                    ThreadCount     = $threadCount
                }
            }
        } catch {
            Write-Error "Get-UmiProcess [Unix]: $_"
        }
    }

    # Apply filters
    if ($Name) {
        $results = $results | Where-Object { $_.ProcessName -like $Name }
    }
    if ($Top -gt 0) {
        $results = $results | Sort-Object CpuPercent -Descending | Select-Object -First $Top
    }

    if ($AsJson) {
        return ($results | ConvertTo-Json -Depth 3)
    }
    return $results
}

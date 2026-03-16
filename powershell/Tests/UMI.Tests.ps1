# UMI Pester Tests
# Run with: Invoke-Pester ./Tests/UMI.Tests.ps1

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'UMI' 'UMI.psd1') -Force
}

Describe 'Get-UmiDisk' {
    It 'Returns at least one disk' {
        $disks = Get-UmiDisk
        $disks | Should -Not -BeNullOrEmpty
    }

    It 'Has all required schema properties' {
        $disk = Get-UmiDisk | Select-Object -First 1
        $disk.DeviceName  | Should -Not -BeNullOrEmpty
        $disk.MountPoint  | Should -Not -BeNullOrEmpty
        $disk.TotalBytes  | Should -BeGreaterThan 0
        $disk.UsedBytes   | Should -BeGreaterOrEqual 0
        $disk.FreeBytes   | Should -BeGreaterOrEqual 0
        $disk.UsedPercent | Should -BeGreaterOrEqual 0
        $disk.UsedPercent | Should -BeLessOrEqual 100
    }

    It 'Outputs valid JSON with -AsJson' {
        $json = Get-UmiDisk -AsJson
        { $json | ConvertFrom-Json } | Should -Not -Throw
    }

    It 'Has consistent byte math (Used + Free ≈ Total)' {
        $disk = Get-UmiDisk | Select-Object -First 1
        $sum = $disk.UsedBytes + $disk.FreeBytes
        # Allow 1% tolerance for filesystem overhead
        $tolerance = $disk.TotalBytes * 0.01
        [Math]::Abs($sum - $disk.TotalBytes) | Should -BeLessThan ([Math]::Max($tolerance, 1048576))
    }
}

Describe 'Get-UmiNetwork' {
    It 'Returns at least one interface' {
        $nets = Get-UmiNetwork -All
        $nets | Should -Not -BeNullOrEmpty
    }

    It 'Has valid InterfaceType enum values' {
        $validTypes = @('Ethernet', 'WiFi', 'Loopback', 'Virtual', 'Tunnel', 'Unknown')
        $nets = Get-UmiNetwork -All
        foreach ($n in $nets) {
            $n.InterfaceType | Should -BeIn $validTypes
        }
    }

    It 'Has valid Status enum values' {
        $validStatus = @('Up', 'Down', 'Unknown')
        $nets = Get-UmiNetwork -All
        foreach ($n in $nets) {
            $n.Status | Should -BeIn $validStatus
        }
    }

    It 'MAC addresses are uppercase colon-separated when present' {
        $nets = Get-UmiNetwork -All
        foreach ($n in $nets) {
            if ($n.MacAddress) {
                $n.MacAddress | Should -Match '^([0-9A-F]{2}:){5}[0-9A-F]{2}$'
            }
        }
    }
}

Describe 'Get-UmiProcess' {
    It 'Returns processes' {
        $procs = Get-UmiProcess
        $procs.Count | Should -BeGreaterThan 0
    }

    It '-Top limits results' {
        $top5 = Get-UmiProcess -Top 5
        $top5.Count | Should -BeLessOrEqual 5
    }

    It '-Top results are sorted by CPU descending' {
        $top10 = Get-UmiProcess -Top 10
        for ($i = 1; $i -lt $top10.Count; $i++) {
            $top10[$i].CpuPercent | Should -BeLessOrEqual $top10[$i-1].CpuPercent
        }
    }

    It 'Has valid Status enum values' {
        $validStatus = @('Running', 'Sleeping', 'Stopped', 'Zombie', 'Idle', 'Unknown')
        $procs = Get-UmiProcess -Top 20
        foreach ($p in $procs) {
            $p.Status | Should -BeIn $validStatus
        }
    }

    It 'ProcessId is a positive integer' {
        $procs = Get-UmiProcess -Top 5
        foreach ($p in $procs) {
            $p.ProcessId | Should -BeGreaterOrEqual 0
        }
    }
}

Describe 'Get-UmiUptime' {
    It 'Returns a single object' {
        $up = Get-UmiUptime
        $up | Should -Not -BeNullOrEmpty
        @($up).Count | Should -Be 1
    }

    It 'Has valid OS enum value' {
        $up = Get-UmiUptime
        $up.OS | Should -BeIn @('Windows', 'Linux', 'macOS')
    }

    It 'Has valid Architecture enum value' {
        $up = Get-UmiUptime
        $up.Architecture | Should -BeIn @('x64', 'ARM64', 'x86', 'ARM')
    }

    It 'Uptime is positive' {
        $up = Get-UmiUptime
        $up.UptimeSeconds | Should -BeGreaterThan 0
    }

    It 'CpuCount is at least 1' {
        $up = Get-UmiUptime
        $up.CpuCount | Should -BeGreaterOrEqual 1
    }

    It 'UptimeHuman matches expected format' {
        $up = Get-UmiUptime
        $up.UptimeHuman | Should -Match '^\d+d \d+h \d+m$'
    }
}

Describe 'Get-UmiUser' {
    It 'Returns at least the current user with -Current' {
        $me = Get-UmiUser -Current
        $me | Should -Not -BeNullOrEmpty
        $me.IsCurrentUser | Should -Be $true
        $me.Username | Should -Not -BeNullOrEmpty
    }

    It 'Username matches environment' {
        $me = Get-UmiUser -Current
        $me.Username | Should -Be ([Environment]::UserName)
    }

    It 'HomeDirectory exists' {
        $me = Get-UmiUser -Current
        if ($me.HomeDirectory) {
            Test-Path $me.HomeDirectory | Should -Be $true
        }
    }
}

Describe 'Test-UmiEnvironment' {
    It 'Returns check results' {
        $checks = Test-UmiEnvironment 6>$null  # Suppress Write-Host
        $checks | Should -Not -BeNullOrEmpty
    }

    It 'PowerShell version check passes on PS7+' {
        $checks = Test-UmiEnvironment 6>$null
        $psCheck = $checks | Where-Object Check -eq 'PowerShell Version'
        if ($PSVersionTable.PSVersion.Major -ge 7) {
            $psCheck.Status | Should -Be 'PASS'
        }
    }
}

# UMI Pester Tests
# Run with: Invoke-Pester ./Tests/UMI.Tests.ps1

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'UMI' 'UMI.psd1') -Force

    function Invoke-UmiSourceOnPlatform {
        param(
            [Parameter(Mandatory)]
            [string]$ScriptName,
            [Parameter(Mandatory)]
            [ValidateSet('Windows', 'Linux', 'macOS')]
            [string]$Platform,
            [string]$Prelude = '',
            [Parameter(Mandatory)]
            [string]$Invocation
        )

        $scriptPath = Join-Path $PSScriptRoot '..' 'UMI' 'Public' $ScriptName
        $source = Get-Content $scriptPath -Raw
        $source = $source.Replace('$IsWindows', '$__umiIsWindows')
        $source = $source.Replace('$IsLinux', '$__umiIsLinux')
        $source = $source.Replace('$IsMacOS', '$__umiIsMacOS')
        $source = $source.Replace('2>/dev/null', '')
        $source = $source.Replace('& ps ', '& __umi_ps ')
        $platformSetup = switch ($Platform) {
            'Windows' { '$__umiIsWindows = $true; $__umiIsLinux = $false; $__umiIsMacOS = $false' }
            'Linux'   { '$__umiIsWindows = $false; $__umiIsLinux = $true; $__umiIsMacOS = $false' }
            'macOS'   { '$__umiIsWindows = $false; $__umiIsLinux = $false; $__umiIsMacOS = $true' }
        }

        $script = @"
$platformSetup
$Prelude
$source
$Invocation
"@

        & ([scriptblock]::Create($script))
    }
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

    It 'Parses Linux DNS servers from resolv.conf' {
        $prelude = @'
function Get-Command {
    [CmdletBinding()]
    param([string]$Name)
    if ($Name -eq 'ip') { return [pscustomobject]@{ Name = 'ip' } }
    Microsoft.PowerShell.Core\Get-Command @PSBoundParameters
}
function ip {
    param([Parameter(ValueFromRemainingArguments = $true)] [object[]]$Args)
    if ($Args[0] -eq '-j' -and $Args[1] -eq 'addr') {
        return '[{"ifname":"eth0","operstate":"UP","flags":["UP"],"addr_info":[{"family":"inet","local":"192.168.1.10","prefixlen":24}],"address":"aa:bb:cc:dd:ee:ff"}]'
    }
    if ($Args[0] -eq '-j' -and $Args[1] -eq 'route') {
        return '[{"dev":"eth0","gateway":"192.168.1.1"}]'
    }
}
function Get-Content {
    [CmdletBinding()]
    param([string]$Path)
    if ($Path -eq '/etc/resolv.conf') {
        return @(
            'nameserver 1.1.1.1',
            'search example.test',
            'nameserver 8.8.8.8'
        )
    }
    Microsoft.PowerShell.Management\Get-Content @PSBoundParameters
}
'@

        $net = Invoke-UmiSourceOnPlatform -ScriptName 'Get-UmiNetwork.ps1' -Platform 'Linux' -Prelude $prelude -Invocation 'Get-UmiNetwork -All | Select-Object -First 1'
        $net.DnsServers | Should -Be @('1.1.1.1', '8.8.8.8')
    }

    It 'Parses macOS fallback gateway and DNS servers' {
        $prelude = @'
function ifconfig {
    @"
en0: flags=8863<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> mtu 1500
    inet 10.0.0.5 netmask 0xffffff00 broadcast 10.0.0.255
    ether aa:bb:cc:dd:ee:ff
    status: active
"@
}
function netstat {
    param([Parameter(ValueFromRemainingArguments = $true)] [object[]]$Args)
    @(
        'Routing tables',
        '',
        'Internet:',
        'default            10.0.0.1           UGSc           en0'
    )
}
function scutil {
    param([Parameter(ValueFromRemainingArguments = $true)] [object[]]$Args)
    @(
        'DNS configuration',
        'resolver #1',
        '  nameserver[0] : 9.9.9.9',
        '  nameserver[1] : 8.8.4.4'
    )
}
'@

        $net = Invoke-UmiSourceOnPlatform -ScriptName 'Get-UmiNetwork.ps1' -Platform 'macOS' -Prelude $prelude -Invocation 'Get-UmiNetwork -All | Select-Object -First 1'
        $net.DefaultGateway | Should -Be '10.0.0.1'
        $net.DnsServers | Should -Be @('9.9.9.9', '8.8.4.4')
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

    It 'Parses Linux thread count from /proc status' {
        $prelude = @'
function __umi_ps {
    '123 1 root 12.5 1.0 S /usr/bin/testproc /usr/bin/testproc --flag'
}
function Get-Content {
    [CmdletBinding()]
    param([string]$Path)
    if ($Path -eq '/proc/meminfo') { return 'MemTotal:       1024000 kB' }
    if ($Path -eq '/proc/123/status') { return @('Name: testproc', 'Threads: 7') }
    Microsoft.PowerShell.Management\Get-Content @PSBoundParameters
}
'@

        $proc = Invoke-UmiSourceOnPlatform -ScriptName 'Get-UmiProcess.ps1' -Platform 'Linux' -Prelude $prelude -Invocation 'Get-UmiProcess | Select-Object -First 1'
        $proc.ThreadCount | Should -Be 7
    }

    It 'Parses Windows parent PID from CIM' {
        $prelude = @'
function Get-Process {
    [CmdletBinding()]
    param([switch]$IncludeUserName)
    [pscustomobject]@{
        ProcessName  = 'pwsh'
        Id           = 42
        CPU          = 5.1
        WorkingSet64 = 1048576
        Responding   = $true
        StartTime    = [datetime]'2026-03-16T10:00:00'
        Threads      = @(1, 2, 3)
        UserName     = 'alice'
    }
}
function Get-CimInstance {
    [CmdletBinding()]
    param([string]$ClassName, [string[]]$Property)
    switch ($ClassName) {
        'Win32_OperatingSystem' { [pscustomobject]@{ TotalVisibleMemorySize = 2048 } }
        'Win32_Process' { [pscustomobject]@{ ProcessId = 42; ParentProcessId = 24; CommandLine = 'pwsh -NoProfile' } }
    }
}
'@

        $proc = Invoke-UmiSourceOnPlatform -ScriptName 'Get-UmiProcess.ps1' -Platform 'Windows' -Prelude $prelude -Invocation 'Get-UmiProcess | Select-Object -First 1'
        $proc.ParentProcessId | Should -Be 24
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

    It 'Parses Linux last login timestamps' {
        $prelude = @'
function Get-Content {
    [CmdletBinding()]
    param([string]$Path)
    if ($Path -eq '/etc/passwd') { return 'alice:x:1000:1000:Alice Example:/home/alice:/bin/bash' }
    Microsoft.PowerShell.Management\Get-Content @PSBoundParameters
}
function id {
    param([Parameter(ValueFromRemainingArguments = $true)] [object[]]$Args)
    if ($Args[0] -eq '-u') { return '1000' }
    if ($Args[0] -eq '-Gn') { return 'sudo users' }
}
function last {
    param([Parameter(ValueFromRemainingArguments = $true)] [object[]]$Args)
    'alice pts/0 10.0.0.5 Mon Mar 15 08:30 - 09:30 (01:00)'
}
'@

        $user = Invoke-UmiSourceOnPlatform -ScriptName 'Get-UmiUser.ps1' -Platform 'Linux' -Prelude $prelude -Invocation 'Get-UmiUser -Current | Select-Object -First 1'
        ([datetimeoffset]$user.LastLogin).ToString('yyyy-MM-ddTHH:mm:ss') | Should -Be '2026-03-15T08:30:00'
    }

    It 'Parses macOS last login timestamps' {
        $prelude = @'
function Get-Content {
    [CmdletBinding()]
    param([string]$Path)
    if ($Path -eq '/etc/passwd') { return 'alice:x:501:20:Alice Example:/Users/alice:/bin/zsh' }
    Microsoft.PowerShell.Management\Get-Content @PSBoundParameters
}
function id {
    param([Parameter(ValueFromRemainingArguments = $true)] [object[]]$Args)
    if ($Args[0] -eq '-u') { return '501' }
    if ($Args[0] -eq '-Gn') { return 'staff admin' }
}
function last {
    param([Parameter(ValueFromRemainingArguments = $true)] [object[]]$Args)
    'alice console Mon Mar 15 08:30   still logged in'
}
'@

        $user = Invoke-UmiSourceOnPlatform -ScriptName 'Get-UmiUser.ps1' -Platform 'macOS' -Prelude $prelude -Invocation 'Get-UmiUser -Current | Select-Object -First 1'
        ([datetimeoffset]$user.LastLogin).ToString('yyyy-MM-ddTHH:mm:ss') | Should -Be '2026-03-15T08:30:00'
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

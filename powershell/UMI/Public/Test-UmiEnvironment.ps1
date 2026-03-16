function Test-UmiEnvironment {
    <#
    .SYNOPSIS
        Validates that the current system can run UMI commands.
    .DESCRIPTION
        Checks PowerShell version, platform, required commands, and permissions.
        Returns a structured report. Run this first on any new machine.
    .PARAMETER Fix
        Attempt to suggest or apply fixes for common issues.
    .EXAMPLE
        Test-UmiEnvironment
        Quick health check before using UMI.
    .LINK
        https://github.com/spinchange/umi
    #>
    [CmdletBinding()]
    param(
        [switch]$Fix
    )

    $checks = @()

    # 1. PowerShell version
    $psVer = $PSVersionTable.PSVersion
    $psOk = $psVer.Major -ge 7
    $checks += [PSCustomObject]@{
        Check   = 'PowerShell Version'
        Status  = if ($psOk) { 'PASS' } else { 'FAIL' }
        Detail  = "Found $psVer" + $(if (-not $psOk) { ' — UMI requires PowerShell 7+. Install from https://aka.ms/powershell' } else { '' })
    }

    # 2. Platform detection
    $platform = Get-UmiPlatform
    $checks += [PSCustomObject]@{
        Check   = 'Platform Detection'
        Status  = if ($platform -ne 'Unknown') { 'PASS' } else { 'WARN' }
        Detail  = "Detected: $platform"
    }

    # 3. Required commands (platform-specific)
    $requiredCmds = @()
    if ($IsWindows) {
        $requiredCmds = @('Get-CimInstance', 'Get-NetAdapter', 'Get-Process')
    }
    elseif ($IsLinux) {
        $requiredCmds = @('ps', 'df', 'id')
        # Preferred but not required
        $preferred = @('ip')
        foreach ($cmd in $preferred) {
            $exists = Get-Command $cmd -ErrorAction SilentlyContinue
            $checks += [PSCustomObject]@{
                Check  = "Command: $cmd"
                Status = if ($exists) { 'PASS' } else { 'WARN' }
                Detail = if ($exists) { 'Available' } else { "Not found — some features will use fallback methods. $(if ($Fix) { 'Try: sudo apt install iproute2' })" }
            }
        }
    }
    elseif ($IsMacOS) {
        $requiredCmds = @('ps', 'df', 'ifconfig', 'sw_vers')
    }

    foreach ($cmd in $requiredCmds) {
        $exists = Get-Command $cmd -ErrorAction SilentlyContinue
        $checks += [PSCustomObject]@{
            Check  = "Command: $cmd"
            Status = if ($exists) { 'PASS' } else { 'FAIL' }
            Detail = if ($exists) { 'Available' } else { "Not found — required for UMI on $platform" }
        }
    }

    # 4. Elevation check
    $isElevated = $false
    if ($IsWindows) {
        $isElevated = ([Security.Principal.WindowsPrincipal]([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } else {
        $isElevated = ((& id -u 2>/dev/null) -eq '0')
    }
    $checks += [PSCustomObject]@{
        Check  = 'Elevated/Root'
        Status = 'INFO'
        Detail = if ($isElevated) { 'Running as admin/root — all features available' } else { 'Running as normal user — some process details may be limited (this is fine for most uses)' }
    }

    # 5. Module integrity
    $moduleRoot = $PSScriptRoot | Split-Path
    $publicFuncs = Get-ChildItem (Join-Path $moduleRoot 'Public') -Filter '*.ps1' -ErrorAction SilentlyContinue
    $checks += [PSCustomObject]@{
        Check  = 'UMI Functions'
        Status = if ($publicFuncs.Count -ge 5) { 'PASS' } else { 'WARN' }
        Detail = "Found $($publicFuncs.Count) public functions: $($publicFuncs.BaseName -join ', ')"
    }

    # Summary
    $fails = ($checks | Where-Object Status -eq 'FAIL').Count
    $warns = ($checks | Where-Object Status -eq 'WARN').Count

    Write-Host ""
    Write-Host "  UMI Environment Check" -ForegroundColor Cyan
    Write-Host "  =====================" -ForegroundColor Cyan
    Write-Host ""

    foreach ($c in $checks) {
        $icon = switch ($c.Status) {
            'PASS' { '✓' }
            'FAIL' { '✗' }
            'WARN' { '!' }
            'INFO' { '·' }
        }
        $color = switch ($c.Status) {
            'PASS' { 'Green'  }
            'FAIL' { 'Red'    }
            'WARN' { 'Yellow' }
            'INFO' { 'Gray'   }
        }
        Write-Host "  $icon " -NoNewline -ForegroundColor $color
        Write-Host "$($c.Check): " -NoNewline
        Write-Host $c.Detail -ForegroundColor $color
    }

    Write-Host ""
    if ($fails -gt 0) {
        Write-Host "  Result: $fails failure(s). Fix these before using UMI." -ForegroundColor Red
    } elseif ($warns -gt 0) {
        Write-Host "  Result: Ready with $warns warning(s). UMI will work with reduced features." -ForegroundColor Yellow
    } else {
        Write-Host "  Result: All checks passed. UMI is ready." -ForegroundColor Green
    }
    Write-Host ""

    return $checks
}

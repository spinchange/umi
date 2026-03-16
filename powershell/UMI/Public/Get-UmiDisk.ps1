function Get-UmiDisk {
    <#
    .SYNOPSIS
        Returns disk/volume information as UMI-schema objects.
    .DESCRIPTION
        Cross-platform disk query. Returns one object per mounted volume,
        conforming to the UMI Disk schema (disk.schema.json).

        Works on Windows, Linux, and macOS without changing your code.
    .PARAMETER AsJson
        Output as a JSON string instead of PSCustomObjects. Useful for
        piping to other agents or storing in a file.
    .EXAMPLE
        Get-UmiDisk
        Returns all fixed disks as UMI objects.
    .EXAMPLE
        Get-UmiDisk | Where-Object UsedPercent -gt 80
        Find disks that are more than 80% full. Works on any OS.
    .EXAMPLE
        Get-UmiDisk -AsJson | Set-Content ~/disk-report.json
        Export a machine-readable report.
    .LINK
        https://github.com/spinchange/umi
    #>
    [CmdletBinding()]
    param(
        [switch]$AsJson
    )

    $results = @()

    if ($IsWindows) {
        try {
            $volumes = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop
            foreach ($vol in $volumes) {
                $used = $vol.Size - $vol.FreeSpace
                $results += [PSCustomObject]@{
                    PSTypeName  = 'UMI.Disk'
                    DeviceName  = $vol.DeviceID
                    MountPoint  = "$($vol.DeviceID)\"
                    FileSystem  = ($vol.FileSystem ?? 'Unknown').ToUpper()
                    TotalBytes  = [long]$vol.Size
                    UsedBytes   = [long]$used
                    FreeBytes   = [long]$vol.FreeSpace
                    UsedPercent = if ($vol.Size -gt 0) { [Math]::Round(($used / $vol.Size) * 100, 1) } else { 0 }
                    IsRemovable = $false
                    Label       = if ([string]::IsNullOrWhiteSpace($vol.VolumeName)) { $null } else { $vol.VolumeName }
                }
            }
        } catch {
            Write-Error "Get-UmiDisk [Windows]: $_"
        }
    }
    else {
        # Linux and macOS — use df with POSIX output
        try {
            $dfOutput = & df -P 2>/dev/null | Select-Object -Skip 1
            # Get filesystem types via mount or df -T
            $fsTypes = @{}
            if ($IsLinux) {
                $dfT = & df -T 2>/dev/null | Select-Object -Skip 1
                foreach ($line in $dfT) {
                    $parts = $line -split '\s+'
                    if ($parts.Count -ge 2) {
                        $fsTypes[$parts[0]] = $parts[1].ToUpper()
                    }
                }
            }

            foreach ($line in $dfOutput) {
                $parts = $line -split '\s+'
                if ($parts.Count -lt 6) { continue }

                $device     = $parts[0]
                $totalKB    = [long]$parts[1] * 1024
                $usedKB     = [long]$parts[2] * 1024
                $freeKB     = [long]$parts[3] * 1024
                $pctString  = $parts[4] -replace '%', ''
                $mountPoint = $parts[5..($parts.Count - 1)] -join ' '

                # Skip pseudo-filesystems
                if ($device -match '^(tmpfs|devtmpfs|udev|none|overlay|shm)$') { continue }
                if ($mountPoint -match '^/(dev|proc|sys|run|snap)') { continue }

                $fs = if ($fsTypes.ContainsKey($device)) { $fsTypes[$device] }
                     elseif ($IsMacOS) { 'APFS' }
                     else { 'Unknown' }

                $results += [PSCustomObject]@{
                    PSTypeName  = 'UMI.Disk'
                    DeviceName  = $device
                    MountPoint  = $mountPoint
                    FileSystem  = $fs
                    TotalBytes  = $totalKB
                    UsedBytes   = $usedKB
                    FreeBytes   = $freeKB
                    UsedPercent = [double]$pctString
                    IsRemovable = $false
                    Label       = $null
                }
            }
        } catch {
            Write-Error "Get-UmiDisk [Unix]: $_"
        }
    }

    if ($AsJson) {
        return ($results | ConvertTo-Json -Depth 3)
    }
    return $results
}

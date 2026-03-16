function Get-UmiUser {
    <#
    .SYNOPSIS
        Returns local user account information as UMI-schema objects.
    .DESCRIPTION
        Cross-platform user query. Returns one object per local user account,
        conforming to the UMI User schema (user.schema.json).
    .PARAMETER Current
        Return only the currently logged-in user.
    .PARAMETER AsJson
        Output as JSON string.
    .EXAMPLE
        Get-UmiUser -Current
        Who am I? Same answer format on any OS.
    .EXAMPLE
        Get-UmiUser | Where-Object IsAdmin -eq $true
        Find all admin accounts, cross-platform.
    .LINK
        https://github.com/spinchange/umi
    #>
    [CmdletBinding()]
    param(
        [switch]$Current,
        [switch]$AsJson
    )

    $results  = @()
    $whoAmI   = [Environment]::UserName

    if ($IsWindows) {
        try {
            if ($Current) {
                $sid = ([System.Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
                $isAdmin = ([Security.Principal.WindowsPrincipal]([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

                $results += [PSCustomObject]@{
                    PSTypeName    = 'UMI.User'
                    Username      = $whoAmI
                    UserId        = $sid
                    FullName      = $null
                    HomeDirectory = [Environment]::GetFolderPath('UserProfile')
                    Shell         = 'powershell'
                    IsCurrentUser = $true
                    IsAdmin       = $isAdmin
                    IsEnabled     = $true
                    Groups        = @()
                    LastLogin     = $null
                }
            }
            else {
                $localUsers = Get-CimInstance Win32_UserAccount -Filter "LocalAccount=True" -ErrorAction Stop
                foreach ($u in $localUsers) {
                    $isCurrent = ($u.Name -eq $whoAmI)
                    $homePath  = Join-Path $env:SystemDrive "Users\$($u.Name)"

                    # Check admin group membership
                    $isAdmin = $false
                    try {
                        $admins = & net localgroup Administrators 2>/dev/null
                        $isAdmin = $admins -contains $u.Name
                    } catch {}

                    $results += [PSCustomObject]@{
                        PSTypeName    = 'UMI.User'
                        Username      = $u.Name
                        UserId        = $u.SID
                        FullName      = if ([string]::IsNullOrWhiteSpace($u.FullName)) { $null } else { $u.FullName }
                        HomeDirectory = if (Test-Path $homePath) { $homePath } else { $null }
                        Shell         = $null
                        IsCurrentUser = $isCurrent
                        IsAdmin       = $isAdmin
                        IsEnabled     = (-not $u.Disabled)
                        Groups        = @()
                        LastLogin     = $null
                    }
                }
            }
        } catch {
            Write-Error "Get-UmiUser [Windows]: $_"
        }
    }
    else {
        # Linux and macOS — parse /etc/passwd
        try {
            $passwdLines = Get-Content /etc/passwd -ErrorAction Stop
            $currentUid = & id -u 2>/dev/null

            foreach ($line in $passwdLines) {
                $parts = $line -split ':'
                if ($parts.Count -lt 7) { continue }

                $username = $parts[0]
                $uid      = [int]$parts[2]
                $gid      = [int]$parts[3]
                $fullName = if ([string]::IsNullOrWhiteSpace($parts[4]) -or $parts[4] -eq $username) { $null } else { ($parts[4] -split ',')[0] }
                $home     = $parts[5]
                $shell    = $parts[6]

                # Skip system accounts (UID < 1000 on Linux, < 500 on macOS) unless root
                if ($IsLinux -and $uid -lt 1000 -and $uid -ne 0) { continue }
                if ($IsMacOS -and $uid -lt 500 -and $uid -ne 0) { continue }

                $isCurrent = ($uid.ToString() -eq $currentUid)

                if ($Current -and -not $isCurrent) { continue }

                # Check admin status
                $isAdmin = $false
                $groups = @()
                try {
                    $groupOutput = & id -Gn $username 2>/dev/null
                    if ($groupOutput) {
                        $groups = @($groupOutput -split '\s+')
                        $isAdmin = ($groups -contains 'sudo' -or $groups -contains 'wheel' -or $groups -contains 'admin' -or $uid -eq 0)
                    }
                } catch {}

                $results += [PSCustomObject]@{
                    PSTypeName    = 'UMI.User'
                    Username      = $username
                    UserId        = $uid
                    FullName      = $fullName
                    HomeDirectory = $home
                    Shell         = $shell
                    IsCurrentUser = $isCurrent
                    IsAdmin       = $isAdmin
                    IsEnabled     = (-not ($shell -match 'nologin|false'))
                    Groups        = $groups
                    LastLogin     = $null
                }
            }
        } catch {
            Write-Error "Get-UmiUser [Unix]: $_"
        }
    }

    if ($AsJson) {
        return ($results | ConvertTo-Json -Depth 3)
    }
    return $results
}

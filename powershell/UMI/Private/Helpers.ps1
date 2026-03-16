function ConvertTo-UmiBytes {
    <#
    .SYNOPSIS
        Converts human-readable size strings (e.g., '4.2G', '512M', '1.1T') to bytes.
    .DESCRIPTION
        Internal helper used by UMI functions to normalize size output from
        Unix utilities into raw byte counts for schema compliance.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SizeString
    )

    $SizeString = $SizeString.Trim()

    # Already a plain number (bytes)
    if ($SizeString -match '^\d+$') {
        return [long]$SizeString
    }

    $multipliers = @{
        'B' = 1
        'K' = 1024
        'M' = 1048576
        'G' = 1073741824
        'T' = 1099511627776
        'P' = 1125899906842624
    }

    if ($SizeString -match '^([\d.]+)\s*([BKMGTP])i?[Bb]?$') {
        $value = [double]$Matches[1]
        $unit  = $Matches[2].ToUpper()
        if ($multipliers.ContainsKey($unit)) {
            return [long]($value * $multipliers[$unit])
        }
    }

    Write-Warning "ConvertTo-UmiBytes: Could not parse '$SizeString'. Returning 0."
    return [long]0
}

function Get-UmiPlatform {
    <#
    .SYNOPSIS
        Returns the current platform as a normalized string.
    #>
    if ($IsWindows) { return 'Windows' }
    if ($IsLinux)   { return 'Linux'   }
    if ($IsMacOS)   { return 'macOS'   }
    return 'Unknown'
}

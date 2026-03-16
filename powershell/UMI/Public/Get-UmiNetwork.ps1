function Get-UmiNetwork {
    <#
    .SYNOPSIS
        Returns network interface information as UMI-schema objects.
    .DESCRIPTION
        Cross-platform network query. Returns one object per active interface,
        conforming to the UMI Network schema (network.schema.json).
    .PARAMETER AsJson
        Output as JSON string.
    .PARAMETER All
        Include interfaces that are currently down.
    .EXAMPLE
        Get-UmiNetwork
        Returns all active network interfaces.
    .EXAMPLE
        Get-UmiNetwork | Where-Object InterfaceType -eq 'WiFi'
        Find wireless adapters across any OS.
    .LINK
        https://github.com/spinchange/umi
    #>
    [CmdletBinding()]
    param(
        [switch]$AsJson,
        [switch]$All
    )

    $results = @()

    if ($IsWindows) {
        try {
            $adapters = Get-NetAdapter -ErrorAction Stop
            if (-not $All) { $adapters = $adapters | Where-Object Status -eq 'Up' }

            foreach ($adapter in $adapters) {
                $ipConfig = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1
                $ip6Config = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv6 -ErrorAction SilentlyContinue |
                    Where-Object { $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1
                $gateway = (Get-NetRoute -InterfaceIndex $adapter.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue).NextHop | Select-Object -First 1
                $dns = (Get-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses

                $ifType = switch -Wildcard ($adapter.InterfaceDescription) {
                    '*Wi-Fi*'    { 'WiFi' }
                    '*Wireless*' { 'WiFi' }
                    '*Loopback*' { 'Loopback' }
                    '*Virtual*'  { 'Virtual' }
                    '*Hyper-V*'  { 'Virtual' }
                    '*Tunnel*'   { 'Tunnel' }
                    default      { 'Ethernet' }
                }

                # Normalize MAC to colon-separated uppercase
                $mac = if ($adapter.MacAddress) {
                    ($adapter.MacAddress -replace '-', ':').ToUpper()
                } else { $null }

                # Convert prefix length to subnet mask
                $subnetMask = $null
                if ($ipConfig.PrefixLength) {
                    $maskBits = ('1' * $ipConfig.PrefixLength).PadRight(32, '0')
                    $octets = for ($i = 0; $i -lt 32; $i += 8) { [Convert]::ToInt32($maskBits.Substring($i, 8), 2) }
                    $subnetMask = $octets -join '.'
                }

                $results += [PSCustomObject]@{
                    PSTypeName     = 'UMI.Network'
                    InterfaceName  = $adapter.Name
                    InterfaceType  = $ifType
                    Status         = if ($adapter.Status -eq 'Up') { 'Up' } else { 'Down' }
                    IPv4Address    = $ipConfig.IPAddress
                    IPv6Address    = $ip6Config.IPAddress
                    SubnetMask     = $subnetMask
                    DefaultGateway = $gateway
                    MacAddress     = $mac
                    SpeedMbps      = if ($adapter.LinkSpeed -match '(\d+)') { [int]$Matches[1] } else { $null }
                    DnsServers     = @($dns)
                }
            }
        } catch {
            Write-Error "Get-UmiNetwork [Windows]: $_"
        }
    }
    else {
        # Linux and macOS
        try {
            if ($IsLinux -and (Get-Command ip -ErrorAction SilentlyContinue)) {
                $ipJson = & ip -j addr 2>/dev/null | ConvertFrom-Json
                foreach ($iface in $ipJson) {
                    $status = if ($iface.operstate -eq 'UP' -or $iface.flags -contains 'UP') { 'Up' } else { 'Down' }
                    if (-not $All -and $status -ne 'Up') { continue }

                    $ipv4 = ($iface.addr_info | Where-Object family -eq 'inet' | Select-Object -First 1).local
                    $ipv6 = ($iface.addr_info | Where-Object { $_.family -eq 'inet6' -and $_.scope -eq 'global' } | Select-Object -First 1).local
                    $prefixLen = ($iface.addr_info | Where-Object family -eq 'inet' | Select-Object -First 1).prefixlen

                    $subnetMask = $null
                    if ($prefixLen) {
                        $maskBits = ('1' * $prefixLen).PadRight(32, '0')
                        $octets = for ($i = 0; $i -lt 32; $i += 8) { [Convert]::ToInt32($maskBits.Substring($i, 8), 2) }
                        $subnetMask = $octets -join '.'
                    }

                    $mac = if ($iface.address -and $iface.address -ne '00:00:00:00:00:00') {
                        $iface.address.ToUpper()
                    } else { $null }

                    $ifType = switch -Regex ($iface.ifname) {
                        'lo'          { 'Loopback' }
                        'wl|wlan'     { 'WiFi' }
                        'docker|veth|br-|virbr' { 'Virtual' }
                        'tun|wg'      { 'Tunnel' }
                        default       { 'Ethernet' }
                    }

                    $results += [PSCustomObject]@{
                        PSTypeName     = 'UMI.Network'
                        InterfaceName  = $iface.ifname
                        InterfaceType  = $ifType
                        Status         = $status
                        IPv4Address    = $ipv4
                        IPv6Address    = $ipv6
                        SubnetMask     = $subnetMask
                        DefaultGateway = $null  # Requires separate 'ip route' call
                        MacAddress     = $mac
                        SpeedMbps      = $null
                        DnsServers     = @()
                    }
                }

                # Fill in default gateway
                $defaultGw = & ip -j route show default 2>/dev/null | ConvertFrom-Json | Select-Object -First 1
                if ($defaultGw) {
                    $gwIface = $results | Where-Object InterfaceName -eq $defaultGw.dev | Select-Object -First 1
                    if ($gwIface) { $gwIface.DefaultGateway = $defaultGw.gateway }
                }
            }
            elseif ($IsMacOS -or (Get-Command ifconfig -ErrorAction SilentlyContinue)) {
                # Fallback: parse ifconfig
                $raw = & ifconfig 2>/dev/null
                $currentIface = $null
                $ifaceBlocks = @{}

                foreach ($line in $raw -split "`n") {
                    if ($line -match '^(\S+):') {
                        $currentIface = $Matches[1] -replace ':$', ''
                        $ifaceBlocks[$currentIface] = @()
                    }
                    if ($currentIface) {
                        $ifaceBlocks[$currentIface] += $line
                    }
                }

                foreach ($name in $ifaceBlocks.Keys) {
                    $block = $ifaceBlocks[$name] -join "`n"
                    $status = if ($block -match 'status:\s*active' -or $block -match '<UP') { 'Up' } else { 'Down' }
                    if (-not $All -and $status -ne 'Up') { continue }

                    $ipv4 = if ($block -match 'inet\s+([\d.]+)') { $Matches[1] } else { $null }
                    $mask = if ($block -match 'netmask\s+(0x[0-9a-f]+)') {
                        $hex = $Matches[1]
                        $octets = for ($i = 2; $i -lt 10; $i += 2) { [Convert]::ToInt32($hex.Substring($i, 2), 16) }
                        $octets -join '.'
                    } elseif ($block -match 'netmask\s+([\d.]+)') { $Matches[1] }
                    else { $null }

                    $mac = if ($block -match 'ether\s+([\da-f:]+)') { $Matches[1].ToUpper() } else { $null }

                    $ifType = switch -Regex ($name) {
                        'lo'       { 'Loopback' }
                        'en\d'     { if ($IsMacOS) { 'WiFi' } else { 'Ethernet' } }
                        'wl|wlan'  { 'WiFi' }
                        'utun|gif|stf' { 'Tunnel' }
                        default    { 'Ethernet' }
                    }

                    $results += [PSCustomObject]@{
                        PSTypeName     = 'UMI.Network'
                        InterfaceName  = $name
                        InterfaceType  = $ifType
                        Status         = $status
                        IPv4Address    = $ipv4
                        IPv6Address    = $null
                        SubnetMask     = $mask
                        DefaultGateway = $null
                        MacAddress     = $mac
                        SpeedMbps      = $null
                        DnsServers     = @()
                    }
                }
            }
        } catch {
            Write-Error "Get-UmiNetwork [Unix]: $_"
        }
    }

    if ($AsJson) {
        return ($results | ConvertTo-Json -Depth 3)
    }
    return $results
}

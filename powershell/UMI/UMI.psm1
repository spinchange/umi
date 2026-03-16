# UMI — Universal Machine Interface
# Root module: auto-loads all public and private functions

$Private = Get-ChildItem -Path (Join-Path $PSScriptRoot 'Private') -Filter '*.ps1' -ErrorAction SilentlyContinue
$Public  = Get-ChildItem -Path (Join-Path $PSScriptRoot 'Public')  -Filter '*.ps1' -ErrorAction SilentlyContinue

foreach ($file in @($Private + $Public)) {
    try {
        . $file.FullName
    } catch {
        Write-Error "Failed to import $($file.FullName): $_"
    }
}

# Export only Public functions (Private stay internal)
foreach ($file in $Public) {
    Export-ModuleMember -Function $file.BaseName
}

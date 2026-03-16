@{
    RootModule        = 'UMI.psm1'
    ModuleVersion     = '0.1.0'
    GUID              = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    Author            = 'Chris @ SpinChange'
    CompanyName       = 'SpinChange'
    Copyright         = '(c) 2026 SpinChange. MIT License.'
    Description       = 'Universal Machine Interface — A cross-platform PowerShell module that returns structured objects conforming to the UMI schema. Designed for humans and AI agents alike.'
    PowerShellVersion = '7.0'
    FunctionsToExport = @(
        'Get-UmiDisk',
        'Get-UmiNetwork',
        'Get-UmiProcess',
        'Get-UmiUptime',
        'Get-UmiUser',
        'Test-UmiEnvironment'
    )
    CmdletsToExport   = @()
    VariablesToExport  = @()
    AliasesToExport    = @()
    PrivateData        = @{
        PSData = @{
            Tags       = @('CrossPlatform', 'AI', 'Agents', 'Schema', 'Universal', 'LLM', 'Automation')
            LicenseUri = 'https://github.com/spinchange/umi/blob/main/LICENSE'
            ProjectUri = 'https://github.com/spinchange/umi'
            ReleaseNotes = 'Initial release — Disk, Network, Process, Uptime, User schemas with PowerShell reference implementation.'
        }
    }
}

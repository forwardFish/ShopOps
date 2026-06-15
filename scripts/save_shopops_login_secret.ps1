param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("tmall", "douyin")]
    [string]$Platform,
    [string]$SecretRoot = "$env:APPDATA\ShopOps\secrets"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $SecretRoot | Out-Null

$target = Join-Path $SecretRoot "$Platform-login.credential.xml"
Write-Host "Saving $Platform login credential for the current Windows user only."
Write-Host "This uses Windows DPAPI via Export-Clixml; it is not portable to another Windows user."
$credential = Get-Credential -Message "Enter the $Platform login username and password"
$credential | Export-Clixml -Path $target
Write-Host "Saved encrypted credential: $target"

# اسکریپت بکاپ سریع PostgreSQL روی ویندوز (PowerShell)
param(
    [string]$BackupDir = ".\backups",
    [string]$ContainerName = "team_finder_db",
    [string]$PostgresUser = "team_admin",
    [string]$PostgresDb = "team_finder",
    [int]$RetentionDays = 7
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$OutFile = Join-Path $BackupDir "${PostgresDb}_${Timestamp}.sql"

Write-Host "Starting PostgreSQL backup -> $OutFile"
docker exec $ContainerName pg_dump -U $PostgresUser $PostgresDb | Out-File -FilePath $OutFile -Encoding utf8

Get-ChildItem -Path $BackupDir -Filter "${PostgresDb}_*.sql" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
    Remove-Item -Force

Write-Host "Backup completed successfully: $OutFile"

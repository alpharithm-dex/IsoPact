$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content (Join-Path $root 'config\required-google-apis.json') -Raw | ConvertFrom-Json
$enabled = @(gcloud services list --enabled --project $manifest.project --format='value(config.name)')
foreach ($service in $manifest.required) {
    if ($service -notin $enabled) {
        gcloud services enable $service --project $manifest.project
    }
}


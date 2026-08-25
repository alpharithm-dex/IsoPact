$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Get-Content (Join-Path $root 'config\deployment-manifest.json') -Raw | ConvertFrom-Json
gcloud run services update $manifest.outcome_gateway.service --project $manifest.project --region $manifest.outcome_gateway.region --image $manifest.outcome_gateway.image --quiet


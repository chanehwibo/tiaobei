param(
    [string]$ReportPath = ".\data\eval\latest_report.json",
    [string]$StorePath = ".\data\memory.sqlite"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$env:PYTHONPATH = "$ProjectRoot\src"

Write-Host "== Demo: sample memory pipeline =="
python -m os_agent_memory.cli demo --input ".\data\samples\events.jsonl"

Write-Host "`n== Evaluation: summary + full report =="
python -m os_agent_memory.cli evaluate --suite ".\data\eval\office_memory_eval.json" --top-k 3 --summary-only --output $ReportPath

Write-Host "`n== Build SQLite memory store =="
python -m os_agent_memory.cli build-store --input ".\data\samples\events.jsonl" --output $StorePath

Write-Host "`n== Unit tests =="
python -m unittest discover -s tests

Write-Host "`nDemo finished."
Write-Host "Report: $ReportPath"
Write-Host "SQLite store: $StorePath"

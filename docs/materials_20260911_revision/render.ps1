param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Output,
    [Parameter(Mandatory = $true)][ValidateSet("word", "ppt")][string]$Kind
)

$ErrorActionPreference = "Stop"
$lab = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE "TiaobeiLab"))
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$target = [IO.Path]::GetFullPath($Output)
$inputFile = (Resolve-Path -LiteralPath $Source).Path
if (-not $target.StartsWith($lab + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Render output must remain in the private lab"
}
if (-not ($inputFile.StartsWith($project + "\", [StringComparison]::OrdinalIgnoreCase) -or
          $inputFile.StartsWith($lab + "\", [StringComparison]::OrdinalIgnoreCase))) {
    throw "Input must remain in the project or private lab"
}
$extension = [IO.Path]::GetExtension($inputFile)
if (($Kind -eq "word" -and $extension -ne ".docx") -or
    ($Kind -eq "ppt" -and $extension -ne ".pptx")) { throw "Office input type mismatch" }
if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite an existing render" }
$before = (Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash
$null = New-Item -ItemType Directory -Path $target
$app = $null
$document = $null
$processName = if ($Kind -eq "ppt") { "wpp" } else { "wps" }
$hadApplication = @(Get-Process -Name $processName -ErrorAction SilentlyContinue).Count -gt 0
try {
    if ($Kind -eq "ppt") {
        $app = New-Object -ComObject "KWPP.Application"
        foreach ($opened in $app.Presentations) {
            if ($opened.FullName -eq $inputFile) { throw "Input is already open; refusing to touch a user's document" }
        }
        $document = $app.Presentations.Open($inputFile, -1, 0, 0)
        $document.Export($target, "PNG", 1600, 900)
        $count = $document.Slides.Count
    } else {
        $app = New-Object -ComObject "KWPS.Application"
        foreach ($opened in $app.Documents) {
            if ($opened.FullName -eq $inputFile) { throw "Input is already open; refusing to touch a user's document" }
        }
        $missing = [Type]::Missing
        $document = $app.Documents.Open($inputFile, $false, $true, $false,
            $missing, $missing, $missing, $missing, $missing, $missing, $missing, $false)
        $document.ExportAsFixedFormat((Join-Path $target "document.pdf"), 17)
        $count = $document.ComputeStatistics(2)
    }
    Write-Output ("Rendered {0}: {1}" -f $Kind, $count)
} finally {
    if ($null -ne $document) {
        if ($Kind -eq "word") { $document.Close(0) } else { $document.Close() }
        $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($null -ne $app) {
        $remaining = if ($Kind -eq "word") { $app.Documents.Count } else { $app.Presentations.Count }
        if (-not $hadApplication -and $remaining -eq 0) { $app.Quit() }
        $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
    }
}
$after = (Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash
if ($before -ne $after) { throw "Read-only rendering changed the Office source" }
$files = [ordered]@{}
foreach ($file in (Get-ChildItem -LiteralPath $target -File | Sort-Object Name)) {
    $files[$file.Name] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$record = [ordered]@{
    scope = "read_only_wps_render_for_private_layout_review"
    kind = $Kind
    source_name = [IO.Path]::GetFileName($inputFile)
    source_raw_sha256 = $before.ToLowerInvariant()
    source_unchanged = $true
    count = $count
    rendered_at_utc = [DateTime]::UtcNow.ToString("o")
    output_raw_sha256 = $files
    private_pdf_is_not_a_deliverable = $true
}
$record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $target "render_manifest.json") -Encoding UTF8

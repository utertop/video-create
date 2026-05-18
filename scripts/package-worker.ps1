$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$workerScript = Join-Path $repoRoot "video_engine_worker.py"
$distDir = Join-Path $repoRoot "scratch\pyinstaller-dist"
$workDir = Join-Path $repoRoot "scratch\pyinstaller-build"
$specDir = Join-Path $repoRoot "scratch\pyinstaller-spec"
$fakeAppDataDir = Join-Path $repoRoot "scratch\pyinstaller-appdata"
$fakeUserBaseDir = Join-Path $repoRoot "scratch\pyinstaller-user-base"
$targetDir = Join-Path $repoRoot "src-tauri\bin"
$targetExe = Join-Path $targetDir "video-create-worker.exe"

$env:PYTHONNOUSERSITE = "1"
if (Test-Path Env:PYTHONPATH) {
  Remove-Item Env:PYTHONPATH
}
$env:APPDATA = $fakeAppDataDir
$env:PYTHONUSERBASE = $fakeUserBaseDir

if (-not (Test-Path $workerScript)) {
  throw "Cannot find worker script: $workerScript"
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $workDir | Out-Null
New-Item -ItemType Directory -Force -Path $specDir | Out-Null
New-Item -ItemType Directory -Force -Path $fakeAppDataDir | Out-Null
New-Item -ItemType Directory -Force -Path $fakeUserBaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

$pyInstallerCheck = & python -I -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is not installed. Run: python -m pip install -r .\requirements-worker-build.txt"
}

$args = @(
  "-I",
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", "video-create-worker",
  "--distpath", $distDir,
  "--workpath", $workDir,
  "--specpath", $specDir,
  "--collect-all", "moviepy",
  "--collect-all", "imageio",
  "--collect-all", "imageio_ffmpeg",
  "--collect-all", "proglog",
  "--collect-all", "pilmoji",
  "--collect-all", "PIL",
  "--collect-all", "requests",
  "--copy-metadata", "moviepy",
  "--copy-metadata", "imageio",
  "--copy-metadata", "imageio-ffmpeg",
  "--copy-metadata", "proglog",
  $workerScript
)

& python @args
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller worker packaging failed."
}

$builtExe = Join-Path $distDir "video-create-worker.exe"
if (-not (Test-Path $builtExe)) {
  throw "Expected packaged worker was not created: $builtExe"
}

for ($attempt = 1; $attempt -le 10; $attempt++) {
  try {
    Copy-Item -LiteralPath $builtExe -Destination $targetExe -Force
    break
  } catch {
    if ($attempt -eq 10) {
      throw
    }
    Start-Sleep -Milliseconds 500
  }
}

Write-Host "Packaged worker copied to $targetExe"

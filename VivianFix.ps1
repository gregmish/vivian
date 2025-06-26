# VivianFix.ps1 – Auto-fix missing files and structure for Vivian assistant

$root = "Vivian"

Write-Host "[✓] Fixing main.py..."
$mainPath = Join-Path $root "main.py"
$mainCode = @"
def main():
    global user_manager
    config = load_config()
    user_manager = UserManager(config)
    memory = MemoryManager(config, event_bus=EventBus())
    voice = VoiceIO(config, event_bus=None)
    agents = start_agents(config, memory, EventBus())

    if server_supported():
        run_server(config, memory, EventBus())

    if gui_supported():
        run_gui()

    while $true:
        \$input = Read-Host "Vivian >"
        \$output = handle_user_input(\$input, config, memory, EventBus())
        Write-Host \$output
if __name__ == '__main__':
    main()
"@
Add-Content -Path $mainPath -Value "`n$mainCode"

Write-Host "[✓] Creating __init__.py files..."
$folders = Get-ChildItem -Recurse -Directory -Path $root
$folders += Get-Item $root
foreach ($folder in $folders) {
    $initPath = Join-Path $folder.FullName "__init__.py"
    if (-not (Test-Path $initPath)) {
        New-Item -ItemType File -Path $initPath | Out-Null
    }
}

Write-Host "[✓] Creating plugins/example_plugin.py..."
$pluginFolder = Join-Path $root "plugins"
if (-not (Test-Path $pluginFolder)) {
    New-Item -ItemType Directory -Path $pluginFolder | Out-Null
}
$pluginCode = @"
def run_plugin(name='example', **kwargs):
    return f"Plugin \{name} says hello!"
"@
Set-Content -Path (Join-Path $pluginFolder "example_plugin.py") -Value $pluginCode

Write-Host "[✓] Removing broken imports if needed..."
(gc $mainPath) -replace "from web\.server import.*", "" | Set-Content $mainPath

Write-Host "[✓] Creating requirements.txt..."
$reqs = @"
pyttsx3
speechrecognition
flask
requests
opencv-python
"@
Set-Content -Path (Join-Path $root "requirements.txt") -Value $reqs

Write-Host "[✓] Creating README.md..."
$readme = @"
# Vivian AI Assistant

To run:

# Vivian.spec – Stable PyInstaller spec with robust auto-skip for missing/invalid files and multi-folder support

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
is_win = sys.platform.startswith('win')
pathex = [os.path.abspath('.'), os.path.abspath('./VivianCore')]  # Both root and VivianCore in path

def safe_add(path, target='.'):
    """Add (src, dst) tuple if src exists, else None (for data folders/files)."""
    return (path, target) if os.path.exists(path) else None

# List all important files and folders to bundle, including VivianCore subfolders/plugins
datas = list(filter(None, [
    safe_add('vivian_gui.py'),
    safe_add('vivian_chatbox.py'),
    safe_add('vivian_logo.png'),
    safe_add('vivian.ico'),
    safe_add('version.txt'),
    safe_add('README.md'),
    safe_add('LICENSE'),
    safe_add('plugins', 'plugins'),
    safe_add('themes', 'themes'),
    safe_add('images', 'images'),
    safe_add('knowledge', 'knowledge'),
    safe_add('VivianCore/plugins', 'VivianCore/plugins'),
    safe_add('VivianCore/themes', 'VivianCore/themes'),
    safe_add('VivianCore/images', 'VivianCore/images'),
    safe_add('VivianCore/knowledge', 'VivianCore/knowledge'),
]))

# Gather dynamic hidden imports for plugins/themes in both root and VivianCore
hiddenimports = [
    'tkinter',
    'tkinter.scrolledtext',
    'tkinter.ttk',
    'tkinter.simpledialog',
    'tkinter.font',
    'tkinterdnd2',
    'ttkthemes',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL._tkinter_finder',
    'tkhtmlview',
] + collect_submodules('plugins') \
  + collect_submodules('themes') \
  + collect_submodules('VivianCore.plugins') \
  + collect_submodules('VivianCore.themes')

excludes = ['PyQt5', 'PySide2', 'pytest']

a = Analysis(
    ['vivian_gui.py'],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Vivian',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=is_win,
    console=False,
    # Only include icon if it exists and is a .ico
    icon='vivian.ico' if os.path.exists('vivian.ico') and os.path.splitext('vivian.ico')[1] == '.ico' else None,
    version='version.txt' if os.path.exists('version.txt') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=is_win,
    upx_exclude=[],
    name='Vivian'
)
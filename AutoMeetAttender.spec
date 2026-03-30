# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for AutoMeet Attender

block_cipher = None

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('.env.example', '.'),
        ('meetings.json', '.'),
    ],
    hiddenimports=[
        'playwright',
        'playwright.sync_api',
        'dotenv',
        'PIL',
        'PIL.Image',
        'imagehash',
        'sounddevice',
        'scipy',
        'scipy.io',
        'scipy.io.wavfile',
        'numpy',
        'pydub',
        'pydub.audio_segment',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AutoMeetAttender',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console window for logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

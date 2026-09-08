# -*- mode: python ; coding: utf-8 -*-
import sys

# .ico on Windows (PNG->ICO conversion would require Pillow at build time);
# .png is fine everywhere else.
_ICON = 'assets/icon.ico' if sys.platform == 'win32' else 'assets/icon.png'


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    # faster-whisper decodes 16 kHz mono numpy arrays straight from memory;
    # file-decoding extras (av / onnxruntime assets) are never exercised but
    # PyInstaller's dependency walker still drags them in.
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Trim unused Qt modules and the unused pillow stack that the dependency
    # walker pulls in transitively (pystray -> PIL). Vocara needs only
    # QtCore/Gui/Widgets/Network. NOTE: av / onnxruntime / tokenizers CANNOT
    # be excluded — faster-whisper imports them at module load (audio.py,
    # vad.py, transcribe.py).
    excludes=[
        'tkinter',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtQuickTest',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtVirtualKeyboard',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtWebChannel',
        'PySide6.QtWebSockets',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DExtras',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtPositioning',
        'PySide6.QtLocation',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSerialBus',
        'PySide6.QtTextToSpeech',
        'PIL',
        'pillow',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Vocara',
    debug=False,
    bootloader_ignore_signals=False,
    # UPX on Linux Qt/CTranslate2 shared libs causes intermittent loader
    # crashes; the size win is not worth it.
    strip=True,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[_ICON],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name='Vocara',
)

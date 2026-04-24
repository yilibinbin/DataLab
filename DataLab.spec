# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab/data_extrapolation_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab/docs/desktop', 'docs/desktop'), ('/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab/shared/help_specs.json', 'shared')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender', 'PySide6.QtAsyncio', 'PySide6.QtBluetooth', 'PySide6.QtCharts', 'PySide6.QtConcurrent', 'PySide6.QtDataVisualization', 'PySide6.QtDesigner', 'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets', 'PySide6.QtHelp', 'PySide6.QtHttpServer', 'PySide6.QtLocation', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtNetworkAuth', 'PySide6.QtNfc', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtPositioning', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickControls2', 'PySide6.QtQuickTest', 'PySide6.QtQuickWidgets', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtSensors', 'PySide6.QtSerialBus', 'PySide6.QtSerialPort', 'PySide6.QtSpatialAudio', 'PySide6.QtSql', 'PySide6.QtStateMachine', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtTest', 'PySide6.QtTextToSpeech', 'PySide6.QtUiTools', 'PySide6.QtWebChannel', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebSockets', 'PySide6.QtWebView', 'PySide6.QtXml', 'PySide6.scripts', 'PySide6.support'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DataLab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab/build/macos_gui_build/app_icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DataLab',
)
app = BUNDLE(
    coll,
    name='DataLab.app',
    icon='/Users/fanghao/Documents/Code/data_extrapolation_gui/DataLab/build/macos_gui_build/app_icon.icns',
    bundle_identifier=None,
)

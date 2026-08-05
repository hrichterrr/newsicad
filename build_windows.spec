# PyInstaller spec para gerar o NewSIcad.exe no Windows.
#
# Uso (dentro do venv do Windows, com pyinstaller instalado):
#   pyinstaller build_windows.spec
#
# O executável final fica em dist/NewSIcad/NewSIcad.exe (modo "onedir" —
# mais rápido para abrir que "onefile", só precisa distribuir a pasta
# dist/NewSIcad inteira, ou zipá-la).

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
for pkg in ("PySide6", "ezdxf"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["newsicad/main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NewSIcad",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NewSIcad",
)

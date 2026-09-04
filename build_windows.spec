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
for pkg in ("PySide6", "ezdxf", "pymupdf", "requests"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

# Binários do LibreDWG (dwg2dxf.exe + DLLs) usados por newsicad/io/dwg_bridge.py
# para abrir .dwg. O destino "resources/libredwg/windows" (relativo à raiz do
# bundle, ou seja sys._MEIPASS) precisa bater com o que
# dwg_bridge._bundled_bin_dir() resolve em modo "frozen".
datas += [("newsicad/resources/libredwg/windows", "resources/libredwg/windows")]

# Ícone (logo NewSI) usado como QIcon em tempo de execução (newsicad/main.py
# _icon_path) — mesmo raciocínio de "resources/" solto na raiz do bundle.
datas += [("newsicad/resources/newsi_icon.ico", "resources")]

# Ícones SVG do ribbon/menus/status bar (newsicad/ui/icon_utils.py:svg_icon
# resolve "resources/icons" do mesmo jeito que o logo acima).
datas += [("newsicad/resources/icons", "resources/icons")]

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
    icon="newsicad/resources/newsi_icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NewSIcad",
)

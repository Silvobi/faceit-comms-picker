from pathlib import Path
import sys

root = Path(SPECPATH).parent
parser = "csda.exe" if sys.platform == "win32" else "csda"
a = Analysis(
    [str(root / "lvig.py")], pathex=[str(root)],
    binaries=[(str(root / "vendor/cs-demo-analyzer" / parser), "vendor/cs-demo-analyzer")],
    datas=[(str(root / "vendor/cs-demo-analyzer/LICENSE.md"), "vendor/cs-demo-analyzer"),
           (str(root / "assets/faceit-comms-picker.png"), "assets")],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="FACEIT-Comms-Picker",
    console=False, debug=False, strip=False, upx=False,
    icon=str(root / "assets/faceit-comms-picker.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FACEIT-Comms-Picker")

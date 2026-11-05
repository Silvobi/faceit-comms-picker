"""Build the native standalone application and distributable packages."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "packaging"
DIST = ROOT / "dist"
PACKAGES = DIST / "packages"
NAME = "FACEIT-Comms-Picker"
CSDA_REVISION = "5a892a6181c38b8d0bece1d162a59bdacee6ac0e"
CSDA_SOURCE_SHA256 = "4c913eb8e384d74678ee3e54d550d1a4da049fd546eadac80c2a0655a6a0e5c9"
CSDA_WINDOWS_SHA256 = "7940724c38b82bbab9d5ab4cebd87b596ef67f9b743724983179c65c84f452c1"
APPIMAGETOOL_URL = "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA256 = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"


def version() -> str:
    for node in ast.parse((ROOT / "lvig.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "APP_VERSION" for t in node.targets):
            return ast.literal_eval(node.value).removeprefix("v")
    raise RuntimeError("APP_VERSION missing")


def run(*args: str | Path, cwd: Path = ROOT, env: dict | None = None) -> None:
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def download(url: str, destination: Path, digest: str) -> None:
    if not destination.exists() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        with urlopen(Request(url, headers={"User-Agent": NAME}), timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError(f"Checksum mismatch: {url}")
        destination.write_bytes(data)


def prepare_parser() -> None:
    parser_dir = ROOT / "vendor" / "cs-demo-analyzer"
    if sys.platform == "win32":
        if hashlib.sha256((parser_dir / "csda.exe").read_bytes()).hexdigest() != CSDA_WINDOWS_SHA256:
            raise RuntimeError("Bundled Windows parser does not match the pinned source revision")
        return
    archive = BUILD / "csda-source.tar.gz"
    download(f"https://github.com/akiver/cs-demo-analyzer/archive/{CSDA_REVISION}.tar.gz", archive, CSDA_SOURCE_SHA256)
    with tarfile.open(archive) as source:
        source.extractall(BUILD, filter="data")
    source_root = BUILD / f"cs-demo-analyzer-{CSDA_REVISION}"
    run("go", "build", "-trimpath", "-o", parser_dir / "csda", "./cmd/cli", cwd=source_root,
        env={**os.environ, "CGO_ENABLED": "0"})
    (parser_dir / "csda").chmod(0o755)


def prepare_icons() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtSvg
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    renderer = QtSvg.QSvgRenderer(str(ROOT / "assets/faceit-comms-picker.svg"))
    image = QtGui.QImage(256, 256, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    renderer.render(painter)
    painter.end()
    assert image.save(str(ROOT / "assets/faceit-comms-picker.png"))
    if sys.platform == "win32":
        assert image.save(str(ROOT / "assets/faceit-comms-picker.ico"), "ICO")
    del app


def add_notices(bundle: Path) -> None:
    notices = bundle / "licenses"
    notices.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "vendor/cs-demo-analyzer/LICENSE.md", notices / "cs-demo-analyzer-MIT.md")
    for package in ("PySide6", "PySide6_Essentials", "shiboken6"):
        dist = importlib.metadata.distribution(package)
        for item in dist.files or []:
            if "licenses/" in str(item).lower():
                target = notices / package / Path(str(item).split("licenses/", 1)[1])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dist.locate_file(item), target)
    (notices / "DEPENDENCIES.txt").write_text(
        f"FACEIT Comms Picker {version()}\n"
        f"Python {platform.python_version()} — https://www.python.org/\n"
        f"PySide6 / Qt {importlib.metadata.version('PySide6')} — https://www.qt.io/qt-for-python\n"
        f"cs-demo-analyzer {CSDA_REVISION} — https://github.com/akiver/cs-demo-analyzer\n"
        "Python/Qt shared libraries are shipped alongside the executable in _internal.\n",
        encoding="utf-8",
    )
    shutil.copy2(ROOT / "README.md", bundle / "README.md")


def windows_packages(bundle: Path) -> None:
    archive = PACKAGES / f"{NAME}-{version()}-windows-x64-portable.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(bundle.rglob("*")):
            if file.is_file():
                output.write(file, Path(NAME) / file.relative_to(bundle))
        output.writestr(f"{NAME}/portable.txt", "Keep settings.ini next to FACEIT-Comms-Picker.exe.\n")
    compiler = shutil.which("iscc")
    if not compiler:
        candidate = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe"
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        raise RuntimeError("Install Inno Setup 6 or add ISCC.exe to PATH")
    run(compiler, f"/DAppVersion={version()}", f"/DProjectRoot={ROOT}", ROOT / "packaging/windows.iss")


def linux_package(bundle: Path) -> None:
    appdir = BUILD / "FACEIT-Comms-Picker.AppDir"
    # This build-owned directory is replaced only after verifying its absolute location.
    if appdir.exists():
        assert appdir.resolve().parent == BUILD.resolve()
        shutil.rmtree(appdir)
    shutil.copytree(bundle, appdir / "usr/bin")
    shutil.copy2(ROOT / "packaging/AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    shutil.copy2(ROOT / "packaging/faceit-comms-picker.desktop", appdir)
    shutil.copy2(ROOT / "assets/faceit-comms-picker.png", appdir)
    tool = BUILD / "appimagetool.AppImage"
    download(APPIMAGETOOL_URL, tool, APPIMAGETOOL_SHA256)
    tool.chmod(0o755)
    run(tool, "--appimage-extract-and-run", "--no-appstream", appdir,
        PACKAGES / f"{NAME}-{version()}-linux-x86_64.AppImage",
        env={**os.environ, "ARCH": "x86_64", "VERSION": version()})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-only", action="store_true")
    args = parser.parse_args()
    if sys.platform not in {"win32", "linux"} or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("Build on 64-bit Windows or x86_64 Linux")
    BUILD.mkdir(parents=True, exist_ok=True)
    PACKAGES.mkdir(parents=True, exist_ok=True)
    prepare_parser()
    prepare_icons()
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", ROOT / "packaging/faceit-comms-picker.spec")
    bundle = DIST / NAME
    add_notices(bundle)
    binary = bundle / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
    report = BUILD / f"smoke-{sys.platform}.json"
    subprocess.run([str(binary), "--smoke-test", str(report)], check=True, timeout=90)
    if not report.is_file() or not json.loads(report.read_text(encoding="utf-8"))["frozen"]:
        raise RuntimeError("Frozen application did not pass its smoke test")
    if not args.bundle_only:
        windows_packages(bundle) if sys.platform == "win32" else linux_package(bundle)
        hashes = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in sorted(PACKAGES.iterdir()) if p.suffix in {".exe", ".zip", ".AppImage"}]
        (PACKAGES / f"SHA256SUMS-{sys.platform}.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

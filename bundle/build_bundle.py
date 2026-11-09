"""Build a release download of Chalk that carries its own Python.

    python bundle/build_bundle.py windows-x64 [--version v1.2.0] [--out dist]
    python bundle/build_bundle.py macos-arm64
    python bundle/build_bundle.py macos-x64

The result is `dist/Chalk-<version>-<platform>.zip`: a `Chalk` folder with
the app, the `Start Chalk` launchers, and a `python` folder holding a
private Python with every package from requirements.txt already installed.
An instructor unzips it and double-clicks Start Chalk: nothing to install
and nothing downloaded on first run, which is what managed university
computers (no admin rights, antivirus watching scripts that download and run
code) need. See DECISIONS.md, "Bundled Python".

Run it on the platform it builds for (GitHub Actions does, in
.github/workflows/bundle.yml): it installs the packages with the bundled
Python itself, then starts Chalk once to prove the bundle works.

Where the Python comes from:
- Windows: python.org's own installer pieces (MSI files), unpacked with
  `msiexec /a`. Those files are signed by the Python Software Foundation,
  which antivirus software trusts, and include tkinter for the Browse
  buttons (the smaller "embeddable" Python has no tkinter).
- macOS: python-build-standalone, a relocatable Python (python.org's macOS
  build only works installed in /Library). It's not signed with an Apple
  Developer ID, so `Start Chalk.command` lifts macOS's download quarantine
  from the python folder.

Every download is pinned by SHA-256, so a changed file stops the build.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_VERSION = "3.14.10"
PBS_RELEASE = "20261026"  # python-build-standalone release tag
STAMP_NAME = ".chalk-requirements.sha256"  # same as chalk.launcher.STAMP_NAME
# Written into a Mac bundle's python folder, so Start Chalk.command can say
# which zip to download when someone picks the one for the other kind of Mac.
ARCH_FILE = ".chalk-arch"
MAC_ARCHES = {"macos-arm64": "arm64", "macos-x64": "x86_64"}

# Tracked files that an instructor doesn't need in the download.
EXCLUDED_PREFIXES = (".github/", "bundle/", "tests/")
EXCLUDED_FILES = {"requirements-dev.txt", ".gitattributes", ".gitignore"}

# Imported once with the bundled Python before zipping, to catch a missing
# package or a broken tkinter (the Browse buttons need it).
SMOKE_IMPORTS = (
    "streamlit, openai, anthropic, docx, pypdf, pdfplumber, pydantic, dotenv, "
    "keyring, pandas, reportlab, tkinter, ssl, sqlite3, chalk.launcher"
)


@dataclass(frozen=True)
class Download:
    url: str
    sha256: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1].replace("%2B", "+")


_MSI_BASE = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/amd64"
_PBS_BASE = f"https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_RELEASE}"

RUNTIMES: dict[str, tuple[Download, ...]] = {
    # core: python314.dll and the C runtime; exe: python.exe; lib: the
    # standard library and pip's bundled wheel; tcltk: tkinter.
    "windows-x64": (
        Download(f"{_MSI_BASE}/core.msi", "c281a45a6f32d09f5964c6c46e9438ac11a578949ae50b486f8a7e3077190171"),
        Download(f"{_MSI_BASE}/exe.msi", "020fe726f23828d705fea820613f7f6806d94a25fa765ad1cd3edd6d4c8a118a"),
        Download(f"{_MSI_BASE}/lib.msi", "b1af18657af9de511c8c66dfc5ab8e89965c95339cc759c3d0733a8eab6a14fc"),
        Download(f"{_MSI_BASE}/tcltk.msi", "9642593510b188aa35dcdf1995cbe2b3c3c07446a0ac1dd0c1d1958bf25526f5"),
    ),
    "macos-arm64": (
        Download(
            f"{_PBS_BASE}/cpython-{PYTHON_VERSION}%2B{PBS_RELEASE}-aarch64-apple-darwin-install_only.tar.gz",
            "30a18bcb9ab75e485b4bf4e5d783dde165571e7e42c56dff47a2d2c5345183a4",
        ),
    ),
    "macos-x64": (
        Download(
            f"{_PBS_BASE}/cpython-{PYTHON_VERSION}%2B{PBS_RELEASE}-x86_64-apple-darwin-install_only.tar.gz",
            "01cedae5d4a66ac570e13cb35fa570d0e79ba8e9affd4518a5d85b6c2b98ff10",
        ),
    ),
}


def log(message: str) -> None:
    print(f"[bundle] {message}", flush=True)


# ---- downloads ------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(download: Download, cache: Path) -> Path:
    """Download once into `cache` and check the pinned hash, every time."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / download.filename
    if not target.exists():
        log(f"Downloading {download.url}")
        partial = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(download.url, timeout=120) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.replace(target)
    actual = sha256_of(target)
    if actual != download.sha256:
        target.unlink()
        raise SystemExit(
            f"{download.filename}: SHA-256 is {actual}, expected {download.sha256}. "
            "The download changed or was corrupted; not using it."
        )
    return target


# ---- the Python runtime ---------------------------------------------------------


def runtime_python(python_dir: Path, platform: str) -> Path:
    if platform.startswith("windows"):
        return python_dir / "python.exe"
    return python_dir / "bin" / "python3"


def unpack_runtime(platform: str, archives: list[Path], python_dir: Path) -> None:
    if platform.startswith("windows"):
        _unpack_msis(archives, python_dir)
    else:
        _unpack_standalone(archives[0], python_dir)


def _unpack_msis(msis: list[Path], python_dir: Path) -> None:
    """An administrative install (`msiexec /a`) copies an MSI's files to a
    folder without installing anything or touching the registry."""
    python_dir.mkdir(parents=True)
    for msi in msis:
        log(f"Unpacking {msi.name}")
        subprocess.run(
            ["msiexec", "/a", str(msi), "/qn", f"TARGETDIR={python_dir}"], check=True,
        )
        # An administrative install leaves a copy of the MSI behind.
        (python_dir / msi.name).unlink(missing_ok=True)
    if not (python_dir / "python.exe").exists():
        found = ", ".join(sorted(path.name for path in python_dir.iterdir()))
        raise SystemExit(f"No python.exe at the top of the unpacked MSIs; found: {found}")


def _unpack_standalone(archive: Path, python_dir: Path) -> None:
    """python-build-standalone's install_only archive holds one `python` folder."""
    log(f"Unpacking {archive.name}")
    with tarfile.open(archive) as tar:
        tar.extractall(python_dir.parent, filter="data")
    if not python_dir.is_dir():
        raise SystemExit(f"{archive.name} didn't contain a python folder.")


def install_requirements(python: Path, python_dir: Path, stage: Path) -> None:
    """Install requirements.txt into the bundled Python's own site-packages,
    then write the stamp the launcher checks, so it won't install again."""
    env = _isolated_env()
    if subprocess.run([str(python), "-m", "pip", "--version"], env=env, capture_output=True, check=False).returncode:
        subprocess.run([str(python), "-m", "ensurepip", "--default-pip"], env=env, check=True)
    requirements = stage / "requirements.txt"
    subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
         "--only-binary=:all:", "-r", str(requirements)],
        env=env, check=True,
    )
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    # The launcher looks for the stamp in sys.prefix, which is python_dir.
    (python_dir / STAMP_NAME).write_text(digest, encoding="utf-8")


def compile_bytecode(python: Path, stage: Path) -> None:
    """Precompile every .py in the bundle (standard library, packages, app)
    as hash-checked bytecode, so the first start doesn't recompile them all.

    By default a .pyc records its source's modification time, and Python
    throws the .pyc away when that time doesn't match. A zip stores times
    rounded to 2 seconds with no time zone, so after unzipping, especially
    in another time zone, every .pyc is stale. The first start on a fresh PC
    then took 3 to 4 minutes, with a blank page the whole time. A
    hash-checked .pyc records the source's hash instead, which unzipping
    doesn't change."""
    log("Compiling Python files")
    result = subprocess.run(
        [str(python), "-m", "compileall", "-q", "-f", "-j", "0",
         "--invalidation-mode", "checked-hash", str(stage)],
        env=_isolated_env(), check=False,
    )
    if result.returncode:
        # Some packages ship .py files that aren't meant to compile (templates,
        # Python 2 examples). Python compiles the rest; those are never imported.
        log("Some files didn't compile (listed above); they are never imported.")


def _isolated_env() -> dict[str, str]:
    """The build machine's own Python settings must not leak into the bundle."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    env["PYTHONNOUSERSITE"] = "1"
    return env


# ---- the app files --------------------------------------------------------------


def app_files(repo: Path = REPO_ROOT) -> list[str]:
    """Tracked files that go in the download, as repo-relative POSIX paths."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo, check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    return [path for path in listed if path and is_shipped(path)]


def is_shipped(path: str) -> bool:
    return not path.startswith(EXCLUDED_PREFIXES) and path not in EXCLUDED_FILES


def copy_app(files: list[str], stage: Path, repo: Path = REPO_ROOT) -> None:
    for relative in files:
        source = repo / relative
        if not source.exists():  # deleted in the working tree but not yet committed
            continue
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for launcher in stage.glob("*.command"):
        launcher.chmod(0o755)


# ---- check, then zip ------------------------------------------------------------


def smoke_test(python: Path, stage: Path, timeout: float = 180) -> None:
    """Import every package, then start Chalk the way the launcher does and
    wait for it to say it's running."""
    env = _isolated_env()
    subprocess.run([str(python), "-c", f"import {SMOKE_IMPORTS}"], cwd=stage, env=env, check=True)
    log("Starting Chalk to check the bundle")
    server = subprocess.Popen(
        [str(python), "-m", "chalk.launcher", "--no-browser"], cwd=stage, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        # Its own process group, so stopping it also stops Streamlit under it.
        **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
           else {"start_new_session": True}),
    )
    deadline = time.monotonic() + timeout
    output = []
    try:
        for line in server.stdout:
            output.append(line)
            if "Chalk is running at" in line:
                log("Chalk started")
                return
            if "Installing Chalk's components" in line:
                raise SystemExit("The launcher tried to install packages; the bundle's stamp is wrong.")
            if time.monotonic() > deadline:
                break
        raise SystemExit("Chalk didn't start from the bundle:\n" + "".join(output))
    finally:
        _stop(server)


def _stop(process: subprocess.Popen) -> None:
    """Stop the launcher and the Streamlit server it started."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


def write_zip(stage: Path, zip_path: Path, top: str = "Chalk") -> None:
    """Zip `stage` as a `top` folder, keeping Unix permissions and symlinks
    (the macOS Python has both) so Finder's unzip restores them."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            name = f"{top}/{path.relative_to(stage).as_posix()}"
            if path.is_symlink():
                info = zipfile.ZipInfo(name)
                info.create_system = 3  # Unix, so external_attr is read as a mode
                info.external_attr = (stat.S_IFLNK | 0o755) << 16
                archive.writestr(info, os.readlink(path))
            elif path.is_dir():
                continue
            else:
                info = zipfile.ZipInfo.from_file(path, name)
                info.compress_type = zipfile.ZIP_DEFLATED
                with path.open("rb") as handle:
                    archive.writestr(info, handle.read())


# ---- main -----------------------------------------------------------------------


def build(platform: str, version: str, out: Path, *, skip_smoke_test: bool = False) -> Path:
    work = out / "work" / platform
    stage = work / "Chalk"
    if work.exists():
        shutil.rmtree(work)
    stage.mkdir(parents=True)

    archives = [fetch(download, out / "cache") for download in RUNTIMES[platform]]
    copy_app(app_files(), stage)
    python_dir = stage / "python"
    unpack_runtime(platform, archives, python_dir)
    python = runtime_python(python_dir, platform)
    if platform in MAC_ARCHES:
        (python_dir / ARCH_FILE).write_text(MAC_ARCHES[platform] + "\n", encoding="utf-8")
    install_requirements(python, python_dir, stage)
    compile_bytecode(python, stage)
    if not skip_smoke_test:
        smoke_test(python, stage)
    # Course projects are never shipped; drop any the smoke test created.
    shutil.rmtree(stage / "projects", ignore_errors=True)

    zip_path = out / f"Chalk-{version}-{platform}.zip"
    log(f"Writing {zip_path}")
    write_zip(stage, zip_path)
    log(f"Done: {zip_path} ({zip_path.stat().st_size / 1e6:.0f} MB)")
    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("platform", choices=sorted(RUNTIMES))
    parser.add_argument("--version", default="dev", help="Goes in the zip's name, e.g. v1.2.0.")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--skip-smoke-test", action="store_true")
    args = parser.parse_args(argv)

    expected = "win32" if args.platform.startswith("windows") else "darwin"
    if sys.platform != expected:
        parser.error(f"build {args.platform} on {expected}: packages are installed by the bundled Python itself")
    build(args.platform, args.version, args.out.resolve(), skip_smoke_test=args.skip_smoke_test)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

"""Tests for bundle/build_bundle.py: the parts that don't need a real
Python download. The full build runs in .github/workflows/bundle.yml."""

import hashlib
import importlib.util
import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "bundle" / "build_bundle.py"
_spec = importlib.util.spec_from_file_location("build_bundle", _PATH)
build_bundle = importlib.util.module_from_spec(_spec)
sys.modules["build_bundle"] = build_bundle  # dataclasses look their module up here
_spec.loader.exec_module(build_bundle)


def test_every_runtime_download_is_pinned_by_sha256():
    for platform, downloads in build_bundle.RUNTIMES.items():
        assert downloads, platform
        for download in downloads:
            assert download.url.startswith("https://"), download.url
            assert len(download.sha256) == 64 and int(download.sha256, 16) >= 0


def test_stamp_name_matches_the_launcher():
    from chalk import launcher

    assert build_bundle.STAMP_NAME == launcher.STAMP_NAME


def test_shipped_files_leave_out_tests_ci_and_the_builder():
    files = build_bundle.app_files()
    assert "app.py" in files
    assert "requirements.txt" in files
    assert "Start Chalk.bat" in files and "Start Chalk.command" in files
    assert "chalk/launcher.py" in files
    assert not any(path.startswith(("tests/", ".github/", "bundle/")) for path in files)
    assert "requirements-dev.txt" not in files


def test_runtime_python_path_per_platform(tmp_path):
    assert build_bundle.runtime_python(tmp_path, "windows-x64") == tmp_path / "python.exe"
    assert build_bundle.runtime_python(tmp_path, "macos-arm64") == tmp_path / "bin" / "python3"


def _download_of(path: Path, sha256: str):
    return build_bundle.Download(path.as_uri(), sha256)


def test_fetch_keeps_a_download_whose_hash_matches(tmp_path):
    source = tmp_path / "python.tar.gz"
    source.write_bytes(b"runtime")
    good = hashlib.sha256(b"runtime").hexdigest()
    fetched = build_bundle.fetch(_download_of(source, good), tmp_path / "cache")
    assert fetched.read_bytes() == b"runtime"
    # A second fetch uses the cached copy, and still checks it.
    assert build_bundle.fetch(_download_of(source, good), tmp_path / "cache") == fetched


def test_fetch_rejects_and_deletes_a_changed_download(tmp_path):
    source = tmp_path / "python.tar.gz"
    source.write_bytes(b"tampered")
    with pytest.raises(SystemExit, match="SHA-256"):
        build_bundle.fetch(_download_of(source, "0" * 64), tmp_path / "cache")
    assert not (tmp_path / "cache" / "python.tar.gz").exists()


def test_download_filename_decodes_the_plus_sign():
    download = build_bundle.Download("https://x/cpython-3.14.10%2B20261026-a.tar.gz", "0" * 64)
    assert download.filename == "cpython-3.14.10+20261026-a.tar.gz"


def test_copy_app_makes_mac_launchers_executable(tmp_path):
    stage = tmp_path / "stage"
    build_bundle.copy_app(["Start Chalk.command", "app.py", "no-such-file.txt"], stage)
    assert (stage / "app.py").exists()
    assert not (stage / "no-such-file.txt").exists()
    assert os.access(stage / "Start Chalk.command", os.X_OK) or sys.platform == "win32"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_zip_keeps_permissions_and_symlinks(tmp_path):
    stage = tmp_path / "stage"
    (stage / "python" / "bin").mkdir(parents=True)
    real = stage / "python" / "bin" / "python3.14"
    real.write_text("binary")
    real.chmod(0o755)
    (stage / "python" / "bin" / "python3").symlink_to("python3.14")
    (stage / "app.py").write_text("print('hi')")

    zip_path = tmp_path / "Chalk.zip"
    build_bundle.write_zip(stage, zip_path)

    with zipfile.ZipFile(zip_path) as archive:
        entries = {info.filename: info for info in archive.infolist()}
        assert set(entries) == {"Chalk/app.py", "Chalk/python/bin/python3.14", "Chalk/python/bin/python3"}
        link = entries["Chalk/python/bin/python3"]
        assert stat.S_ISLNK(link.external_attr >> 16)
        assert archive.read(link) == b"python3.14"
        assert (entries["Chalk/python/bin/python3.14"].external_attr >> 16) & 0o111


def test_main_refuses_to_build_for_another_platform(capsys):
    other = "macos-arm64" if sys.platform == "win32" else "windows-x64"
    with pytest.raises(SystemExit):
        build_bundle.main([other])
    assert "packages are installed by the bundled Python itself" in capsys.readouterr().err


def test_every_mac_bundle_records_its_cpu_type_for_the_launcher():
    macs = {name for name in build_bundle.RUNTIMES if name.startswith("macos")}
    assert set(build_bundle.MAC_ARCHES) == macs
    launcher = (_PATH.parent.parent / "Start Chalk.command").read_text(encoding="utf-8")
    assert f"python/{build_bundle.ARCH_FILE}" in launcher
    for arch in build_bundle.MAC_ARCHES.values():
        assert f'"$bundle_arch" = {arch}' in launcher

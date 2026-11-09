import hashlib
import json
import zipfile
from types import SimpleNamespace

import httpx
import pytest

import diagnostics
import updater

EXE = b"MZ nuovo DriverCore"
GOOD = {"version": "9.0.0", "url": "https://example.com/DriverCore.exe",
        "sha256": hashlib.sha256(EXE).hexdigest(), "notes": "Novità"}


def _client(manifest, body=EXE):
    def handler(req):
        if req.url.path.endswith(".json"):
            return httpx.Response(200, text=manifest if isinstance(manifest, str) else json.dumps(manifest))
        return httpx.Response(200, content=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_manifest_validation():
    assert updater.parse_manifest(GOOD)["sha256"] == GOOD["sha256"]
    with pytest.raises(updater.UpdateError):
        updater.parse_manifest(dict(GOOD, url="http://example.com/x.exe"))  # niente http in chiaro
    with pytest.raises(updater.UpdateError):
        updater.parse_manifest(dict(GOOD, sha256="abc"))
    with pytest.raises(updater.UpdateError):
        updater.parse_manifest(dict(GOOD, version="non una versione"))
    with pytest.raises(updater.UpdateError):
        updater.parse_manifest(["lista"])


def test_check_reports_only_newer_versions():
    url = "https://example.com/manifest.json"
    assert updater.check(_client(GOOD), url)["version"] == "9.0.0"
    assert updater.check(_client(dict(GOOD, version=updater.APP_VERSION)), url) is None
    assert updater.check(_client(dict(GOOD, version="0.1")), url) is None
    with pytest.raises(updater.UpdateError):
        updater.check(_client("<html>non json</html>"), url)
    with pytest.raises(updater.UpdateError):
        updater.check(_client(GOOD), "")  # non configurato


def test_download_verifies_hash(tmp_path):
    path = updater.download(updater.parse_manifest(GOOD), _client(GOOD), tmp_path)
    assert path.read_bytes() == EXE
    bad = updater.parse_manifest(dict(GOOD, version="9.0.1"))
    with pytest.raises(updater.UpdateError):
        updater.download(bad, _client(GOOD, body=b"file manomesso"), tmp_path)
    assert not list(tmp_path.glob("*9.0.1*"))  # il file non verificato viene cancellato


def test_github_release_urls():
    import config
    assert config.release_manifest_url("") == ""
    assert (config.release_manifest_url("utente/DriverCore")
            == "https://github.com/utente/DriverCore/releases/latest/download/latest.json")
    url = config.release_asset_url("utente/DriverCore", "1.2.0")
    assert url == "https://github.com/utente/DriverCore/releases/download/v1.2.0/DriverCore.exe"
    assert updater.parse_manifest(dict(GOOD, url=url))["url"] == url


def test_build_manifest_matches_exe(tmp_path, monkeypatch):
    import importlib.util
    import config
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("build", Path(__file__).resolve().parents[1] / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    exe = tmp_path / "DriverCore.exe"
    exe.write_bytes(EXE)
    monkeypatch.setattr(config, "UPDATE_REPO", "utente/DriverCore")
    data = json.loads(build.write_manifest(exe, "Novità").read_text(encoding="utf-8"))
    info = updater.parse_manifest(data)
    assert info["sha256"] == GOOD["sha256"] and info["version"] == config.APP_VERSION
    assert info["url"].endswith(f"/v{config.APP_VERSION}/DriverCore.exe")
    monkeypatch.setattr(config, "UPDATE_REPO", "")
    with pytest.raises(SystemExit):
        build.write_manifest(exe)


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="solo Windows")
def test_swap_runs_after_parent_exits(tmp_path):
    """Lo script parte da un processo che si chiude subito (come DriverCore) e deve comunque scambiare i file."""
    import subprocess
    import sys
    import time
    new, old = tmp_path / "new.exe", tmp_path / "old.exe"
    new.write_bytes(b"NEW")
    old.write_bytes(b"OLD")
    marker = tmp_path / "riavviato.txt"
    ps = updater.SWAP_PS.replace("Start-Process -FilePath $env:DC_OLD", f"'ok' | Out-File -LiteralPath '{marker}'")
    src = str(updater.Path(updater.__file__).parent)
    parent = (f"import sys, os, time; sys.path.insert(0, {src!r}); import updater; "
              f"updater.launch_after_exit({ps!r}, {{'DC_PIDS': str(os.getpid()), 'DC_NEW': {str(new)!r}, "
              f"'DC_OLD': {str(old)!r}}}); f = open({str(old)!r}, 'rb'); time.sleep(1)")  # file in uso, poi esce
    subprocess.run([sys.executable, "-c", parent], check=True, timeout=60)
    for _ in range(100):
        if marker.exists():
            break
        time.sleep(0.2)
    assert old.read_bytes() == b"NEW" and not new.exists() and marker.exists()


def test_due_once_a_day():
    assert updater.due(None)
    assert not updater.due(1000.0, now=1000.0 + 3600)
    assert updater.due(1000.0, now=1000.0 + 25 * 3600)


def test_diagnostics_zip(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "session_activity.log").write_text("riga", encoding="utf-8")
    (logs / "session_activity.log.1").write_text("vecchia", encoding="utf-8")
    (logs / "altro.txt").write_text("no", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text('{"language": "it"}', encoding="utf-8")
    drv = SimpleNamespace(DeviceName="Realtek", DriverProviderName="Realtek", DriverVersion="1.0", InfName="oem1.inf",
                          DeviceClass="NET")
    ms = SimpleNamespace(DeviceName="Disco", DriverProviderName="Microsoft", DriverVersion="10", InfName="disk.inf",
                         DeviceClass="DISKDRIVE")
    wmi = SimpleNamespace(
        select=lambda cls, cols, where="": ([SimpleNamespace(Name=" CPU ")] if cls == "Win32_Processor" else
                                            [SimpleNamespace(Manufacturer="ASUS", Model="X", TotalPhysicalMemory=str(16 * 2**30))]),
        Win32_VideoController=lambda: [SimpleNamespace(Name="RTX", DriverVersion="32", PNPDeviceID="PCI\\X")],
        Win32_PnPSignedDriver=lambda: [drv, ms],
    )
    out = diagnostics.export(tmp_path / "d.zip", wmi, logs, (settings, tmp_path / "manca.json"))
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        info = json.loads(z.read("system.json"))
    assert names == {"system.json", "logs/session_activity.log", "logs/session_activity.log.1", "data/settings.json"}
    assert info["cpu"] == "CPU" and info["ram_gb"] == 16.0 and info["pc"] == "ASUS X"
    assert [d["device"] for d in info["third_party_drivers"]] == ["Realtek"]  # niente driver Microsoft

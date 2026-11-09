import os
import subprocess
import sys

import pytest

import uninstaller

win = pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")


def test_data_paths_only_drivercore_files(tmp_path):
    for name in ("backups", "logs"):
        (tmp_path / name).mkdir()
    (tmp_path / "settings.json").write_text("{}")
    (tmp_path / "src").mkdir()                      # non è di DriverCore: non va toccato
    (tmp_path / "appunti.txt").write_text("mio")
    names = {p.name for p in uninstaller.data_paths(tmp_path)}
    assert names == {"backups", "logs", "settings.json"}


def test_size_of(tmp_path):
    (tmp_path / "b" / "x").mkdir(parents=True)
    (tmp_path / "b" / "x" / "f.inf").write_bytes(b"a" * 1000)
    (tmp_path / "s.json").write_bytes(b"b" * 24)
    assert uninstaller.size_of([tmp_path / "b", tmp_path / "s.json"]) == 1024


def test_size_of_counts_hard_links_once(tmp_path):
    (tmp_path / "b1").mkdir()
    (tmp_path / "b2").mkdir()
    (tmp_path / "b1" / "same.sys").write_bytes(b"x" * 1000)
    os.link(tmp_path / "b1" / "same.sys", tmp_path / "b2" / "same.sys")
    assert uninstaller.size_of([tmp_path / "b1", tmp_path / "b2"]) == 1000


@win
def test_remove_registry_only_drivercore_entries():
    import winreg
    root = r"Software\DriverCoreTest"
    tree = rf"{root}\Classes\drivercore"
    vals = rf"{root}\MuiCache"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{tree}\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "x")
    exe = r"C:\Prove\DriverCore.exe"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, vals) as k:
        winreg.SetValueEx(k, exe + ".FriendlyAppName", 0, winreg.REG_SZ, "DriverCore")
        winreg.SetValueEx(k, r"C:\Altro\Programma.exe.FriendlyAppName", 0, winreg.REG_SZ, "Altro")
    try:
        errors = uninstaller.remove_registry(trees=(tree,), exe_value_keys=(vals, rf"{root}\Manca"), exe=exe)
        assert errors == []
        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, tree)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, vals) as k:
            left = [winreg.EnumValue(k, i)[0] for i in range(winreg.QueryInfoKey(k)[1])]
        assert left == [r"C:\Altro\Programma.exe.FriendlyAppName"]
        assert uninstaller.remove_registry(trees=(tree,), exe_value_keys=(), exe=exe) == []  # già tolte: ok
    finally:
        uninstaller._delete_tree(winreg.HKEY_CURRENT_USER, root)


@win
def test_remove_task_missing_folder_is_not_an_error():
    assert uninstaller.remove_task("\\DriverCoreTestNonEsiste\\") == []


@win
@pytest.mark.parametrize("extra", [True, False])
def test_cleanup_after_exit(tmp_path, extra):
    base = tmp_path / "DriverManager"
    (base / "backups" / "2026").mkdir(parents=True)
    (base / "backups" / "2026" / "oem1.inf").write_text("x")
    (base / "logs").mkdir()
    (base / "settings.json").write_text("{}")
    if extra:
        (base / "src").mkdir()
        (base / "src" / "gui.py").write_text("# codice dell'utente")
    exe = tmp_path / "DriverCore.exe"
    exe.write_bytes(b"MZ")
    # finto DriverCore ancora aperto: tiene il file di log aperto per un attimo
    holder = subprocess.Popen([sys.executable, "-c",
                               f"import time; f = open(r'{base / 'logs' / 'a.log'}', 'w'); time.sleep(1.5)"])
    proc = uninstaller.schedule_cleanup(uninstaller.data_paths(base), str(exe), base, pids=[holder.pid])
    proc.wait(timeout=60)
    holder.wait()
    assert not exe.exists()
    if extra:
        assert sorted(p.name for p in base.iterdir()) == ["src"]  # resta solo ciò che non è di DriverCore
    else:
        assert not base.exists()  # cartella vuota: rimossa

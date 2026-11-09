import driver_history as dh


def _inf(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(text, encoding="utf-8")
    return p


def _catalog_entry(before, after, old_inf="oem40.inf"):
    return dh.build_entry("catalog", "Realtek PCIe GbE", r"PCI\VEN_10EC&DEV_8125\1", "1168.20", "1168.26",
                          old_inf, before, after)


def test_build_entry_tracks_added_removed_and_previous():
    before = {"oem40.inf": "aaa", "oem12.inf": "nv-old"}
    after = {"oem40.inf": "aaa", "oem41.inf": "bbb"}
    e = _catalog_entry(before, after)
    assert e["added"] == {"oem41.inf": "bbb"}
    assert e["removed"] == {"oem12.inf": "nv-old"}
    assert e["previous"] == {"inf": "oem40.inf", "hash": "aaa"}
    # Driver inbox di Windows (es. net.inf): non è un pacchetto di terze parti da ricordare
    assert _catalog_entry(before, after, "net.inf")["previous"] is None


def test_undo_plan_removes_new_package_and_keeps_previous(tmp_path):
    e = _catalog_entry({"oem40.inf": "aaa"}, {"oem40.inf": "aaa", "oem41.inf": "bbb"})
    plan = dh.undo_plan(e, [e], {"oem40.inf": "aaa", "oem41.inf": "bbb"}, tmp_path)
    assert plan["ok"] and plan["remove"] == ["oem41.inf"] and plan["restore"] == [] and not plan["warnings"]


def test_undo_plan_restores_previous_from_backup_by_hash(tmp_path):
    old = _inf(tmp_path / "backup_20261101_100000" / "rt640x64.inf_amd64_x", "rt640x64.inf", "vecchio driver")
    h_old = dh.file_hash(old)
    e = _catalog_entry({"oem40.inf": h_old}, {"oem40.inf": h_old, "oem41.inf": "bbb"})
    # Nel frattempo la pulizia del DriverStore ha tolto il pacchetto precedente
    plan = dh.undo_plan(e, [e], {"oem41.inf": "bbb"}, tmp_path)
    assert plan["ok"] and plan["restore"] == [str(old)] and not plan["warnings"]

    plan = dh.undo_plan(e, [e], {"oem41.inf": "bbb"}, tmp_path / "vuota")
    assert plan["ok"] and "non è più nel DriverStore" in plan["warnings"][0]


def test_undo_plan_refusals():
    e = _catalog_entry({"oem40.inf": "aaa"}, {"oem40.inf": "aaa", "oem41.inf": "bbb"})
    # pacchetto nuovo già sparito
    assert not dh.undo_plan(e, [e], {"oem40.inf": "aaa"})["ok"]
    # aggiornamento successivo della stessa periferica: va annullato prima quello
    later = dict(_catalog_entry({}, {"oem42.inf": "ccc"}), time="2999-01-01T00:00:00", new_ver="1168.30")
    plan = dh.undo_plan(e, [e, later], {"oem40.inf": "aaa", "oem41.inf": "bbb", "oem42.inf": "ccc"})
    assert not plan["ok"] and "1168.30" in plan["reason"]
    # già annullato
    assert not dh.undo_plan(dict(e, status="undone"), [], {"oem41.inf": "bbb"})["ok"]


def test_problem_device_without_driver_warns():
    e = dh.build_entry("catalog", "Controller sconosciuto", "PCI\\X", "", "1.0", None, {}, {"oem50.inf": "n"})
    plan = dh.undo_plan(e, [e], {"oem50.inf": "n"})
    assert plan["ok"] and "driver generico" in plan["warnings"][0]


def test_nvidia_restores_packages_removed_by_installer(tmp_path):
    old = _inf(tmp_path / "backup_20261101_100000" / "nv_dispi.inf_amd64_x", "nv_dispi.inf", "nvidia 610")
    h = dh.file_hash(old)
    e = dh.build_entry("nvidia", "RTX 5070", "PCI\\VEN_10DE", "610.22", "621.14", "oem12.inf",
                       {"oem12.inf": h}, {"oem60.inf": "nv621"})
    plan = dh.undo_plan(e, [e], {"oem60.inf": "nv621"}, tmp_path)
    assert plan["ok"] and plan["remove"] == ["oem60.inf"] and plan["restore"] == [str(old)]
    assert any("pannello" in w for w in plan["warnings"])


def test_history_persistence_and_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "HISTORY_FILE", tmp_path / "h.json")
    e = dh.record_install("catalog", "Realtek", "PCI\\1", "1", "2", "oem40.inf", {"oem40.inf": "a"},
                          {"oem40.inf": "a", "oem41.inf": "b"})
    assert dh.load_history()[0]["id"] == e["id"]
    assert dh.protected_infs() == {"oem40.inf"}
    dh._set_status(e["id"], status="undone")
    assert dh.protected_infs() == set()


def test_backups_needed_for_undo(tmp_path):
    b_old = tmp_path / "backup_20261101_100000"
    b_new = tmp_path / "backup_20261105_100000"
    h = dh.file_hash(_inf(b_old / "nv_dispi.inf_amd64_x", "nv_dispi.inf", "nvidia 610"))
    _inf(b_new / "other.inf_amd64_y", "other.inf", "altro")
    e = dh.build_entry("nvidia", "RTX", "PCI\\1", "610", "621", "oem12.inf", {"oem12.inf": h}, {"oem60.inf": "n"})
    assert dh.backups_needed_for_undo([b_old, b_new], [e], {"oem60.inf": "n"}) == {b_old}
    # Se il pacchetto è ancora nel DriverStore, nessun backup è indispensabile
    assert dh.backups_needed_for_undo([b_old, b_new], [e], {"oem12.inf": h}) == set()

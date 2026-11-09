import json

import ignore_list as il

ITEM = {"name": "Realtek PCIe GbE", "specific": "PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043",
        "generic": "PCI\\VEN_10EC&DEV_8168", "hwid": "PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043",
        "remote_ver": "1168.26", "update_id": "uid-1"}


def test_legacy_format_is_read(tmp_path):
    f = tmp_path / "ignored.json"
    f.write_text(json.dumps(["uid-0", "PCI\\X|1.0"]), encoding="utf-8")
    entries = il.load_entries(f)
    assert len(entries) == 1 and entries[0]["scope"] == "auto"
    assert il.load_ignored_updates(f) == {"uid-0", "PCI\\X|1.0"}
    # aggiungendo una voce il file passa al formato nuovo senza perdere le vecchie chiavi
    il.add_ignored(["k"], name="n", scope="version", path=f)
    assert il.load_ignored_updates(f) == {"uid-0", "PCI\\X|1.0", "k"}
    assert json.loads(f.read_text(encoding="utf-8"))["version"] == 2


def test_ignore_version_and_restore(tmp_path):
    f = tmp_path / "ignored.json"
    e = il.add_ignored(il.keys_for(ITEM, "version"), name=ITEM["name"], version="1168.26", scope="version", path=f)
    ignored = il.load_ignored_updates(f)
    assert il.is_ignored(ignored, ITEM["generic"], "1168.26")
    assert il.is_ignored(ignored, "PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043", "1168.26", "uid-1")
    assert not il.is_ignored(ignored, ITEM["generic"], "1168.30")  # una versione più nuova si propone ancora
    assert il.remove_entry(e["id"], f)
    assert il.load_ignored_updates(f) == set()


def test_ignore_whole_device():
    ignored = set(il.keys_for(ITEM, "device"))
    assert il.is_ignored(ignored, ITEM["generic"], "9999.0")
    assert not il.is_ignored(ignored, "PCI\\VEN_8086&DEV_1234", "1.0")


def test_windows_update_keys():
    wu = dict(ITEM, source="wu", update_id="wu-guid")
    ignored = set(il.keys_for(wu, "version"))
    assert il.is_ignored(ignored, "OTHER", "x", "wu-guid", wu=True)
    assert not il.is_ignored(ignored, "OTHER", "x", "wu-guid", wu=False)

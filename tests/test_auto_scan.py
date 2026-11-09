import auto_scan as a

GPUS = [{"name": "NVIDIA GeForce RTX 5070", "remote": "621.14", "update": True},
        {"name": "Intel Iris Xe", "remote": "32.0.101.9175", "update": False}]
PROBLEMS = [{"name": "Controller sconosciuto", "device_id": "PCI\\X", "code": 28, "problem": "Driver non installato"},
            {"name": "Lettore SD", "device_id": "PCI\\Y", "code": 28, "update_id": "u1", "remote_ver": "10.0.1"}]
UPDATES = [{"name": "Realtek PCIe GbE", "hwid": "PCI\\VEN_10EC&DEV_8125", "remote_ver": "1168.26"}]


def test_summarize_and_dedupe():
    items = a.summarize(GPUS, PROBLEMS, UPDATES)
    texts = [i["text"] for i in items]
    assert texts == ["NVIDIA GeForce RTX 5070 621.14", "Controller sconosciuto: Driver non installato",
                     "Lettore SD: 10.0.1 disponibile", "Realtek PCIe GbE 1168.26"]
    assert len({i["key"] for i in items}) == 4
    assert a.to_notify(items, [items[0]["key"], items[3]["key"]]) == items[1:3]
    # Una versione nuova della stessa periferica è una novità
    newer = a.summarize([], [], [dict(UPDATES[0], remote_ver="1168.30")])
    assert a.to_notify(newer, [items[3]["key"]]) == newer


def test_notification_text_and_xml_escaping():
    items = a.summarize(GPUS, PROBLEMS, UPDATES)
    title, body = a.notification_text(items)
    assert title == "4 novità sui driver" and body.endswith("… e altre 1")
    assert a.notification_text(items[:1])[0] == "1 novità sui driver"
    xml = a.toast_xml("A & B", "<driver>")
    assert "A &amp; B" in xml and "&lt;driver&gt;" in xml and 'launch="drivercore://open"' in xml


def test_frequency_settings_and_mark_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "SETTINGS_FILE", tmp_path / "s.json")
    monkeypatch.setattr(a, "AUTO_SCAN_FILE", tmp_path / "r.json")
    assert a.get_frequency() == "off"
    (tmp_path / "s.json").write_text('{"auto_scan": "weekly"}', encoding="utf-8")
    assert a.get_frequency() == "weekly"
    assert a.set_frequency("hourly")[0] is False
    items = a.summarize(GPUS, [], [])
    a.mark_seen(items)
    assert a.to_notify(items, a.last_result()["notified"]) == []

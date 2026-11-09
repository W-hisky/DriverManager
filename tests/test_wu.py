from datetime import datetime
from types import SimpleNamespace

import ignore_list
import wu_drivers as wu

DRIVERS = [SimpleNamespace(HardWareID="PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15", DriverVersion="1168.20.1",
                           DriverDate="20250101000000.000000-000", InfName="oem40.inf", DeviceID="PCI\\VEN_10EC&DEV_8168\\1"),
           SimpleNamespace(HardWareID="USB\\VID_046D&PID_C52B", DriverVersion="1.0", DriverDate=None,
                           InfName="usb.inf", DeviceID="USB\\X")]


def _update(uid="u1", title="Realtek Semiconductor Corp. - Net - 10.68.815.2023",
            hwid="PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15"):
    return SimpleNamespace(Title=title, DriverHardwareID=hwid, DriverModel="Realtek PCIe GbE Family Controller",
                           DriverProvider="Realtek", DriverVerDate=datetime(2023, 8, 15),
                           Identity=SimpleNamespace(UpdateID=uid))


def test_version_and_installed_match():
    assert wu.version_from_title("Intel - System - 10.1.1.44") == "10.1.1.44"
    assert wu.version_from_title("Driver senza versione") == ""
    assert wu.find_installed("PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15", DRIVERS) is DRIVERS[0]
    assert wu.find_installed("USB\\VID_046D&PID_C52B&REV_1201", DRIVERS) is DRIVERS[1]  # ID più specifico
    assert wu.find_installed("PCI\\VEN_8086&DEV_0001", DRIVERS) is None


def test_to_item_has_catalog_shape():
    item = wu.to_item(_update(), DRIVERS)
    assert item["source"] == "wu" and item["verified"] is True
    assert item["remote_ver"] == "10.68.815.2023" and item["remote_date"] == "2023-08-15"
    assert item["local_ver"] == "1168.20.1" and item["inf_name"] == "oem40.inf"
    assert item["generic"] == "PCI\\VEN_10EC&DEV_8168"
    assert item["specific"] == "PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043"


def test_windows_update_wins_over_catalog():
    w = wu.to_item(_update(), DRIVERS)
    catalog = [{"name": "Realtek PCIe GbE", "generic": "PCI\\VEN_10EC&DEV_8168", "hwid": "PCI\\VEN_10EC&DEV_8168"},
               {"name": "Altra periferica", "generic": "PCI\\VEN_8086&DEV_0001", "hwid": "PCI\\VEN_8086&DEV_0001"}]
    merged = wu.merge(catalog, [w])
    assert [m["name"] for m in merged] == ["Altra periferica", "Realtek PCIe GbE Family Controller"]


def test_search_skips_ignored(monkeypatch):
    updates = [_update("u1"), _update("u2", "Logitech - USB - 2.0", "USB\\VID_046D&PID_C52B")]
    result = SimpleNamespace(Updates=SimpleNamespace(Count=2, Item=lambda i: updates[i]))
    searcher = SimpleNamespace(Search=lambda q: result)
    monkeypatch.setattr(wu, "_session", lambda: SimpleNamespace(CreateUpdateSearcher=lambda: searcher))
    items, ok = wu.search_drivers(DRIVERS)
    assert ok and len(items) == 2
    logitech = items[1]
    ignored = set(ignore_list.keys_for(logitech, "version"))
    items, _ = wu.search_drivers(DRIVERS, frozenset(ignored))
    assert [i["update_id"] for i in items] == ["u1"]
    ignored = set(ignore_list.keys_for(items[0], "device"))
    assert [i["update_id"] for i in wu.search_drivers(DRIVERS, frozenset(ignored))[0]] == ["u2"]


def test_search_failure_is_reported(monkeypatch):
    def broken():
        raise OSError("servizio disattivato")
    monkeypatch.setattr(wu, "_session", broken)
    assert wu.search_drivers(DRIVERS) == ([], False)

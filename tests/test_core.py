from datetime import datetime

import httpx

import deep_catalog as dc
import driver_cleanup as cl
import driver_installer as di
import driver_scanner as ds


def test_wmi_to_nvidia_version():
    assert ds.wmi_to_nvidia_version("32.0.16.2101") == "621.01"
    assert ds.wmi_to_nvidia_version("32.0.15.6094") == "560.94"


def test_extract_generic_hwid():
    raw = r"PCI\VEN_10EC&DEV_8168&SUBSYS_816810EC&REV_15"
    assert dc.extract_generic_hwid(raw) == r"PCI\VEN_10EC&DEV_8168"
    assert dc.extract_generic_hwid(r"USB\VID_046D&PID_C52B&REV_1201") == r"USB\VID_046D&PID_C52B"
    assert dc.extract_generic_hwid("ROOT\\FOO") is None
    assert dc.extract_generic_hwid("") is None


def test_dates():
    assert dc.parse_catalog_date("10/02/2026") == datetime(2026, 10, 2)
    assert dc.parse_catalog_date("garbage") == datetime(2000, 1, 1)
    assert dc.parse_wmi_date("20240105000000.000000-000") == datetime(2024, 1, 5)
    assert dc.parse_wmi_date(None) == datetime(2000, 1, 1)


# --- Catalog (risposte HTTP simulate) ---------------------------------------
HTML = """<table id="ctl00_catalogBody_updateMatches"><tr><th>h</th></tr>
<tr><td></td><td>Intel LAN</td><td>Windows 11</td><td>Drivers</td><td>10/02/2026</td><td>2.5.1.0</td><td>1MB</td><td><input id="abc-123"></td></tr>
<tr><td></td><td>Old</td><td>Windows 10</td><td>Drivers</td><td>01/02/2020</td><td>1.0.0.0</td><td>1MB</td><td><input id="old"></td></tr></table>"""


def _client():
    def handler(req):
        q = req.url.params["q"]
        if q == "FOUND":
            return httpx.Response(200, text=HTML)
        if q == "NONE":
            return httpx.Response(200, text="We did not find any results for NONE")
        if q == "BUSY":
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text="<html>captcha</html>")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_catalog_found_picks_newer_only():
    res = dc.query_ms_catalog(_client(), "FOUND", "2.0.0.0", datetime(2025, 1, 1))
    assert res.ok and res.relevant
    assert res.candidate["update_id"] == "abc-123" and res.candidate["remote_ver"] == "2.5.1.0"


def test_catalog_already_up_to_date():
    res = dc.query_ms_catalog(_client(), "FOUND", "9.0.0.0", datetime(2025, 1, 1))
    assert res.ok and res.relevant and res.candidate is None


def test_catalog_no_results_is_ok_but_errors_are_not():
    assert dc.query_ms_catalog(_client(), "NONE", "1.0", datetime(2025, 1, 1)) == (None, True, False)
    assert dc.query_ms_catalog(_client(), "BUSY", "1.0", datetime(2025, 1, 1)) == (None, False, False)
    assert dc.query_ms_catalog(_client(), "OTHER", "1.0", datetime(2025, 1, 1)) == (None, False, False)


def _row(title, products, date, ver, uid):
    return (f"<tr><td></td><td>{title}</td><td>{products}</td><td>Drivers</td><td>{date}</td>"
            f"<td>{ver}</td><td>1MB</td><td><input id=\"{uid}\"></td></tr>")


def _table_client(rows_by_query):
    def handler(req):
        rows = rows_by_query.get(req.url.params["q"])
        if rows is None:
            return httpx.Response(200, text="We did not find any results")
        return httpx.Response(200, text='<table id="ctl00_catalogBody_updateMatches"><tr><th>h</th></tr>'
                                        + "".join(rows) + "</table>")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_catalog_skips_other_architectures_and_vendors():
    rows = [
        _row("Realtek - Net - 10.70 ARM64", "Windows 11", "10/02/2026", "10.70.0.0", "arm"),
        _row("Dell - Net - 99.0", "Windows 11", "10/02/2026", "99.0.0.0", "dell"),
        _row("Realtek Semiconductor Corp. - Net - 10.68", "Windows 11", "10/02/2026", "10.68.0.0", "good"),
    ]
    res = dc.query_ms_catalog(_table_client({"Q": rows}), "Q", "10.0.0.0", datetime(2025, 1, 1), "Realtek")
    assert res.candidate["update_id"] == "good"


def test_catalog_only_foreign_packages_is_not_relevant():
    rows = [_row("Dell - Net - 99.0", "Windows 11", "10/02/2026", "99.0.0.0", "dell")]
    res = dc.query_ms_catalog(_table_client({"Q": rows}), "Q", "1.0", datetime(2025, 1, 1), "Realtek")
    assert res == (None, True, False)


def test_architecture_and_provider_helpers():
    assert dc.is_foreign_architecture("Intel - System - x86")
    assert not dc.is_foreign_architecture("Intel - System - x86, x64")
    assert not dc.is_foreign_architecture("Intel - System - 10.1")
    assert dc.provider_matches("Advanced Micro Devices, Inc.", "AMD - System - 5.0")
    assert dc.provider_matches("Intel", "Intel Corporation - Net")
    assert not dc.provider_matches("Realtek Semiconductor Corp.", "Intel - Net")
    assert dc.provider_matches("", "qualsiasi")


def test_ignored_update_is_skipped_without_falling_back_to_generic():
    rows = [_row("Realtek - Net", "Windows 11", "10/02/2026", "2.0.0.0", "bad")]
    generic = [_row("Realtek - Net", "Windows 11", "10/02/2026", "3.0.0.0", "generic")]
    res, used = dc.check_device(_table_client({"SPEC": rows, "GEN": generic}), _info("SPEC", "GEN"), {"bad"})
    assert used == "SPEC" and res.ok and res.relevant and res.candidate is None


def test_ignored_version_hides_all_catalog_ids_of_same_driver():
    # Il Catalog pubblica lo stesso driver con un ID per ogni versione di Windows
    rows = [_row("Realtek - Net", "Windows 11", "10/02/2026", "2.0.0.0", f"id{i}") for i in range(5)]
    ignored = {"id0", dc.ignore_key("spec", "2.0.0.0")}
    res, used = dc.check_device(_table_client({"SPEC": rows}), _info("SPEC", "GEN"), ignored)
    assert used == "SPEC" and res.candidate is None


def test_ignored_updates_roundtrip(tmp_path, monkeypatch):
    import ignore_list
    monkeypatch.setattr(ignore_list, "IGNORED_UPDATES_FILE", tmp_path / "ignored.json")
    assert dc.load_ignored_updates() == set()
    dc.add_ignored_update("a")
    dc.add_ignored_update("b")
    assert dc.load_ignored_updates() == {"a", "b"}


def test_published_driver_names():
    out = ("Aggiunta del pacchetto driver in corso: 0\\rt68cx21x64.inf\n"
           "Pacchetto driver aggiunto. Nome pubblicato: oem2.inf\nNome pubblicato: OEM2.inf")
    assert dc.published_driver_names(out) == ["oem2.inf"]


# --- Periferiche senza driver o in errore ------------------------------------
class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeWmi:
    def __init__(self, entities, drivers=()):
        self._entities, self._drivers = entities, drivers

    def Win32_PnPEntity(self):
        return self._entities

    def Win32_PnPSignedDriver(self):
        return self._drivers


def test_catalog_queries():
    ids = [r"PCI\VEN_8086&DEV_A0E8&SUBSYS_86941043&REV_20", r"PCI\VEN_8086&DEV_A0E8&SUBSYS_86941043",
           r"PCI\VEN_8086&DEV_A0E8&REV_20", r"PCI\VEN_8086&DEV_A0E8"]
    assert dc.catalog_queries(ids) == [r"PCI\VEN_8086&DEV_A0E8&SUBSYS_86941043", r"PCI\VEN_8086&DEV_A0E8"]
    assert dc.catalog_queries([r"ACPI\VEN_INT&DEV_34A8", r"ACPI\INT34A8"]) == [r"ACPI\VEN_INT&DEV_34A8", r"ACPI\INT34A8"]
    assert dc.catalog_queries([r"HID\VID_046D&PID_C52B&REV_1201"]) == [r"HID\VID_046D&PID_C52B"]
    assert dc.catalog_queries([r"ROOT\LEGACY_X", r"SWD\MSRRAS\X"]) == []


def test_collect_problem_devices():
    wmi_fake = _FakeWmi(
        entities=[
            _Obj(Name="Controller SM Bus", DeviceID=r"PCI\VEN_8086&DEV_A0A3\3&1", ConfigManagerErrorCode=28, Present=True,
                 HardwareID=(r"PCI\VEN_8086&DEV_A0A3&SUBSYS_86941043&REV_20",)),
            _Obj(Name="Wi-Fi", DeviceID="PCI\\W\\1", ConfigManagerErrorCode=43, Present=True,
                 HardwareID=(r"PCI\VEN_8086&DEV_2723&SUBSYS_00848086",)),
            _Obj(Name="Disattivato", DeviceID="X\\1", ConfigManagerErrorCode=22, Present=True, HardwareID=("X",)),
            _Obj(Name="Scollegato", DeviceID="X\\2", ConfigManagerErrorCode=10, Present=False, HardwareID=("X",)),
            _Obj(Name="OK", DeviceID="X\\3", ConfigManagerErrorCode=0, Present=True, HardwareID=("X",)),
            _Obj(Name="NVIDIA GeForce RTX 5070", DeviceID="PCI\\N\\1", ConfigManagerErrorCode=43, Present=True,
                 HardwareID=(r"PCI\VEN_10DE&DEV_2F04",)),
        ],
        drivers=[_Obj(DeviceID="PCI\\W\\1", DriverVersion="22.1.0.3", DriverDate="20240105000000.000000-000",
                      DriverProviderName="Intel")],
    )
    devs = {d["name"]: d for d in dc.collect_problem_devices(wmi_fake)}
    assert set(devs) == {"Controller SM Bus", "Wi-Fi", "NVIDIA GeForce RTX 5070"}

    smbus = devs["Controller SM Bus"]
    assert smbus["problem"] == "Driver non installato" and not smbus["has_driver"] and smbus["local_ver"] == "0"
    assert smbus["queries"] == [r"PCI\VEN_8086&DEV_A0A3&SUBSYS_86941043", r"PCI\VEN_8086&DEV_A0A3"]

    wifi = devs["Wi-Fi"]  # driver presente: si propone solo una versione più recente, dello stesso fornitore
    assert wifi["has_driver"] and wifi["local_ver"] == "22.1.0.3" and wifi["provider"] == "Intel"

    assert devs["NVIDIA GeForce RTX 5070"]["queries"] == []  # la GPU passa dall'API NVIDIA


def test_check_device_uses_query_list_and_handles_none():
    rows = [_row("Intel - System", "Windows 11", "10/02/2026", "10.1.0.0", "smbus")]
    info = dict(queries=["A", "B"], local_ver="0", local_date=datetime(2000, 1, 1), provider="")
    res, used = dc.check_device(_table_client({"B": rows}), info)
    assert used == "B" and res.candidate["update_id"] == "smbus"
    assert dc.check_device(_table_client({}), dict(info, queries=[])) == ((None, True, False), "")


def test_extract_specific_hwid():
    raw = r"PCI\VEN_10EC&DEV_8168&SUBSYS_816810EC&REV_15"
    assert dc.extract_specific_hwid(raw) == r"PCI\VEN_10EC&DEV_8168&SUBSYS_816810EC"
    assert dc.extract_specific_hwid(r"USB\VID_046D&PID_C52B&REV_1201") is None


def _info(specific, generic):
    return dict(specific=specific, generic=generic, local_ver="1.0", local_date=datetime(2025, 1, 1), provider="Realtek")


def test_check_device_prefers_subsys_and_never_falls_back_when_known():
    newer = [_row("Realtek - Net", "Windows 11", "10/02/2026", "2.0.0.0", "generic")]
    same = [_row("Realtek - Net", "Windows 11", "10/02/2026", "1.0.0.0", "oem")]
    client = _table_client({"SPEC": same, "GEN": newer})
    res, used = dc.check_device(client, _info("SPEC", "GEN"))
    assert used == "SPEC" and res.candidate is None   # variante OEM nota: niente driver generico


def test_check_device_falls_back_to_generic_when_subsys_unknown():
    newer = [_row("Realtek - Net", "Windows 11", "10/02/2026", "2.0.0.0", "generic")]
    res, used = dc.check_device(_table_client({"GEN": newer}), _info("SPEC", "GEN"))
    assert used == "GEN" and res.candidate["update_id"] == "generic"


# --- Pulizia DriverStore -----------------------------------------------------
def _pkg(driver, orig, ver, date, provider="Intel", cls="Net", boot=False, inbox=False):
    return dict(Driver=driver, OriginalFileName=f"C:\\Windows\\System32\\DriverStore\\FileRepository\\{orig}\\{orig}",
                ProviderName=provider, ClassName=cls, Version=ver, Date=date, BootCritical=boot, Inbox=inbox)


def test_select_obsolete():
    pk = [
        _pkg("oem1.inf", "e1.inf", "12.9.0.0", "2020-01-01"),
        _pkg("oem7.inf", "e1.inf", "12.10.0.0", "2022-01-01"),
        _pkg("oem3.inf", "e1.inf", "12.8.0.0", "2019-01-01"),   # in uso
        _pkg("oem2.inf", "nv.inf", "31.0.101.9", "2024-01-01", "NVIDIA", "Display"),  # unico
        _pkg("oem4.inf", "a.inf", "1.0", "2020-01-01", boot=True),
        _pkg("oem5.inf", "a.inf", "2.0", "2021-01-01", boot=True),
        _pkg("oem6.inf", "x.inf", "1.0", "2020-01-01", inbox=True),
        _pkg("oem8.inf", "x.inf", "2.0", "2021-01-01", inbox=True),
    ]
    names = [o["driver"] for o in cl.select_obsolete(pk, {"oem3.inf"})]
    assert names == ["oem1.inf"]


def test_select_obsolete_keeps_newest_not_highest_oem_number():
    pk = [_pkg("oem9.inf", "e.inf", "1.0", "2020-01-01"), _pkg("oem2.inf", "e.inf", "2.0", "2024-01-01")]
    assert [o["driver"] for o in cl.select_obsolete(pk, set())] == ["oem9.inf"]


# --- Installer: firma e backup -----------------------------------------------
def test_subject_organization():
    subj = "CN=NVIDIA Corporation, OU=2008B9F, O=NVIDIA Corporation, L=Santa Clara, S=California, C=US"
    assert di.subject_organization(subj) == "NVIDIA Corporation"
    assert di.subject_organization('CN=x, O="Evil, NVIDIA Corporation", C=US') == "Evil, NVIDIA Corporation"
    assert di.subject_organization("CN=NVIDIA Corporation") is None


def test_backups_to_prune(tmp_path):
    for name in ("backup_20260101_100000", "backup_20260301_100000", "backup_20260201_100000", "altro"):
        (tmp_path / name).mkdir()
    backups = di.list_backups(tmp_path)
    assert [b.name for b in backups] == ["backup_20260101_100000", "backup_20260201_100000", "backup_20260301_100000"]
    assert [b.name for b in di.backups_to_prune(backups, 2)] == ["backup_20260101_100000"]
    assert di.backups_to_prune(backups, 5) == []


def test_driverstore_fingerprint_changes_with_drivers(tmp_path):
    (tmp_path / "oem1.inf").write_text("a")
    (tmp_path / "netrtl.inf").write_text("inbox")   # inbox: ignorato
    first = di.driverstore_fingerprint(tmp_path)
    assert len(first) == 1 and first == di.driverstore_fingerprint(tmp_path)
    (tmp_path / "oem2.inf").write_text("nuovo")
    assert di.driverstore_fingerprint(tmp_path) != first

from datetime import date, datetime

import deep_catalog as dc
import inf_rank as ir

OS = ir.OsInfo(arch="amd64", major=10, minor=0, product_type=1, build=26100)

DEV_HW = [r"PCI\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15", r"PCI\VEN_10EC&DEV_8168&SUBSYS_86771043"]
DEV_COMP = [r"PCI\VEN_10EC&DEV_8168&REV_15", r"PCI\VEN_10EC&DEV_8168", r"PCI\VEN_10EC"]


def inf(models: str, manufacturer: str = "%V%=Vendor, NTamd64.10.0", extra: str = "", driver_ver="10/03/2025,1.0.0.0"):
    return ir.Inf(f"""
[Version]
Signature="$WINDOWS NT$"
DriverVer = {driver_ver} ; commento
[Manufacturer]
{manufacturer}
{models}
{extra}
[Strings]
V = "Vendor"
DESC = "Scheda di rete"
""", "test.inf")


def test_parse_driver_ver_is_month_day_year():
    assert ir.parse_driver_ver("10/03/2025,10.079.50.1003") == (date(2025, 10, 3), "10.79.50.1003")
    assert ir.parse_driver_ver("07/10/2025, 1168.026.50.2025") == (date(2025, 7, 10), "1168.26.50.2025")
    assert ir.parse_driver_ver(None) == (None, "")


def test_identifier_scores_follow_microsoft_ranges():
    exact = inf("[Vendor.NTamd64.10.0]\n%DESC% = Inst, PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15")
    assert ir.best_match(exact, DEV_HW, DEV_COMP, OS).rank == 0xFF0000          # HW = HW, posizione 0
    second = inf("[Vendor.NTamd64.10.0]\n%DESC% = Inst, PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043")
    assert ir.best_match(second, DEV_HW, DEV_COMP, OS).rank == 0xFF0001         # HW = HW, posizione 1
    via_comp = inf("[Vendor.NTamd64.10.0]\n%DESC% = Inst, PCI\\VEN_10EC&DEV_8168")
    assert ir.best_match(via_comp, DEV_HW, DEV_COMP, OS).rank == 0xFF2001       # compatibile della periferica
    inf_comp = inf("[Vendor.NTamd64.10.0]\n%DESC% = Inst, PCI\\VEN_FFFF&DEV_0000, PCI\\VEN_10EC")
    assert ir.best_match(inf_comp, DEV_HW, DEV_COMP, OS).rank == 0xFF3002       # comp = comp (j=2, k=0)
    other = inf("[Vendor.NTamd64.10.0]\n%DESC% = Inst, PCI\\VEN_8086&DEV_1234")
    assert ir.best_match(other, DEV_HW, DEV_COMP, OS) is None


def test_feature_score_from_ddinstall_section():
    text = "[Vendor.NTamd64.10.0]\n%DESC% = Inst, PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15"
    scored = inf(text, extra="[Inst.NTamd64]\nFeatureScore = 0x80\n")
    assert ir.best_match(scored, DEV_HW, DEV_COMP, OS).rank == 0x800000
    commented = inf(text, extra="[Inst.NT]\n;FeatureScore = 0x10\n")
    assert ir.best_match(commented, DEV_HW, DEV_COMP, OS).rank == 0xFF0000


def test_models_decoration_choice():
    models = ("[Vendor.NTamd64]\n%DESC% = Old, PCI\\VEN_10EC&DEV_8168\n"
              "[Vendor.NTamd64.10.0...22000]\n%DESC% = New, PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15\n"
              "[Vendor.NTarm64]\n%DESC% = Arm, PCI\\VEN_10EC&DEV_8168&SUBSYS_86771043&REV_15")
    f = inf(models, manufacturer="%V%=Vendor, NTamd64, NTamd64.10.0...22000, NTarm64")
    assert ir.models_sections(f, OS) == ["Vendor.NTamd64.10.0...22000"]
    assert ir.best_match(f, DEV_HW, DEV_COMP, OS).install == "New"
    old_os = ir.OsInfo(build=19045)  # Windows 10: la sezione per build >= 22000 non vale
    assert ir.models_sections(f, old_os) == ["Vendor.NTamd64"]
    plain = inf("[Vendor]\n%DESC% = X, PCI\\VEN_10EC&DEV_8168", manufacturer="%V%=Vendor")
    assert ir.models_sections(plain, OS) == []  # su x64 serve la decorazione NTamd64


def test_judge_realtek_case_same_rank_older_date_is_rejected():
    m = ir.Match(0xFF0000, "X", "Inst", "a.inf")
    ok, reason = ir.judge((m, date(2025, 7, 10), "1168.26.50.2025"), (m, date(2025, 10, 3), "10.79.50.1003"))
    assert not ok and "data più recente" in reason
    assert ir.judge((m, date(2025, 11, 1), "10.80"), (m, date(2025, 10, 3), "10.79"))[0]
    assert ir.judge((m, date(2025, 10, 3), "10.80"), (m, date(2025, 10, 3), "10.79"))[0]


def test_judge_rank_wins_over_date():
    better, worse = ir.Match(0xFF0000, "A", "I", "a"), ir.Match(0xFF2001, "B", "I", "b")
    assert not ir.judge((worse, date(2026, 1, 1), "9"), (better, date(2020, 1, 1), "1"))[0]
    assert ir.judge((better, date(2020, 1, 1), "1"), (worse, date(2026, 1, 1), "9"))[0]
    assert ir.judge((better, None, ""), None)[0]           # nessun driver installato
    assert not ir.judge(None, None)[0]                     # pacchetto senza la periferica


def test_inf_load_utf16(tmp_path):
    p = tmp_path / "u.inf"
    p.write_bytes("[Version]\nDriverVer=01/02/2024,1.2.3.4\n".encode("utf-16"))
    assert ir.inf_driver_ver(p) == (date(2024, 1, 2), "1.2.3.4")


def test_verify_and_refine_tries_alternative_then_gives_up(monkeypatch):
    calls = []

    def fake_verify(client, item, hwids, compids):
        calls.append(item["update_id"])
        return ("ok", "Data più recente.") if item["update_id"] == "good" else ("no", "Windows terrà il driver installato.")

    alternatives = iter([dc.CatalogResult({"update_id": "good", "remote_ver": "2.0", "remote_date": "2026-01-01",
                                           "title": "t"}, True, True)])
    monkeypatch.setattr(dc, "verify_candidate", fake_verify)
    monkeypatch.setattr(dc, "check_device", lambda c, i, ig: (next(alternatives, dc.CatalogResult(None, True, True)), "Q"))
    monkeypatch.setattr(dc, "cleanup_package_cache", lambda: None)

    item = dict(name="LAN", update_id="bad", remote_ver="1.5", remote_date="2025-01-01", device_id="D",
                local_ver="1.0", local_date=datetime(2024, 1, 1), provider="", queries=["Q"])
    dc.verify_and_refine(None, [item], {"D": (["H"], [])}, frozenset())
    assert calls == ["bad", "good"] and item["update_id"] == "good" and item["verified"]

    lonely = dict(item, update_id="bad", remote_ver="1.5")
    lonely.pop("verified")
    dc.verify_and_refine(None, [lonely], {"D": (["H"], [])}, frozenset())
    assert "update_id" not in lonely and "terrà" in lonely["rejected_reason"]

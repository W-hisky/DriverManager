import httpx

import gpu_check as g

SERIES_XML = """<LookupValueSearch><LookupValues>
<LookupValue RequiresProduct="True" ParentID="1"><Name>GeForce RTX 50 Series (Notebooks)</Name><Value>133</Value></LookupValue>
<LookupValue RequiresProduct="True" ParentID="1"><Name>GeForce RTX 50 Series</Name><Value>131</Value></LookupValue>
<LookupValue RequiresProduct="True" ParentID="1"><Name>GeForce RTX 40 Series (Notebooks)</Name><Value>129</Value></LookupValue>
<LookupValue RequiresProduct="True" ParentID="1"><Name>GeForce RTX 40 Series</Name><Value>127</Value></LookupValue>
<LookupValue RequiresProduct="True" ParentID="1"><Name>GeForce 16 Series</Name><Value>112</Value></LookupValue>
<LookupValue RequiresProduct="True" ParentID="1"><Name>GeForce 10 Series</Name><Value>101</Value></LookupValue>
<LookupValue RequiresProduct="True" ParentID="11"><Name>NVIDIA RTX Series</Name><Value>122</Value></LookupValue>
</LookupValues></LookupValueSearch>"""

PRODUCTS = {
    "131": [("NVIDIA GeForce RTX 5070", "1066"), ("NVIDIA GeForce RTX 5090", "1068")],
    "129": [("GeForce RTX 4060 Laptop GPU", "1007")],
    "101": [("NVIDIA GeForce GTX 1080 Ti", "845")],
}


def _products_xml(psid):
    items = "".join(f'<LookupValue ParentID="{psid}"><Name>{n}</Name><Value>{v}</Value></LookupValue>'
                    for n, v in PRODUCTS.get(psid, []))
    return f"<LookupValueSearch><LookupValues>{items}</LookupValues></LookupValueSearch>"


def _nv_client(requested):
    def handler(req):
        if "lookupValueSearch" in str(req.url):
            if req.url.params["TypeID"] == "2":
                return httpx.Response(200, text=SERIES_XML)
            requested.append(req.url.params["ParentID"])
            return httpx.Response(200, text=_products_xml(req.url.params["ParentID"]))
        version = "582.78" if req.url.params["psid"] == "101" else "621.14"
        return httpx.Response(200, json={"IDS": [{"downloadInfo": {
            "Version": version, "ReleaseDateTime": "2026%20novembre%204", "DownloadURL": f"https://x/{version}.exe",
            "Name": "GeForce%20Game%20Ready%20Driver"}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


class _Gpu:
    def __init__(self, name, pnp, ver):
        self.Name, self.PNPDeviceID, self.DriverVersion = name, pnp, ver


def test_pure_helpers():
    assert g.vendor_of(r"PCI\VEN_10DE&DEV_2F04&SUBSYS_1") == "nvidia"
    assert g.vendor_of(r"PCI\VEN_1002&DEV_7550") == "amd"
    assert g.vendor_of(r"ROOT\DISPLAY\0000") == "other"
    assert g.normalize_name("NVIDIA GeForce RTX 5070") == g.normalize_name("GeForce RTX 5070")
    assert g.normalize_name("Intel(R) Arc(TM) A770 Graphics") == "intel arc a770 graphics"
    assert g.nv_date_to_iso("2026 novembre 4") == "2026-11-04"
    assert g.us_date_to_iso("11/4/2026") == "2026-11-04"
    assert g.wmi_to_nvidia_version("32.0.16.2114") == "621.14"


def test_nvidia_series_order_prefers_matching_generation_and_form_factor():
    series = g.parse_lookup_values(SERIES_XML)
    assert g.nvidia_series_order("NVIDIA GeForce RTX 4060 Laptop GPU", series)[0] == "129"
    assert g.nvidia_series_order("NVIDIA GeForce RTX 5070", series)[0] == "131"
    assert g.nvidia_series_order("NVIDIA GeForce GTX 1660 SUPER", series)[0] == "112"
    assert g.nvidia_series_order("NVIDIA GeForce GTX 1080 Ti", series)[0] == "101"
    assert g.nvidia_series_order("NVIDIA GeForce RTX 5070", series)[-1] == "122"  # non GeForce in fondo


def test_check_gpu_nvidia_finds_model_and_legacy_branch():
    requested = []
    r = g.check_gpu(_nv_client(requested), _Gpu("NVIDIA GeForce RTX 5070", r"PCI\VEN_10DE&DEV_2F04", "32.0.16.2114"))
    assert (r["remote"], r["update"], r["can_install"], r["date"]) == ("621.14", False, True, "2026-11-04")
    assert requested[0] == "131"  # la serie giusta è la prima interrogata
    old = g.check_gpu(_nv_client([]), _Gpu("NVIDIA GeForce GTX 1080 Ti", r"PCI\VEN_10DE&DEV_1B06", "32.0.15.7270"))
    assert old["remote"] == "582.78" and old["note"] == "GeForce 10 Series"


def test_check_gpu_nvidia_unknown_model():
    r = g.check_gpu(_nv_client([]), _Gpu("NVIDIA Modello Inesistente", r"PCI\VEN_10DE&DEV_0000", "32.0.15.1000"))
    assert r["error"] and r["update"] is None and not r["can_install"]


INTEL_HTML = ('<meta name="DownloadVersion" content="32.0.101.9175 WHQL Certified"/>'
              '<meta name="lastModifieddate" content="11/04/2026 00:00:00"/>'
              '<a href="https://downloadmirror.intel.com/932449/gfx_win_101.9175.exe">x</a>')

AMD_HTML = ("<p>Revision Number</p><p>Adrenalin 26.10.2 WHQL (Optional)</p><p>File Size 979 MB</p>"
            "<p>Release Date</p><p>2026-10-30</p>"
            "<p>Revision Number</p><p>Adrenalin 26.10.1 WHQL (Recommended)</p><p>File Size 887 MB</p>"
            "<p>Release Date</p><p>2026-10-20</p>")


def _page_client():
    def handler(req):
        return httpx.Response(200, text=INTEL_HTML if "intel.com" in str(req.url) else AMD_HTML)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_intel_and_amd_pages():
    assert g.parse_intel_page(INTEL_HTML) == {"version": "32.0.101.9175", "date": "2026-11-04",
                                              "url": "https://downloadmirror.intel.com/932449/gfx_win_101.9175.exe"}
    assert g.parse_amd_page(AMD_HTML) == {"optional": {"version": "26.10.2", "date": "2026-10-30"},
                                          "recommended": {"version": "26.10.1", "date": "2026-10-20"}}

    arc = g.check_gpu(_page_client(), _Gpu("Intel(R) Arc(TM) A770 Graphics", r"PCI\VEN_8086&DEV_56A0", "32.0.101.6881"))
    assert arc["remote"] == "32.0.101.9175" and arc["update"] is True
    uhd630 = g.check_gpu(_page_client(), _Gpu("Intel(R) UHD Graphics 630", r"PCI\VEN_8086&DEV_3E92", "31.0.101.2130"))
    assert uhd630["remote"] is None and "generazione precedente" in uhd630["note"]

    rx = g.check_gpu(_page_client(), _Gpu("AMD Radeon RX 7800 XT", r"PCI\VEN_1002&DEV_747E", "32.0.21025.10016"))
    assert rx["remote"] == "26.10.1" and rx["update"] is None and "26.10.2" in rx["note"]  # registro assente nei test
    polaris = g.check_gpu(_page_client(), _Gpu("Radeon RX 580 Series", r"PCI\VEN_1002&DEV_67DF", "31.0.21921.1000"))
    assert polaris["remote"] is None and "legacy" in polaris["note"]


def test_basic_display_adapter_means_missing_vendor_driver():
    r = g.check_gpu(_page_client(), _Gpu("Microsoft Basic Display Adapter", r"PCI\VEN_10DE&DEV_2F04", "10.0.26100.1"))
    assert r["update"] is True and "non è installato" in r["note"] and r["page"]

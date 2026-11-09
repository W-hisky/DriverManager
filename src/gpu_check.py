"""Controllo dei driver delle schede video dalle fonti ufficiali dei produttori.

- NVIDIA: API pubblica del sito NVIDIA. Serie e modello (psid/pfid) si ricavano dal nome della GPU,
  così funziona per ogni GeForce/RTX, desktop e notebook. Installazione automatica (driver_installer).
- Intel: pagina ufficiale del driver Arc / Iris Xe (versione nei meta tag). Solo verifica + link.
- AMD: pagina ufficiale di un modello attuale; Adrenalin è unico per Radeon RX 5000 e successive.
  Versione installata dal registro. Solo verifica + link.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import unquote

import httpx
from packaging import version

from i18n import LANG, tr

NV_PAGE = "https://www.nvidia.com/it-it/drivers/" if LANG == "it" else "https://www.nvidia.com/en-us/drivers/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
VENDORS = {"10DE": "nvidia", "1002": "amd", "8086": "intel"}

NV_LOOKUP = "https://www.nvidia.com/Download/API/lookupValueSearch.aspx"
NV_DRIVER = ("https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php"
             "?func=DriverManualLookup&psid={psid}&pfid={pfid}&osID=57&languageCode=1040&beta=0&isWHQL=1"
             "&dltype=-1&dch=1&upCRD=0&sort1=0&numberOfResults=1")
INTEL_PAGE = "https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html"
AMD_PAGE = ("https://www.amd.com/en/support/downloads/drivers.html/graphics/radeon-rx/"
            "radeon-rx-9000-series/amd-radeon-rx-9070-xt.html")
AMD_SUPPORT = "https://www.amd.com/en/support/download/drivers.html"

MESI_IT = {m: i for i, m in enumerate(("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                       "agosto", "settembre", "ottobre", "novembre", "dicembre"), 1)}


# --- Utilità pure ------------------------------------------------------------------
def vendor_of(pnp_id: str | None) -> str:
    m = re.search(r"VEN_([0-9A-F]{4})", pnp_id or "", re.IGNORECASE)
    return VENDORS.get(m.group(1).upper(), "other") if m else "other"


def normalize_name(name: str) -> str:
    n = re.sub(r"\((r|tm)\)|®|™", "", (name or "").lower())
    n = re.sub(r"^nvidia\s+", "", n.strip())
    return re.sub(r"\s+", " ", n).strip()


def wmi_to_nvidia_version(wmi_ver: str) -> str:
    """Versione WMI (es. 32.0.16.2101) -> formato NVIDIA (es. 621.01)."""
    digits = (wmi_ver or "").replace(".", "")[-5:]
    return f"{digits[:3]}.{digits[3:]}"


def nv_date_to_iso(raw: str) -> str:
    """'2026 novembre 4' (API NVIDIA in italiano) -> '2026-11-04'."""
    m = re.match(r"(\d{4})\s+(\w+)\s+(\d{1,2})", raw or "")
    if m and m.group(2).lower() in MESI_IT:
        return date(int(m.group(1)), MESI_IT[m.group(2).lower()], int(m.group(3))).isoformat()
    return raw or ""


def us_date_to_iso(raw: str) -> str:
    """'11/4/2026' -> '2026-11-04'."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", raw or "")
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat() if m else (raw or "")


def is_newer(remote: str, local: str) -> bool | None:
    try:
        return version.parse(remote) > version.parse(local)
    except (version.InvalidVersion, TypeError):
        return None


def parse_lookup_values(xml: str) -> list[tuple[str, str, str]]:
    """(nome, valore, parent) dalla risposta XML di lookupValueSearch."""
    out = []
    for m in re.finditer(r"<LookupValue\b([^>]*)>\s*<Name>([^<]+)</Name>\s*<Value>([^<]+)</Value>", xml):
        parent = re.search(r'ParentID="(\d+)"', m.group(1))
        out.append((m.group(2).strip(), m.group(3).strip(), parent.group(1) if parent else ""))
    return out


def nvidia_series_order(gpu_name: str, series: list[tuple[str, str, str]]) -> list[str]:
    """Serie da provare, la più probabile per prima (es. 'RTX 4060 Laptop GPU' -> 'GeForce RTX 40 Series (Notebooks)')."""
    n = normalize_name(gpu_name)
    laptop = "laptop" in n or "notebook" in n or bool(re.search(r"\d{3,4}m\b", n))
    m = re.search(r"\b(?:rtx|gtx|gt|mx)\s*(\d{3,4})", n)
    gen = None
    if m:
        num = m.group(1)
        gen = num[:2] if len(num) == 4 else num[0] + "00"   # 5070 -> 50, 1660 -> 16, 960 -> 900
    def score(s):
        name = s[0].lower()
        same_kind = ("notebook" in name) == laptop
        hit = gen is not None and (f" {gen} series" in name or f" {gen}m series" in name)
        return (0 if hit and same_kind else 1 if hit else 2 if same_kind else 3)
    geforce = [s for s in series if "geforce" in s[0].lower() or "titan" in s[0].lower()]
    others = [s for s in series if s not in geforce]
    return [s[1] for s in sorted(geforce, key=score)] + [s[1] for s in others]


def intel_covered(name: str, local_ver: str) -> bool:
    """Il pacchetto Arc/Iris Xe copre Arc, Iris Xe, Core Ultra e UHD dalle CPU di 11a generazione."""
    n = normalize_name(name)
    if "arc" in n or "iris xe" in n or n in ("intel graphics", "graphics"):
        return True
    if re.search(r"uhd graphics 7\d\d", n):
        return True
    return (local_ver or "").startswith("32.0.101.")


def amd_covered(name: str) -> bool | None:
    """True per Radeon RX 5000 e successive, False per le serie in supporto legacy, None se non si capisce."""
    n = normalize_name(name)
    if re.search(r"\bvega\b|\brx\s*(4\d0|5[0-9]0)\b|\br[579]\s|\bhd\s*\d", n):
        return False
    if re.search(r"\brx\s*(5\d00|6\d00|7\d00|9\d00)", n) or re.search(r"radeon\s*(6\d0m|7\d0m|8\d0m|890m)", n):
        return True
    return None


def parse_intel_page(html: str) -> dict | None:
    ver = re.search(r'name="DownloadVersion"\s+content="([\d.]+)', html)
    if not ver:
        return None
    when = re.search(r'name="lastModifieddate"\s+content="([\d/]+)', html)
    exe = re.search(r'https://downloadmirror\.intel\.com/[^"\']+\.exe', html)
    return {"version": ver.group(1), "date": us_date_to_iso(when.group(1)) if when else "",
            "url": exe.group(0) if exe else INTEL_PAGE}


def parse_amd_page(html: str) -> dict:
    """Versioni Adrenalin consigliata e opzionale con le date (pagina di un modello AMD)."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    out = {}
    for m in re.finditer(r"Adrenalin (\d+\.\d+\.\d+) WHQL \((Recommended|Optional)\)(.{0,120}?)Release Date (\d{4}-\d{2}-\d{2})",
                         text):
        out.setdefault(m.group(2).lower(), {"version": m.group(1), "date": m.group(4)})
    return out


# --- Rete -------------------------------------------------------------------------
def nvidia_ids(client: httpx.Client, gpu_name: str) -> tuple[str, str, str] | None:
    """(psid, pfid, nome serie) del modello, cercandolo nelle liste ufficiali NVIDIA."""
    series = parse_lookup_values(client.get(NV_LOOKUP, params={"TypeID": 2}).text)
    names = dict((s[1], s[0]) for s in series)
    target = normalize_name(gpu_name)
    order = nvidia_series_order(gpu_name, series)

    def products(psid):
        try:
            return psid, parse_lookup_values(client.get(NV_LOOKUP, params={"TypeID": 3, "ParentID": psid}).text)
        except httpx.HTTPError:
            return psid, []

    # Prima le 3 serie più probabili, poi tutte le altre in parallelo
    for batch in (order[:3], order[3:]):
        with ThreadPoolExecutor(max_workers=6) as pool:
            for psid, prods in pool.map(products, batch):
                for pname, pfid, _ in prods:
                    if normalize_name(pname) == target:
                        return psid, pfid, names.get(psid, "")
    return None


def nvidia_latest(client: httpx.Client, psid: str, pfid: str) -> dict:
    data = client.get(NV_DRIVER.format(psid=psid, pfid=pfid)).json()
    info = data["IDS"][0]["downloadInfo"]
    return {"version": info["Version"], "date": nv_date_to_iso(unquote(info.get("ReleaseDateTime", ""))),
            "url": info["DownloadURL"], "name": unquote(info.get("Name", ""))}


def amd_installed_version() -> str | None:
    """Versione di AMD Software (Adrenalin) dal registro, es. '26.10.1'."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\AMD\CN") as key:
            val, _ = winreg.QueryValueEx(key, "RadeonSoftwareVersion")
            return str(val).strip() or None
    except (OSError, ImportError, AttributeError):
        return None


def check_gpu(client: httpx.Client, gpu) -> dict:
    """Stato del driver di una scheda video (oggetto Win32_VideoController)."""
    name = gpu.Name or tr("Scheda video")
    vendor = vendor_of(getattr(gpu, "PNPDeviceID", None))
    wmi_ver = getattr(gpu, "DriverVersion", None) or ""
    res = {"vendor": vendor, "name": name, "local": wmi_ver, "remote": None, "date": "", "update": None,
           "url": None, "page": None, "note": "", "error": None, "can_install": False,
           # Per la cronologia: periferica e INF del driver attuale
           "device_id": getattr(gpu, "PNPDeviceID", None) or "", "inf_name": getattr(gpu, "InfFilename", None)}
    if "basic display" in name.lower() or "base video" in name.lower():
        # Windows usa il driver generico: quello del produttore non è installato
        res.update(name=f"{tr('Scheda video')} {vendor.upper() if vendor != 'other' else ''}".strip(), local=tr("driver generico"),
                   update=True, note=tr("Il driver del produttore non è installato: la scheda funziona al minimo."),
                   page={"nvidia": NV_PAGE, "amd": AMD_SUPPORT,
                         "intel": INTEL_PAGE}.get(vendor))
        return res
    try:
        if vendor == "nvidia":
            res["local"] = wmi_to_nvidia_version(wmi_ver)
            ids = nvidia_ids(client, name)
            if not ids:
                res["error"] = tr("Modello non trovato negli elenchi NVIDIA.")
                res["page"] = NV_PAGE
                return res
            psid, pfid, series = ids
            latest = nvidia_latest(client, psid, pfid)
            res.update(remote=latest["version"], date=latest["date"], url=latest["url"], can_install=True,
                       update=is_newer(latest["version"], res["local"]), note=series,
                       page=NV_PAGE)
        elif vendor == "intel":
            res["page"] = INTEL_PAGE
            if not intel_covered(name, wmi_ver):
                res["note"] = tr("Grafica integrata di generazione precedente: usa il driver del produttore del PC.")
                return res
            latest = parse_intel_page(client.get(INTEL_PAGE).text)
            if not latest:
                res["error"] = tr("Versione non leggibile dalla pagina Intel.")
                return res
            res.update(remote=latest["version"], date=latest["date"], url=latest["url"],
                       update=is_newer(latest["version"], wmi_ver))
        elif vendor == "amd":
            res["page"] = AMD_SUPPORT
            covered = amd_covered(name)
            if covered is False:
                res["note"] = tr("Serie in supporto legacy: controlla la pagina AMD del tuo modello.")
                return res
            versions = parse_amd_page(client.get(AMD_PAGE).text)
            rec = versions.get("recommended") or versions.get("optional")
            if not rec:
                res["error"] = tr("Versione non leggibile dalla pagina AMD.")
                return res
            installed = amd_installed_version()
            res.update(remote=rec["version"], date=rec["date"])
            if installed:
                res["local"] = installed
                res["update"] = is_newer(rec["version"], installed)
            else:
                res["note"] = tr("Versione di AMD Software non rilevata: confrontala sulla pagina AMD.")
            opt = versions.get("optional")
            if opt and opt["version"] != rec["version"]:
                res["note"] = (res["note"] + " " if res["note"] else "") + tr("Disponibile anche la {version} (opzionale).", version=opt["version"])
            if covered is None:
                res["note"] = (res["note"] + " " if res["note"] else "") + tr("Verifica che il tuo modello sia supportato.")
        else:
            res["note"] = tr("Produttore non gestito.")
    except Exception as e:  # rete, formato cambiato, ...
        res["error"] = tr("Controllo non riuscito ({error}).", error=e.__class__.__name__)
    return res


def check_gpus(wmi_client) -> list[dict]:
    """Tutte le schede video, la dedicata per prima."""
    # Solo schede NVIDIA/AMD/Intel: gli adattatori virtuali (desktop remoto, ecc.) non hanno driver da aggiornare
    gpus = [g for g in wmi_client.Win32_VideoController()
            if g.Name and vendor_of(getattr(g, "PNPDeviceID", None)) != "other"]
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20.0) as client:
        results = [check_gpu(client, g) for g in gpus]
    order = {"nvidia": 0, "amd": 1, "intel": 2, "other": 3}
    return sorted(results, key=lambda r: order.get(r["vendor"], 3))

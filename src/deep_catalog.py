import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
import httpx
from bs4 import BeautifulSoup
from packaging import version
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

import driver_history as dh
import ignore_list
import inf_rank as ir
from ignore_list import ignore_key, load_ignored_updates  # noqa: F401
from i18n import LANG, tr
from config import CAB_DIR, CATALOG_PKG_DIR, SEVEN_ZIP, VERDICTS_FILE

INF_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "INF"
# Oltre questa dimensione il pacchetto non viene scaricato solo per verificarlo
MAX_VERIFY_BYTES = 300 * 1024 * 1024
CATALOG_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

console = Console()
NO_WIN = subprocess.CREATE_NO_WINDOW

# pnputil: pacchetto aggiunto al DriverStore ma nessuna periferica lo ha adottato (ERROR_NO_MORE_ITEMS)
PNPUTIL_NOT_APPLIED = 259


def add_ignored_update(*keys: str, name: str = "", version: str = "") -> None:
    """Aggiornamento rifiutato da Windows durante l'installazione: non riproporlo."""
    ignore_list.add_ignored(keys, name=name, version=version, scope="auto")


def published_driver_names(pnputil_output: str) -> list[str]:
    """Nomi oemN.inf che pnputil ha pubblicato (il testo intorno dipende dalla lingua di Windows)."""
    return list(dict.fromkeys(m.lower() for m in re.findall(r"\boem\d+\.inf\b", pnputil_output or "", re.IGNORECASE)))

HWID_PATTERN = re.compile(
    r"(PCI\\VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4}|"
    r"HDAUDIO\\FUNC_[0-9A-F]{2}&VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4}|"
    r"USB\\VID_[0-9A-F]{4}&PID_[0-9A-F]{4})",
    re.IGNORECASE
)

# Variante specifica della scheda (SUBSYS = produttore/modello OEM): più precisa del solo VEN&DEV
SPECIFIC_HWID_PATTERN = re.compile(
    r"((?:PCI\\VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4}|"
    r"HDAUDIO\\FUNC_[0-9A-F]{2}&VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4})&SUBSYS_[0-9A-F]{8})",
    re.IGNORECASE
)

# Parole che non identificano un fornitore ("Realtek Semiconductor Corp." -> "realtek")
_PROVIDER_STOPWORDS = {
    "inc", "corp", "corporation", "co", "ltd", "limited", "llc", "gmbh", "ag", "sa", "srl", "bv",
    "semiconductor", "semiconductors", "technology", "technologies", "tech", "electronics",
    "international", "the", "company", "computer", "group", "systems", "communications",
}


class CatalogResult(NamedTuple):
    candidate: dict | None  # aggiornamento migliore trovato (o None)
    ok: bool                # False = ricerca fallita (rete, pagina inattesa, ...)
    relevant: bool          # True = il Catalog ha almeno un pacchetto compatibile per questo ID


def extract_generic_hwid(raw_id: str) -> str | None:
    if not raw_id:
        return None
    match = HWID_PATTERN.search(raw_id)
    return match.group(1).upper() if match else None


def extract_specific_hwid(raw_id: str) -> str | None:
    """ID con SUBSYS (es. PCI\\VEN_10EC&DEV_8168&SUBSYS_816810EC), se presente."""
    if not raw_id:
        return None
    match = SPECIFIC_HWID_PATTERN.search(raw_id)
    return match.group(1).upper() if match else None


def is_foreign_architecture(text: str) -> bool:
    """True se il pacchetto è per ARM/ARM64 o solo per x86 (il sistema è x64)."""
    t = text.lower()
    if re.search(r"\b(arm64|arm|aarch64)\b", t):
        return True
    return bool(re.search(r"\bx86\b", t)) and not re.search(r"\b(x64|amd64|64-bit)\b", t)


def provider_matches(provider: str, title: str) -> bool:
    """True se il titolo del Catalog appartiene allo stesso fornitore del driver installato.

    Le versioni di fornitori diversi non sono confrontabili (un 10.x OEM non è "più nuovo" di un 2.x Realtek).
    Se il fornitore non è riconoscibile non si filtra.
    """
    p = (provider or "").lower()
    t = (title or "").lower()
    if "advanced micro devices" in p or re.search(r"\bamd\b", p):
        return "advanced micro devices" in t or bool(re.search(r"\bamd\b", t))
    tokens = {w for w in re.findall(r"[a-z0-9]+", p) if len(w) >= 3 and w not in _PROVIDER_STOPWORDS}
    if not tokens:
        return True
    return any(re.search(rf"\b{re.escape(tok)}\b", t) for tok in tokens)

def parse_wmi_date(wmi_date: str) -> datetime:
    if wmi_date and len(wmi_date) >= 8:
        try:
            return datetime.strptime(wmi_date[:8], "%Y%m%d")
        except ValueError:
            pass
    return datetime(2000, 1, 1)

def installed_driver_date(inf_name: str | None, wmi_date: str | None) -> datetime:
    """Data del driver installato letta dal suo INF (DriverVer, mese/giorno/anno).

    La data di WMI non è affidabile: viene convertita con la lingua di Windows e su un sistema italiano
    '10/03/2025' (3 ottobre) diventa il 10 marzo. Si usa solo se l'INF non è leggibile.
    """
    if inf_name:
        d, _ = ir.inf_driver_ver(INF_DIR / inf_name)
        if d:
            return datetime(d.year, d.month, d.day)
    return parse_wmi_date(wmi_date)


def device_ids_map(wmi_client) -> dict[str, tuple[list[str], list[str]]]:
    """DeviceID -> (ID hardware, ID compatibili) di ogni periferica, come li usa Windows per scegliere il driver."""
    out = {}
    for dev in wmi_client.Win32_PnPEntity():
        dev_id = (getattr(dev, "DeviceID", None) or "").upper()
        if dev_id:
            out[dev_id] = (list(getattr(dev, "HardwareID", None) or []), list(getattr(dev, "CompatibleID", None) or []))
    return out


def parse_catalog_date(date_str: str) -> datetime:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime(2000, 1, 1)

def query_ms_catalog(client: httpx.Client, hwid: str, local_ver: str, local_date: datetime,
                     provider: str = "", ignored: frozenset | set = frozenset()) -> CatalogResult:
    """Cerca sul Microsoft Update Catalog.

    ok=False se la ricerca è fallita (rete, pagina inattesa, ...), così il chiamante non scambia
    un errore per "nessun aggiornamento". Si considerano solo pacchetti per Windows 10/11 x64
    dello stesso fornitore del driver installato.
    """
    url = "https://www.catalog.update.microsoft.com/Search.aspx"
    try:
        # Accept-Language fisso: il formato delle date nel Catalog dipende dalla lingua
        resp = client.get(url, params={"q": hwid}, timeout=12.0,
                          headers={"Accept-Language": "en-US,en;q=0.9"})
        if resp.status_code != 200:
            return CatalogResult(None, False, False)

        # Nessun risultato: il Catalog lo dice esplicitamente (pagina in inglese grazie ad Accept-Language).
        # Una pagina senza tabella e senza questo messaggio (errore, throttling) conta come fallimento.
        if "ctl00_catalogBody_updateMatches" not in resp.text:
            return CatalogResult(None, "did not find any results" in resp.text.lower(), False)

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="ctl00_catalogBody_updateMatches")
        if not table:
            return CatalogResult(None, False, False)

        best_candidate = None
        best_ver = version.parse(local_ver)
        relevant = False

        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 8:
                continue

            title = cols[1].get_text(strip=True)
            products = cols[2].get_text(strip=True)
            date_str = cols[4].get_text(strip=True)
            ver_str = cols[5].get_text(strip=True)
            btn = cols[7].find("input")

            if not ("Windows 11" in products or "Windows 10" in products):
                continue
            if is_foreign_architecture(f"{title} {products}"):
                continue
            if not provider_matches(provider, title):
                continue
            if not btn or not btn.get("id"):
                continue

            try:
                rem_ver = version.parse(ver_str)
                rem_date = parse_catalog_date(date_str)
            except Exception:
                continue

            relevant = True  # anche se ignorato: la variante è nota, non si ricade sull'ID generico
            if ignore_list.is_ignored(ignored, hwid, ver_str, btn.get("id")):
                continue
            if rem_ver > best_ver and rem_date >= local_date:
                best_ver = rem_ver
                best_candidate = {
                    "title": title,
                    "remote_ver": ver_str,
                    "remote_date": rem_date.strftime("%Y-%m-%d"),
                    "update_id": btn.get("id")
                }

        return CatalogResult(best_candidate, True, relevant)
    except Exception:
        return CatalogResult(None, False, False)


def check_device(client: httpx.Client, info: dict, ignored: frozenset | set = frozenset()) -> tuple[CatalogResult, str]:
    """Cerca prima con l'ID specifico (SUBSYS); ricade su VEN&DEV solo se il Catalog non conosce
    quella variante. Se la variante OEM è nota non si propone mai il driver generico.
    Con info["queries"] si usa quell'elenco di ID, dal più specifico al più generico.
    Ritorna (risultato, ID usato)."""
    candidates = info.get("queries") or (info.get("specific"), info.get("generic"))
    queries = [q for q in dict.fromkeys(candidates) if q]
    if not queries:
        return CatalogResult(None, True, False), ""
    res, used = CatalogResult(None, True, False), queries[-1]
    for q in queries:
        res, used = query_ms_catalog(client, q, info["local_ver"], info["local_date"], info["provider"], ignored), q
        if not res.ok or res.relevant:
            break
    return res, used


# --- Periferiche senza driver o in errore (Gestione dispositivi) ---------------
# Codici ConfigManagerErrorCode: https://learn.microsoft.com/windows-hardware/drivers/install/device-manager-error-messages
PROBLEM_CODES = {
    1: tr("Non configurato correttamente"),
    3: tr("Driver danneggiato o memoria insufficiente"),
    10: tr("Il dispositivo non si avvia"),
    12: tr("Risorse hardware insufficienti"),
    14: tr("Serve un riavvio del PC"),
    18: tr("Il driver va reinstallato"),
    19: tr("Configurazione nel registro danneggiata"),
    21: tr("Windows sta rimuovendo il dispositivo"),
    24: tr("Non presente o driver incompleti"),
    28: tr("Driver non installato"),
    31: tr("Non funziona correttamente"),
    32: tr("Servizio del driver disattivato"),
    37: tr("Il driver non si è avviato"),
    39: tr("Driver mancante o danneggiato"),
    40: tr("Configurazione del servizio danneggiata"),
    41: tr("Driver caricato ma dispositivo non trovato"),
    43: tr("Fermato dopo aver segnalato un problema"),
    48: tr("Driver bloccato perché incompatibile"),
    52: tr("Firma digitale del driver non verificabile"),
}
# Non sono guasti: disattivato dall'utente, dispositivo scollegato
SKIP_PROBLEM_CODES = {22, 45}


def catalog_queries(hardware_ids, limit: int = 3) -> list[str]:
    """ID da cercare sul Catalog per una periferica, dal più specifico al più generico.

    PCI/HDAUDIO/USB: variante SUBSYS, poi VEN&DEV. Altri bus (ACPI, HID, ...): l'ID senza revisione.
    Le periferiche software (ROOT\\, SWD\\) non hanno driver sul Catalog.
    """
    out = []
    for raw in hardware_ids or []:
        rid = (raw or "").strip().upper()
        if not rid or rid.startswith(("ROOT\\", "SWD\\", "{")):
            continue
        spec, gen = extract_specific_hwid(rid), extract_generic_hwid(rid)
        if spec or gen:
            out += [spec, gen]
        else:
            out.append(re.sub(r"&REV_[0-9A-F]+", "", rid))
    return [q for q in dict.fromkeys(out) if q][:limit]


def collect_problem_devices(wmi_client) -> list[dict]:
    """Periferiche presenti con un errore in Gestione dispositivi (driver mancante compreso). Nessun accesso alla rete."""
    installed = {}
    for drv in wmi_client.Win32_PnPSignedDriver():
        dev_id = (getattr(drv, "DeviceID", None) or "").upper()
        if dev_id and getattr(drv, "DriverVersion", None):
            installed[dev_id] = drv

    devices = []
    # FastWMI filtra già lato WMI le sole periferiche in errore (2 s -> 0,03 s)
    entities = wmi_client.problem_entities() if hasattr(wmi_client, "problem_entities") else wmi_client.Win32_PnPEntity()
    for dev in entities:
        code = getattr(dev, "ConfigManagerErrorCode", 0) or 0
        if code == 0 or code in SKIP_PROBLEM_CODES or getattr(dev, "Present", True) is False:
            continue
        dev_id = getattr(dev, "DeviceID", None) or ""
        hwids = list(getattr(dev, "HardwareID", None) or [])
        ids = hwids or ([dev_id] if dev_id else [])
        name = getattr(dev, "Name", None) or getattr(dev, "Description", None) or tr("Dispositivo sconosciuto")
        drv = installed.get(dev_id.upper())
        nvidia = "NVIDIA" in name.upper()
        devices.append({
            "name": name,
            "device_id": dev_id,
            "code": code,
            "problem": PROBLEM_CODES.get(code, tr("Errore {code}", code=code)),
            "hwid": (ids[0] if ids else dev_id).upper(),
            # La GPU NVIDIA si aggiorna dall'API NVIDIA, non dal Catalog
            "queries": [] if nvidia else catalog_queries(ids),
            "nvidia": nvidia,
            "has_driver": drv is not None,
            # Con un driver già installato si propone solo una versione più recente
            "local_ver": drv.DriverVersion if drv else "0",
            "local_date": (installed_driver_date(getattr(drv, "InfName", None), drv.DriverDate)
                           if drv else datetime(2000, 1, 1)),
            "provider": (drv.DriverProviderName or "") if drv else "",
            "inf_name": getattr(drv, "InfName", None) if drv else None,
            "hwids": hwids,
            "compids": list(getattr(dev, "CompatibleID", None) or []),
        })
    return devices


# --- Verifica dei pacchetti: Windows applicherebbe davvero il driver proposto? -----
CANDIDATE_FIELDS = ("update_id", "remote_ver", "remote_date", "title")
_verdict_lock = threading.Lock()


class PackageTooLarge(Exception):
    pass


def _load_verdicts() -> dict:
    try:
        return json.loads(VERDICTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_verdict(keys: list[str], verdict: str, reason: str) -> None:
    with _verdict_lock:
        data = _load_verdicts()
        for k in keys:
            data[k] = {"verdict": verdict, "reason": reason, "lang": LANG}
        try:
            VERDICTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            VERDICTS_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def verdict_keys(item: dict) -> list[str]:
    """Il verdetto dipende dal pacchetto, dalla periferica e dal driver installato in quel momento.
    La seconda chiave copre gli altri ID del Catalog con lo stesso driver (ne pubblica uno per versione di Windows)."""
    dev = (item.get("device_id") or item.get("hwid") or "").upper()
    local = item.get("local_ver") or "0"
    return [f"{item['update_id']}|{dev}|{local}", f"v|{dev}|{item.get('remote_ver')}|{local}"]


def cleanup_package_cache(max_age_days: int = 7) -> None:
    if not CATALOG_PKG_DIR.exists():
        return
    limit = time.time() - max_age_days * 86400
    for d in CATALOG_PKG_DIR.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def cab_links_for(client: httpx.Client, update_id: str) -> list[str]:
    payload = {"updateIDs": json.dumps([{"size": 0, "languages": "", "uidInfo": update_id, "updateID": update_id}])}
    resp = client.post("https://www.catalog.update.microsoft.com/DownloadDialog.aspx", data=payload)
    resp.raise_for_status()
    # Un aggiornamento può essere composto da più .cab: servono tutti
    return list(dict.fromkeys(re.findall(r"https?://[^\s'\"]+\.cab", resp.text)))


def fetch_package(client: httpx.Client, update_id: str) -> tuple[Path | None, str]:
    """Scarica ed estrae un pacchetto del Catalog in cache (riusato poi per l'installazione).
    Ritorna (cartella estratta, motivo dell'eventuale errore)."""
    root = CATALOG_PKG_DIR / re.sub(r"[^A-Za-z0-9-]", "_", update_id)
    out = root / "x"
    if (root / ".ok").exists() and any(out.rglob("*.inf")):
        return out, ""
    shutil.rmtree(root, ignore_errors=True)
    try:
        links = cab_links_for(client, update_id)
        if not links:
            return None, tr("link di download non trovato")
        for n, url in enumerate(links):
            if not _download_and_extract(client, url, root / f"pkg_{n}.cab", out / str(n), MAX_VERIFY_BYTES):
                shutil.rmtree(root, ignore_errors=True)
                return None, tr("estrazione del pacchetto non riuscita")
        if not any(out.rglob("*.inf")):
            shutil.rmtree(root, ignore_errors=True)
            return None, tr("il pacchetto non contiene file .inf")
        for cab in root.glob("pkg_*.cab"):
            cab.unlink(missing_ok=True)
        (root / ".ok").write_text("", encoding="utf-8")
        return out, ""
    except PackageTooLarge as e:
        shutil.rmtree(root, ignore_errors=True)
        return None, tr("pacchetto troppo grande per la verifica ({size} MB)", size=e)
    except Exception as e:
        shutil.rmtree(root, ignore_errors=True)
        return None, tr("download non riuscito ({error})", error=e.__class__.__name__)


def verify_candidate(client: httpx.Client, item: dict, hwids: list[str], compids: list[str]) -> tuple[str, str]:
    """'ok' / 'no' / 'unknown' e il motivo. Con 'ok' imposta item['package_dir'] per l'installazione."""
    keys = verdict_keys(item)
    cached = _load_verdicts()
    for k in keys:
        if k in cached and cached[k]["verdict"] in ("ok", "no"):
            if cached[k]["verdict"] == "ok":
                pkg = CATALOG_PKG_DIR / re.sub(r"[^A-Za-z0-9-]", "_", item["update_id"]) / "x"
                if (pkg.parent / ".ok").exists():
                    item["package_dir"] = str(pkg)
            reason = cached[k]["reason"] if cached[k].get("lang", "it") == LANG else \
                tr("Esito di una verifica precedente.")
            return cached[k]["verdict"], reason

    if not hwids:
        return "unknown", tr("ID della periferica non disponibili.")
    console.print(tr("Controllo: verifica del pacchetto {remote_ver} per {value}...", remote_ver=item['remote_ver'], value=item['name'][:40]))
    pkg, err = fetch_package(client, item["update_id"])
    if pkg is None:
        return "unknown", tr("Non verificato: {reason}.", reason=err)

    osinfo = ir.current_os()
    candidate = ir.best_match_in_package(pkg, hwids, compids, osinfo)
    installed = None
    if item.get("has_driver", True) and (item.get("local_ver") or "0") != "0":
        d_inst = item.get("local_date")
        d_inst = d_inst.date() if isinstance(d_inst, datetime) else None
        inf_path = INF_DIR / item["inf_name"] if item.get("inf_name") else None
        match = None
        if inf_path and inf_path.exists():
            try:
                inst_inf = ir.Inf.load(inf_path)
                match = ir.best_match(inst_inf, hwids, compids, osinfo)
                d_inf, _ = ir.parse_driver_ver(inst_inf.directive("version", "DriverVer"))
                d_inst = d_inf or d_inst
            except OSError:
                match = None
        if match is None and candidate is not None:
            # INF installato non leggibile: si confrontano solo data e versione, a parità di corrispondenza
            match = candidate[0]
        if match is not None:
            installed = (match, d_inst, item.get("local_ver") or "")

    ok, reason = ir.judge(candidate, installed)
    verdict = "ok" if ok else "no"
    _save_verdict(keys, verdict, reason)
    if ok:
        item["package_dir"] = str(pkg)
    else:
        shutil.rmtree(pkg.parent, ignore_errors=True)
    return verdict, reason


def verify_and_refine(client: httpx.Client, items: list[dict], ids_map: dict, ignored: frozenset,
                      attempts: int = 3) -> None:
    """Verifica i candidati trovati; se Windows non applicherebbe un pacchetto, cerca un'alternativa.

    Imposta su ogni voce 'verified' (True/False=non verificabile) e 'verify_reason'; a una voce senza
    alternative valide toglie i campi del candidato e mette 'rejected_reason'."""
    cleanup_package_cache()
    for item in items:
        hwids, compids = ids_map.get((item.get("device_id") or "").upper(), ([], []))
        skip = set(ignored)
        for _ in range(attempts):
            verdict, reason = verify_candidate(client, item, hwids, compids)
            if verdict != "no":
                item["verified"] = verdict == "ok"
                item["verify_reason"] = reason
                break
            console.print("[dim] -> " + tr("Scartato {value} {remote_ver}: {reason}", value=item['name'][:40], remote_ver=item['remote_ver'], reason=reason) + "[/dim]")
            skip |= {item["update_id"]} | {ignore_key(q, item["remote_ver"])
                                            for q in (item.get("queries") or (item.get("specific"), item.get("generic")))
                                            if q}
            res, used = check_device(client, item, frozenset(skip))
            for f in CANDIDATE_FIELDS:
                item.pop(f, None)
            item.pop("package_dir", None)
            item["rejected_reason"] = reason
            if not res.candidate:
                break
            item.update(res.candidate)
            item["hwid"] = used
            item.pop("rejected_reason", None)
        else:
            for f in CANDIDATE_FIELDS:
                item.pop(f, None)
            item.pop("package_dir", None)
            item["rejected_reason"] = tr("Nessuno dei pacchetti trovati verrebbe applicato da Windows.")


def scan_problem_devices(wmi_client) -> list[dict]:
    """Trova le periferiche in errore o senza driver e cerca per ognuna un driver sul Microsoft Update Catalog.

    Ogni voce ha "update_id" (e i campi del candidato) se è stato trovato un driver installabile,
    "lookup_ok" = False se la ricerca non è riuscita.
    """
    console.print("\n[bold cyan]" + tr("[Diagnosi] Ricerca di periferiche senza driver o in errore...") + "[/bold cyan]")
    devices = collect_problem_devices(wmi_client)
    if not devices:
        console.print(tr("Nessuna periferica in errore o senza driver."))
        return []

    ignored = frozenset(load_ignored_updates())
    searchable = [d for d in devices if d["queries"]]
    with httpx.Client(headers=CATALOG_HEADERS, follow_redirects=True, timeout=30.0) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(check_device, client, d, ignored): d for d in searchable}
            for fut in as_completed(futures):
                d = futures[fut]
                try:
                    res, used = fut.result()
                except Exception:
                    res, used = CatalogResult(None, False, False), ""
                d["lookup_ok"] = res.ok
                if res.candidate:
                    d.update(res.candidate)
                    d["hwid"] = used
        ids_map = {d["device_id"].upper(): (d["hwids"], d["compids"]) for d in devices if d.get("device_id")}
        verify_and_refine(client, [d for d in devices if d.get("update_id")], ids_map, ignored)

    devices.sort(key=lambda d: (not d.get("update_id"), d["name"].lower()))
    fixable = sum(1 for d in devices if d.get("update_id"))
    table = Table(title=tr("Periferiche con problemi"))
    table.add_column(tr("Periferica"), style="white")
    table.add_column(tr("Problema"), style="yellow")
    table.add_column(tr("Driver sul Catalog"), style="bold green")
    for d in devices:
        found = (f"{d['remote_ver']} ({d['remote_date']})" + (" · " + tr("verificato") if d.get("verified") else "")
                 if d.get("update_id") else "—")
        table.add_row(d["name"][:40], tr("{problem} (codice {code})", problem=d["problem"], code=d["code"]), found)
    console.print(table)
    console.print("[bold cyan]" + tr("{value} periferiche con problemi, {fixable} con un driver disponibile.", value=len(devices), fixable=fixable) + "[/bold cyan]")
    return devices


def deep_scan_peripherals(wmi_client, exclude_device_ids=frozenset()):
    """Scansiona tutte le periferiche confrontandole col database globale Microsoft.

    exclude_device_ids: periferiche già gestite altrove (es. quelle in errore), per non elencarle due volte.
    """
    console.print("\n[bold cyan]" + tr("[Deep Scan] Controllo globale periferiche (PCI, USB, Audio, LAN, Chipset)...") + "[/bold cyan]")
    devices_to_check = {}
    exclude = {d.upper() for d in exclude_device_ids}

    for drv in wmi_client.Win32_PnPSignedDriver():
        if not drv.DeviceName or not drv.DriverVersion:
            continue
        if drv.DriverProviderName in ("Microsoft", None) or "NVIDIA" in (drv.DeviceName or ""):
            continue
        if (getattr(drv, "DeviceID", None) or "").upper() in exclude:
            continue

        raw_id = drv.HardWareID or drv.DeviceID
        gen_id = extract_generic_hwid(raw_id)
        if not gen_id:
            continue
        spec_id = extract_specific_hwid(raw_id)
        key = spec_id or gen_id
        if key in devices_to_check:
            continue

        devices_to_check[key] = {
            "name": drv.DeviceName,
            "provider": drv.DriverProviderName or "",
            "local_ver": drv.DriverVersion,
            "local_date": installed_driver_date(getattr(drv, "InfName", None), drv.DriverDate),
            "specific": spec_id,
            "generic": gen_id,
            "hwid": key,
            "device_id": getattr(drv, "DeviceID", None) or "",
            "inf_name": getattr(drv, "InfName", None),
        }

    updates_found = []
    failed_checks = 0
    headers = CATALOG_HEADERS

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(tr("Interrogazione Microsoft Update Catalog..."), total=len(devices_to_check))
        with httpx.Client(headers=headers, follow_redirects=True) as client:
            # Poche richieste in parallelo: più veloce, ma senza martellare il Catalog
            with ThreadPoolExecutor(max_workers=4) as pool:
                ignored = frozenset(load_ignored_updates())
                futures = {
                    pool.submit(check_device, client, info, ignored): (hwid, info)
                    for hwid, info in devices_to_check.items()
                }
                for fut in as_completed(futures):
                    hwid, info = futures[fut]
                    progress.update(task, description=f"Controllo: {info['name'][:40]} ({hwid})...")
                    try:
                        res, used_id = fut.result()
                    except Exception:
                        res, used_id = CatalogResult(None, False, False), hwid
                    if not res.ok:
                        failed_checks += 1
                    elif res.candidate:
                        info.update(res.candidate)
                        info["hwid"] = used_id
                        updates_found.append(info)
                    progress.advance(task)

    # Si propone solo ciò che Windows applicherebbe davvero (verifica dell'INF del pacchetto)
    if updates_found:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
            verify_and_refine(client, updates_found, device_ids_map(wmi_client), frozenset(load_ignored_updates()))
        updates_found = [u for u in updates_found if u.get("update_id")]

    updates_found.sort(key=lambda i: i["name"].lower())

    if failed_checks:
        console.print("[yellow]! " + tr("{failed} controlli su {total} non sono riusciti "
                                        "(rete o Catalog non raggiungibile): il risultato è parziale.",
                                        failed=failed_checks, total=len(devices_to_check)) + "[/yellow]")

    if not updates_found:
        if failed_checks:
            console.print("[yellow]! " + tr("Nessun aggiornamento trovato, ma la scansione non è completa. Riprova più tardi.") + "[/yellow]")
        else:
            console.print("[bold green]✔ " + tr("Tutte le periferiche PCI/USB/Audio hanno già l'ultimo driver WHQL disponibile!") + "[/bold green]")
        return []

    table = Table(title=tr("Aggiornamenti Periferiche Trovati (Deep Catalog Match)"))
    table.add_column("#", style="cyan")
    table.add_column(tr("Periferica"), style="white")
    table.add_column("Hardware ID", style="dim")
    table.add_column(tr("Installato"), style="yellow")
    table.add_column(tr("Nuova Versione WHQL"), style="bold green")

    for idx, item in enumerate(updates_found, 1):
        table.add_row(
            str(idx),
            item["name"][:35],
            item["hwid"],
            f"{item['local_ver']} ({item['local_date'].strftime('%Y-%m-%d')})",
            f"{item['remote_ver']} ({item['remote_date']})" + (" · " + tr("verificato") if item.get("verified") else "")
        )

    console.print(table)
    return updates_found

def _download_and_extract(client: httpx.Client, url: str, cab_path, out_dir, max_bytes: int | None = None) -> bool:
    """Scarica un .cab e lo estrae in out_dir (7-Zip se presente, altrimenti expand.exe).
    Con max_bytes, un file più grande solleva PackageTooLarge (dimensione in MB)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url) as dl_resp:
        dl_resp.raise_for_status()
        total = int(dl_resp.headers.get("Content-Length", 0) or 0)
        if max_bytes and total > max_bytes:
            raise PackageTooLarge(total // (1024 * 1024))
        written = 0
        with open(cab_path, "wb") as f:
            for chunk in dl_resp.iter_bytes(65536):
                written += len(chunk)
                if max_bytes and written > max_bytes:
                    raise PackageTooLarge(written // (1024 * 1024))
                f.write(chunk)

    if SEVEN_ZIP.exists():
        cmd = [str(SEVEN_ZIP), "x", str(cab_path), f"-o{out_dir}", "-y"]
        ok_codes = (0, 1)  # 7-Zip: 1 = solo avvisi
    else:
        cmd = ["expand.exe", str(cab_path), "-F:*", str(out_dir)]
        ok_codes = (0,)
    ext = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WIN)
    return ext.returncode in ok_codes


def install_catalog_cab_updates(updates_list) -> tuple[int, int]:
    """Scarica i pacchetti .cab dal Microsoft Update Catalog (evitando duplicati) e li installa.

    Ritorna (installati, falliti).
    """
    if not updates_list:
        return 0, 0

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    done_uids = set()
    ok_count = 0
    fail_count = 0
    not_applied = 0

    with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
        for item in updates_list:
            uid = item["update_id"]
            if uid in done_uids:
                console.print("[dim] -> " + tr("Pacchetto già elaborato per {name}, salto download duplicato.", name=item['name']) + "[/dim]")
                continue

            cached_pkg = Path(item["package_dir"]) if item.get("package_dir") else None
            try:
                if cached_pkg and any(cached_pkg.rglob("*.inf")):
                    # Pacchetto già scaricato e verificato durante la scansione
                    console.print("\n[bold cyan]" + tr("Pacchetto verificato pronto per:[/bold cyan] {name} ({remote_ver})", name=item['name'], remote_ver=item['remote_ver']))
                    extract_path = cached_pkg
                    cab_links = None
                else:
                    console.print("\n[bold cyan]" + tr("Richiesta link download per:[/bold cyan] {name} ({remote_ver})", name=item['name'], remote_ver=item['remote_ver']))
                    cab_links = cab_links_for(client, uid)
                if cab_links is not None and not cab_links:
                    console.print("[red]✖ " + tr("Impossibile estrarre il link .cab per {name}", name=item['name']) + "[/red]")
                    fail_count += 1
                    continue

                bad_cab = None
                if cab_links:
                    if CAB_DIR.exists():
                        shutil.rmtree(CAB_DIR, ignore_errors=True)
                    CAB_DIR.mkdir(parents=True, exist_ok=True)
                    extract_path = CAB_DIR / "extracted"
                for n, cab_url in enumerate(cab_links or []):
                    cab_name = cab_url.split("/")[-1]
                    console.print(" -> " + tr("Download ed estrazione di {cab_name} ({value}/{value2})...", cab_name=cab_name, value=n + 1, value2=len(cab_links)))
                    if not _download_and_extract(client, cab_url, CAB_DIR / f"pkg_{n}.cab", extract_path / str(n)):
                        bad_cab = cab_name
                        break

                if bad_cab or not any(extract_path.rglob("*.inf")):
                    detail = tr("errore su {name}", name=bad_cab) if bad_cab else tr("nessun .inf trovato")
                    console.print("[red]✖ " + tr("Estrazione del pacchetto non riuscita per {name} ({detail}).", name=item['name'], detail=detail) + "[/red]")
                    fail_count += 1
                    continue

                console.print(" -> " + tr("Installazione {name} tramite pnputil...", name=item['name']))
                snap_before = dh.snapshot_infs()
                before = set(snap_before)
                res = subprocess.run(
                    ["pnputil", "/add-driver", str(extract_path / "*.inf"), "/subdirs", "/install"],
                    capture_output=True,
                    text=True,
                    encoding="mbcs",  # con l'output rediretto pnputil scrive nella codepage ANSI, non OEM
                    errors="replace",
                    creationflags=NO_WIN
                )

                # Solo il codice di ritorno decide l'esito (il testo di pnputil dipende dalla lingua di Windows)
                if res.returncode in (0, 3010):
                    console.print("[bold green]✔ " + tr("{name} aggiornato alla versione {remote_ver}!", name=item['name'], remote_ver=item['remote_ver']) + "[/bold green]")
                    if res.returncode == 3010:
                        console.print("[bold yellow]! " + tr("Riavvio del sistema consigliato.") + "[/bold yellow]")
                    done_uids.add(uid)
                    ok_count += 1
                    dh.record_install("catalog", item["name"], item.get("device_id", ""),
                                      "" if item.get("local_ver") in (None, "0") else item["local_ver"],
                                      item["remote_ver"], item.get("inf_name"), snap_before)
                elif res.returncode == PNPUTIL_NOT_APPLIED:
                    # Windows ha preferito il driver attuale: togli il pacchetto appena aggiunto e non riproporlo
                    new_pkgs = [n for n in published_driver_names(res.stdout) if n not in before]
                    for pkg in new_pkgs:
                        subprocess.run(["pnputil", "/delete-driver", pkg], capture_output=True, creationflags=NO_WIN)
                    # Ignora questa versione per la periferica (sia con ID SUBSYS sia con VEN&DEV)
                    add_ignored_update(uid, *(ignore_key(h, item["remote_ver"])
                                              for h in (item.get("specific"), item.get("generic"), item.get("hwid")) if h),
                                       name=item["name"], version=item["remote_ver"])
                    done_uids.add(uid)
                    not_applied += 1
                    current = (tr("ha mantenuto il driver attuale ({version})", version=item["local_ver"])
                               if item.get("local_ver") not in (None, "", "0")
                               else tr("non ha associato il pacchetto alla periferica"))
                    console.print("[yellow]! " + tr("{name}: Windows {what}, il pacchetto {version} non è adatto a questa "
                                                    "periferica. Rimosso dal DriverStore e non verrà più proposto.",
                                                    name=item["name"], what=current, version=item["remote_ver"])
                                  + "[/yellow]")
                else:
                    lines = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
                    out_msg = (lines[-1] if lines else "")[:160]
                    console.print("[bold red]✖ " + tr("Installazione di {name} non riuscita (pnputil codice {returncode}): {out_msg}", name=item['name'], returncode=res.returncode, out_msg=out_msg) + "[/bold red]")
                    fail_count += 1
            except Exception as e:
                console.print("[bold red]✖ " + tr("Errore su {name}: {e}", name=item['name'], e=e) + "[/bold red]")
                fail_count += 1
            finally:
                shutil.rmtree(CAB_DIR, ignore_errors=True)
                if cached_pkg:
                    shutil.rmtree(cached_pkg.parent, ignore_errors=True)

    extra = tr(", {count} non applicabili", count=not_applied) if not_applied else ""
    console.print("\n[bold cyan]" + tr("Riepilogo installazione: {ok_count} riusciti, {fail_count} falliti{extra}.", ok_count=ok_count, fail_count=fail_count, extra=extra) + "[/bold cyan]")
    return ok_count, fail_count

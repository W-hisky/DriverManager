"""Esporta la diagnostica in un file .zip da allegare a una segnalazione.

Contiene: i log di DriverCore, impostazioni, cronologia, aggiornamenti ignorati, ultimo controllo automatico
e un riepilogo del sistema (Windows, processore, memoria, schede video, driver di terze parti).
Non contiene file personali né backup dei driver.
"""
import json
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from config import (APP_VERSION, AUTO_SCAN_FILE, FROZEN, HISTORY_FILE, IGNORED_UPDATES_FILE, LOG_DIR,
                    SETTINGS_FILE)

DATA_FILES = (SETTINGS_FILE, HISTORY_FILE, IGNORED_UPDATES_FILE, AUTO_SCAN_FILE)


def default_name(now: datetime | None = None) -> str:
    return f"DriverCore-diagnostica-{(now or datetime.now()):%Y%m%d-%H%M}.zip"


def _plain(v):
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v if isinstance(v, (str, int, float, bool, type(None))) else str(v)


def system_info(wmi_client=None) -> dict:
    """Riepilogo del sistema. Senza WMI (o se fallisce) si limita a Windows e Python."""
    from i18n import LANG
    info = {
        "drivercore": APP_VERSION, "exe": FROZEN, "language": LANG,
        "windows": platform.platform(), "windows_build": sys.getwindowsversion().build if hasattr(sys, "getwindowsversion") else None,
        "python": sys.version.split()[0], "created": datetime.now().isoformat(timespec="seconds"),
    }
    if wmi_client is None:
        return info
    try:
        cpu = wmi_client.select("Win32_Processor", ("Name",))
        cs = wmi_client.select("Win32_ComputerSystem", ("Manufacturer", "Model", "TotalPhysicalMemory"))
        info["cpu"] = cpu[0].Name.strip() if cpu else None
        if cs:
            info["pc"] = f"{cs[0].Manufacturer} {cs[0].Model}"
            info["ram_gb"] = round(int(cs[0].TotalPhysicalMemory or 0) / 2**30, 1)
        info["gpus"] = [{k: _plain(getattr(g, k)) for k in ("Name", "DriverVersion", "PNPDeviceID")}
                        for g in wmi_client.Win32_VideoController()]
        info["third_party_drivers"] = sorted(
            ({"device": d.DeviceName, "provider": d.DriverProviderName, "version": d.DriverVersion,
              "inf": d.InfName, "class": d.DeviceClass}
             for d in wmi_client.Win32_PnPSignedDriver()
             if d.DeviceName and d.DriverProviderName not in (None, "Microsoft")),
            key=lambda x: (x["class"] or "", x["device"] or ""))
    except Exception as e:  # la diagnostica non deve mai fallire per colpa di WMI
        info["wmi_error"] = repr(e)
    return info


def export(dest: Path, wmi_client=None, log_dir: Path | None = None, data_files=DATA_FILES) -> Path:
    """Crea lo zip in dest e ritorna il percorso."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    log_dir = log_dir or LOG_DIR
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("system.json", json.dumps(system_info(wmi_client), indent=1, ensure_ascii=False))
        if log_dir.exists():
            for f in sorted(log_dir.iterdir()):
                if f.is_file() and ".log" in f.name:
                    z.write(f, f"logs/{f.name}")
        for f in data_files:
            f = Path(f)
            if f.is_file():
                z.write(f, f"data/{f.name}")
    return dest

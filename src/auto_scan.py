"""Controllo automatico pianificato e notifiche di Windows.

- L'attività "\\DriverCore\\Controllo driver" dell'Utilità di pianificazione avvia questo file (senza finestra)
  ogni giorno o ogni settimana; se il PC era spento all'ora prevista, parte appena possibile.
- Il controllo NON installa nulla: cerca driver nuovi per schede video e periferiche, controlla le periferiche
  in errore e, se trova qualcosa di nuovo rispetto all'ultima notifica, mostra un avviso di Windows.
- Un clic sull'avviso apre DriverCore (protocollo drivercore:// registrato per l'utente corrente).

Uso diretto: python auto_scan.py            esegue il controllo
             python auto_scan.py --test     mostra una notifica di prova
Dal programma: DriverCore.exe --auto-scan / --test-notify (oppure gui.py con gli stessi argomenti)
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import AUTO_SCAN_FILE, BASE_DIR, LOG_DIR, SETTINGS_FILE, app_command  # noqa: E402
from i18n import tr  # noqa: E402

NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TASK_PATH = "\\DriverCore\\"
TASK_NAME = "Controllo driver"  # identificativo: non tradurre (resta lo stesso in ogni lingua)
AUMID = "DriverCore.App"
PROTOCOL = "drivercore"
FREQUENCIES = ("off", "daily", "weekly")


# --- Impostazioni e risultati -------------------------------------------------------
def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def get_frequency() -> str:
    f = _read_json(SETTINGS_FILE, {}).get("auto_scan", "off")
    return f if f in FREQUENCIES else "off"


def last_result() -> dict:
    return _read_json(AUTO_SCAN_FILE, {})


# --- Logica pura --------------------------------------------------------------------
def summarize(gpus: list[dict], problems: list[dict], updates: list[dict]) -> list[dict]:
    """Le novità trovate, ciascuna con una chiave stabile (per non notificare due volte la stessa cosa)."""
    items = []
    for g in gpus:
        if g.get("update") is True and g.get("remote"):
            items.append({"key": f"gpu|{g['name']}|{g['remote']}", "text": f"{g['name']} {g['remote']}"})
    for d in problems:
        what = tr("{version} disponibile", version=d["remote_ver"]) if d.get("update_id") else d.get("problem", tr("problema"))
        items.append({"key": f"dev|{d.get('device_id')}|{d.get('code')}|{d.get('remote_ver', '')}",
                      "text": f"{d['name']}: {what}"})
    for u in updates:
        items.append({"key": f"per|{u.get('hwid')}|{u['remote_ver']}", "text": f"{u['name']} {u['remote_ver']}"})
    return items


def to_notify(items: list[dict], already_notified: list[str]) -> list[dict]:
    seen = set(already_notified or [])
    return [i for i in items if i["key"] not in seen]


def notification_text(items: list[dict]) -> tuple[str, str]:
    n = len(items)
    title = tr("1 novità sui driver") if n == 1 else tr("{count} novità sui driver", count=n)
    lines = [i["text"] for i in items[:3]]
    if n > 3:
        lines.append(tr("… e altre {count}", count=n - 3))
    return title, "\n".join(lines)


def toast_xml(title: str, body: str) -> str:
    launch = f"{PROTOCOL}://open"
    return (
        f'<toast activationType="protocol" launch="{launch}">'
        "<visual><binding template=\"ToastGeneric\">"
        f"<text>{escape(title)}</text><text>{escape(body)}</text>"
        "</binding></visual>"
        f'<actions><action content="{escape(tr("Apri DriverCore"))}" activationType="protocol" arguments="{launch}"/></actions>'
        "</toast>"
    )


# --- Windows: notifiche, protocollo, Utilità di pianificazione ------------------------
def _command_line(*args: str) -> tuple[str, str]:
    exe, argv = app_command(*args)
    return exe, " ".join(f'"{a}"' for a in argv)


def _powershell(script: str, env: dict) -> subprocess.CompletedProcess:
    # I valori passano da variabili d'ambiente: niente quoting/iniezione nel comando
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, encoding="oem", errors="replace",
                          creationflags=NO_WIN, timeout=60, env={**os.environ, **env})


def register_app() -> None:
    """Nome mostrato nelle notifiche e protocollo drivercore:// che apre la GUI (solo utente corrente)."""
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{AUMID}") as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "DriverCore")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROTOCOL}") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:DriverCore")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROTOCOL}\shell\open\command") as k:
        exe, args = _command_line()
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}" {args}'.strip())


_TOAST_PS = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null; "
    "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml($env:DC_TOAST); "
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:DC_AUMID)"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
)


def show_notification(title: str, body: str) -> bool:
    try:
        register_app()
        res = _powershell(_TOAST_PS, {"DC_TOAST": toast_xml(title, body), "DC_AUMID": AUMID})
        return res.returncode == 0
    except Exception:
        return False


_REGISTER_PS = (
    "$a = New-ScheduledTaskAction -Execute $env:DC_EXE -Argument $env:DC_ARGS -WorkingDirectory $env:DC_DIR; "
    "if ($env:DC_FREQ -eq 'weekly') { $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 12:00 "
    "-RandomDelay (New-TimeSpan -Minutes 30) } "
    "else { $t = New-ScheduledTaskTrigger -Daily -At 12:00 -RandomDelay (New-TimeSpan -Minutes 30) }; "
    "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries "
    "-DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30); "
    "$p = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) "
    "-LogonType Interactive -RunLevel Limited; "
    "Register-ScheduledTask -TaskPath $env:DC_TPATH -TaskName $env:DC_TNAME -Action $a -Trigger $t -Settings $s "
    "-Principal $p -Description $env:DC_DESC "
    "-Force -ErrorAction Stop | Out-Null"
)
_UNREGISTER_PS = ("Get-ScheduledTask -TaskPath $env:DC_TPATH -TaskName $env:DC_TNAME -ErrorAction SilentlyContinue "
                  "| Unregister-ScheduledTask -Confirm:$false -ErrorAction Stop")
_NEXT_RUN_PS = ("$i = Get-ScheduledTask -TaskPath $env:DC_TPATH -TaskName $env:DC_TNAME -ErrorAction Stop "
                "| Get-ScheduledTaskInfo; if ($i.NextRunTime) { $i.NextRunTime.ToString('s') }")


def set_frequency(freq: str) -> tuple[bool, str]:
    """Attiva ("daily"/"weekly") o disattiva ("off") il controllo automatico. Ritorna (riuscito, messaggio)."""
    if freq not in FREQUENCIES:
        return False, tr("frequenza non valida: {value}", value=freq)
    env = {"DC_TPATH": TASK_PATH, "DC_TNAME": TASK_NAME}
    if freq == "off":
        res = _powershell(_UNREGISTER_PS, env)
    else:
        register_app()
        exe, args = _command_line("--auto-scan")
        res = _powershell(_REGISTER_PS, {**env, "DC_FREQ": freq, "DC_EXE": exe, "DC_ARGS": args,
                                         "DC_DESC": tr("Controlla i driver e avvisa se ci sono aggiornamenti. Non installa nulla."),
                                         "DC_DIR": str(BASE_DIR)})
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip().splitlines()
        return False, err[0][:160] if err else f"codice {res.returncode}"
    settings = _read_json(SETTINGS_FILE, {})
    settings["auto_scan"] = freq
    _write_json(SETTINGS_FILE, settings)
    return True, ""


def next_run() -> datetime | None:
    try:
        res = _powershell(_NEXT_RUN_PS, {"DC_TPATH": TASK_PATH, "DC_TNAME": TASK_NAME})
        out = (res.stdout or "").strip()
        return datetime.fromisoformat(out) if res.returncode == 0 and out else None
    except Exception:
        return None


def mark_seen(items: list[dict]) -> None:
    """La GUI ha appena mostrato queste novità: il controllo automatico non deve riannunciarle."""
    data = last_result()
    data["notified"] = sorted(set(data.get("notified", [])) | {i["key"] for i in items})
    try:
        _write_json(AUTO_SCAN_FILE, data)
    except OSError:
        pass


# --- Il controllo ---------------------------------------------------------------------
def run_scan() -> list[dict]:
    """Esegue il controllo senza installare nulla, salva il risultato e notifica le novità."""
    import pythoncom

    import wu_drivers
    from ignore_list import load_ignored_updates
    from wmi_fast import FastWMI

    import deep_catalog
    import driver_scanner
    from deep_catalog import deep_scan_peripherals, scan_problem_devices
    from driver_scanner import check_all_gpus

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "auto_scan.log", "w", encoding="utf-8") as log:
        for c in (deep_catalog.console, driver_scanner.console, wu_drivers.console):
            c.file = log
            c.width = 160
        log.write(tr("Controllo automatico del {when}", when=f"{datetime.now():%Y-%m-%d %H:%M}") + "\n")
        # Processo a sé: COM resta inizializzato fino all'uscita (rilasciarlo prima degli oggetti WMI dà errori)
        pythoncom.CoInitialize()
        c = FastWMI().prefetch()
        gpus = check_all_gpus(c)
        problems = scan_problem_devices(c)
        updates = deep_scan_peripherals(c, {d["device_id"] for d in problems if d.get("device_id")})
        wu_items, _ = wu_drivers.search_drivers(c.Win32_PnPSignedDriver(), frozenset(load_ignored_updates()))
        updates = wu_drivers.merge(updates, wu_items)

        items = summarize(gpus, problems, updates)
        previous = last_result()
        prev_keys = set(previous.get("notified", []))
        fresh = to_notify(items, prev_keys)
        # Restano "già notificate" solo le novità ancora presenti: se una sparisce e poi torna, si riavvisa
        notified = [i["key"] for i in items if i["key"] in prev_keys]
        if fresh:
            title, body = notification_text(fresh)
            shown = show_notification(title, body)
            log.write((tr("Notifica mostrata: {title}", title=title) if shown
                       else tr("Notifica NON mostrata: {title}", title=title)) + "\n")
            if shown:
                notified += [i["key"] for i in fresh]
        else:
            log.write(tr("Nessuna novità da notificare ({count} elementi già noti).", count=len(items)) + "\n")
        _write_json(AUTO_SCAN_FILE, {"time": datetime.now().isoformat(timespec="seconds"),
                                     "items": items, "notified": notified})
    return items


def main(argv: list[str]) -> None:
    if "--test" in argv or "--test-notify" in argv:
        ok = show_notification("DriverCore", tr("Notifica di prova: il controllo automatico funziona."))
        print("ok" if ok else "errore")
        return
    try:
        run_scan()
    except Exception:
        import traceback
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "auto_scan.log", "a", encoding="utf-8") as log:
            log.write(traceback.format_exc())


if __name__ == "__main__":
    main(sys.argv[1:])

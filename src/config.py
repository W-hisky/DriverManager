"""Percorsi e impostazioni condivise. Con la variabile d'ambiente DRIVERCORE_HOME puoi spostare i dati."""
import os
import sys
from pathlib import Path

APP_VERSION = "1.2.1"
# Aggiornamento automatico di DriverCore dalle GitHub Releases: "utente/repository" (pubblico).
# DriverCore legge latest.json dall'ultima release; build.py --release lo genera con l'impronta SHA-256.
# Vuoto = funzione disattivata (si imposta qui o con la variabile DRIVERCORE_UPDATE_REPO).
UPDATE_REPO = os.environ.get("DRIVERCORE_UPDATE_REPO", "W-hisky/DriverManager").strip().strip("/")
MANIFEST_NAME = "latest.json"


def release_manifest_url(repo: str) -> str:
    """Indirizzo fisso che GitHub reindirizza al file dell'ultima release (esclusi bozze e pre-release)."""
    return f"https://github.com/{repo}/releases/latest/download/{MANIFEST_NAME}" if repo else ""


def release_asset_url(repo: str, version: str, name: str = "DriverCore.exe") -> str:
    return f"https://github.com/{repo}/releases/download/v{version}/{name}"


# Un manifest su un altro server https resta possibile con DRIVERCORE_UPDATE_URL
UPDATE_MANIFEST_URL = os.environ.get("DRIVERCORE_UPDATE_URL", "") or release_manifest_url(UPDATE_REPO)

SRC_DIR = Path(__file__).resolve().parent
# True quando gira come DriverCore.exe (PyInstaller)
FROZEN = bool(getattr(sys, "frozen", False))


def app_command(*args: str, windowed: bool = True) -> tuple[str, list[str]]:
    """Programma e argomenti per avviare DriverCore (GUI, o con --auto-scan il controllo automatico).

    Da .exe è l'eseguibile stesso; da sorgente è pythonw/python del venv con gui.py.
    """
    if FROZEN:
        return sys.executable, list(args)
    venv = Path(os.environ.get("DRIVERCORE_HOME", "C:/DriverManager")) / ".venv" / "Scripts"
    name = "pythonw.exe" if windowed else "python.exe"
    exe = next((p for p in (venv / name, Path(sys.executable).with_name(name)) if p.exists()), Path(sys.executable))
    return str(exe), [str(SRC_DIR / "gui.py"), *args]
BASE_DIR = Path(os.environ.get("DRIVERCORE_HOME", "C:/DriverManager"))

BACKUP_ROOT = BASE_DIR / "backups"
DOWNLOAD_DIR = BASE_DIR / "downloads"
CAB_DIR = DOWNLOAD_DIR / "cab_temp"
# Pacchetti del Catalog scaricati per la verifica (riusati per l'installazione) e verdetti già calcolati
CATALOG_PKG_DIR = DOWNLOAD_DIR / "catalog"
VERDICTS_FILE = BASE_DIR / "package_verdicts.json"
LOG_DIR = BASE_DIR / "logs"
# Aggiornamenti del Catalog che Windows ha rifiutato per le periferiche presenti: non riproporli
IGNORED_UPDATES_FILE = BASE_DIR / "ignored_updates.json"
# Cronologia delle installazioni (per annullare il singolo aggiornamento)
HISTORY_FILE = BASE_DIR / "driver_history.json"
# Impostazioni dell'utente (es. frequenza del controllo automatico) e risultato dell'ultimo controllo automatico
SETTINGS_FILE = BASE_DIR / "settings.json"
AUTO_SCAN_FILE = BASE_DIR / "last_auto_scan.json"
SEVEN_ZIP = Path("C:/Program Files/7-Zip/7z.exe")

# Quanti backup completi dei driver conservare (ognuno occupa alcuni GB)
BACKUP_KEEP = max(1, int(os.environ.get("DRIVERCORE_BACKUP_KEEP", "3")))
# Organizzazione (campo O= del certificato) che deve firmare l'installer NVIDIA
NVIDIA_SIGNER_ORG = "NVIDIA Corporation"

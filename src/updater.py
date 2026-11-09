"""Aggiornamento automatico di DriverCore.exe.

Il manifest (UPDATE_MANIFEST_URL) è un JSON: {"version", "url", "sha256", "notes"}.
Sicurezza:
- il file scaricato si usa solo se il suo SHA-256 coincide con quello del manifest (solo https);
- se l'eseguibile attuale è firmato, anche il nuovo deve essere firmato dallo stesso editore.
Sostituzione: DriverCore.exe è in uso mentre gira, quindi uno script PowerShell nascosto aspetta che il programma
si chiuda, mette il nuovo file al posto del vecchio e lo riavvia.
"""
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
from packaging import version as pkg_version

from config import APP_VERSION, DOWNLOAD_DIR, FROZEN, UPDATE_MANIFEST_URL
from i18n import tr

NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = 0x00000008  # DETACHED_PROCESS: lo script sopravvive alla chiusura di DriverCore
UPDATE_DIR = DOWNLOAD_DIR / "update"
CHECK_EVERY_S = 24 * 3600
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class UpdateError(Exception):
    pass


def parse_manifest(data) -> dict:
    """Valida il manifest; solleva UpdateError se manca qualcosa o non è sicuro."""
    if not isinstance(data, dict):
        raise UpdateError(tr("manifest non valido"))
    ver, url, sha = str(data.get("version", "")).strip(), str(data.get("url", "")).strip(), str(data.get("sha256", "")).strip()
    try:
        pkg_version.parse(ver)
    except Exception:
        raise UpdateError(tr("versione non valida nel manifest: {value}", value=ver or "—"))
    if not url.lower().startswith("https://"):
        raise UpdateError(tr("l'indirizzo del file deve usare https"))
    if not _SHA256.match(sha):
        raise UpdateError(tr("impronta SHA-256 mancante o non valida"))
    return {"version": ver, "url": url, "sha256": sha.lower(), "notes": str(data.get("notes", "") or "")}


def is_newer(remote: str, local: str = APP_VERSION) -> bool:
    try:
        return pkg_version.parse(remote) > pkg_version.parse(local)
    except Exception:
        return False


def configured(url: str | None = None) -> bool:
    return bool((url if url is not None else UPDATE_MANIFEST_URL).strip())


def check(client: httpx.Client | None = None, url: str | None = None) -> dict | None:
    """Manifest se c'è una versione più nuova, altrimenti None. Solleva UpdateError (o httpx.HTTPError)."""
    url = (url if url is not None else UPDATE_MANIFEST_URL).strip()
    if not url:
        raise UpdateError(tr("aggiornamenti automatici non configurati"))
    own = client is None
    client = client or httpx.Client(timeout=15.0, follow_redirects=True,
                                    headers={"User-Agent": f"DriverCore/{APP_VERSION}"})
    try:
        resp = client.get(url)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            raise UpdateError(tr("manifest non valido"))
        info = parse_manifest(data)
    finally:
        if own:
            client.close()
    return info if is_newer(info["version"]) else None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(info: dict, client: httpx.Client | None = None, dest_dir: Path | None = None) -> Path:
    """Scarica e verifica il nuovo eseguibile. Ritorna il percorso del file verificato."""
    dest_dir = dest_dir or UPDATE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"DriverCore-{info['version']}.exe"
    part = dest.with_suffix(".part")
    own = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True,
                                    headers={"User-Agent": f"DriverCore/{APP_VERSION}"})
    try:
        with client.stream("GET", info["url"]) as resp:
            resp.raise_for_status()
            with open(part, "wb") as f:
                for chunk in resp.iter_bytes(1 << 16):
                    f.write(chunk)
    finally:
        if own:
            client.close()
    if sha256_of(part) != info["sha256"]:
        part.unlink(missing_ok=True)
        raise UpdateError(tr("il file scaricato non corrisponde all'impronta del manifest"))
    part.replace(dest)
    _check_signer(dest)
    return dest


def _signer(path: Path) -> str | None:
    from driver_installer import subject_organization
    ps = ("$s = Get-AuthenticodeSignature -LiteralPath $env:DC_SIG; "
          "if ($s.Status -eq 'Valid') { $s.SignerCertificate.Subject }")
    res = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                         encoding="oem", errors="replace", creationflags=NO_WIN, timeout=60,
                         env={**os.environ, "DC_SIG": str(path)})
    return subject_organization((res.stdout or "").strip()) if res.returncode == 0 else None


def _check_signer(new_exe: Path) -> None:
    """Se l'eseguibile attuale è firmato, il nuovo deve avere lo stesso editore."""
    if not FROZEN:
        return
    current = _signer(Path(sys.executable))
    if current and _signer(new_exe) != current:
        new_exe.unlink(missing_ok=True)
        raise UpdateError(tr("il nuovo file non è firmato da {org}", org=current))


SWAP_PS = (
    "foreach ($p in ($env:DC_PIDS -split ',')) { Wait-Process -Id ([int]$p) -ErrorAction SilentlyContinue }; "
    "$ok = $false; "
    "for ($i = 0; $i -lt 40 -and -not $ok; $i++) { "
    "  try { Move-Item -LiteralPath $env:DC_NEW -Destination $env:DC_OLD -Force -ErrorAction Stop; $ok = $true } "
    "  catch { Start-Sleep -Milliseconds 500 } }; "
    "Start-Process -FilePath $env:DC_OLD"
)


def apply_and_restart(new_exe: Path) -> None:
    """Avvia lo scambio dei file e ritorna: il chiamante deve chiudere DriverCore subito dopo."""
    if not FROZEN:
        raise UpdateError(tr("l'aggiornamento automatico funziona solo con DriverCore.exe"))
    # Nel .exe a file unico il file è tenuto aperto dal processo padre (quello che scompatta): si aspettano entrambi
    pids = f"{os.getpid()},{os.getppid()}"
    subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", SWAP_PS],
                     creationflags=NO_WIN | DETACHED, close_fds=True,
                     env={**os.environ, "DC_PIDS": pids, "DC_NEW": str(new_exe), "DC_OLD": sys.executable})


def due(last_check: float | None, now: float | None = None) -> bool:
    """Controllo automatico al massimo una volta al giorno."""
    return not last_check or (now or time.time()) - float(last_check) >= CHECK_EVERY_S

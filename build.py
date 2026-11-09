"""Crea dist\\DriverCore.exe (GUI, file unico) con PyInstaller.

    .venv\\Scripts\\python build.py              solo la GUI
    .venv\\Scripts\\python build.py --console    anche DriverCore-Console.exe (menu testuale)
    .venv\\Scripts\\python build.py --release --notes "Novità"   anche dist\\latest.json per GitHub Releases

Lo stesso DriverCore.exe esegue anche il controllo automatico (DriverCore.exe --auto-scan).
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# La console di Windows usa cp1252, che non ha simboli come ✔: senza questo il build si ferma su una print
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
BUILD = ROOT / "build"
ASSETS = ROOT / "assets"
ICON = ASSETS / "DriverCore.ico"
sys.path.insert(0, str(SRC))
from config import APP_VERSION  # noqa: E402  (una sola fonte per il numero di versione)

VERSION = tuple(int(x) for x in (APP_VERSION.split(".") + ["0"] * 4)[:4])
ACCENT = (31, 111, 235)
EXCLUDE = ["numpy", "yaml", "win32ui", "pythonwin", "PIL._avif", "PIL.AvifImagePlugin", "PIL._webp",
           "PIL.WebPImagePlugin", "PIL._imagingcms", "PIL.ImageCms", "unittest", "pydoc", "tkinter.test",
           "lib2to3", "xmlrpc", "pdb"]


def make_icon() -> None:
    """Icona: quadrato arrotondato blu con un chip bianco stilizzato (disegnata a 1024 px e ridotta)."""
    if ICON.exists():
        return
    ASSETS.mkdir(exist_ok=True)
    s = 1024
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, s - 40, s - 40), radius=230, fill=ACCENT)
    white = (255, 255, 255)
    d.rounded_rectangle((322, 322, 702, 702), radius=60, outline=white, width=56)
    d.rounded_rectangle((440, 440, 584, 584), radius=24, fill=white)
    for i in range(3):  # piedini del chip sui quattro lati
        o = 392 + i * 120
        for box in ((o - 22, 200, o + 22, 300), (o - 22, 724, o + 22, 824),
                    (200, o - 22, 300, o + 22), (724, o - 22, 824, o + 22)):
            d.rounded_rectangle(box, radius=22, fill=white)
    img.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def version_file(name: str, description: str) -> Path:
    v = ", ".join(map(str, VERSION))
    dotted = ".".join(map(str, VERSION))
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v}), prodvers=({v}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
  kids=[
    StringFileInfo([StringTable('041004B0', [
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{dotted}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', 'DriverCore'),
      StringStruct('ProductVersion', '{dotted}')])]),
    VarFileInfo([VarStruct('Translation', [0x0410, 1200])])
  ]
)
"""
    path = BUILD / f"{name}_version.txt"
    path.write_text(text, encoding="utf-8")
    return path


def pyinstaller(script: str, name: str, description: str, windowed: bool, extra: list[str]) -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller", str(SRC / script),
        "--name", name, "--onefile", "--noconfirm", "--clean",
        "--windowed" if windowed else "--console",
        "--icon", str(ICON), "--version-file", str(version_file(name, description)),
        "--paths", str(SRC), "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD / name), "--specpath", str(BUILD),
        # customtkinter carica temi e font da file: vanno inclusi
        "--collect-data", "customtkinter",
        "--hidden-import", "win32timezone",
        # moduli caricati solo in certi percorsi (controllo automatico, cronologia)
        "--hidden-import", "auto_scan", "--hidden-import", "driver_history", "--hidden-import", "wmi_fast",
        "--hidden-import", "locale_en",
        # Librerie trascinate dalle dipendenze ma mai caricate dal programma (verificato a runtime):
        # numpy da sola è il 40% del pacchetto e rallenta lo scompattamento a ogni avvio
        *[a for mod in EXCLUDE for a in ("--exclude-module", mod)],
        *extra,
    ]
    print(">", name)
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    make_icon()
    pyinstaller("gui.py", "DriverCore", "DriverCore - gestione driver", windowed=True, extra=[])
    if "--console" in sys.argv:
        # Il menu testuale richiede l'amministratore: lo chiede il manifesto dell'eseguibile
        pyinstaller("main.py", "DriverCore-Console", "DriverCore - menu testuale", windowed=False,
                    extra=["--uac-admin"])
    for exe in sorted((ROOT / "dist").glob("*.exe")):
        print(f"✔ {exe}  ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    shutil.rmtree(BUILD / "__pycache__", ignore_errors=True)
    if "--release" in sys.argv:
        write_manifest(ROOT / "dist" / "DriverCore.exe", _arg("--notes"))


def _arg(name: str) -> str:
    """Valore dopo un'opzione: --notes "testo"."""
    args = sys.argv[1:]
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else ""


def write_manifest(exe: Path, notes: str = "") -> Path:
    """dist\\latest.json per la release GitHub v{APP_VERSION}, con l'impronta dell'eseguibile appena creato."""
    import hashlib
    import json
    from config import MANIFEST_NAME, UPDATE_REPO, release_asset_url
    if not UPDATE_REPO:
        sys.exit("✘ Imposta UPDATE_REPO in src\\config.py (es. \"utente/DriverCore\") e ricompila: "
                 "è il repository che l'eseguibile controllerà.")
    h = hashlib.sha256()
    with open(exe, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    manifest = {"version": APP_VERSION, "url": release_asset_url(UPDATE_REPO, APP_VERSION),
                "sha256": h.hexdigest(), "notes": notes}
    out = exe.parent / MANIFEST_NAME
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✔ {out}\n  Release da creare: tag v{APP_VERSION} su https://github.com/{UPDATE_REPO}/releases/new\n"
          f"  File da allegare: DriverCore.exe e {MANIFEST_NAME}")
    return out


if __name__ == "__main__":
    main()

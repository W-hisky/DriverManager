"""Permette di testare la logica pura anche fuori da Windows (CI/Linux) simulando i moduli Windows."""
import os
import subprocess
import sys

# I test controllano i testi italiani (la lingua del codice), qualunque sia la lingua di Windows
os.environ["DRIVERCORE_LANG"] = "it"
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

if not hasattr(subprocess, "CREATE_NO_WINDOW"):
    subprocess.CREATE_NO_WINDOW = 0

for name in ("wmi", "winreg"):
    sys.modules.setdefault(name, types.ModuleType(name))
win32com = types.ModuleType("win32com")
win32com.client = types.ModuleType("win32com.client")
sys.modules.setdefault("win32com", win32com)
sys.modules.setdefault("win32com.client", win32com.client)

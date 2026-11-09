"""Lettura veloce di WMI, con la stessa interfaccia minima del modulo `wmi` usata nel programma.

- COM diretto (WbemScripting) invece del modulo `wmi`: leggere i valori costa molto meno.
- Solo le colonne che il programma usa davvero.
- Una sola lettura per oggetto FastWMI: problemi, periferiche e pulizia condividono lo stesso elenco.
- Le periferiche in errore si chiedono a WMI con un filtro (in pratica istantaneo).

Misure su questo PC: Win32_PnPSignedDriver 2,7 s -> 0,9 s; le periferiche in errore 2 s -> 0,03 s.
I risultati sono oggetti Python semplici: si possono usare da qualunque thread una volta letti.
"""
from types import SimpleNamespace

DRIVER_COLS = ("DeviceID", "DeviceName", "DriverVersion", "DriverProviderName", "HardWareID", "InfName",
               "DriverDate", "DeviceClass")
ENTITY_COLS = ("DeviceID", "Name", "Description", "ConfigManagerErrorCode", "Present", "HardwareID", "CompatibleID")
VIDEO_COLS = ("Name", "PNPDeviceID", "DriverVersion", "InfFilename")
_FORWARD_ONLY = 0x30  # wbemFlagReturnImmediately | wbemFlagForwardOnly: niente copia dell'elenco lato WMI


class FastWMI:
    def __init__(self):
        import win32com.client
        self._svc = win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer(".", "root\\cimv2")
        self._cache: dict[str, list] = {}

    def _query(self, key: str, cls: str, cols: tuple, where: str = "") -> list:
        if key not in self._cache:
            wql = f"SELECT {', '.join(cols)} FROM {cls}" + (f" WHERE {where}" if where else "")
            self._cache[key] = [SimpleNamespace(**{c: getattr(o, c) for c in cols})
                                for o in self._svc.ExecQuery(wql, "WQL", _FORWARD_ONLY)]
        return self._cache[key]

    def select(self, cls: str, cols: tuple, where: str = "") -> list:
        """Query qualsiasi (colonne esplicite), con cache come le altre."""
        return self._query(f"{cls}|{','.join(cols)}|{where}", cls, cols, where)

    def refresh(self) -> None:
        """Dimentica i dati letti (dopo un'installazione)."""
        self._cache.clear()

    def Win32_PnPSignedDriver(self):
        return self._query("drivers", "Win32_PnPSignedDriver", DRIVER_COLS)

    def Win32_PnPEntity(self):
        return self._query("entities", "Win32_PnPEntity", ENTITY_COLS)

    def problem_entities(self):
        """Solo le periferiche con un codice di errore in Gestione dispositivi."""
        return self._query("problems", "Win32_PnPEntity", ENTITY_COLS, "ConfigManagerErrorCode <> 0")

    def Win32_VideoController(self):
        return self._query("video", "Win32_VideoController", VIDEO_COLS)

    def prefetch(self) -> "FastWMI":
        """Legge subito tutto ciò che serve a una scansione: poi i dati si usano anche da altri thread."""
        self.Win32_VideoController()
        self.Win32_PnPSignedDriver()
        self.problem_entities()
        return self

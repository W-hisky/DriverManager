"""Lettura degli INF e simulazione di come Windows sceglie il driver per una periferica.

Regole (Microsoft Learn, "How Windows Ranks Driver Packages"):
- rank = 0xSSGGTHHH, più basso = migliore. SS firma (qui uguale: arrivano tutti da fonti firmate),
  GG = FeatureScore del DDInstall (0xFF se assente), THHH = punteggio dell'identificatore:
    0x0000+p  ID hardware della periferica (posizione p) = ID hardware dell'INF
    0x1000+p  ID hardware della periferica (posizione p) = ID compatibile dell'INF
    0x2000+p  ID compatibile della periferica (posizione p) = ID hardware dell'INF
    0x3000+j+k*0x100  ID compatibile della periferica (j) = ID compatibile dell'INF (k)
- a parità di rank vince la data DriverVer più recente, poi la versione più alta.
"""
from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from packaging import version as pkg_version

from i18n import fmt_date, tr

DEFAULT_FEATURE_SCORE = 0xFF


@dataclass(frozen=True)
class OsInfo:
    arch: str = "amd64"
    major: int = 10
    minor: int = 0
    product_type: int = 1  # 1 = workstation
    build: int = 0


@dataclass(frozen=True)
class Match:
    rank: int
    hwid: str           # ID dell'INF che ha fatto corrispondenza
    install: str        # sezione DDInstall
    inf: str            # file INF


def current_os() -> OsInfo:
    try:
        v = sys.getwindowsversion()
        machine = platform.machine().lower()
        arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "x86": "x86"}.get(machine, machine)
        return OsInfo(arch, v.major, v.minor, getattr(v, "product_type", 1), v.build)
    except AttributeError:  # non Windows (test)
        return OsInfo(build=26100)


# --- Lettura INF ---------------------------------------------------------------
class Inf:
    def __init__(self, text: str, name: str = ""):
        self.name = name
        self.sections: dict[str, list[str]] = {}
        self.strings: dict[str, str] = {}
        current = None
        pending = ""
        for raw in text.splitlines():
            line = pending + _strip_comment(raw).strip()
            pending = ""
            if line.endswith("\\"):  # continuazione di riga
                pending = line[:-1]
                continue
            if not line:
                continue
            m = re.fullmatch(r"\[([^\]]+)\]", line)
            if m:
                current = m.group(1).strip().lower()
                self.sections.setdefault(current, [])
                continue
            if current is not None:
                self.sections[current].append(line)
        for sec, lines in self.sections.items():
            if sec == "strings" or sec.startswith("strings."):
                for line in lines:
                    k, _, v = line.partition("=")
                    self.strings.setdefault(k.strip().lower(), v.strip().strip('"'))

    @classmethod
    def load(cls, path: Path) -> "Inf":
        data = Path(path).read_bytes()
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = data.decode("utf-16")
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("cp1252", errors="replace")
        return cls(text, Path(path).name)

    def expand(self, value: str) -> str:
        return re.sub(r"%([^%]+)%", lambda m: self.strings.get(m.group(1).lower(), m.group(0)), value)

    def entries(self, section: str) -> list[tuple[str, list[str]]]:
        """Righe 'chiave = v1, v2, ...' di una sezione (valori espansi, senza virgolette)."""
        out = []
        for line in self.sections.get(section.lower(), []):
            key, sep, rest = line.partition("=")
            values = [self.expand(v.strip().strip('"')) for v in rest.split(",")] if sep else []
            out.append((key.strip(), values))
        return out

    def directive(self, section: str, name: str) -> str | None:
        for key, values in self.entries(section):
            if key.lower() == name.lower():
                return ",".join(values)
        return None


def _strip_comment(line: str) -> str:
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ";" and not in_quote:
            return line[:i]
    return line


def parse_driver_ver(value: str | None) -> tuple[date | None, str]:
    """'07/10/2025,1168.026.50.2025' -> (date(2025, 7, 10), '1168.26.50.2025'). Formato INF: mese/giorno/anno."""
    if not value:
        return None, ""
    d_str, _, v_str = value.partition(",")
    d = None
    m = re.fullmatch(r"\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*", d_str)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            d = None
    ver = ".".join(str(int(p)) for p in re.findall(r"\d+", v_str)) if v_str.strip() else ""
    return d, ver


def inf_driver_ver(path: Path) -> tuple[date | None, str]:
    """DriverVer di un INF installato (data affidabile: WMI la converte con la lingua di Windows e sbaglia)."""
    try:
        return parse_driver_ver(Inf.load(path).directive("version", "DriverVer"))
    except OSError:
        return None, ""


# --- Scelta delle sezioni Models per questo sistema -----------------------------
def _decoration_applies(deco: str, osinfo: OsInfo):
    """None se la decorazione non vale per questo sistema, altrimenti una chiave di specificità."""
    parts = deco.lower().split(".")
    head = parts[0]
    if not head.startswith("nt"):
        return None
    arch = head[2:]
    if arch and arch != osinfo.arch:
        return None
    nums = parts[1:] + [""] * 5
    major, minor, ptype, _suite, build = nums[:5]
    try:
        if major and (int(major), int(minor or 0)) > (osinfo.major, osinfo.minor):
            return None
        if ptype and int(ptype, 0) != osinfo.product_type:
            return None
        if build and int(build) > osinfo.build:
            return None
        return (int(major or 0), int(minor or 0), int(build or 0), 1 if arch else 0)
    except ValueError:
        return None


def models_sections(inf: Inf, osinfo: OsInfo) -> list[str]:
    """Le sezioni Models che Windows usa su questo sistema (la decorazione più specifica per produttore)."""
    out = []
    for _key, values in inf.entries("manufacturer"):
        if not values or not values[0]:
            continue
        base, decos = values[0], [d for d in values[1:] if d]
        best = None
        for d in decos:
            spec = _decoration_applies(d, osinfo)
            if spec is not None and (best is None or spec > best[0]):
                best = (spec, d)
        if best:
            out.append(f"{base}.{best[1]}")
        elif not decos and osinfo.arch == "x86":
            out.append(base)  # sezione non decorata: valida solo su x86
    return out


def feature_score(inf: Inf, install: str, osinfo: OsInfo) -> int:
    for sec in (f"{install}.nt{osinfo.arch}", f"{install}.nt", install):
        if sec.lower() in inf.sections:
            raw = inf.directive(sec, "FeatureScore")
            if raw:
                try:
                    return int(raw.strip(), 0) & 0xFF
                except ValueError:
                    pass
            return DEFAULT_FEATURE_SCORE
    return DEFAULT_FEATURE_SCORE


def best_match(inf: Inf, hwids: list[str], compids: list[str], osinfo: OsInfo) -> Match | None:
    """La corrispondenza migliore (rank più basso) tra la periferica e questo INF, se c'è."""
    dev_hw = [h.upper() for h in hwids]
    dev_comp = [c.upper() for c in compids]
    best = None
    for section in models_sections(inf, osinfo):
        for _desc, values in inf.entries(section):
            if len(values) < 2:
                continue
            install = values[0]
            ids = [v.upper() for v in values[1:] if v]
            if not ids:
                continue
            inf_hw, inf_comp = ids[0], ids[1:]
            scores = []
            if inf_hw in dev_hw:
                scores.append((0x0000 + dev_hw.index(inf_hw), inf_hw))
            for c in inf_comp:
                if c in dev_hw:
                    scores.append((0x1000 + dev_hw.index(c), c))
            if inf_hw in dev_comp:
                scores.append((0x2000 + dev_comp.index(inf_hw), inf_hw))
            for k, c in enumerate(inf_comp):
                if c in dev_comp:
                    scores.append((0x3000 + dev_comp.index(c) + k * 0x100, c))
            if not scores:
                continue
            ident, hit = min(scores)
            rank = (feature_score(inf, install, osinfo) << 16) | ident
            if best is None or rank < best.rank:
                best = Match(rank, hit, install, inf.name)
    return best


def best_match_in_package(folder: Path, hwids, compids, osinfo: OsInfo):
    """(Match, data, versione) migliore tra tutti gli INF di un pacchetto estratto."""
    best = None
    for path in sorted(Path(folder).rglob("*.inf")):
        try:
            inf = Inf.load(path)
        except OSError:
            continue
        m = best_match(inf, hwids, compids, osinfo)
        if m is None:
            continue
        d, v = parse_driver_ver(inf.directive("version", "DriverVer"))
        if best is None or _better(m.rank, d, v, best[0].rank, best[1], best[2]):
            best = (m, d, v)
    return best


def _ver_key(v: str):
    try:
        return pkg_version.parse(v or "0")
    except pkg_version.InvalidVersion:
        return pkg_version.parse("0")


def _better(rank_a, date_a, ver_a, rank_b, date_b, ver_b) -> bool:
    """True se A batte B secondo Windows: rank più basso, poi data più recente, poi versione più alta."""
    if rank_a != rank_b:
        return rank_a < rank_b
    da, db = date_a or date.min, date_b or date.min
    if da != db:
        return da > db
    return _ver_key(ver_a) > _ver_key(ver_b)


def _fmt(d: date | None) -> str:
    return fmt_date(d)


def judge(candidate, installed) -> tuple[bool, str]:
    """Windows applicherebbe il pacchetto? candidate/installed: (Match, data, versione) o None.

    Ritorna (sì/no, motivo leggibile)."""
    if candidate is None:
        return False, tr("Il pacchetto non contiene questa periferica per la tua versione di Windows.")
    if installed is None:
        return True, tr("Il pacchetto contiene questa periferica.")
    (mc, dc, vc), (mi, di, vi) = candidate, installed
    if mc.rank != mi.rank:
        if mc.rank < mi.rank:
            return True, tr("Corrispondenza più precisa del driver installato.")
        return False, tr("Windows preferisce il driver installato: corrisponde in modo più preciso alla periferica.")
    if (dc or date.min) != (di or date.min):
        if (dc or date.min) > (di or date.min):
            return True, tr("Data più recente del driver installato ({new} contro {old}).", new=_fmt(dc), old=_fmt(di))
        return False, tr("Il driver installato ha una data più recente ({old} contro {new}): "
                         "Windows lo terrà anche se il numero di versione è più basso.", old=_fmt(di), new=_fmt(dc))
    if _ver_key(vc) > _ver_key(vi):
        return True, tr("Stessa data, versione più alta.")
    return False, tr("Stessa data e versione non più alta: Windows terrà il driver installato.")
# DriverCore – Personal Driver Manager

Gestore di driver per Windows 10/11 (solo uso personale): controlla NVIDIA (API ufficiale), cerca driver WHQL sul
Microsoft Update Catalog, crea backup/punti di ripristino e pulisce il DriverStore. Richiede privilegi di amministratore.

## Avvio
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python src\gui.py      # interfaccia grafica
.venv\Scripts\python src\main.py     # versione a console
```
I dati (backup, download, log) stanno in `C:\DriverManager`; per spostarli imposta la variabile `DRIVERCORE_HOME`.
Per la modalità SLIM NVIDIA serve 7-Zip in `C:\Program Files\7-Zip`.

## Eseguibile
```
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python build.py             # dist\DriverCore.exe (GUI, file unico)
.venv\Scripts\python build.py --console   # anche dist\DriverCore-Console.exe
```
`DriverCore.exe` chiede da solo i diritti di amministratore all'avvio. Con `--auto-scan` esegue il controllo
automatico (è ciò che avvia l'Utilità di pianificazione), con `--selftest` verifica il pacchetto senza mostrare finestre.
I dati restano in `C:\DriverManager` (o in `DRIVERCORE_HOME`). Il file non è firmato: Windows SmartScreen può
mostrare un avviso al primo avvio.

## Lingua
Italiano o inglese: di default segue la lingua di Windows; si cambia dalla card Impostazioni (vale dal riavvio)
o con la variabile `DRIVERCORE_LANG=it|en`. I testi italiani nel codice passano da `tr()`; l'inglese è in
`src/locale_en.py` e `tests/test_i18n.py` verifica che ogni testo abbia la traduzione con gli stessi segnaposto.

## Tema
Chiaro o scuro: di default segue il tema delle app di Windows; si cambia dalla card Impostazioni (vale dal riavvio)
o con `DRIVERCORE_THEME=light|dark`. Entrambe le palette rispettano il contrasto WCAG AA (4,5:1) per il testo.

## Aggiornamento automatico di DriverCore
Le nuove versioni si pubblicano come GitHub Releases. Una volta sola: crea un repository **pubblico** (gli allegati
dei repository privati non si scaricano senza login) e scrivi `UPDATE_REPO = "utente/repository"` in `src/config.py`.

Per ogni versione:
1. aumenta `APP_VERSION` in `src/config.py` (es. `1.2.0`);
2. `.venv\Scripts\python build.py --release --notes "Novità di questa versione"`
   crea `dist\DriverCore.exe` e `dist\latest.json` (versione, indirizzo e impronta SHA-256 del file);
3. su GitHub crea la release con tag `v1.2.0` (non come bozza né pre-release) e allega **entrambi** i file.

DriverCore legge `https://github.com/<repository>/releases/latest/download/latest.json` una volta al giorno
(e con «Cerca aggiornamenti»). Il nuovo eseguibile si usa solo se l'impronta coincide; se l'eseguibile attuale è
firmato, anche il nuovo deve esserlo dallo stesso editore. Un manifest su un altro server https resta possibile con
la variabile `DRIVERCORE_UPDATE_URL`:
```json
{"version": "1.2.0", "url": "https://.../DriverCore.exe", "sha256": "<impronta SHA-256 del file>", "notes": "Novità"}
```

## Diagnostica
«Esporta diagnostica» (card Impostazioni) crea uno zip con log, impostazioni, cronologia, aggiornamenti ignorati
e un riepilogo del sistema (Windows, CPU, RAM, schede video, driver di terze parti). Nessun file personale.

## Moduli
- `updater.py` – aggiornamento automatico di DriverCore.exe (manifest, verifica SHA-256 e firma, sostituzione)
- `diagnostics.py` – esportazione della diagnostica in un file zip
- `prefs.py` – preferenze dell'utente in settings.json
- `driver_scanner.py` – controllo delle schede video, inventario driver, Windows Update
- `gpu_check.py` – driver GPU dalle fonti ufficiali: NVIDIA (tutte le serie, desktop e notebook), Intel Arc/Iris Xe, AMD Adrenalin
- `deep_catalog.py` – ricerca sul Microsoft Update Catalog, periferiche in errore, verifica e installazione dei pacchetti
- `inf_rank.py` – lettura degli INF e simulazione della scelta del driver da parte di Windows (rank, data, versione)
- `driver_history.py` – cronologia delle installazioni e annullamento del singolo aggiornamento
- `auto_scan.py` – controllo automatico pianificato (Utilità di pianificazione) e notifiche di Windows
- `wu_drivers.py` – driver proposti da Windows Update (ricerca in parallelo alla scansione, installazione)
- `ignore_list.py` – aggiornamenti ignorati dall'utente o rifiutati da Windows, con ripristino
- `single_instance.py` – una sola finestra: un secondo avvio porta in primo piano quella aperta
- `wmi_fast.py` – lettura veloce di WMI (COM diretto, solo le colonne utili, una lettura per scansione)
- `driver_cleanup.py` – rimozione dei pacchetti driver obsoleti dal DriverStore
- `driver_installer.py` – backup, download/installazione NVIDIA, runtime, punto di ripristino, MSI
- `config.py` – percorsi condivisi

## Test
```
pip install -r requirements-dev.txt
pytest
```
I test coprono la logica pura e girano anche fuori da Windows.

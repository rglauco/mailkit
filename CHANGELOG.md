# Changelog

## [1.6.1] - 2026-05-17

### Added

- **Cifratura della password nel JSON di configurazione**: `smtp_pass` viene ora salvata cifrata con AES-256 (Fernet) in `smtp_config.json`. La decifratura avviene automaticamente al caricamento; i file di config esistenti con password in chiaro continuano a funzionare senza intervento (retrocompatibilità garantita tramite prefisso `enc:`).
- **Segreto di build personalizzabile per la modalità locked**: gli amministratori possono ora differenziare il segreto usato per cifrare `smtp.key` rispetto alla chiave default pubblica, rendendo la build specifica dell'organizzazione.
  - Nuovo script **`build_env.py`**: legge `MAILKIT_SECRET` da `.env` o variabile d'ambiente, deriva i frammenti di chiave via PBKDF2 e genera `_secret.py` da includere nella build.
  - `_secret.py` viene importato automaticamente da `gui.py` e `genera_smtp_key.py`; se assente, si usa il segreto default (comportamento invariato rispetto alle versioni precedenti).
  - `genera_smtp_key.py` aggiornato per importare i frammenti da `_secret.py` con fallback al default.
- **Supporto GitHub Actions per build admin con segreto custom**: il workflow `build.yml` esegue `build_env.py` prima di PyInstaller se il secret `MAILKIT_SECRET` è configurato nel repository.
- `_secret.py` aggiunto a `.gitignore`.

### Changed

- `_derive_key()` usa ora i frammenti di `_secret.py` (se disponibili) invece dei frammenti hardcoded, per generare la chiave di `smtp.key` nelle build admin.
- Aggiunta `_derive_config_key()`: chiave separata, sempre derivata dai frammenti default (100k iterazioni PBKDF2, risultato cachato), usata esclusivamente per cifrare `smtp_pass` nel JSON.
- `save_config()` cifra `smtp_pass` prima di scrivere su disco (solo in modalità non-locked).
- `load_config()` decifra `smtp_pass` se il valore inizia con `enc:`.

### Security

- La password SMTP dell'utente non è mai in chiaro su disco, né in modalità personale (JSON cifrato) né in modalità locked (JSON vuoto, password in `smtp.key`).
- Il segreto di build admin è ora separato dal segreto default distribuito pubblicamente con il sorgente: una build dell'organizzazione non può essere decifrata con strumenti derivati dal codice pubblico.

## [1.5.0] - 2026-05-15

### Added

- **Check pre-invio sui file di log**: prima di avviare il thread di invio, `_check_files_accessible()` verifica che CSV e log non siano bloccati da altri processi (es. Excel aperto sul file CSV). Se un file non è accessibile, viene mostrato un `QMessageBox.warning` con il percorso esatto del file da chiudere; l'invio non parte finché il problema non è risolto.
- **Tab "📋 Storico"** (terza tab): conserva uno storico degli invii con oggetto, corpo HTML e allegati.
  - Al click su **"📧 Invia Email"** viene salvata automaticamente una voce in `storico.json` con timestamp, oggetto, HTML del corpo e percorsi degli allegati; gli allegati vengono copiati nella sottocartella `storico_allegati/YYYY-MM-DD_HH-MM-SS/` nella directory di lavoro.
  - Le voci sono elencate dalla più recente, con oggetto, timestamp e numero di allegati.
  - **Doppio click** o pulsante **"📂 Carica in Invio"** ripristina oggetto, corpo e allegati nel tab Invio e porta l'utente su quel tab.
  - Se un allegato salvato non è più reperibile sul disco al momento del caricamento, viene mostrato un avviso con l'elenco dei file mancanti; gli allegati ancora presenti vengono caricati normalmente.
  - Pulsante **"🗑 Elimina voce"**: rimuove la voce dallo storico con conferma; gli allegati copiati rimangono su disco.
  - `storico.json` e `storico_allegati/` vengono migrati insieme agli altri file quando si cambia la cartella di lavoro.
- `shutil` portato a import di modulo (era importato localmente dentro `_change_work_dir`)

### Changed

- `_change_work_dir` copia anche `storico.json` e l'intera cartella `storico_allegati/` durante la migrazione della directory di lavoro, e ricarica la lista dello storico dopo il cambio.
- `_setup_work_dir` inizializza i percorsi `HISTORY_FILE` e `HISTORY_ATTACH_DIR` come attributi d'istanza.

## [1.4.0] - 2026-05-15 — branch `distribuisci`

### Added

- **Modalità "locked" per la distribuzione ai colleghi**: la password SMTP non è mai visibile nell'UI né salvata su disco. Si attiva automaticamente in base alla presenza del file `smtp.key` accanto all'eseguibile; nessuna modifica al sorgente o ricompilazione necessaria per passare da una modalità all'altra.
  - Con `smtp.key` presente → modalità locked: campo password nascosto, password decifrata dal file al momento dell'invio
  - Senza `smtp.key` → modalità normale: campo password visibile e modificabile, comportamento invariato rispetto alle versioni precedenti
- **Cifratura AES-256 della password con autenticazione** tramite `cryptography.fernet` (AES-128-CBC + HMAC-SHA256):
  - La chiave non è mai presente in chiaro nel binario: è derivata da tre frammenti di byte non contigui (`_F1`, `_F2`, `_F3`) via **PBKDF2HMAC-SHA256 con 600.000 iterazioni**
  - Il token Fernet include un MAC che rileva qualsiasi alterazione del file (`InvalidToken` se `smtp.key` è corrotto o manomesso)
- **Script `genera_smtp_key.py`** (solo per l'amministratore, non da distribuire):
  - Deriva la stessa chiave presente nell'exe, cifra la password SMTP e scrive `smtp.key` nella stessa cartella
  - Include conferma password e verifica immediata della decifratura prima di scrivere il file
  - Permette di aggiornare la password distribuendo solo il nuovo `smtp.key`, senza ricompilare l'exe
- **Gestione errori credenziali nell'UI**: se `smtp.key` è assente o corrotto al momento dell'invio, viene mostrato un `QMessageBox.critical` con messaggio descrittivo invece di un crash silenzioso
- `cryptography>=42.0` aggiunto a `requirements.txt`

### Changed

- `_SMTP_PASS_LOCKED` è ora una variabile booleana calcolata a runtime (`os.path.exists(smtp.key)`) invece di un flag hardcoded nel sorgente
- `_get_locked_smtp_pass()` legge il token da `smtp.key` su disco invece di decifrare una costante embedded nel sorgente; il percorso è risolto correttamente sia in modalità sviluppo (`.py`) che compilata (PyInstaller `sys.frozen`)
- `_save_smtp_config()` scrive `smtp_pass: ""` nel JSON quando la modalità locked è attiva, così la password reale non compare mai in `smtp_config.json` sul disco del collega
- `send_emails()` recupera la password tramite `_get_locked_smtp_pass()` con gestione esplicita di `RuntimeError`

### Security

- **Prima (base64)**: la password era codificata in chiaro nel bytecode; `pyinstxtractor` + `uncompyle6` la esponeva in pochi secondi senza competenze specifiche.
- **Ora (Fernet + PBKDF2)**: la password non compare mai come stringa leggibile nel binario. Per recuperarla occorre: decompilare il bytecode, identificare i tre frammenti del segreto, ricostruire la derivazione PBKDF2 a 600k iterazioni ed eseguirla. Protezione adeguata contro analisi superficiali e strumenti automatici; non garantita contro un reverse engineer esperto con accesso prolungato al binario.

## [1.3.0] - 2026-04-29

### Added
- **Icone SVG vettoriali per B, I, U** nella toolbar WYSIWYG (stile Word/Google Docs):
  - `ICON_BOLD`: lettera B in grassetto (Material Design `format_bold`)
  - `ICON_ITALIC`: lettera I corsiva (Material Design `format_italic`)
  - `ICON_UNDERLINE`: lettera U sottolineata (Material Design `format_underlined`)
- **Pulsanti toggle checkable** per Grassetto, Corsivo, Sottolineato:
  - Il pulsante resta "premuto" quando il cursore si trova su testo con quella formattazione
  - Si aggiorna automaticamente muovendo il cursore (`currentCharFormatChanged`)
  - Cliccando si attiva/disattiva la formattazione per il testo selezionato o i caratteri futuri
- Tooltip italiani sui pulsanti: "Grassetto", "Corsivo", "Sottolineato"

### Changed
- I pulsanti B/I/U usano ora icone SVG invece del solo testo
- Le funzioni `toggle_bold/italic/underline` sono state sostituite da `_on_bold/italic/underline_triggered(checked)` che ricevono lo stato dal pulsante
- Nuovo metodo `_update_format_buttons(fmt)` sincronizza lo stato visivo dei pulsanti col formato del cursore

## [1.2.0] - 2026-04-29

### Added
- **Slider per delay e sleep** al posto di QSpinBox, con granularità di 100 ms
  - Delay base (retry): da 0.1 s a 10.0 s, step 0.1 s
  - Sleep tra email: da 0 s a 5.0 s, step 0.1 s
- Label dinamica affiancata allo slider che mostra il valore formattato (es. "300 ms", "1.5 s")
- Metodo `_make_delay_slider()` factory per creare slider+label riutilizzabile
- Metodo `_format_ms()` per formattazione leggibile dei millisecondi
- **Icone vettoriali SVG nella toolbar** per lista puntata, lista numerata e link:
  - `ICON_LIST_BULLET` — tre righe con pallini
  - `ICON_LIST_NUMBERED` — tre righe con numeri 1, 2, 3
  - `ICON_LINK` — catena di collegamento
- Metodo `_svg_icon()` che converte stringhe SVG in `QIcon` multirisoluzione (16, 24, 32, 48 px)

### Changed
- `base_delay` e `sleep_between` nel config JSON ora sono float in secondi (es. `0.3`, `1.5` invece di interi)
- Il thread di invio usa `time.sleep()` con valori float per pause sotto il secondo
- I log dei retry mostrano il delay formattato (es. "Retry tra 0.3 s" invece di "Retry tra 1 secondi")
- I valori slider sono salvati in JSON come secondi decimali (retrocompatibili con config precedenti)
- I pulsanti della toolbar per lista e link ora mostrano l'icona SVG oltre al testo

## [1.1.0] - 2026-04-29

### Added

- **Sezione "Directory di lavoro"** nella GUI con percorso visibile e pulsante "📁 Cambia cartella"
- **Scelta della directory al primo avvio**: se nessuna cartella è salvata, viene richiesto all'utente di selezionarne una tramite `QFileDialog`
- **Persistenza della directory** tramite `QSettings` (registro su Windows, `.config` su Linux, `.plist` su macOS)
- **Migrazione file** quando si cambia cartella: l'utente può scegliere di copiare log, config e CSV nella nuova posizione
- **Ricaricamento automatico** della configurazione SMTP dai campi dopo un cambio di directory (`_fill_smtp_fields()`)
- Metodo `_fill_smtp_fields(config)` per riempire i campi SMTP da un dizionario

### Changed

- `LOG_FILE`, `CSV_FILE` e `CONFIG_FILE` sono ora attributi d'istanza (`self.LOG_FILE` ecc.) invece di costanti globali
- `load_config()` e `save_config()` accettano il percorso del file come parametro esplicito
- Creazione dell'header CSV spostata in `_setup_work_dir()` (non più a livello modulo)

## [1.0.0] - 2026-04-29

### Added

- **Sezione "Configurazione SMTP"** nella GUI con campi modificabili:
  - Server SMTP (`QLineEdit`)
  - Porta (`QSpinBox`, 1–65535)
  - Utente (`QLineEdit`)
  - Password (`QLineEdit` con `EchoMode.Password`)
  - Max tentativi (`QSpinBox`, 0–20)
  - Delay base (`QSpinBox` con suffisso " s")
  - Sleep tra email (`QSpinBox` con suffisso " s")
- **Pulsante "💾 Salva configurazione"** che scrive i parametri su file JSON
- **Persistenza su `smtp_config.json`** con fallback ai valori default e merge per chiavi mancanti
- **Validazione** dei campi Server SMTP e Utente prima dell'invio
- Il thread di invio email utilizza i valori dinamici (`smtp_config`) per `sleep_between` e `base_delay` invece delle costanti globali

### Changed

- Le costanti `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAX_RETRIES`, `BASE_DELAY`, `SLEEP_BETWEEN` sostituite da `DEFAULT_CONFIG` (dizionario) e campi GUI
- Su sistemi senza `APPDATA` (Linux/macOS), la directory di logfallback è `~/MailSenderLogs` anziché crashare

### Removed

- Costanti globali hardcoded per i parametri SMTP
# Changelog

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
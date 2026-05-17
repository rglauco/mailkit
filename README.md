# MailKit

Invio email massivo con interfaccia grafica WYSIWYG (PyQt5).

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt5](https://img.shields.io/badge/PyQt5-5.15+-green.svg)

## Caratteristiche

- ✉️ Invio email massivo con SMTP configurabile da GUI
- 📝 Editor WYSIWYG HTML per il corpo del messaggio (grassetto, corsivo, sottolineato, colore, liste, link)
- 📎 Allegati multipli
- 🔄 Retry automatico con backoff esponenziale
- 📂 Scelta della directory di lavoro (log, config, CSV)
- 💾 Salvataggio configurazione SMTP su file JSON
- 📊 Log e CSV con traccia di ogni invio
- 📂 Gestione dello storico dei messaggi inviati insieme agli allegati

## Installazione

### Prerequisiti

- Python 3.8 o superiore
- pip

### Setup con virtual environment

```bash
# Clona o scarica il progetto
cd mailkit

# Crea il virtual environment
python3 -m venv venv

# Attiva il venv
# Linux / macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Installa le dipendenze
pip install -r requirements.txt
```

## Avvio

```bash
# Assicurati che il venv sia attivato
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows

# Lancia l'applicazione
python gui.py
```

> **Nota Linux**: se hai problemi di display con Wayland, lancia con:
> ```bash
> QT_QPA_PLATFORM=xcb python gui.py
> ```

### Primo avvio

Al primo avvio l'app chiederà di scegliere una **directory di lavoro** dove salvare:
- `smtp_config.json` — configurazione SMTP
- `mail_gui.log` — log degli invii
- `mail_gui.csv` — report CSV dettagliato

La scelta viene memorizzata e riproposta automaticamente ai successivi avvii. È comunque possibile cambiarla in qualsiasi momento con il pulsante **📁 Cambia cartella**.

## Creare l'eseguibile con PyInstaller

PyInstaller permette di creare un eseguibile standalone che non richiede Python installato sulla macchina target.

### Installazione

```bash
pip install pyinstaller
pip install pyqt5
```

### Linux

```bash
pyinstaller --onefile --windowed --icon=logo.ico gui.py
```

L'eseguibile si trova in `dist/gui`.

> **Nota**: l'eseguibile creato su Linux funziona solo sulla stessa distribuzione (o compatibile) dove è stato compilato. Per distribuire su più distro, considera [AppImage](https://appimage.org/) o crea l'eseguibile sulla distro target.

### macOS

```bash
pyinstaller --onefile --windowed --icon=logo.ico gui.py
```

L'eseguibile si trova in `dist/gui` (tipo Unix) oppure come bundle `gui.app` se usi l'opzione `--windowed`.

> **Nota su Apple Silicon (M1/M2/M3/M4)**:
> - Se lanci PyInstaller su un Mac ARM, l'eseguibile funziona nativamente su ARM
> - Per supportare anche Mac Intel, compila con:
>   ```bash
>   pyinstaller --onefile --windowed --icon=logo.ico --target-architecture universal2 gui.py
>   ```
> - Se il Mac blocca l'app per "sviluppatore non identificato", esegui:
>   ```bash
>   xattr -cr dist/gui
>   ```
>   oppure: Impostazioni di Sistema → Privacy & Security → clicca "Apri comunque"

### Windows

```powershell
pyinstaller --onefile --windowed --icon=logo.ico gui.py
```

L'eseguibile si trova in `dist\gui.exe`.

> **Nota**: se `pyinstaller` non è nel PATH, puoi usare il percorso completo:
> ```powershell
> C:\Users\tuo_utente\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.10_qbz5n2kfra8p0\LocalCache\local-packages\Python310\Scripts\pyinstaller.exe --onefile --windowed --icon=logo.ico gui.py
> ```

### Riepilogo opzioni PyInstaller

| Opzione | Significato |
|---|---|
| `--onefile` | Genera un singolo file eseguibile |
| `--windowed` | Nasconde la finestra del terminale (solo GUI) |
| `--icon=logo.ico` | Imposta l'icona del programma |
| `--name MailKit` | Nome personalizzato dell'eseguibile (al posto di `gui`) |
| `--add-data` | Aggiunge file esterni (es. risorse) |
| `--target-architecture universal2` | Solo macOS: binario universal ARM+Intel |

### Esempio con nome personalizzato

```bash
pyinstaller --onefile --windowed --icon=logo.ico --name MailKit gui.py
```

L'eseguibile sarà `dist/MailKit` (Linux/macOS) o `dist\MailKit.exe` (Windows).

## Modalità di utilizzo e sicurezza della password

MailKit supporta due modalità operative, selezionate automaticamente in base ai file presenti accanto all'eseguibile.

---

### Modalità personale (default, out of the box)

Adatta all'uso individuale. Non richiede nessuna configurazione aggiuntiva.

1. Lancia `mailkit.exe` (o `python gui.py`)
2. Vai nella tab **Configurazione SMTP**, inserisci i tuoi dati e la password
3. Clicca **💾 Salva configurazione**

La password viene salvata **cifrata** nel file `smtp_config.json` tramite AES-256 (Fernet). Non è mai in chiaro su disco.

---

### Modalità locked — distribuzione agli utenti (build admin)

Adatta quando un amministratore vuole distribuire MailKit a dei colleghi con la password SMTP già configurata e **non visibile né modificabile** dall'utente finale.

In questa modalità il campo password è nascosto nell'interfaccia. La password viene decifrata al momento dell'invio direttamente da `smtp.key`, senza mai passare dal JSON o dall'UI.

#### Prerequisiti

- Python con le dipendenze installate (`pip install -r requirements.txt`)
- PyInstaller (`pip install pyinstaller`)

#### Flusso completo (step by step)

**Step 1 — Crea il segreto di build**

Crea un file `.env` nella cartella del progetto:

```
MAILKIT_SECRET=la-tua-passphrase-segreta
```

Scegli una passphrase lunga e casuale. Questo segreto è ciò che distingue la tua build da quella default pubblica; non distribuirlo mai.

**Step 2 — Genera `_secret.py`**

```bash
python build_env.py
```

Lo script legge `MAILKIT_SECRET` dal `.env` e genera `_secret.py` con i frammenti di chiave derivati. Questo file viene compilato nell'eseguibile da PyInstaller.

**Step 3 — Genera `smtp.key`**

```bash
python genera_smtp_key.py
```

Lo script deriva la stessa chiave presente in `_secret.py`, chiede la password SMTP, la cifra e scrive `smtp.key`. Eseguilo nella stessa cartella dell'exe che distribuirai.

> Se la password SMTP cambia in futuro, riesegui solo questo step e ridistribuisci il nuovo `smtp.key`. Non è necessario ricompilare l'exe.

**Step 4 — Compila l'eseguibile**

```bash
pyinstaller gui.spec
```

`_secret.py` viene incluso automaticamente nell'exe (è nella stessa cartella). L'exe risultante contiene il segreto di build compilato al suo interno.

**Step 5 — Distribuisci**

Consegna ai colleghi questi due file nella stessa cartella:

```
mailkit.exe
smtp.key
```

L'app si avvia in modalità locked: il campo password non è visibile, la password viene letta da `smtp.key` al momento dell'invio.

> **Non distribuire mai**: `.env`, `_secret.py`, `genera_smtp_key.py`, `build_env.py`.

---

### Build automatica via GitHub Actions

Il workflow `.github/workflows/build.yml` supporta la build admin tramite GitHub Secrets.

Imposta il secret `MAILKIT_SECRET` nelle impostazioni del repository (Settings → Secrets → Actions) e il workflow eseguirà automaticamente `build_env.py` prima di PyInstaller ad ogni push di un tag versione.

Il file `smtp.key` deve essere generato localmente e distribuito separatamente: non può essere creato in CI senza la password SMTP reale.

---

### Riepilogo delle modalità

| | Modalità personale | Modalità locked |
|---|---|---|
| `smtp.key` presente | No | Sì |
| Password visibile in UI | Sì | No |
| Password nel JSON | Cifrata (AES-256) | Vuota |
| Password al momento dell'invio | Dal campo UI | Da `smtp.key` |
| Setup richiesto | Nessuno | build_env → genera_smtp_key → pyinstaller |

---

## Struttura dei file

```
mailkit/
├── gui.py                  # Sorgente principale
├── build_env.py            # Script admin: genera _secret.py da .env
├── genera_smtp_key.py      # Script admin: genera smtp.key (non distribuire)
├── gui.spec                # Configurazione PyInstaller
├── logo.ico                # Icona dell'applicazione
├── requirements.txt        # Dipendenze Python
├── CHANGELOG.md            # Cronologia delle modifiche
└── README.md               # Questo file

# File generati (non nel repository):
├── _secret.py              # Frammenti segreto di build (gitignored)
├── .env                    # MAILKIT_SECRET (gitignored)
└── smtp.key                # Password SMTP cifrata (gitignored, da distribuire)
```

## Directory di lavoro (generata dall'app)

```
MailSenderLogs/
├── smtp_config.json    # Configurazione SMTP (smtp_pass cifrata con AES-256)
├── mail_gui.log        # Log degli invii
└── mail_gui.csv        # Report CSV (Timestamp;Destinatario;Stato;Tentativo;Errore)
```

## Licenza

MIT

### È sicuro abbassare il delay?

Dipende dal server SMTP:
- La maggior parte dei server ha rate limit (es. 100 email/minuto, 500/ora)
- Andare troppo veloce può innescare greylisting, throttling o il ban temporaneo dell'account
- Un intervallo di 200-500ms tra le email è generalmente accettabile per volumi moderati
- Scendere sotto i 100ms è rischioso: molti server lo considerano spam/abuse
- Il base_delay (per il retry) può restare più alto, perché serve a dare tempo al server per riprendersi

Consiglio: 300-500ms per lo sleep tra email, 1-2s per il base_delay dei retry.
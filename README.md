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

## Struttura dei file

```
mailkit/
├── gui.py              # Sorgente principale
├── logo.ico            # Icona dell'applicazione
├── requirements.txt    # Dipendenze Python
├── CHANGELOG.md        # Cronologia delle modifiche
└── README.md           # Questo file
```

## Directory di lavoro (generata dall'app)

```
MailSenderLogs/
├── smtp_config.json    # Configurazione SMTP salvata
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
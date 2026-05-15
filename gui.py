import sys, os, smtplib, ssl, csv, time, json
from datetime import datetime
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtWidgets import (QFileDialog, QMessageBox, QTextEdit, QLineEdit, QLabel,
                            QPushButton, QListWidget, QVBoxLayout, QHBoxLayout, QWidget,
                            QToolBar, QSpinBox, QGroupBox, QFormLayout, QSlider,
                            QTabWidget)
from PyQt5.QtGui import QFont, QColor, QTextCursor, QIcon, QPixmap
from PyQt5.QtCore import QThread, pyqtSignal, QSettings, Qt, QByteArray
from PyQt5.QtGui import QIcon

from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid
from html.parser import HTMLParser
import re

# ================= CONFIG DEFAULTS =================
DEFAULT_CONFIG = {
    "smtp_server": "mail.example.com",
    "smtp_port": 587,
    "smtp_user": "account@mail-example.com",
    "smtp_pass": "password",
    "smtp_sender_name": "",
    "max_retries": 2,
    "base_delay": 1,
    "sleep_between": 1,
    "reconnect_every": 100,
    "batch_size": 0,
    "batch_pause_min": 60
}


def load_config(config_file):
    """Carica la configurazione da file JSON, fallback ai default."""
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config, config_file):
    """Salva la configurazione su file JSON."""
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


# ================= STRIP HTML → TESTO PLAIN =================
class _HTMLStripper(HTMLParser):
    """Estrae il testo puro da HTML, con gestione dei blocchi."""
    def __init__(self):
        super().__init__()
        self._pieces = []
        self._block_tags = {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'blockquote'}

    def handle_data(self, data):
        self._pieces.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in self._block_tags:
            self._pieces.append('\n')

    def handle_endtag(self, tag):
        if tag in self._block_tags:
            self._pieces.append('\n')

    def get_text(self):
        return re.sub(r'\n{3,}', '\n\n', ''.join(self._pieces)).strip()


def html_to_plain(html):
    """Converte HTML in testo plain per la parte text/plain dell'email."""
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


# ================= REDISTRIBUZIONE DOMINI =================
def redistribute_emails_by_domain(emails):
    """Riordina gli indirizzi email per minimizzare invii consecutivi
    allo stesso dominio, usando una strategia round-robin.

    Esempio:
      user1@a.com, user2@a.com, user3@a.com, user1@b.com, user2@b.com
      → user1@a.com, user1@b.com, user2@a.com, user2@b.com, user3@a.com
    """
    groups = defaultdict(list)
    no_domain = []
    for email in emails:
        if '@' in email:
            domain = email.rsplit('@', 1)[1].strip()
            groups[domain].append(email)
        else:
            no_domain.append(email)

    # Ordina i gruppi per dimensione (più grandi prima)
    sorted_groups = sorted(groups.values(), key=len, reverse=True)

    result = []
    remaining = True
    while remaining:
        remaining = False
        for group in sorted_groups:
            if group:
                result.append(group.pop(0))
                remaining = True

    # Aggiunge le righe senza @ alla fine
    result.extend(no_domain)
    return result


# ================= EMAIL TEXT EDIT (intercetta incolla) =================
class EmailTextEdit(QTextEdit):
    """QTextEdit personalizzato che emette un segnale quando si incolla testo."""
    pasted = pyqtSignal()

    def insertFromMimeData(self, source):
        super().insertFromMimeData(source)
        self.pasted.emit()


# ================= THREAD EMAIL =================
class EmailSenderThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, smtp_config, emails, subject, body_html, attachments, csv_file):
        super().__init__()
        self.smtp_config = smtp_config
        self.emails = emails
        self.subject = subject
        self.body_html = body_html
        self.attachments = attachments
        self.csv_file = csv_file
        self._stop_requested = False

    def _connect_smtp(self):
        """Crea una nuova connessione SMTP e ritorna l'oggetto server."""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        port = self.smtp_config["port"]
        if port == 465:
            server = smtplib.SMTP_SSL(self.smtp_config["server"], port, context=context)
        else:
            server = smtplib.SMTP(self.smtp_config["server"], port)
            server.starttls(context=context)
        server.login(self.smtp_config["user"], self.smtp_config["password"])
        self.log_signal.emit("SMTP connesso e autenticato")
        return server

    def _safe_quit(self, server):
        """Chiude la connessione SMTP in modo sicuro, ignorando errori se già chiusa."""
        try:
            server.quit()
        except Exception:
            try:
                server.close()
            except Exception:
                pass

    def request_stop(self):
        """Richiede l'interruzione del thread (interrompe le pause e lo ciclo principale)."""
        self._stop_requested = True

    def _sleep_with_stop_check(self, seconds):
        """Sleep che viene interrotta se viene richiesto lo stop. Ritorna True se interrotta."""
        remaining = seconds
        while remaining > 0:
            if self._stop_requested:
                return True
            chunk = min(remaining, 1)  # Check ogni secondo
            time.sleep(chunk)
            remaining -= chunk
        return False

    def run(self):
        server = None
        reconnect_every = self.smtp_config.get("reconnect_every", 0)

        try:
            server = self._connect_smtp()
        except Exception as e:
            self.log_signal.emit(f"Errore SMTP: {str(e)}")
            self.finished_signal.emit()
            return

        sent_count = 0
        batch_since_last_pause = 0
        batch_size = self.smtp_config.get("batch_size", 0)
        batch_pause_min = self.smtp_config.get("batch_pause_min", 60)

        for idx, to_email in enumerate(self.emails, 1):
            # Check interruzione
            if self._stop_requested:
                self.log_signal.emit("⛔ Invio interrotto dall'utente")
                break

            # Pausa batch: dopo aver inviato batch_size email, aspetta batch_pause_min minuti
            if batch_size > 0 and batch_since_last_pause >= batch_size:
                self._safe_quit(server)
                server = None
                pause_sec = batch_pause_min * 60
                self.log_signal.emit(f"⏸ Pausa batch: {batch_since_last_pause} email inviate, attesa {batch_pause_min} minuti...")
                # Countdown visibile nel log ogni 60 secondi
                remaining = pause_sec
                interrupted = False
                while remaining > 0:
                    if self._stop_requested:
                        self.log_signal.emit("⛔ Pausa interrotta dall'utente")
                        interrupted = True
                        break
                    chunk = min(remaining, 60)
                    time.sleep(chunk)
                    remaining -= chunk
                    if remaining > 0:
                        mins_left = remaining // 60
                        secs_left = remaining % 60
                        self.log_signal.emit(f"⏸ Ripresa tra {mins_left}m {secs_left}s...")
                    else:
                        self.log_signal.emit("⏸ Pausa terminata, riconnessione...")
                if interrupted:
                    break
                try:
                    server = self._connect_smtp()
                    batch_since_last_pause = 0
                except Exception as e:
                    self.log_signal.emit(f"Errore riconnessione dopo pausa batch: {str(e)}")
                    self.finished_signal.emit()
                    return

            # Riconnessione preventiva ogni N email inviate
            if reconnect_every > 0 and sent_count > 0 and (sent_count % reconnect_every == 0):
                self.log_signal.emit(f"Riconnessione preventiva dopo {sent_count} email inviate...")
                self._safe_quit(server)
                time.sleep(2)
                try:
                    server = self._connect_smtp()
                except Exception as e:
                    self.log_signal.emit(f"Errore riconnessione SMTP dopo {sent_count} email: {str(e)}")
                    self.finished_signal.emit()
                    return

            attempt = 0
            sent = False
            while not sent and attempt < self.smtp_config.get("max_retries", 5):
                attempt += 1
                try:
                    self.log_signal.emit(f"Invio a {to_email} (tentativo {attempt})")
                    msg = MIMEMultipart()
                    sender_name = self.smtp_config.get("sender_name", "")
                    if sender_name:
                        msg["From"] = f"{sender_name} <{self.smtp_config['user']}>"
                    else:
                        msg["From"] = self.smtp_config["user"]
                    msg["To"] = to_email
                    msg["Subject"] = self.subject
                    msg["Date"] = formatdate(localtime=True)
                    msg["Message-ID"] = make_msgid(domain=self.smtp_config["user"].rsplit("@", 1)[-1])

                    # Parte text/plain + text/html = multipart/alternative
                    plain_body = html_to_plain(self.body_html)
                    alt = MIMEMultipart("alternative")
                    alt.attach(MIMEText(plain_body, "plain", "utf-8"))
                    alt.attach(MIMEText(self.body_html, "html", "utf-8"))
                    msg.attach(alt)

                    for file in self.attachments:
                        with open(file, "rb") as f:
                            part = MIMEApplication(f.read(), Name=os.path.basename(file))
                            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file)}"'
                            msg.attach(part)

                    server.sendmail(self.smtp_config["user"], to_email, msg.as_string())
                    sent = True
                    sent_count += 1
                    batch_since_last_pause += 1
                    self.log_signal.emit(f"OK {to_email}")
                    # scrittura CSV
                    with open(self.csv_file, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=';')
                        writer.writerow([datetime.now(), to_email, "OK", attempt, ""])
                    time.sleep(self.smtp_config.get("sleep_between", 1))

                except smtplib.SMTPServerDisconnected as e:
                    err = str(e).replace("\n", " ").replace("\r", " ")
                    self.log_signal.emit(f"ERRORE {to_email}: connessione persa - {err}")
                    with open(self.csv_file, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=';')
                        writer.writerow([datetime.now(), to_email, "FAILED", attempt, err])

                    # Prova a riconnettere
                    self.log_signal.emit("Riconnessione SMTP...")
                    time.sleep(5)
                    try:
                        server = self._connect_smtp()
                        self.log_signal.emit("Riconnessione OK, retry stesso indirizzo")
                        # Non consumare il tentativo per errori di connessione
                        attempt -= 1
                        continue
                    except Exception as conn_err:
                        self.log_signal.emit(f"Riconnessione fallita: {str(conn_err)}")
                        self.log_signal.emit(f"ABORT {to_email} - impossibile riconnettersi")
                        with open(self.csv_file, "a", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f, delimiter=';')
                            writer.writerow([datetime.now(), to_email, "ABORT", attempt, "SMTP riconnessione fallita"])
                        break

                except smtplib.SMTPResponseException as e:
                    err_bytes = e.smtp_error if isinstance(e.smtp_error, bytes) else str(e.smtp_error).encode()
                    err = f"{e.smtp_code} {err_bytes.decode('utf-8', errors='replace')}"
                    err = err.replace("\n", " ").replace("\r", " ")
                    self.log_signal.emit(f"ERRORE {to_email}: {err}")
                    with open(self.csv_file, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=';')
                        writer.writerow([datetime.now(), to_email, "FAILED", attempt, err])

                    # Errore 4xx = problema temporaneo (rate limit, ecc.)
                    if 400 <= e.smtp_code < 500:
                        self.log_signal.emit("Errore temporaneo (4xx), riconnessione e pausa...")
                        self._safe_quit(server)
                        time.sleep(30)  # Pausa più lunga per rate limit
                        try:
                            server = self._connect_smtp()
                            self.log_signal.emit("Riconnessione OK dopo errore temporaneo")
                            # Non consumare il tentativo, riprova lo stesso indirizzo
                            attempt -= 1
                            continue
                        except Exception as conn_err:
                            self.log_signal.emit(f"Riconnessione fallita: {str(conn_err)}")
                            break
                    # Errore 5xx = permanente, salta questo indirizzo
                    elif e.smtp_code >= 500:
                        self.log_signal.emit(f"Errore permanente ({e.smtp_code}), salto {to_email}")
                        break
                    # Altri errori: retry con backoff
                    else:
                        if attempt < self.smtp_config.get("max_retries", 5):
                            delay = (2 ** attempt) * self.smtp_config.get("base_delay", 1)
                            delay_str = f"{delay:.1f} s" if delay != int(delay) else f"{int(delay)} s"
                            self.log_signal.emit(f"Retry tra {delay_str}")
                            time.sleep(delay)

                except Exception as e:
                    err = str(e).replace("\n"," ").replace("\r"," ")
                    self.log_signal.emit(f"ERRORE {to_email}: {err}")
                    with open(self.csv_file, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=';')
                        writer.writerow([datetime.now(), to_email, "FAILED", attempt, err])
                    if attempt < self.smtp_config.get("max_retries", 5):
                        delay = (2 ** attempt) * self.smtp_config.get("base_delay", 1)
                        delay_str = f"{delay:.1f} s" if delay != int(delay) else f"{int(delay)} s"
                        self.log_signal.emit(f"Retry tra {delay_str}")
                        time.sleep(delay)

            if not sent:
                self.log_signal.emit(f"ABORT {to_email} dopo {self.smtp_config.get('max_retries',5)} tentativi")

        self._safe_quit(server)
        self.log_signal.emit(f"Invio completato ({sent_count}/{len(self.emails)} email inviate)")
        self.finished_signal.emit()


# ================= GUI =================
class MailSenderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invio Email Massivo - WYSIWYG")
        self.resize(960, 800)
        self.attachments = []

        # ===== Scelta / caricamento directory di lavoro =====
        self._init_work_dir()

        # FONT GENERALE
        default_font = QFont("Segoe UI", 12)
        self.setFont(default_font)

        config = load_config(self.CONFIG_FILE)

        # ===== Layout principale =====
        main_layout = QVBoxLayout()

        # ===== Tab Widget =====
        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 12))

        # ===================== TAB CONFIGURAZIONE =====================
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)

        # Info directory di lavoro
        dir_group = QGroupBox("Directory di lavoro (log, config, CSV)")
        dir_group.setFont(QFont("Segoe UI", 12))
        dir_layout = QVBoxLayout()
        self.dir_label = QLabel(self.log_dir)
        self.dir_label.setFont(QFont("Segoe UI", 11))
        self.dir_label.setWordWrap(True)
        self.dir_label.setStyleSheet("color: #2a6db5;")
        dir_layout.addWidget(self.dir_label)

        change_dir_btn = QPushButton("📁 Cambia cartella")
        change_dir_btn.setFont(QFont("Segoe UI", 11))
        change_dir_btn.clicked.connect(self._change_work_dir)
        dir_layout.addWidget(change_dir_btn)
        dir_group.setLayout(dir_layout)
        config_layout.addWidget(dir_group)

        # Configurazione SMTP
        smtp_group = QGroupBox("Configurazione SMTP")
        smtp_group.setFont(QFont("Segoe UI", 12))
        smtp_form = QFormLayout()

        self.smtp_server_input = QLineEdit(config["smtp_server"])
        smtp_form.addRow("Server SMTP:", self.smtp_server_input)

        self.smtp_port_input = QSpinBox()
        self.smtp_port_input.setRange(1, 65535)
        self.smtp_port_input.setValue(config["smtp_port"])
        smtp_form.addRow("Porta:", self.smtp_port_input)

        self.smtp_user_input = QLineEdit(config["smtp_user"])
        smtp_form.addRow("Utente:", self.smtp_user_input)

        self.smtp_sender_name_input = QLineEdit(config.get("smtp_sender_name", ""))
        self.smtp_sender_name_input.setPlaceholderText('es. "Servizi Newsletter"')
        smtp_form.addRow("Nome mittente:", self.smtp_sender_name_input)

        self.smtp_pass_input = QLineEdit(config["smtp_pass"])
        self.smtp_pass_input.setEchoMode(QLineEdit.Password)
        smtp_form.addRow("Password:", self.smtp_pass_input)

        self.max_retries_input = QSpinBox()
        self.max_retries_input.setRange(0, 20)
        self.max_retries_input.setValue(config["max_retries"])
        smtp_form.addRow("Max tentativi:", self.max_retries_input)

        self.reconnect_every_input = QSpinBox()
        self.reconnect_every_input.setRange(0, 1000)
        self.reconnect_every_input.setValue(config.get("reconnect_every", 100))
        self.reconnect_every_input.setSpecialValueText("Mai")
        smtp_form.addRow("Riconnetti ogni N email:", self.reconnect_every_input)

        self.batch_size_input = QSpinBox()
        self.batch_size_input.setRange(0, 10000)
        self.batch_size_input.setValue(config.get("batch_size", 0))
        self.batch_size_input.setSpecialValueText("Disabilitato")
        smtp_form.addRow("Invio a lotti - N email per lotto:", self.batch_size_input)

        self.batch_pause_input = QSpinBox()
        self.batch_pause_input.setRange(1, 1440)
        self.batch_pause_input.setValue(config.get("batch_pause_min", 60))
        self.batch_pause_input.setSuffix(" min")
        smtp_form.addRow("Pausa tra i lotti:", self.batch_pause_input)

        # Delay base (slider: 0.1 s - 10.0 s, step 0.1 s)
        base_delay_ms = int(config["base_delay"] * 1000)
        self.base_delay_slider, self.base_delay_label = self._make_delay_slider(
            base_delay_ms, min_ms=100, max_ms=10000, step_ms=100
        )
        smtp_form.addRow("Delay base (retry):", self.base_delay_slider)
        smtp_form.addRow("", self.base_delay_label)

        # Sleep tra email (slider: 0 - 5.0 s, step 0.1 s)
        sleep_ms = int(config["sleep_between"] * 1000)
        self.sleep_between_slider, self.sleep_between_label = self._make_delay_slider(
            sleep_ms, min_ms=0, max_ms=5000, step_ms=100
        )
        smtp_form.addRow("Sleep tra email:", self.sleep_between_slider)
        smtp_form.addRow("", self.sleep_between_label)

        # Pulsante salva config
        save_config_btn = QPushButton("💾 Salva configurazione")
        save_config_btn.setFont(QFont("Segoe UI", 11))
        save_config_btn.clicked.connect(self._save_smtp_config)
        smtp_form.addRow(save_config_btn)

        smtp_group.setLayout(smtp_form)
        config_layout.addWidget(smtp_group)
        config_layout.addStretch()

        # ===================== TAB INVIO =====================
        send_tab = QWidget()
        send_layout = QVBoxLayout(send_tab)

        # Oggetto
        send_layout.addWidget(QLabel("Oggetto:"))
        self.subject_entry = QLineEdit()
        self.subject_entry.setFont(QFont("Segoe UI", 12))
        send_layout.addWidget(self.subject_entry)

        # Destinatari
        recipients_header = QHBoxLayout()
        recipients_header.addWidget(QLabel("Email destinatari (una per riga):"))
        recipients_header.addStretch()
        mix_btn = QPushButton("🔀 Mix domini")
        mix_btn.setFont(QFont("Segoe UI", 11))
        mix_btn.setToolTip("Riordina gli indirizzi per minimizzare\ninvii consecutivi allo stesso dominio")
        mix_btn.clicked.connect(self.redistribute_emails)
        recipients_header.addWidget(mix_btn)
        send_layout.addLayout(recipients_header)

        self.emails_text = EmailTextEdit()
        self.emails_text.setFont(QFont("Segoe UI", 12))
        self.emails_text.pasted.connect(self._on_emails_pasted)
        send_layout.addWidget(self.emails_text)

        # Toolbar WYSIWYG
        self.toolbar = QToolBar()
        self.add_toolbar_buttons()
        send_layout.addWidget(self.toolbar)

        # Corpo messaggio
        send_layout.addWidget(QLabel("Corpo messaggio (Editor HTML):"))
        self.body_edit = QTextEdit()
        self.body_edit.setFont(QFont("Segoe UI", 12))
        send_layout.addWidget(self.body_edit)

        # Allegati
        hbox_attach = QHBoxLayout()
        hbox_attach.addWidget(QLabel("Allegati:"))
        self.attach_list = QListWidget()
        self.attach_list.setFont(QFont("Segoe UI", 11))
        self.attach_list.setSelectionMode(QListWidget.ExtendedSelection)
        hbox_attach.addWidget(self.attach_list)

        vbox_attach_btn = QVBoxLayout()
        attach_button = QPushButton("📎 Aggiungi...")
        attach_button.setFont(QFont("Segoe UI", 11))
        attach_button.clicked.connect(self.add_attachments)
        vbox_attach_btn.addWidget(attach_button)

        remove_attach_button = QPushButton("✖ Rimuovi selezionato")
        remove_attach_button.setFont(QFont("Segoe UI", 11))
        remove_attach_button.clicked.connect(self.remove_attachments)
        vbox_attach_btn.addWidget(remove_attach_button)

        clear_attach_button = QPushButton("🗑 Rimuovi tutto")
        clear_attach_button.setFont(QFont("Segoe UI", 11))
        clear_attach_button.clicked.connect(self.clear_attachments)
        vbox_attach_btn.addWidget(clear_attach_button)

        vbox_attach_btn.addStretch()
        hbox_attach.addLayout(vbox_attach_btn)
        send_layout.addLayout(hbox_attach)

        # Pulsanti invio / ferma
        btn_layout = QHBoxLayout()
        self.send_button = QPushButton("📧 Invia Email")
        self.send_button.setFont(QFont("Segoe UI", 13))
        self.send_button.setStyleSheet("QPushButton { background-color: #27ae60; color: white; padding: 8px; }")
        self.send_button.clicked.connect(self.send_emails)
        btn_layout.addWidget(self.send_button)

        self.stop_button = QPushButton("⛔ Ferma")
        self.stop_button.setFont(QFont("Segoe UI", 13))
        self.stop_button.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; padding: 8px; }")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_sending)
        btn_layout.addWidget(self.stop_button)
        send_layout.addLayout(btn_layout)

        # Log
        send_layout.addWidget(QLabel("Log:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Segoe UI", 11))
        send_layout.addWidget(self.log_text)

        # Aggiorna lo stato dei pulsanti quando il cursore si muove
        self.body_edit.currentCharFormatChanged.connect(self._update_format_buttons)

        # ===== Assembla tab =====
        self.tabs.addTab(config_tab, "⚙️ Configurazione")
        self.tabs.addTab(send_tab, "📧 Invio")
        main_layout.addWidget(self.tabs)

        self.setLayout(main_layout)

    # ===== Gestione directory di lavoro =====
    def _init_work_dir(self):
        """Sceglie o carica la directory di lavoro per log, config e CSV."""
        settings = QSettings("MailSender", "MailKit")
        saved_dir = settings.value("work_dir", type=str)

        if saved_dir and os.path.isdir(saved_dir):
            self.log_dir = saved_dir
        else:
            # Primo avvio: chiedi all'utente
            chosen = self._pick_work_dir()
            if chosen:
                self.log_dir = chosen
                settings.setValue("work_dir", self.log_dir)
            else:
                # L'utente ha annullato: fallback nella home
                self.log_dir = os.path.join(os.path.expanduser("~"), "MailSenderLogs")
                settings.setValue("work_dir", self.log_dir)

        self._setup_work_dir()

    def _pick_work_dir(self):
        """Mostra un dialog per la scelta della directory di lavoro."""
        # Suggerimento iniziale
        default = os.path.join(os.path.expanduser("~"), "MailSenderLogs")
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Directory di lavoro")
        msg.setText("Scegli la cartella dove salvare log, configurazione e CSV.\n"
                    "Verrà creata se non esiste.")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

        chosen = QFileDialog.getExistingDirectory(
            self, "Seleziona cartella per log e configurazione", default
        )
        if chosen:
            # Aggiungiamo una sottocartella per tenere ordinato
            chosen = os.path.join(chosen, "MailSenderLogs")
        return chosen if chosen else None

    def _setup_work_dir(self):
        """Crea la directory di lavoro e i file necessari."""
        os.makedirs(self.log_dir, exist_ok=True)
        self.LOG_FILE = os.path.join(self.log_dir, "mail_gui.log")
        self.CSV_FILE = os.path.join(self.log_dir, "mail_gui.csv")
        self.CONFIG_FILE = os.path.join(self.log_dir, "smtp_config.json")

        # CSV header
        if not os.path.exists(self.CSV_FILE):
            with open(self.CSV_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Timestamp", "Recipient", "Status", "Attempt", "Error"])

    def _change_work_dir(self):
        """Permette di cambiare la directory di lavoro in qualsiasi momento."""
        chosen = QFileDialog.getExistingDirectory(
            self, "Seleziona nuova cartella per log e configurazione", self.log_dir
        )
        if not chosen:
            return

        new_dir = os.path.join(chosen, "MailSenderLogs")

        # Conferma migrazione
        reply = QMessageBox.question(
            self,
            "Cambia cartella di lavoro",
            f"La nuova cartella sarà:\n{new_dir}\n\n"
            f"Vuoi anche copiare i file esistenti dalla cartella attuale?\n"
            f"({self.log_dir})",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Cancel:
            return

        if reply == QMessageBox.Yes:
            # Copia i file nella nuova directory
            import shutil
            os.makedirs(new_dir, exist_ok=True)
            for fname in ("mail_gui.log", "mail_gui.csv", "smtp_config.json"):
                src = os.path.join(self.log_dir, fname)
                if os.path.exists(src):
                    dst = os.path.join(new_dir, fname)
                    # Non sovrascrivere se già esiste nella nuova dir
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)

        # Aggiorna la directory
        old_dir = self.log_dir
        self.log_dir = new_dir
        self._setup_work_dir()

        # Salva la preferenza
        settings = QSettings("MailSender", "MailKit")
        settings.setValue("work_dir", self.log_dir)

        # Aggiorna la label
        self.dir_label.setText(self.log_dir)

        # Ricarica la configurazione SMTP nei campi
        config = load_config(self.CONFIG_FILE)
        self._fill_smtp_fields(config)

        self.log(f"Cartella di lavoro cambiata: {old_dir} → {self.log_dir}")

    def _fill_smtp_fields(self, config):
        """Riempie i campi SMTP con i valori del dizionario config."""
        self.smtp_server_input.setText(config["smtp_server"])
        self.smtp_port_input.setValue(config["smtp_port"])
        self.smtp_user_input.setText(config["smtp_user"])
        self.smtp_sender_name_input.setText(config.get("smtp_sender_name", ""))
        self.smtp_pass_input.setText(config["smtp_pass"])
        self.max_retries_input.setValue(config["max_retries"])
        self.reconnect_every_input.setValue(config.get("reconnect_every", 100))
        self.batch_size_input.setValue(config.get("batch_size", 0))
        self.batch_pause_input.setValue(config.get("batch_pause_min", 60))
        self.base_delay_slider.setValue(int(config["base_delay"] * 1000))
        self.sleep_between_slider.setValue(int(config["sleep_between"] * 1000))

    # ===== SVG Icons =====
    ICON_BOLD = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M15.6 10.8c1-.7 1.6-1.8 1.6-3 0-2.3-1.8-4-4.1-4H6v14h7.8c2.2 0 4.2-1.8 4.2-4.1 0-1.6-1-3-2.4-3.9zM8 7h5c1 0 2 .8 2 2s-1 2-2 2H8V7zm5.8 10H8v-4h5.8c1.1 0 2.2.9 2.2 2s-1.1 2-2.2 2z" fill="currentColor"/>
    </svg>'''

    ICON_ITALIC = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M10 4v2h2.2l-2.4 12H7v2h8v-2h-2.2l2.4-12H18V4h-8z" fill="currentColor"/>
    </svg>'''

    ICON_UNDERLINE = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M12 17c3.3 0 5-2.2 5-5V4h-2v8c0 2-1 3-3 3s-3-1-3-3V4H7v8c0 2.8 1.7 5 5 5zM5 19v2h14v-2H5z" fill="currentColor"/>
    </svg>'''

    ICON_LIST_BULLET = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <circle cx="4" cy="5" r="2" fill="currentColor"/>
      <rect x="9" y="4" width="13" height="2.5" rx="1" fill="currentColor"/>
      <circle cx="4" cy="12" r="2" fill="currentColor"/>
      <rect x="9" y="11" width="13" height="2.5" rx="1" fill="currentColor"/>
      <circle cx="4" cy="19" r="2" fill="currentColor"/>
      <rect x="9" y="18" width="13" height="2.5" rx="1" fill="currentColor"/>
    </svg>'''

    ICON_LIST_NUMBERED = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <text x="1" y="7.5" font-size="7" font-weight="bold" font-family="sans-serif" fill="currentColor">1</text>
      <rect x="9" y="4" width="13" height="2.5" rx="1" fill="currentColor"/>
      <text x="1" y="14.5" font-size="7" font-weight="bold" font-family="sans-serif" fill="currentColor">2</text>
      <rect x="9" y="11" width="13" height="2.5" rx="1" fill="currentColor"/>
      <text x="1" y="21.5" font-size="7" font-weight="bold" font-family="sans-serif" fill="currentColor">3</text>
      <rect x="9" y="18" width="13" height="2.5" rx="1" fill="currentColor"/>
    </svg>'''

    ICON_LINK = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
      <path d="M7 17a5 5 0 0 1 0-10h3v2H7a3 3 0 0 0 0 6h3v2H7zm10 0h-3v-2h3a3 3 0 0 0 0-6h-3V7h3a5 5 0 0 1 0 10zM8 11h8v2H8z" fill="currentColor"/>
    </svg>'''

    @staticmethod
    def _svg_icon(svg_data):
        """Converte una stringa SVG in QIcon multirisoluzione."""
        icon = QIcon()
        for size in (16, 24, 32, 48):
            pixmap = QPixmap(size, size)
            pixmap.loadFromData(QByteArray(svg_data.encode('utf-8')), 'SVG')
            if not pixmap.isNull():
                scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon.addPixmap(scaled)
        return icon

    # ===== Toolbar WYSIWYG =====
    def add_toolbar_buttons(self):
        toolbar_font = QFont("Segoe UI", 10)

        # Pulsanti checkable (Bold, Italic, Underline) - restano premuti
        self.bold_action = QtWidgets.QAction(self._svg_icon(self.ICON_BOLD), "Grassetto", self)
        self.bold_action.setCheckable(True)
        self.bold_action.triggered.connect(self._on_bold_triggered)
        self.bold_action.setFont(toolbar_font)
        self.toolbar.addAction(self.bold_action)

        self.italic_action = QtWidgets.QAction(self._svg_icon(self.ICON_ITALIC), "Corsivo", self)
        self.italic_action.setCheckable(True)
        self.italic_action.triggered.connect(self._on_italic_triggered)
        self.italic_action.setFont(toolbar_font)
        self.toolbar.addAction(self.italic_action)

        self.underline_action = QtWidgets.QAction(self._svg_icon(self.ICON_UNDERLINE), "Sottolineato", self)
        self.underline_action.setCheckable(True)
        self.underline_action.triggered.connect(self._on_underline_triggered)
        self.underline_action.setFont(toolbar_font)
        self.toolbar.addAction(self.underline_action)

        # Pulsanti non-checkable
        color_action = QtWidgets.QAction("Colore", self)
        color_action.triggered.connect(self.change_color)
        color_action.setFont(toolbar_font)
        self.toolbar.addAction(color_action)

        for label, svg, func in [
            ("Lista puntata", self.ICON_LIST_BULLET, lambda: self.insert_list("bullet")),
            ("Lista numerata", self.ICON_LIST_NUMBERED, lambda: self.insert_list("number")),
            ("Link", self.ICON_LINK, self.insert_link)
        ]:
            action = QtWidgets.QAction(label, self)
            action.setIcon(self._svg_icon(svg))
            action.triggered.connect(func)
            action.setFont(toolbar_font)
            self.toolbar.addAction(action)

    def _on_bold_triggered(self, checked):
        fmt = self.body_edit.currentCharFormat()
        fmt.setFontWeight(QFont.Bold if checked else QFont.Normal)
        self.merge_format(fmt)

    def _on_italic_triggered(self, checked):
        fmt = self.body_edit.currentCharFormat()
        fmt.setFontItalic(checked)
        self.merge_format(fmt)

    def _on_underline_triggered(self, checked):
        fmt = self.body_edit.currentCharFormat()
        fmt.setFontUnderline(checked)
        self.merge_format(fmt)

    def _update_format_buttons(self, fmt):
        """Aggiorna lo stato premuto/non premuto dei pulsanti B/I/U
        in base al formato del cursore corrente."""
        self.bold_action.setChecked(fmt.fontWeight() == QFont.Bold)
        self.italic_action.setChecked(fmt.fontItalic())
        self.underline_action.setChecked(fmt.fontUnderline())

    def change_color(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            fmt = self.body_edit.currentCharFormat()
            fmt.setForeground(color)
            self.merge_format(fmt)

    def insert_list(self, style):
        cursor = self.body_edit.textCursor()
        if style == "bullet":
            cursor.insertList(QtGui.QTextListFormat.ListDisc)
        else:
            cursor.insertList(QtGui.QTextListFormat.ListDecimal)

    def insert_link(self):
        url, ok = QtWidgets.QInputDialog.getText(self, "Inserisci link", "URL:")
        if ok and url:
            cursor = self.body_edit.textCursor()
            text = cursor.selectedText() or url
            cursor.insertHtml(f'<a href="{url}">{text}</a>')

    def merge_format(self, fmt):
        cursor = self.body_edit.textCursor()
        cursor.mergeCharFormat(fmt)
        self.body_edit.mergeCurrentCharFormat(fmt)

    # ===== Crea slider per delay =====
    def _make_delay_slider(self, initial_ms, min_ms=0, max_ms=10000, step_ms=100):
        """Crea uno slider per impostare un delay in millisecondi.
        Ritorna (QSlider, QLabel) dove la label mostra il valore formattato."""
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_ms, max_ms)
        slider.setSingleStep(step_ms)
        slider.setPageStep(step_ms * 5)
        slider.setValue(initial_ms)
        slider.setFont(QFont("Segoe UI", 10))

        # Tick marks
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(step_ms * 10 if (max_ms - min_ms) > 2000 else step_ms * 5)

        label = QLabel(self._format_ms(initial_ms))
        label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #2a6db5;")

        # Aggiorna label quando lo slider si muove
        slider.valueChanged.connect(lambda v: label.setText(self._format_ms(v)))

        return slider, label

    @staticmethod
    def _format_ms(ms):
        """Formatta millisecondi in stringa leggibile (es. '1.5 s', '300 ms')."""
        if ms < 1000:
            return f"{ms} ms"
        else:
            seconds = ms / 1000.0
            if seconds == int(seconds):
                return f"{int(seconds)} s"
            return f"{seconds:.1f} s"

    # ===== Salva configurazione SMTP =====
    def _save_smtp_config(self):
        config = {
            "smtp_server": self.smtp_server_input.text().strip(),
            "smtp_port": self.smtp_port_input.value(),
            "smtp_user": self.smtp_user_input.text().strip(),
            "smtp_pass": self.smtp_pass_input.text(),
            "smtp_sender_name": self.smtp_sender_name_input.text().strip(),
            "max_retries": self.max_retries_input.value(),
            "base_delay": self.base_delay_slider.value() / 1000.0,
            "sleep_between": self.sleep_between_slider.value() / 1000.0,
            "reconnect_every": self.reconnect_every_input.value(),
            "batch_size": self.batch_size_input.value(),
            "batch_pause_min": self.batch_pause_input.value()
        }
        save_config(config, self.CONFIG_FILE)
        self.log("Configurazione SMTP salvata")

    # ===== Allegati =====
    def add_attachments(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Seleziona allegati")
        for f in files:
            if f not in self.attachments:
                self.attachments.append(f)
                self.attach_list.addItem(os.path.basename(f))

    def remove_attachments(self):
        """Rimuove gli allegati selezionati nella lista."""
        selected = self.attach_list.selectedItems()
        if not selected:
            QMessageBox.information(self, "Info", "Seleziona uno o più allegati da rimuovere.")
            return
        for item in selected:
            row = self.attach_list.row(item)
            self.attachments.pop(row)
            self.attach_list.takeItem(row)
        self.log(f"Rimossi {len(selected)} allegato/i")

    def clear_attachments(self):
        """Rimuove tutti gli allegati."""
        if not self.attachments:
            return
        reply = QMessageBox.question(
            self, "Conferma",
            f"Rimuovere tutti i {len(self.attachments)} allegati?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            count = len(self.attachments)
            self.attachments.clear()
            self.attach_list.clear()
            self.log(f"Rimossi tutti i {count} allegati")

    # ===== Ridistribuzione domini =====
    def redistribute_emails(self):
        """Riordina gli indirizzi email nel campo di testo
        per minimizzare invii consecutivi allo stesso dominio."""
        emails_raw = self.emails_text.toPlainText().splitlines()
        emails = [e.strip() for e in emails_raw if e.strip()]
        if not emails:
            return

        redistributed = redistribute_emails_by_domain(emails)
        self.emails_text.setPlainText('\n'.join(redistributed))

        # Conta domini unici per il log
        domains = set()
        for e in redistributed:
            if '@' in e:
                domains.add(e.rsplit('@', 1)[1].strip())
        self.log(f"Ridistribuite {len(redistributed)} email su {len(domains)} domini")

    def _on_emails_pasted(self):
        """Chiamato automaticamente quando si incolla testo nel campo email."""
        self.redistribute_emails()

    # ===== Log =====
    def log(self, message):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} {message}"
        self.log_text.append(line)
        with open(self.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ===== Invio email (threaded) =====
    def send_emails(self):
        emails_raw = self.emails_text.toPlainText().splitlines()
        emails = [e.strip() for e in emails_raw if e.strip()]
        subject = self.subject_entry.text()
        body_html = self.body_edit.toHtml()

        if not emails:
            QMessageBox.warning(self, "Attenzione", "Inserisci almeno un destinatario.")
            return

        smtp_config = {
            "server": self.smtp_server_input.text().strip(),
            "port": self.smtp_port_input.value(),
            "user": self.smtp_user_input.text().strip(),
            "sender_name": self.smtp_sender_name_input.text().strip(),
            "password": self.smtp_pass_input.text(),
            "max_retries": self.max_retries_input.value(),
            "base_delay": self.base_delay_slider.value() / 1000.0,
            "sleep_between": self.sleep_between_slider.value() / 1000.0,
            "reconnect_every": self.reconnect_every_input.value(),
            "batch_size": self.batch_size_input.value(),
            "batch_pause_min": self.batch_pause_input.value()
        }

        if not smtp_config["server"] or not smtp_config["user"]:
            QMessageBox.warning(self, "Attenzione", "Compila Server SMTP e Utente nella configurazione.")
            return

        self.send_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.thread = EmailSenderThread(smtp_config, emails, subject, body_html, self.attachments, self.CSV_FILE)
        self.thread.log_signal.connect(self.log)
        self.thread.finished_signal.connect(self._on_sending_finished)
        self.thread.start()

    def _stop_sending(self):
        """Richiede l'interruzione dell'invio email."""
        if hasattr(self, 'thread') and self.thread is not None and self.thread.isRunning():
            self.thread.request_stop()
            self.log("⛔ Interruzione richiesta...")
            self.stop_button.setEnabled(False)

    def _on_sending_finished(self):
        """Chiamato quando il thread di invio termina (completamento o interruzione)."""
        self.send_button.setEnabled(True)
        self.stop_button.setEnabled(False)


# ================= Avvio GUI =================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    default_font = QtGui.QFont("Segoe UI", 12)
    app.setFont(default_font)
    app.setWindowIcon(QIcon("logo.ico"))
    window = MailSenderGUI()
    window.show()
    sys.exit(app.exec_())
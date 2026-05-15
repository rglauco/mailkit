# MailKit — Invio email massivo con interfaccia grafica

MailKit è un'applicazione desktop per l'invio massivo di email che unisce semplicità d'uso e affidabilità. È pensata per chi ha bisogno di raggiungere molte destinatari — comunicazioni aziendali, newsletter, circolari — senza complicati servizi online e mantenendo il pieno controllo dei propri dati.

## Caratteristiche principali

**Editor WYSIWYG integrato**  
Il corpo del messaggio si compone con un editor visuale: grassetto, corsivo, sottolineato, colore del testo, elenchi puntati e numerati, link. Tutto ciò che si vede nell'editor è ciò che il destinatario riceverà, in formato HTML.

**Configurazione SMTP guidata**  
Server, porta, utente e password sono inseribili direttamente dalla GUI. La configurazione si salva su file JSON crittografabile e viene ricaricata automaticamente ad ogni avvio. Nessun parametro da editare a mano.

**Gestione allegati**  
Si possono aggiungere uno o più allegati a ogni invio, rimuoverli o svuotare la lista con un clic.

**Ridistribuzione automatica dei domini**  
Quando si incolla un elenco di destinatari, MailKit analizza i domini e li ridistribuisce in modo round-robin: nessun dominio riceve messaggi consecutivi più del necessario. Questo riduce il rischio che un server di posta blocchi l'invio per traffico concentrato da un solo mittente. Un pulsante "Mix domini" permette anche di riordinare manualmente in qualsiasi momento.

**Retry automatico con backoff esponenziale**  
Se un invio fallisce, MailKit ritenta automaticamente fino al numero configurabile di volte, aumentando progressivamente l'intervallo tra i tentativi (1 s, 2 s, 4 s...). Questo massimizza le probabilità di recapito in caso di problemi temporanei del server.

**Controllo preciso delle tempistiche**  
Due slider dedicati permettono di impostare con granularità di 100 ms il ritardo tra un'email e la successiva (da 0 a 5 s) e il delay base per i retry (da 0,1 a 10 s). Un intervallo ragionevole, calibrato sul proprio server SMTP, evita blocchi per rate limiting.

**Directory di lavoro configurabile**  
Al primo avvio l'app chiede dove salvare log, configurazione e CSV. La scelta viene ricordata per le sessioni successive e può essere cambiata in qualsiasi momento, con la possibilità di migrare i file esistenti nella nuova posizione.

**Report CSV e log completo**  
Ogni invio viene tracciato in un file CSV (timestamp, destinatario, stato, tentativo, eventuale errore) e in un file di log testuale. Ideali per verifiche, statistiche e auditorie.

**Cross-platform**  
Scritto in Python con PyQt5, funziona su Linux, macOS e Windows. È distribuibile come eseguibile standalone tramite PyInstaller, senza bisogno di installare Python sulla macchina dell'utente finale.

## Requisiti

- Python 3.8 o superiore
- PyQt5
- Un account SMTP configurabile (Gmail con app password,provider di posta aziendale, ecc.)

## In breve

MailKit nasce per rispondere a una necessità pratica — inviare molte email in modo affidabile — senza dipendere da servizi esterni a pagamento e mantenendo i propri dati sul proprio computer. L'interfaccia è in italiano e pensata per essere comprensibile fin dal primo avvio.
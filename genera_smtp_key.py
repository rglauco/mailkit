"""
Utility per generare smtp.key — il file cifrato con la password SMTP.

Prerequisito: eseguire prima build_env.py per generare _secret.py.

Eseguire UNA VOLTA (o ad ogni cambio password) nella stessa cartella
in cui si trova mailkit.exe da distribuire:

    python build_env.py       # genera _secret.py dal .env
    python genera_smtp_key.py # genera smtp.key

Il file smtp.key verrà creato nella stessa cartella dello script.

Distribuzione ai colleghi:
    mailkit.exe  +  smtp.key  →  modalità locked (password nascosta)

NON distribuire questo script ai colleghi.
"""

import base64, getpass, os, sys
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

try:
    from _secret import _F1, _F2, _F3, _KS
except ImportError:
    print(
        "Errore: _secret.py non trovato.\n"
        "Esegui prima:  python build_env.py\n"
        "(richiede MAILKIT_SECRET nel file .env)",
        file=sys.stderr,
    )
    sys.exit(1)


def derive_key() -> bytes:
    secret = _F1 + _F2 + _F3
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_KS, iterations=600_000)
    return base64.urlsafe_b64encode(kdf.derive(secret))


def main():
    print("=== Genera smtp.key per mailkit ===\n")
    print("Derivazione chiave in corso (alcuni secondi)...", end="", flush=True)
    key = derive_key()
    print(" fatto.\n")

    password = getpass.getpass("Inserisci la password SMTP da cifrare: ")
    if not password:
        print("Errore: password vuota.", file=sys.stderr)
        sys.exit(1)
    confirm = getpass.getpass("Conferma password: ")
    if password != confirm:
        print("Errore: le password non coincidono.", file=sys.stderr)
        sys.exit(1)

    token = Fernet(key).encrypt(password.encode())

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smtp.key")
    with open(out_path, "wb") as f:
        f.write(token)

    recovered = Fernet(key).decrypt(token).decode()
    assert recovered == password, "ERRORE INTERNO: verifica fallita!"

    print(f"\nsmtp.key scritto in: {out_path}")
    print("\nPer distribuire ai colleghi (modalità locked):")
    print("  mailkit.exe  +  smtp.key  → nella stessa cartella")


if __name__ == "__main__":
    main()

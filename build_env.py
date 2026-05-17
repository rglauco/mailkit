"""
Genera _secret.py con il segreto di derivazione personalizzato per le build admin.

Flusso admin:
    1. Crea .env con:  MAILKIT_SECRET=la-tua-passphrase-segreta
    2. python build_env.py          → genera _secret.py
    3. python genera_smtp_key.py    → genera smtp.key (usa _secret.py)
    4. pyinstaller gui.spec         → genera mailkit.exe (include _secret.py)
    5. Distribuisci: mailkit.exe + smtp.key

_secret.py e .env NON vanno mai committati nel repository.

Per le build CI/CD: imposta MAILKIT_SECRET come GitHub Secret e aggiungi
il passo "python build_env.py" nel workflow prima di pyinstaller.
"""

import hashlib, os, sys

# Salt fisso per la derivazione dei frammenti dalla passphrase.
# Non è un segreto: serve solo a separare questo uso da altri.
_MASTER_SALT = b"mailkit-build-secret-v1"


def _derive_fragments(passphrase: str) -> tuple[bytes, bytes, bytes, bytes]:
    """Deriva _F1, _F2, _F3, _KS dalla passphrase via PBKDF2."""
    raw = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), _MASTER_SALT, 100_000, 37)
    return raw[16:23], raw[23:30], raw[30:37], raw[:16]  # F1, F2, F3, KS


def _to_bytes_literal(b: bytes) -> str:
    return 'b"' + "".join(f"\\x{byte:02x}" for byte in b) + '"'


def _read_dotenv(path: str = ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> None:
    env = _read_dotenv()
    passphrase = os.environ.get("MAILKIT_SECRET") or env.get("MAILKIT_SECRET", "")

    if not passphrase:
        print("Errore: MAILKIT_SECRET non trovato in .env o nelle variabili d'ambiente.", file=sys.stderr)
        print("Crea un file .env con:  MAILKIT_SECRET=la-tua-passphrase", file=sys.stderr)
        sys.exit(1)

    print("Derivazione frammenti in corso...", end="", flush=True)
    f1, f2, f3, ks = _derive_fragments(passphrase)
    print(" fatto.")

    content = (
        "# Auto-generato da build_env.py — NON COMMITTARE\n"
        f"_F1 = {_to_bytes_literal(f1)}\n"
        f"_F2 = {_to_bytes_literal(f2)}\n"
        f"_F3 = {_to_bytes_literal(f3)}\n"
        f"_KS = {_to_bytes_literal(ks)}\n"
    )

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_secret.py")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"_secret.py scritto in: {out_path}")
    print("\nProssimi passi:")
    print("  python genera_smtp_key.py   → crea smtp.key con il nuovo segreto")
    print("  pyinstaller gui.spec        → compila mailkit.exe")


if __name__ == "__main__":
    main()

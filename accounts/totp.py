"""Logowanie dwuskładnikowe: kody z aplikacji w telefonie (TOTP, RFC 6238) i kody zapasowe.

Kod z aplikacji zmienia się co 30 sekund. Przyjmujemy kod bieżący i po jednym sąsiednim
(zegar telefonu może się spieszyć), ale każdy kod tylko raz: ``totp_last_counter`` zapamiętuje
ostatni użyty krok, więc podsłuchany kod nie zadziała drugi raz.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

import segno

STEP_SECONDS = 30
DIGITS = 6
# Ile kroków w przód i w tył akceptujemy (rozjechany zegar telefonu).
DRIFT_STEPS = 1

RECOVERY_CODE_COUNT = 10
# Bez liter i cyfr, które łatwo pomylić przy przepisywaniu z kartki (0/o, 1/l/i).
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_secret():
    """Losowy sekret (160 bitów) w base32, tak jak go wpisuje się ręcznie do aplikacji."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _key(secret):
    return base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))


def code_at(secret, counter):
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_counter(now=None):
    return int((time.time() if now is None else now) // STEP_SECONDS)


def clean_code(raw):
    """Kod tak, jak go wpisano: spacje i myślniki nie mają znaczenia."""
    return "".join((raw or "").split()).replace("-", "").lower()


def verify(secret, raw_code, last_counter=0, now=None):
    """Zwraca numer kroku pasującego kodu albo None. Krok musi być nowszy niż ``last_counter``."""
    code = clean_code(raw_code)
    if not secret or len(code) != DIGITS or not code.isdigit():
        return None
    counter = current_counter(now)
    for candidate in range(counter - DRIFT_STEPS, counter + DRIFT_STEPS + 1):
        if candidate > last_counter and hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret, account, issuer):
    label = quote(f"{issuer}:{account}", safe="")
    query = urlencode({"secret": secret, "issuer": issuer, "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"


def qr_data_uri(uri):
    """Kod QR jako obrazek SVG w adresie data: (CSP pozwala tylko na takie obrazki spoza plików)."""
    return segno.make(uri, error="m").svg_data_uri(scale=6, border=2, dark="#1f1a14", light="#ffffff")


def format_secret(secret):
    """Sekret w grupach po 4 znaki: łatwiej go przepisać, gdy kod QR nie działa."""
    return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))


def new_recovery_codes(count=RECOVERY_CODE_COUNT):
    def one():
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(count)]


def hash_recovery_code(raw):
    # Kody są losowe (ok. 49 bitów) i jednorazowe, więc wystarczy zwykły skrót zamiast Argon2.
    return hashlib.sha256(clean_code(raw).encode()).hexdigest()

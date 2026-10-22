"""Passwords, sessions, verification codes, channel contacts and the signed Telegram token."""
import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from . import config

# ---------- Passwords (REQ-18: salted slow hash) ----------
_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def hash_password(plain: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(plain.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(plain: str, stored: str) -> bool:
    try:
        _, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except ValueError:
        return False
    actual = hashlib.scrypt(plain.encode(), salt=salt, **_SCRYPT)
    return hmac.compare_digest(actual, expected)


# ---------- Session tokens ----------
def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=config.SESSION_DAYS)


# ---------- Verification codes (ChannelVerifier.generateCode / hashCode) ----------
def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


# ---------- Channel contacts (REQ-18, ContactCipher) ----------
# channel_connections stores the contact encrypted, plus a keyed hash so the
# same chat / email / webhook can be found (and not reused by a second account).
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"contact-cipher:" + config.SECRET_KEY.encode()).digest()))


def encrypt_contact(contact: str) -> bytes:
    return _fernet.encrypt(contact.encode())


def decrypt_contact(token: bytes) -> str:
    return _fernet.decrypt(bytes(token)).decode()


def contact_hash(contact: str) -> str:
    normalized = contact.strip().lower()
    return hmac.new(config.SECRET_KEY.encode(), normalized.encode(), hashlib.sha256).hexdigest()


# ---------- Telegram start-link token (Section 10.2, Change 1) ----------
# Format: <userId>_<expiresAtUnix>_<signature>. Telegram only allows
# A-Z a-z 0-9 _ - in a start parameter, up to 64 characters, so this fits.
# The token is signed, so nothing needs to be stored to check it later.
def _sign(payload: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]


def make_telegram_token(user_id: int) -> str:
    expires = int(time.time()) + config.TELEGRAM_LINK_MINUTES * 60
    payload = f"{user_id}_{expires}"
    return f"{payload}_{_sign(payload)}"


def read_telegram_token(token: str) -> int | None:
    """Return the user id if the token is genuine and not expired, else None."""
    try:
        user_id, expires, sig = token.split("_")
        payload = f"{user_id}_{expires}"
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        if int(expires) < time.time():
            return None
        return int(user_id)
    except ValueError:
        return None

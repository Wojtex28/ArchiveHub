"""Ustawienia ArchiveHub.

Całą konfigurację środowiska czytamy ze zmiennych środowiskowych (plik .env
w Docker Compose). Domyślne wartości są bezpieczne dla produkcji; tryb
deweloperski włącza się przez DJANGO_DEBUG=1.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "tak"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Ustaw DJANGO_SECRET_KEY (patrz .env.example).")
    SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"  # noqa: S105

# localhost zawsze: healthcheck Dockera pyta aplikację o /healthz pod 127.0.0.1.
ALLOWED_HOSTS = [*env_list("DJANGO_ALLOWED_HOSTS"), "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Katalog na dane trwałe (baza, później miniatury i biblioteka zdjęć).
DATA_DIR = Path(env("ARCHIVEHUB_DATA_DIR", str(BASE_DIR / "var")))
(DATA_DIR / "db").mkdir(parents=True, exist_ok=True)

# Biblioteka zdjęć: każdy podfolder to jeden album (synchronizacja w panelu).
ARCHIVEHUB_ALBUMS_DIR = Path(env("ARCHIVEHUB_ALBUMS_DIR", str(DATA_DIR / "albumy")))
# Udział sieciowy, do którego wrzucasz foldery ze skanami (w kontenerze tylko do odczytu).
ARCHIVEHUB_IMPORT_DIR = Path(env("ARCHIVEHUB_IMPORT_DIR", str(BASE_DIR / "var" / "import")))
# Folder trafia do importu, gdy jego zawartość nie zmienia się przez tyle minut.
ARCHIVEHUB_IMPORT_STABLE_MINUTES = int(env("ARCHIVEHUB_IMPORT_STABLE_MINUTES", "10"))
# Rewers ma nazwę awersu z tym dopiskiem, np. 012.jpg i 012_r.jpg.
ARCHIVEHUB_REVERSE_SUFFIX = env("ARCHIVEHUB_REVERSE_SUFFIX", "_r")
# Po tylu sekundach od ostatniego kliknięcia ↺/↻ worker obraca pliki zdjęcia.
ARCHIVEHUB_ROTATION_DELAY_SECONDS = int(env("ARCHIVEHUB_ROTATION_DELAY_SECONDS", "30"))
# Dłuższy bok wersji do oglądania i miniatury (px).
# Oryginał do pobrania: 0 = pełna rozdzielczość skanu.
ARCHIVEHUB_ORIGINAL_MAX_SIDE = int(env("ARCHIVEHUB_ORIGINAL_MAX_SIDE", "0"))
ARCHIVEHUB_ORIGINAL_QUALITY = int(env("ARCHIVEHUB_ORIGINAL_QUALITY", "92"))
ARCHIVEHUB_PREVIEW_MAX_SIDE = int(env("ARCHIVEHUB_PREVIEW_MAX_SIDE", "2560"))
ARCHIVEHUB_THUMB_MAX_SIDE = 640
# Zdjęcia w tle strony logowania. Wgrywane w panelu, nigdy nie trafiają do repozytorium.
ARCHIVEHUB_LOGIN_PHOTOS_DIR = DATA_DIR / "tlo-logowania"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "core",
    "panel",
    "albums",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

# SQLite w trybie WAL: czytanie nie blokuje zapisu, a "IMMEDIATE" chroni przed
# błędami "database is locked" przy jednoczesnych zapisach.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db" / "archivehub.sqlite3",
        "OPTIONS": {
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA busy_timeout=5000;"
                "PRAGMA foreign_keys=ON;"
            ),
            "transaction_mode": "IMMEDIATE",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = ["accounts.backends.CaseInsensitiveModelBackend"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "archive"
LOGOUT_REDIRECT_URL = "landing"

# Rodzina loguje się rzadko; sesja trwa rok. Wyłączenie konta lub zmiana hasła
# natychmiast kończy wszystkie sesje tej osoby.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365

# Nagłówek z prawdziwym adresem IP odwiedzającego (Cloudflare Tunnel ustawia
# CF-Connecting-IP). Używany do limitu prób logowania.
ARCHIVEHUB_CLIENT_IP_HEADER = env("ARCHIVEHUB_CLIENT_IP_HEADER", "HTTP_CF_CONNECTING_IP")

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(env("ARCHIVEHUB_STATIC_ROOT", str(BASE_DIR / "var" / "static")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        )
    },
}

# Wbudowany panel Django zostaje tylko jako narzędzie awaryjne, pod
# nieoczywistym adresem. Właściwy panel administratora jest pod /panel/.
DJANGO_ADMIN_PATH = env("ARCHIVEHUB_DJANGO_ADMIN_PATH", "zaplecze/")

SITE_TITLE = env("ARCHIVEHUB_SITE_TITLE", "Skany fotografii Włodyka/Bereza")

# --- Bezpieczeństwo -------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    # HTTPS kończy się na Cloudflare; Caddy przekazuje dalej nagłówek
    # X-Forwarded-Proto, więc Django wie, że połączenie było szyfrowane.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("ARCHIVEHUB_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Bez includeSubDomains: na tej samej domenie mogą działać inne usługi.
    SECURE_HSTS_SECONDS = int(env("ARCHIVEHUB_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    # Świadoma decyzja (patrz wyżej), więc wyciszamy te dwa ostrzeżenia.
    SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

# --- Logi -----------------------------------------------------------------
# Wszystko na standardowe wyjście; Docker zbiera i rotuje logi.

LOG_LEVEL = env("ARCHIVEHUB_LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Błędy 500 z pełnym śladem trafiają tu.
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # Boty skanujące internet wysyłają błędne nagłówki Host; to nie są błędy aplikacji.
        "django.security.DisallowedHost": {"handlers": [], "propagate": False},
    },
}

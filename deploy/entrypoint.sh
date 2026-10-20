#!/bin/sh
# Przy każdym starcie: migracje bazy i pliki statyczne, potem właściwy proces.
set -eu

mkdir -p "$ARCHIVEHUB_DATA_DIR/db"
# Worker importu startuje po aplikacji, więc migracje i statyki są już gotowe.
if [ "${ARCHIVEHUB_SKIP_SETUP:-0}" != "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput --clear --verbosity 0
fi

exec "$@"

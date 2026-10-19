#!/bin/sh
# Przy każdym starcie: migracje bazy i pliki statyczne, potem właściwy proces.
set -eu

mkdir -p "$ARCHIVEHUB_DATA_DIR/db"
python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear --verbosity 0

exec "$@"

#!/bin/sh
# Przy każdym starcie: migracje bazy i pliki statyczne, potem właściwy proces.
set -eu

if [ "$(id -u)" = "0" ]; then
    # Tylko worker startuje jako root. Folder kopii na serwerze zakłada Docker jako root,
    # więc przekazujemy go użytkownikowi archivehub i dalej działamy już bez uprawnień roota.
    if [ -n "${ARCHIVEHUB_BACKUP_DIR:-}" ]; then
        mkdir -p "$ARCHIVEHUB_BACKUP_DIR"
        chown archivehub:archivehub "$ARCHIVEHUB_BACKUP_DIR" && chmod 700 "$ARCHIVEHUB_BACKUP_DIR" \
            || echo "Uwaga: nie mogę ustawić właściciela $ARCHIVEHUB_BACKUP_DIR; kopie trafią do wolumenu danych." >&2
    fi
    exec setpriv --reuid=archivehub --regid=archivehub --init-groups "$0" "$@"
fi

mkdir -p "$ARCHIVEHUB_DATA_DIR/db"
# Worker importu startuje po aplikacji, więc migracje i statyki są już gotowe.
if [ "${ARCHIVEHUB_SKIP_SETUP:-0}" != "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput --clear --verbosity 0
fi

exec "$@"

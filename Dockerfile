FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARCHIVEHUB_DATA_DIR=/data \
    ARCHIVEHUB_STATIC_ROOT=/srv/static

# Aplikacja działa jako zwykły użytkownik, nie root.
RUN groupadd --gid 1000 archivehub \
 && useradd --uid 1000 --gid archivehub --no-create-home --shell /usr/sbin/nologin archivehub \
 && mkdir -p /app /data /srv/static \
 && chown archivehub:archivehub /data /srv/static

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=root:root . .
RUN chmod +x deploy/entrypoint.sh

USER archivehub
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

ENTRYPOINT ["deploy/entrypoint.sh"]
CMD ["gunicorn", "--config", "deploy/gunicorn.conf.py", "config.wsgi:application"]

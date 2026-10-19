# ArchiveHub

Prywatne, rodzinne archiwum zeskanowanych fotografii **„Skany fotografii Włodyka/Bereza”**.

Albumy powstają z katalogów na serwerze, rodzina loguje się kodem rodzinnym i własnym hasłem,
a administrator zarządza wszystkim w panelu. Pełna architektura: dokument „ETAP 0: analiza i architektura”
w projekcie.

## Stan prac

| Etap | Zakres | Stan |
| --- | --- | --- |
| 0 | Analiza i architektura | gotowe |
| 1 | Fundament: Django, baza, Docker, Caddy, konfiguracja, testy | gotowe |
| 2 | Konta, logowanie, kody rodzinne, konto administratora, podstawy panelu | **gotowe** |
| 3 | Panel administratora: pełna struktura (albumy, uprawnienia, synchronizacja) | następny |
| 3+ | Panel, import albumów, uprawnienia, galeria, pobieranie, komentarze… | zaplanowane |

## Technologie

- Python 3.13, Django 5.2 LTS (wsparcie do kwietnia 2028)
- SQLite w trybie WAL (jeden plik bazy w wolumenie `data`)
- Gunicorn jako serwer aplikacji
- Caddy: pliki statyczne i przekazywanie ruchu do aplikacji
- Cloudflare Tunnel: dostęp z internetu bez otwierania portów na routerze
- Docker Compose: całość uruchamiana jednym poleceniem

## Uruchomienie lokalnie (Windows, macOS, Linux)

Potrzebny jest [Docker Desktop](https://www.docker.com/products/docker-desktop/) (na Linuksie wystarczy Docker Engine z Compose).

```bash
git clone https://github.com/Wojtex28/ArchiveHub.git
cd ArchiveHub
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
docker compose up -d --build
```

Strona działa pod <http://localhost:8080>. Stan aplikacji: <http://localhost:8080/healthz>.

Przydatne polecenia:

```bash
docker compose logs -f app        # logi aplikacji
docker compose ps                 # stan kontenerów
docker compose down               # zatrzymanie (dane zostają w wolumenach)
```

## Konto administratora i pierwsze kroki

Konto administratora („master”) zakładasz raz, poleceniem w terminalu:

```bash
docker compose exec app python manage.py createsuperuser
```

Podajesz nick (login), opcjonalnie e-mail (można zostawić pusty) i hasło. Potem logujesz się
na zwykłej stronie logowania; w menu pojawi się „Panel” (`/panel/`), którego nikt inny nie widzi.

W panelu:

1. **Grupy**: utwórz grupy, np. „Bereza”, „Włodyka”, „Najbliższa rodzina”.
2. **Kody rodzinne**: utwórz kod dla grupy (panel proponuje losowy, np. `lipa-bocian-64`).
   Przekaż rodzinie adres `/dolacz/` i kod. Każda osoba wybiera swój nick i własne hasło.
3. **Osoby**: lista kont, przypisanie do grup, nowe hasło dla kogoś, kto zapomniał,
   wyłączenie lub usunięcie konta. Konto można też założyć ręcznie.

Limit prób: 8 błędnych haseł na nick lub 20 z jednego adresu IP w 15 minut blokuje logowanie
na kwadrans; 10 błędnych kodów z jednego adresu blokuje dołączanie. Za Cloudflare Tunnel
adres IP odwiedzającego pochodzi z nagłówka `CF-Connecting-IP`.

Awaryjny panel Django (`/zaplecze/`) też jest dostępny tylko dla administratora i loguje przez tę samą stronę.

## Uruchomienie na serwerze domowym (produkcja)

1. Zainstaluj Docker i sklonuj repozytorium, np. do `/srv/archivehub`.
2. `cp .env.example .env` i ustaw:
   - `DJANGO_DEBUG=0`
   - `DJANGO_SECRET_KEY`: wygeneruj `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `DJANGO_ALLOWED_HOSTS=archiwum.twojadomena.pl`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://archiwum.twojadomena.pl`
   - `CLOUDFLARE_TUNNEL_TOKEN`: token tunelu (niżej)
3. W panelu Cloudflare: Zero Trust → Networks → Tunnels → Create tunnel (typ Cloudflared).
   Skopiuj token do `.env`. W „Public Hostname” dodaj `archiwum.twojadomena.pl` kierujący na usługę
   `http://caddy:80`.
4. Uruchom z tunelem:

   ```bash
   docker compose --profile tunnel up -d --build
   ```

Aplikacja nie zajmuje portów 80/443 na serwerze, więc działa obok innych usług (np. Nextcloud).
Caddy nasłuchuje tylko na `127.0.0.1:8080`, czyli z innych komputerów nie jest dostępny bezpośrednio.

Szczegółowa instrukcja „postawienie systemu od zera” powstanie w ETAPIE 16.

## Testy i jakość kodu

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # Windows: .venv\Scripts\pip ...
.venv/bin/pytest                                  # testy
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

GitHub Actions uruchamia przy każdej zmianie: lint, testy, budowanie obrazu Dockera i sprawdzenie, że kontener startuje.

## Struktura

```text
config/        ustawienia (wszystko ze zmiennych środowiskowych), adresy URL
accounts/      konta, grupy, kody rodzinne, logowanie, limit prób
panel/         panel administratora (osoby, kody, grupy)
core/          strona powitalna, /healthz, robots.txt, nagłówki bezpieczeństwa
templates/     szablony wspólne
static/        CSS
tests/         testy (pytest)
deploy/        Caddyfile, konfiguracja Gunicorna, skrypt startowy kontenera
compose.yaml   usługi: app, caddy, cloudflared (profil „tunnel”)
```

## Dane i bezpieczeństwo

- Baza danych leży w wolumenie Dockera `data` (`/data/db/archivehub.sqlite3` w kontenerze).
- Plik `.env`, baza i zdjęcia nigdy nie trafiają do repozytorium (`.gitignore`). Repozytorium jest publiczne.
- Produkcja: przekierowanie na HTTPS, ciasteczka tylko przez HTTPS, HSTS, Content-Security-Policy
  bez skryptów inline, `noindex` dla wyszukiwarek, aplikacja w kontenerze działa jako zwykły użytkownik.

## Aktualizacja zależności

Wersje są przypięte w `requirements.txt` i `requirements-dev.txt`. Raz w miesiącu: sprawdzić nowe wersje
poprawek (np. `pip list --outdated`), podbić, uruchomić testy.

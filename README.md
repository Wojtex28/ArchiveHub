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

Konto administratora („master”) zakładasz raz, poleceniem w terminalu (na serwerze: krok 7 poradnika niżej):

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

## Wdrożenie na serwer domowy od zera

Efekt: archiwum działa pod `https://archiwum.twojadomena.pl`, obok Nextclouda, bez otwierania
żadnych portów na routerze. HTTPS zapewnia Cloudflare, a ruch do serwera idzie tunelem
(serwer sam łączy się z Cloudflare).

```text
przeglądarka → Cloudflare (HTTPS) → tunel → cloudflared → Caddy → aplikacja (Django) → baza SQLite
```

W przykładach domena to `archiwum.twojadomena.pl`; wszędzie wpisz swoją.

### Czego potrzebujesz

- Serwer z Linuksem (ten z Nextcloudem), dostęp przez SSH i konto z `sudo`.
- Domenę, której DNS obsługuje Cloudflare (darmowy plan wystarczy), patrz krok 1.
- Około 1 GB wolnego miejsca na start; później ~300 MB na każdy album.

### Krok 1. Domena w Cloudflare

Tunel potrzebuje domeny, której serwery nazw (DNS) są w Cloudflare.

- **Domena już jest w Cloudflare:** nic nie rób, przejdź do kroku 2.
- **Domena jest u innego dostawcy DNS:** w <https://dash.cloudflare.com> wybierz „Add a domain”,
  plan Free. Cloudflare wczyta obecne rekordy DNS. **Zanim zmienisz serwery nazw**, sprawdź, że są tam
  wszystkie rekordy, z których korzysta Nextcloud i poczta. Rekordom Nextclouda ustaw „DNS only”
  (szara chmurka), żeby działał dokładnie tak jak dziś. Dopiero potem zmień serwery nazw u rejestratora
  domeny na te podane przez Cloudflare. Zmiana zwykle działa po kilkunastu minutach, czasem po kilku godzinach.

### Krok 2. Docker na serwerze

Sprawdź, czy Docker już jest (często jest, jeśli Nextcloud działa w kontenerach):

```bash
docker --version
docker compose version
```

Jeśli którejś komendy brakuje, zainstaluj Dockera oficjalnym skryptem i dodaj siebie do grupy `docker`:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Wyloguj się z SSH i zaloguj ponownie, żeby grupa zaczęła działać. Test: `docker run --rm hello-world`.

### Krok 3. Pobranie aplikacji

```bash
sudo mkdir -p /srv/archivehub
sudo chown $USER: /srv/archivehub
git clone https://github.com/Wojtex28/ArchiveHub.git /srv/archivehub
cd /srv/archivehub
```

Wszystkie dalsze polecenia uruchamiasz w katalogu `/srv/archivehub`.

### Krok 4. Tunel w Cloudflare

1. Wejdź na <https://one.dash.cloudflare.com> (Zero Trust). Przy pierwszym wejściu Cloudflare poprosi
   o nazwę zespołu i wybór planu: wybierz Free (karta płatnicza może być wymagana, ale nic nie jest pobierane).
2. **Networks → Tunnels → Create a tunnel** (w nowszym panelu: Networks → Connectors → Cloudflare Tunnels).
   Typ: **Cloudflared**. Nazwa: np. `archivehub`.
3. Na ekranie instalacji wybierz **Docker**. Pokaże się polecenie `docker run ... --token eyJ...`.
   **Nie uruchamiaj go.** Skopiuj sam token (długi ciąg po `--token`); trafi do `.env` w kroku 5.
4. Dalej, w części **Public Hostname** (w nowszym panelu: Published application routes), dodaj:
   - Subdomain: `archiwum`, Domain: `twojadomena.pl`
   - Service: Type **HTTP**, URL **`caddy:80`**

   `caddy` to nazwa kontenera w naszym `compose.yaml`; cloudflared widzi go w sieci Dockera.
5. Zapisz. Cloudflare sam utworzy rekord DNS dla `archiwum.twojadomena.pl`.
6. Zalecane: w panelu domeny **SSL/TLS → Edge Certificates** włącz „Always Use HTTPS”.

### Krok 5. Plik `.env`

```bash
cp .env.example .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Ostatnia komenda wypisze losowy klucz (bez Pythona: `openssl rand -base64 48`). Otwórz plik (`nano .env`) i ustaw:

```ini
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<wklej wygenerowany klucz>
DJANGO_ALLOWED_HOSTS=archiwum.twojadomena.pl
DJANGO_CSRF_TRUSTED_ORIGINS=https://archiwum.twojadomena.pl
CLOUDFLARE_TUNNEL_TOKEN=<wklej token z kroku 4>
```

Resztę zostaw bez zmian. Jeśli port `8080` na serwerze jest już zajęty (np. przez Nextcloud),
zmień `ARCHIVEHUB_HTTP_PORT` na inny, np. `8090`. Ten port służy tylko do sprawdzania z samego serwera.

`.env` zawiera tajne dane: nie kopiuj go nigdzie publicznie i nie wrzucaj do repozytorium.

### Krok 6. Uruchomienie

```bash
docker compose --profile tunnel up -d --build
```

Pierwsze budowanie trwa kilka minut. Potem sprawdź:

```bash
docker compose ps                          # app powinno być „healthy”, caddy i cloudflared „running”
curl http://127.0.0.1:8080/healthz          # {"status": "ok"}  (port z ARCHIVEHUB_HTTP_PORT)
docker compose logs cloudflared | tail      # powinno być „Registered tunnel connection”
```

W panelu Cloudflare tunel powinien mieć status **Healthy**. Otwórz `https://archiwum.twojadomena.pl`:
pojawi się strona powitalna archiwum.

### Krok 7. Konto administratora

```bash
docker compose exec app python manage.py createsuperuser
```

Podaj nick, e-mail możesz pominąć (Enter), potem dwa razy hasło. Użyj długiego, unikalnego hasła:
to konto ma dostęp do wszystkiego. Zaloguj się na stronie, w menu pojawi się „Panel”.

### Krok 8. Test całości (10 minut)

1. W panelu utwórz grupę, np. „Test”.
2. Utwórz kod rodzinny dla tej grupy (panel podpowie losowy).
3. Na telefonie, najlepiej w trybie prywatnym, wejdź na `https://archiwum.twojadomena.pl/dolacz/`,
   wpisz kod, wybierz nick i hasło. Powinno Cię przenieść do archiwum.
4. W panelu, w „Osoby”, nowa osoba powinna być widoczna w grupie „Test”.
5. Wyloguj się na telefonie i zaloguj ponownie nickiem i hasłem.
6. Po teście usuń testowe konto, a kod wyłącz.

### Aktualizacja do nowej wersji

Po każdym zmergowanym etapie:

```bash
cd /srv/archivehub
git pull
docker compose --profile tunnel up -d --build
```

Migracje bazy uruchamiają się same przy starcie. Dane zostają w wolumenach Dockera.

### Kopia zapasowa bazy (na razie ręcznie)

Pełne kopie zapasowe dojdą w późniejszym etapie. Do tego czasu, przed każdą aktualizacją:

```bash
docker compose exec app python -c "import sqlite3; sqlite3.connect('/data/db/archivehub.sqlite3').backup(sqlite3.connect('/data/kopia.sqlite3'))"
docker compose cp app:/data/kopia.sqlite3 ./kopia-$(date +%F).sqlite3
```

Plik `kopia-RRRR-MM-DD.sqlite3` przenieś poza serwer (np. na Google Drive).

### Gdy coś nie działa

| Objaw | Przyczyna i rozwiązanie |
| --- | --- |
| `Bad Request (400)` w przeglądarce | Domena niezgodna z `DJANGO_ALLOWED_HOSTS` w `.env`. Popraw, potem `docker compose --profile tunnel up -d` |
| `403` przy logowaniu lub wysyłaniu formularza | Brak lub literówka w `DJANGO_CSRF_TRUSTED_ORIGINS` (musi zaczynać się od `https://`) |
| `app` ma status „unhealthy” albo się restartuje | `docker compose logs app`; najczęściej pusty `DJANGO_SECRET_KEY` |
| Błąd 1033 lub 502 z Cloudflare | Tunel nie działa: `docker compose logs cloudflared`. Sprawdź token oraz że usługa w Cloudflare to `http://caddy:80` |
| „Za wiele przekierowań” | Sprawdź, że usługa w tunelu to `http://caddy:80` (nie `https`). Jeśli to nie to, wyślij mi wynik `docker compose logs caddy app` |
| `port is already allocated` | Zmień `ARCHIVEHUB_HTTP_PORT` w `.env` |

Zatrzymanie: `docker compose --profile tunnel down` (dane zostają). Logi na żywo: `docker compose logs -f`.

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

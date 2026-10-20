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
| 2 | Konta, logowanie, kody rodzinne, konto administratora, podstawy panelu | gotowe |
| 3 | Panel administratora: albumy, uprawnienia grupa × album, synchronizacja, tło logowania | gotowe |
| 4 | Import albumów z udziału sieciowego (konwersja, miniatury, rewersy) | gotowe |
| 5 | Zarządzanie albumami: nazwa, opis, okładka, ukrywanie, kolejność | gotowe |
| 6 | Uprawnienia: kto widzi album, jakie albumy widzi osoba, kontrola każdego pliku | gotowe |
| 7 | Galeria: siatka miniatur, podgląd na cały ekran, awers/rewers, obracanie zdjęć | gotowe |
| 8 | Pobieranie: pojedyncze zdjęcie w pełnej rozdzielczości, zaznaczone zdjęcia jako ZIP | gotowe |
| 9 | Cały album jako ZIP (limit jednoczesnych pobrań), link do skanów PNG w Google Drive | gotowe |
| 10 | Komentarze pod zdjęciami, moderacja w panelu | gotowe |
| 11 | Strona główna: zdjęcia rozrzucone jak na stole, licznik albumów | gotowe |
| 12 | Telefon i tablet: powiększanie zdjęć, układ na małych ekranach | **gotowe** |
| 13+ | Metadane, wyszukiwanie, bezpieczeństwo i backup… | zaplanowane |

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

Konto administratora („master”) zakładasz raz, poleceniem w terminalu (na serwerze: krok 8 poradnika niżej):

```bash
docker compose exec app python manage.py createsuperuser
```

Podajesz nick (login), opcjonalnie e-mail (można zostawić pusty) i hasło. Potem logujesz się
na zwykłej stronie logowania; w menu pojawi się „Panel” (`/panel/`), którego nikt inny nie widzi.

W panelu:

1. **Grupy**: utwórz grupy, np. „Bereza”, „Włodyka”, „Wszystkie albumy”. Grupa z opcją
   „widzi wszystkie albumy” ma dostęp do każdego albumu, także dodanego później.
2. **Kody rodzinne**: utwórz kod dla grupy (panel proponuje losowy, np. `lipa-bocian-64`).
   Przekaż rodzinie adres `/dolacz/` i kod. Każda osoba wybiera swój nick i własne hasło,
   a kod od razu dopisuje ją do grupy. Kto dostanie kolejny kod, wpisuje go po zalogowaniu
   w menu „Mam kod” i dochodzi do następnej grupy na tym samym koncie.
3. **Synchronizacja**: każdy folder w bibliotece zdjęć (`/data/albumy` w kontenerze) to album.
   Przycisk „Synchronizuj archiwum” dodaje nowe foldery jako albumy i zapisuje raport w historii.
   Album, którego folder zniknął, dostaje znacznik „brak folderu”; nic nie jest usuwane.
   Folder z `_` na początku nazwy trafia do archiwum jako ukryty.
4. **Uprawnienia**: tabela albumy × grupy. Osoba widzi album, jeśli jest w choć jednej zaznaczonej grupie.
5. **Osoby**: lista kont, przypisanie do grup, nowe hasło dla kogoś, kto zapomniał,
   wyłączenie lub usunięcie konta. Konto można też założyć ręcznie.
6. **Tło logowania**: zdjęcia pływające pod siatką kropek na stronie logowania (można je łapać
   i przesuwać). Wgrywasz je tutaj; aplikacja zmniejsza je do 900 px i usuwa dane z aparatu (np. GPS).
   Strona logowania jest publiczna, więc wybieraj zdjęcia, które możesz pokazać obcym.

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
  **TrueNAS SCALE 24.10 lub nowszy też się nadaje:** przeczytaj najpierw sekcję
  [„Wariant: TrueNAS SCALE”](#wariant-truenas-scale), bo kroki 2 i 3 wyglądają tam inaczej.
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

### Krok 4. Tunel w Cloudflare (część 1: token)

1. Wejdź na <https://one.dash.cloudflare.com> (panel **Zero Trust**, osobny od zwykłego panelu domeny;
   w zwykłym panelu jest do niego link „Zero Trust” w menu po lewej). Przy pierwszym wejściu Cloudflare
   poprosi o nazwę zespołu (dowolna) i plan: wybierz **Free**.
2. **Networks → Tunnels → Create a tunnel** (w nowszym panelu: Networks → Connectors → Cloudflare Tunnels).
   Typ: **Cloudflared**. Nazwa: np. `archivehub`.
3. Na ekranie „Install and run” wybierz **Docker**. Pokaże się polecenie `docker run ... --token eyJ...`.
   **Nie uruchamiaj go i niczego nie instaluj**: nasz `compose.yaml` ma własny cloudflared.
   Skopiuj przyciskiem kopiowania całe polecenie i zostaw z niego sam token (od `eyJ` do końca).
4. **Zostaw tę kartę otwartą.** Kreator czeka („Waiting for your Tunnel to connect”), aż tunel się
   połączy, czyli aż uruchomisz aplikację w kroku 6. Wrócisz tu w kroku 7.

Token to hasło do tunelu: nie wklejaj go w czaty ani maile. Jeśli wyciekł, w ustawieniach tunelu
wygeneruj nowy (Refresh token) i podmień w `.env`.

### Krok 5. Plik `.env`

```bash
cp .env.example .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Ostatnia komenda wypisze losowy klucz (bez Pythona: `openssl rand -base64 48`). Otwórz plik (`nano .env`)
i **zmień istniejące linijki** (nie dopisuj ich drugi raz na dole):

```ini
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<wklej wygenerowany klucz>
DJANGO_ALLOWED_HOSTS=archiwum.twojadomena.pl
DJANGO_CSRF_TRUSTED_ORIGINS=https://archiwum.twojadomena.pl
CLOUDFLARE_TUNNEL_TOKEN=<wklej token z kroku 4>
```

W nano: zapis **Ctrl+O**, Enter; wyjście **Ctrl+X**. Sprawdzenie, czy każda zmienna jest raz
(linijki są ucinane, żeby nie pokazać całego tokenu):

```bash
grep -E "^(DJANGO_|CLOUDFLARE)" .env | cut -c1-40
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
docker compose logs cloudflared | grep Registered   # 4 linijki „Registered tunnel connection”
```

Ostrzeżenie `QUIC connection failed` w logu cloudflared nie przeszkadza: tunel sam przełącza się na HTTP/2.

### Krok 7. Tunel w Cloudflare (część 2: adres archiwum)

1. Wróć do karty z kroku 4. Po chwili pojawi się **„Tunnel connected successfully”**; kliknij **Next**.
2. W części **Published application routes** (w starszym panelu: Public Hostname) dodaj:
   - Subdomain: `archiwum`, Domain: `twojadomena.pl`
   - Service URL: **`http://caddy:80`** (pełny adres z `http://`; nie `https`)

   `caddy` to nazwa kontenera w naszym `compose.yaml`; cloudflared widzi go w sieci Dockera.
3. Zapisz. Cloudflare sam utworzy rekord DNS `archiwum` (CNAME na `<id-tunelu>.cfargotunnel.com`).
   **Nie dodawaj go ręcznie.**
4. Zalecane: w panelu domeny **SSL/TLS → Edge Certificates** włącz „Always Use HTTPS”.

Otwórz `https://archiwum.twojadomena.pl`: pojawi się strona powitalna archiwum. Jeśli z telefonu działa,
a z komputera nie, patrz tabelka „Gdy coś nie działa” niżej (stary DNS w pamięci komputera).

### Krok 8. Konto administratora

```bash
docker compose exec app python manage.py createsuperuser
```

Podaj nick, e-mail możesz pominąć (Enter), potem dwa razy hasło (podczas wpisywania nic się nie wyświetla).
Użyj długiego, unikalnego hasła: to konto ma dostęp do wszystkiego. Zaloguj się na stronie, w menu pojawi się „Panel”.

Nie ma żadnego domyślnego konta ani hasła: nick i hasło mastera wymyślasz sam przy tym poleceniu.
Zapomniane hasło mastera ustawisz od nowa (zamiast `Wojtek` podaj swój nick; jeśli go nie pamiętasz,
`createsuperuser` powie, że wybrany nick jest zajęty):

```bash
docker compose exec app python manage.py changepassword Wojtek
```

Zwykłym osobom hasło zmieniasz w panelu: Osoby → osoba → „Nowe hasło” → Ustaw hasło.

### Krok 9. Test całości (10 minut)

1. Zaloguj się kontem master, wejdź w **Panel → Grupy** i utwórz grupę, np. „Test”.
2. **Panel → Kody rodzinne:** utwórz kod dla tej grupy (panel podpowie losowy, np. `lipa-bocian-64`).
3. Na telefonie, najlepiej w trybie prywatnym, wejdź na `https://archiwum.twojadomena.pl/dolacz/`,
   wpisz kod, wybierz nick i hasło. Powinno Cię przenieść do archiwum.
4. Na komputerze w **Panel → Osoby** nowa osoba powinna być widoczna w grupie „Test”.
5. Wyloguj się na telefonie i zaloguj ponownie nickiem i hasłem.
6. Sprawdź błędy: zły kod na `/dolacz/` pokazuje „Ten kod nie działa…”, złe hasło
   „Nieprawidłowy nick lub hasło.”
7. Sprzątanie: usuń testowe konto w „Osoby”, a kod w „Kody rodzinne” wyłącz.

### Aktualizacja do nowej wersji

Po każdym zmergowanym etapie:

```bash
cd /srv/archivehub
git pull
docker compose --profile tunnel up -d --build
```

Migracje bazy uruchamiają się same przy starcie. Dane zostają w wolumenach Dockera.
Na TrueNAS zamiast `git pull` pobierz kod ponownie (patrz [wariant TrueNAS](#wariant-truenas-scale));
plik `.env` zostaje nietknięty.

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
| Z telefonu (LTE) działa, z komputera nie | Komputer albo router pamięta DNS sprzed przełączenia na Cloudflare. PowerShell jako administrator: `ipconfig /flushdns`, zamknij przeglądarkę; w Chrome także `chrome://net-internals/#dns` → Clear host cache. Samo mija po kilku godzinach |
| `Invalid service URL format` w Cloudflare | Adres usługi w tunelu musi mieć protokół: `http://caddy:80` |
| Przy tunelu w Cloudflare „Unsupported” | Stara wersja cloudflared. Pobierz aktualny kod i `docker compose --profile tunnel up -d` |
| Import nie widzi folderów (`ls /import` pusty albo „Permission denied”) | Sprawdź `ARCHIVEHUB_IMPORT_PATH` w `.env` i uprawnienie `everyone@` Read na datasecie (sekcja [Import albumów](#udział-importu-na-truenas)) |
| `worker` ma status „unhealthy” | `docker compose logs worker`. Worker po każdym przejściu i każdym zdjęciu zapisuje znacznik życia; „unhealthy” znaczy, że stoi od 10 minut |
| „Out of memory” w logach serwera | Kontenery ArchiveHub mają twarde limity RAM (aplikacja 768 MB, `ARCHIVEHUB_APP_MEMORY`; worker 1 GB, `ARCHIVEHUB_WORKER_MEMORY`), więc nie zabiorą pamięci NAS-owi. Sprawdź `free -h` i `docker stats --no-stream`, co zajmuje resztę |

Zatrzymanie: `docker compose --profile tunnel down` (dane zostają). Logi na żywo: `docker compose logs -f`.

### Wariant: TrueNAS SCALE

Sprawdzone na TrueNAS SCALE 25.10 (aplikacje na Dockerze; wersje przed 24.10 używały Kubernetesa
i się nie nadają). Kroki 1, 4 i 7–9 bez zmian; poniżej różnice.

- **Nie instaluj Dockera** (krok 2) ani niczego przez `apt`: TrueNAS to zamknięty system.
  Docker jest wbudowany; wystarczy, że w **Apps** wybrana jest pula na aplikacje (Configuration → Choose Pool).
  Sprawdź: `sudo docker compose version`.
- **Shell:** używaj **System → Shell** w panelu WWW TrueNAS. Wklejasz tam przez **Ctrl+Shift+V**
  albo Shift+Insert. Nie wklejaj w oknie konsoli Hyper-V/maszyny wirtualnej: „Wpisz tekst ze schowka”
  przekłamuje znaki przy polskiej klawiaturze.
- **`sudo` przed każdym `docker`** (i przy edycji `.env`). Hasło to hasło Twojego konta TrueNAS
  (zwykle `truenas_admin`); podczas wpisywania nic się nie wyświetla.
- **Katalog (zamiast kroku 3):** w panelu **Datasets** zaznacz pulę → **Add Dataset**, nazwa np. `ArchiveHub`,
  preset Generic. Nie używaj `ix-apps`. Potem w shellu (git może być niedostępny, więc pobieramy archiwum):

  ```bash
  cd "$(find /mnt -maxdepth 3 -name ArchiveHub -type d | head -1)" && pwd
  curl -L https://github.com/Wojtex28/ArchiveHub/archive/refs/heads/main.tar.gz | sudo tar xz --strip-components=1
  ```

  Tą samą komendą `curl … | sudo tar …` pobierasz aktualizacje; `.env` zostaje.
- **TrueNAS w Hyper-V:** daj maszynie co najmniej **8 GB** pamięci **statycznej** i wyłącz
  „pamięć dynamiczną” (ZFS źle ją znosi; objaw: „Out of memory” zaraz po starcie). Zmiana tylko na wyłączonej
  maszynie: Ustawienia → Pamięć, albo w PowerShellu
  `Set-VMMemory -VMName "TrueNAS" -DynamicMemoryEnabled $false -StartupBytes 8GB`.

## Import albumów

Album dodajesz, kopiując jego folder do udziału sieciowego (np. `\\truenas\ArchiveImport` w Eksploratorze Windows).
Osobny kontener `worker` co 30 sekund przegląda udział:

1. Nowy folder czeka, aż przez `ARCHIVEHUB_IMPORT_STABLE_MINUTES` (domyślnie 10) minut nic się w nim nie zmieni,
   czyli aż kopiowanie się skończy.
2. Z każdego skanu (JPEG, TIFF, PNG) powstają trzy pliki w bibliotece `/data/albumy/<folder>/`:
   `oryginaly/` (JPEG w pełnej rozdzielczości skanu, jakość 92, do pobrania), `podglad/` (JPEG 2560 px
   do oglądania na ekranie) i `miniatury/` (WebP 640 px). Dane EXIF (np. GPS) są usuwane, profil kolorów zostaje.
3. Rewers łączy się ze zdjęciem po nazwie: `012.jpg` + `012_r.jpg` (końcówka: `ARCHIVEHUB_REVERSE_SUFFIX`).
4. Postęp i raport (dodane, pominięte, błędy) są w Panel → Synchronizacja i na stronie albumu.

Zasady:
- Udział jest podpięty **tylko do odczytu**. Aplikacja nigdy nie zmienia ani nie usuwa Twoich skanów;
  po udanym imporcie możesz je usunąć z udziału sam (album zostaje).
- Dorzucenie plików do folderu uruchamia import ponownie. Zdjęcia już obecne (ta sama nazwa albo ta sama
  zawartość pliku) są pomijane, a rewers dorzucony później dołącza do istniejącego zdjęcia.
- Folder z `_` na początku nazwy trafia do archiwum jako ukryty.
- Nowy album nie jest widoczny dla nikogo poza masterem i grupami „widzi wszystkie albumy”,
  dopóki nie zaznaczysz go w Panel → Uprawnienia.
- Uszkodzony plik nie zatrzymuje importu: trafia do listy pominiętych.
- **Przetwórz ponownie** (Panel → Albumy → album) robi wszystkie pliki albumu od nowa ze skanów w udziale,
  np. po zmianie jakości. Nazwa, opis i uprawnienia albumu zostają. Albumy zaimportowane przed wprowadzeniem
  pełnej rozdzielczości (wersja 5000 px) worker sam ustawia w kolejce po aktualizacji; skany muszą wtedy leżeć w udziale.
- Strona albumu w panelu pokazuje, ile zajmuje on na dysku. Pełna rozdzielczość to zwykle 1–2 GB na album,
  więc przed importem wszystkich albumów sprawdź wolne miejsce (`sudo zfs list -o name,used,avail`).
- Jakość i rozmiary zmienisz w `.env`: `ARCHIVEHUB_ORIGINAL_QUALITY` (domyślnie 92),
  `ARCHIVEHUB_ORIGINAL_MAX_SIDE` (0 = pełna rozdzielczość), `ARCHIVEHUB_PREVIEW_MAX_SIDE` (2560).

### Udział importu na TrueNAS

1. **Datasets** → zaznacz pulę → **Add Dataset**: nazwa `ArchiveImport`, preset **SMB**. Zaznacz
   „Create SMB Share”. Zapamiętaj ścieżkę, np. `/mnt/NASTest/ArchiveImport`.
2. Kontener czyta pliki jako użytkownik o numerze 1000, więc musi mieć prawo odczytu:
   **Datasets** → `ArchiveImport` → **Permissions → Edit** → **Add Item**: Who `everyone@`,
   Permissions **Read**, Flags **Inherit**, zaznacz „Apply permissions recursively” → **Save Access Control List**.
   Dostęp przez sieć nadal wymaga logowania do udziału SMB.
3. W Windows: Eksplorator → `\\<adres-NAS>\ArchiveImport`, zaloguj się kontem TrueNAS z dostępem do SMB.
4. W `.env` aplikacji (`sudo nano .env`) dopisz: `ARCHIVEHUB_IMPORT_PATH=/mnt/NASTest/ArchiveImport`,
   potem `sudo docker compose --profile tunnel up -d`.
5. Sprawdź: `sudo docker compose exec worker ls /import` pokazuje foldery z udziału,
   a `sudo docker compose logs -f worker` pokazuje przebieg importu.

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
panel/         panel administratora (osoby, albumy, uprawnienia, synchronizacja, kody, grupy, tło)
albums/        albumy, zdjęcia, widoczność dla grup, import z udziału, synchronizacja, miniatury
core/          strona powitalna, tło logowania, /healthz, robots.txt, nagłówki bezpieczeństwa
templates/     szablony wspólne
static/        CSS i JavaScript (tło logowania)
tests/         testy (pytest)
deploy/        Caddyfile, konfiguracja Gunicorna, skrypt startowy kontenera
compose.yaml   usługi: app, worker (import), caddy, cloudflared (profil „tunnel”)
```

## Dane i bezpieczeństwo

- Baza danych leży w wolumenie Dockera `data` (`/data/db/archivehub.sqlite3` w kontenerze),
  obok biblioteki albumów (`/data/albumy`: oryginały JPEG, podglądy i miniatury) i zdjęć tła logowania (`/data/tlo-logowania`).
- Oryginalne skany nie są kopiowane na serwer aplikacji: worker czyta je z udziału tylko do odczytu.
- Plik `.env`, baza i zdjęcia nigdy nie trafiają do repozytorium (`.gitignore`). Repozytorium jest publiczne.
- Produkcja: przekierowanie na HTTPS, ciasteczka tylko przez HTTPS, HSTS, Content-Security-Policy
  bez skryptów inline, `noindex` dla wyszukiwarek, aplikacja w kontenerze działa jako zwykły użytkownik.

## Aktualizacja zależności

Wersje są przypięte w `requirements.txt` i `requirements-dev.txt`. Raz w miesiącu: sprawdzić nowe wersje
poprawek (np. `pip list --outdated`), podbić, uruchomić testy.

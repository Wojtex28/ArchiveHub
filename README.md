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
| 13 | Opisy zdjęć: data (także przybliżona), miejsce, osoby, tagi, historia zmian | **gotowe** |
| 14 | Wyszukiwanie: tekst bez polskich znaków, osoba, tag, miejsce, lata, album, zdjęcia bez opisu | **gotowe** |
| 15 | Bezpieczeństwo: logowanie dwuskładnikowe dla mastera, codzienna kopia bazy, snapshoty, kopia na Drive | **gotowe** |
| 16 | Produkcja: stan serwera i dziennik w panelu, monitoring, dane na datasecie, odtwarzanie po awarii | **gotowe** |
| 17+ | Import wszystkich albumów, testy końcowe… | zaplanowane |

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
docker compose exec -u archivehub worker python manage.py kopia_bazy   # kopia bazy przed aktualizacją
git pull
docker compose --profile tunnel up -d --build --force-recreate
docker compose ps        # app i worker: IMAGE „archivehub:latest”, CREATED „… seconds ago”
```

`--force-recreate` jest potrzebne: bez niego Docker Compose potrafi zbudować nowy obraz, a zostawić kontenery
na starym. Wersję, która naprawdę działa, pokazuje Panel → Start (lista zmian: [CHANGELOG.md](CHANGELOG.md)).

Migracje bazy uruchamiają się same przy starcie. Dane zostają w wolumenach Dockera.
Na TrueNAS zamiast `git pull` pobierz kod ponownie (patrz [wariant TrueNAS](#wariant-truenas-scale));
plik `.env` zostaje nietknięty.

### Kopie zapasowe

Co chroni co:

| Dane | Gdzie są | Kopia |
| --- | --- | --- |
| Baza (konta, grupy, kody, opisy, komentarze, uprawnienia) | wolumen `data`, `/data/db` | worker codziennie po 3:00 → folder `kopie/` obok `compose.yaml`; snapshoty ZFS i Google Drive (niżej) |
| Zdjęcia tła logowania | `/data/tlo-logowania` | razem z kopią bazy, w `kopie/tlo-logowania/` |
| Kod i `.env` | katalog aplikacji (dataset `ArchiveHub`) | snapshoty ZFS; kod jest też na GitHubie |
| Biblioteka albumów (JPEG, podglądy, miniatury) | `/data/albumy`: wolumen `data` albo dataset `ArchiveData` ([niżej](#dane-na-osobnym-datasecie-truenas)) | na datasecie: snapshoty ZFS. Po utracie dysku odtwarza się ją importem ze skanów PNG z Google Drive |

**Codzienna kopia bazy** powstaje sama: worker raz na dobę, po godzinie `ARCHIVEHUB_BACKUP_HOUR` (domyślnie 3),
robi spójną kopię bazy na żywo, sprawdza ją i zapisuje jako `kopie/archivehub-RRRR-MM-DD_GGMM.sqlite3`.
Zostaje 14 ostatnich dni i po jednej kopii z 12 ostatnich miesięcy (`ARCHIVEHUB_BACKUP_DAILY`, `ARCHIVEHUB_BACKUP_MONTHLY`).
Panel → Start pokazuje datę ostatniej kopii i ostrzega, gdy jest starsza niż półtorej doby albo gdy zapis się nie udał.

Kopia ręcznie, np. przed aktualizacją:

```bash
docker compose exec -u archivehub worker python manage.py kopia_bazy
```

**Przywracanie bazy** (aplikacja musi stać; obecna baza zostaje zachowana jako `archivehub-przed-przywroceniem-….sqlite3`):

```bash
docker compose stop app worker
docker compose run --rm --no-deps worker python manage.py przywroc_baze        # lista kopii
docker compose run --rm --no-deps worker python manage.py przywroc_baze archivehub-2026-10-26_0300.sqlite3
docker compose --profile tunnel up -d
```

Kopię z Google Drive najpierw wgraj do folderu `kopie/` (np. `sudo cp ~/archivehub-….sqlite3 kopie/`).
Na TrueNAS dopisz `sudo` przed `docker`.

#### Snapshoty ZFS na TrueNAS

Snapshot to zapis stanu datasetu z danej chwili; zajmuje miejsce tylko na zmiany. Chroni przed pomyłką
(usunięty plik, zepsuta aktualizacja), ale nie przed awarią dysku: do tego służy kopia na Drive.

1. **Data Protection → Periodic Snapshot Tasks → Add.**
2. Dataset: `<pula>/ArchiveHub` (Twoja pula i dataset aplikacji, z folderem `kopie`).
   **Recursive**: zaznaczone. **Snapshot Lifetime**: 2 tygodnie (`2` `Week`).
3. Schedule: **Daily**, godzina po kopii bazy, np. własny harmonogram `0 4 * * *` (4:00).
4. **Save.** Snapshoty zobaczysz w **Datasets** → `ArchiveHub` → **Data Protection** → **Manage Snapshots**.

Przywrócenie jednego pliku ze snapshotu: każdy snapshot jest widoczny w ukrytym katalogu
`/mnt/<pula>/ArchiveHub/.zfs/snapshot/<nazwa>/`, skąd kopiujesz plik poleceniem `sudo cp`.
**Rollback** całego datasetu (Manage Snapshots → ⋮ → Rollback) cofa wszystko, łącznie z nowszymi kopiami: używaj go tylko w ostateczności.

Nigdy nie usuwaj datasetów, w których nazwie jest `ArchiveHub`: tam są aplikacja, `.env` i kopie bazy.

#### Kopia poza serwerem: Google Drive

1. **Credentials → Backup Credentials → Cloud Credentials → Add**: Provider **Google Drive**,
   nazwa np. `Drive`, przycisk **Log In To Provider**, zaloguj się kontem Google i zezwól. **Verify Credential**, **Save**.
2. **Data Protection → Cloud Sync Tasks → Add**:
   - Credentials: `Drive`; Direction: **PUSH**; Transfer Mode: **COPY** (na Drive zostają też kopie usunięte już z serwera).
   - Directory/Files (lokalnie): `/mnt/<pula>/ArchiveHub/kopie`.
   - Folder (na Drive): nowy folder, np. `ArchiveHub-kopie`.
   - Schedule: codziennie, np. `30 4 * * *` (4:30, po kopii i snapshocie).
3. **Save**, potem na liście zadań **Run Now** i sprawdź, czy pliki pojawiły się na Drive.

Kopia bazy zawiera skróty haseł (nie same hasła), sekrety logowania dwuskładnikowego, kody rodzinne
i komentarze. Folder na Drive trzymaj prywatny, nie udostępniaj go nikomu.

Plik `.env` (klucz aplikacji i token tunelu) warto mieć osobno, np. w menedżerze haseł. Bez niego
aplikacja też wstanie: nowy `DJANGO_SECRET_KEY` tylko wyloguje wszystkich, a token tunelu można wygenerować
w Cloudflare od nowa.

#### Dane na osobnym datasecie (TrueNAS)

Domyślnie dane aplikacji (baza, biblioteka albumów, tło logowania) leżą w wolumenie Dockera, schowanym w `ix-apps`.
Snapshoty datasetu `ArchiveHub` go nie obejmują. Lepiej trzymać je na osobnym datasecie `ArchiveData`:
widać je wtedy w **Datasets**, można je snapshotować i od razu wiadomo, ile zajmują.

Jednorazowe przeniesienie (ok. 10–30 minut, zależnie od liczby albumów; archiwum w tym czasie nie działa):

1. **Datasets** → zaznacz pulę → **Add Dataset**: nazwa `ArchiveData`, preset **Generic** → **Save**.
2. W **System → Shell**:
   ```bash
   cd /mnt/<pula>/ArchiveHub
   sudo docker compose exec -u archivehub worker python manage.py kopia_bazy
   sudo docker compose stop app worker
   sudo chown 1000:1000 /mnt/<pula>/ArchiveData
   sudo docker run --rm -v archivehub_data:/z -v /mnt/<pula>/ArchiveData:/do alpine:3.22 cp -a /z/. /do/
   sudo du -sh /mnt/<pula>/ArchiveData       # mniej więcej tyle, ile zajmowały albumy
   echo "ARCHIVEHUB_DATA_PATH=/mnt/<pula>/ArchiveData" | sudo tee -a .env
   sudo docker compose --profile tunnel up -d --force-recreate
   sudo docker compose ps
   ```
3. Sprawdź archiwum: albumy, zdjęcia, logowanie. Panel → **Stan serwera** pokazuje wolne miejsce już na nowym datasecie.
4. Dodaj `ArchiveData` do snapshotów (**Periodic Snapshot Tasks**, jak wyżej).
5. Po kilku dniach, gdy wszystko działa, usuń stary wolumen: `sudo docker volume rm archivehub_data`.

Wolumen nazywa się `archivehub_data`, gdy katalog aplikacji to `ArchiveHub`; listę pokazuje `sudo docker volume ls`.

### Monitoring

Panel → **Stan serwera** pokazuje bazę, workera (import, obroty, kopie), ostatnią kopię i wolne miejsce,
a pod spodem dziennik: logowania, zmiany zabezpieczeń, ostrzeżenia i błędy z ostatnich 90 dni.
Gdy coś wymaga uwagi, Panel → Start pokazuje ostrzeżenie.

Żeby dostać **maila, gdy archiwum przestanie działać**, podłącz bezpłatny [UptimeRobot](https://uptimerobot.com):

1. Wygeneruj klucz: `python3 -c "import secrets; print(secrets.token_urlsafe(24))"` i dopisz do `.env`
   `ARCHIVEHUB_STATUS_TOKEN=<klucz>`. Potem `sudo docker compose --profile tunnel up -d`.
2. Sprawdź w przeglądarce `https://<twoja-domena>/healthz/pelny?klucz=<klucz>`: ma pokazać `"status": "ok"`.
3. W UptimeRobot: **New monitor** → typ **HTTP(s)**, adres jak wyżej, interwał 5 minut, powiadomienie mailem.

Adres odpowiada błędem 503, gdy nie działa strona, baza albo worker, gdy kopia bazy jest starsza niż półtorej doby
albo gdy zostało mniej niż 5 GB miejsca. UptimeRobot wysyła wtedy maila, a drugi, gdy wszystko wróci do normy.
Bez klucza adres nie istnieje (404).

### Odtwarzanie po awarii

**Serwer nie wstaje po restarcie, w przeglądarce błąd Cloudflare 1033:**

1. Odczekaj 5 minut: TrueNAS, Docker i kontenery startują po kolei.
2. Strona TrueNAS (adres pokazuje konsola maszyny) → **Apps**. Błąd „Unable to determine default interface”
   oznacza, że przy starcie nie było sieci (np. odpięty kabel). Podłącz kabel i w Shellu:
   ```bash
   sudo midclt call -j docker.update '{"pool": null}'
   sudo midclt call -j docker.update '{"pool": "<pula>"}'
   cd /mnt/<pula>/ArchiveHub && sudo docker compose --profile tunnel up -d
   ```
3. „no configuration file provided” po `cd`: dataset się nie zamontował, `sudo zfs mount <pula>/ArchiveHub`.

**Zepsuta baza albo pomyłka w panelu** (np. usunięte konto, grupa): przywróć bazę z kopii
(sekcja [Kopie zapasowe](#kopie-zapasowe)). Zmiany od czasu tej kopii przepadną.

**Utrata całego serwera albo dysku** (nowy TrueNAS od zera):

1. Postaw TrueNAS i aplikację według kroków 1–6 tej instrukcji (wariant TrueNAS). Ten sam tunel Cloudflare:
   token z panelu Cloudflare (Networks → Tunnels → `archivehub` → Configure), domena bez zmian.
   W `.env` możesz dać nowy `DJANGO_SECRET_KEY`: wszyscy zostaną tylko wylogowani.
2. Pobierz z Google Drive najnowszą kopię `archivehub-….sqlite3` (folder `ArchiveHub-kopie`) i wgraj ją
   do `kopie/` w katalogu aplikacji.
3. Przywróć bazę: `sudo docker compose stop app worker`, potem
   `sudo docker compose run --rm --no-deps worker python manage.py przywroc_baze <plik> --tak`
   i `sudo docker compose --profile tunnel up -d`. Rodzina loguje się jak dawniej: konta, grupy, uprawnienia,
   opisy i komentarze są w bazie.
4. Zdjęcia tła logowania wgraj ponownie w Panel → **Tło logowania** (są na Drive w `ArchiveHub-kopie/tlo-logowania`).
5. Albumy: skopiuj foldery ze skanami PNG z Google Drive do udziału importu (te same nazwy folderów).
   Worker rozpozna istniejące albumy. Potem w Panel → **Albumy** → album → **Przetwórz ponownie**:
   zdjęcia odzyskają pliki, a opisy, komentarze i obroty zostaną.
6. Ustaw ponownie snapshoty, Cloud Sync i monitoring.

### Gdy coś nie działa

| Objaw | Przyczyna i rozwiązanie |
| --- | --- |
| `Bad Request (400)` w przeglądarce | Domena niezgodna z `DJANGO_ALLOWED_HOSTS` w `.env`. Popraw, potem `docker compose --profile tunnel up -d` |
| `403` przy logowaniu lub wysyłaniu formularza | Brak lub literówka w `DJANGO_CSRF_TRUSTED_ORIGINS` (musi zaczynać się od `https://`) |
| `app` ma status „unhealthy” albo się restartuje | `docker compose logs app`; najczęściej pusty `DJANGO_SECRET_KEY` |
| Błąd 1033 lub 502 z Cloudflare | Tunel nie działa: `docker compose logs cloudflared`. Sprawdź token oraz że usługa w Cloudflare to `http://caddy:80` |
| „Za wiele przekierowań” | Sprawdź, że usługa w tunelu to `http://caddy:80` (nie `https`). Jeśli to nie to, wyślij mi wynik `docker compose logs caddy app` |
| Po restarcie serwera błąd 1033, w TrueNAS → Apps „Unable to determine default interface” | Przy starcie nie było sieci. Zobacz [Odtwarzanie po awarii](#odtwarzanie-po-awarii) |
| Inne strony z tego samego tunelu (np. Nextcloud) pokazują „Bad gateway” po restarcie | Serwer dostał z routera nowy adres IP. Popraw adres w Cloudflare (Tunnels → Public Hostname) i ustaw stały adres: TrueNAS → Network → Interfaces, albo rezerwacja DHCP w routerze |
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

  Aktualizacja na TrueNAS (`.env` zostaje):

  ```bash
  cd /mnt/<pula>/ArchiveHub     # Twój dataset
  sudo -v
  sudo docker compose exec -u archivehub worker python manage.py kopia_bazy
  curl -L https://github.com/Wojtex28/ArchiveHub/archive/refs/heads/main.tar.gz | sudo tar xz --strip-components=1
  sudo docker compose --profile tunnel up -d --build --force-recreate
  sudo docker compose ps
  ```
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
core/          strona powitalna, tło logowania, /healthz, stan serwera, dziennik, kopie bazy, nagłówki bezpieczeństwa
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
- Hasła: Argon2, minimum 8 znaków, odrzucane popularne hasła. Limity nieudanych prób: logowanie
  (8 na konto, 20 na adres IP w kwadransie), kody rodzinne, kod z aplikacji (5 na konto).
- Logowanie dwuskładnikowe (kod z aplikacji w telefonie) jest obowiązkowe dla konta master: bez niego
  panel i panel awaryjny są niedostępne. Sesja mastera trwa 30 dni (`ARCHIVEHUB_MASTER_SESSION_DAYS`), rodziny rok.
  Włączenie, nowe kody zapasowe i wyłączenie: link „ustawienia” w Panel → Start.
- Zgubiony telefon i kody zapasowe: na serwerze
  `docker compose exec -u archivehub app python manage.py wylacz_2fa <nick>`, zaloguj się samym hasłem
  i od razu włącz logowanie dwuskładnikowe ponownie.
- Logi (`docker compose logs app`) zapisują udane i nieudane logowania z adresem IP oraz zmiany ustawień 2FA.

## Aktualizacja zależności

Wersje są przypięte w `requirements.txt` i `requirements-dev.txt`. Raz w miesiącu: sprawdzić nowe wersje
poprawek (np. `pip list --outdated`), podbić, uruchomić testy. Co poniedziałek GitHub Actions sprawdza
zależności `pip-audit`; czerwony wynik (mail z GitHuba) znaczy, że w którejś wykryto lukę i trzeba ją zaktualizować.

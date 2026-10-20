# Lista zmian

Wszystkie zmiany w archiwum „Skany fotografii Włodyka/Bereza”, od najnowszych.

## Jak numerujemy wersje

`0.<etap>.<poprawka>`, np. `0.13.1`:

- **drugi numer to etap** z planu (ETAP 1 → `0.1.0`, ETAP 13 → `0.13.0`);
- **trzeci numer to poprawka** w obrębie etapu albo etap „b” (ETAP 4b → `0.4.1`, ETAP 7b → `0.7.1`);
- **`1.0.0`** proponuję dla wersji, z którą archiwum dostanie cała rodzina (ETAP 19). Od tej pory numer rośnie zwykłym trybem: `1.1.0` za nową funkcję, `1.0.1` za poprawkę.

Każda wersja to jeden PR (albo kilka etapów w jednym PR, gdy były zależne). Bieżącą wersję widać w Panelu na stronie Start.
Wersja jest zapisana w `config/__init__.py`, a każda ma też tag w Git (`v0.13.1`).

---

## 0.13.1 (2026-10-20)

Porządki po pierwszym pełnym wdrożeniu etapów 7–13.

### Dodane
- Ta lista zmian (`CHANGELOG.md`) i numer wersji aplikacji.
- Panel → Start pokazuje wersję działającą na serwerze i link do listy zmian. Po aktualizacji widać od razu, czy serwer naprawdę działa na nowym kodzie.

### Poprawione
- Poradnik aktualizacji: `docker compose ... up -d --build --force-recreate`. Bez `--force-recreate` Docker Compose budował nowy obraz, ale zostawiał kontenery na starym. Przez to serwer działał na wersji z ETAPU 6, choć kod był nowy.

## 0.13.0 (2026-10-20) · ETAP 13: opisy zdjęć

### Dodane
- **Panel „Opis i komentarze”** pod przyciskiem 💬 w podglądzie zdjęcia. Na górze jest opis, pod nim komentarze.
- **Pola opisu:** Kiedy, Gdzie, Kto jest na zdjęciu, Tagi, Opis. Poprawiać może każdy, kto widzi album.
- **Podpis pod zdjęciem**, np. „ok. 1958 · Berezów · Helena Bereza”: na komputerze pod zdjęciem, na telefonie nad nim. Także na osobnej stronie zdjęcia.
- **Daty wpisywane po ludzku:** `1965`, `ok. 1965` / `około` / `~`, `1965–1968`, `1965-68`, `lata 60.`, `lato 1965`, `czerwiec 1965`, `06.1965`, `12.06.1965`, `12 czerwca 1965`, `1965-06-12`.
  - Zła data daje zrozumiały komunikat („31.02.1965 nie istnieje”), a wpisane dane zostają w formularzu.
  - Oprócz tekstu zapisuje się zakres lat do wyszukiwania (ETAP 14). „ok. 1965” to 1963–1967, „lata 60.” to 1960–1969.
- **Osoby i tagi** wpisuje się po przecinku, z podpowiedziami istniejących nazw, także dla kolejnej osoby w polu. Wielkość liter nie ma znaczenia („Łucja” = „łucja”).
- **Podpowiedzi miejsc** z już wpisanych opisów.
- **Historia zmian opisu:** kto, kiedy, co było przed i po. Pod opisem widać „Ostatnia zmiana: …”.
- **Panel → Opisy:**
  - lista osób i tagów z liczbą zdjęć;
  - zmiana nazwy działa na wszystkich zdjęciach, a nazwa, która już istnieje, łączy dwa wpisy w jeden;
  - usuwanie z potwierdzeniem;
  - 100 ostatnich zmian opisów.
- Opis działa też bez JavaScriptu na stronie zdjęcia.

### Bezpieczeństwo
- Podpowiedzi osób, tagów i miejsc pochodzą tylko z albumów, które dana osoba widzi.
- Limit 30 zmian opisu na minutę na osobę. Treść zawsze przechodzi przez escapowanie HTML.

## 0.12.0 (2026-10-20) · ETAP 12: telefon, tablet, komputer

### Dodane
- **Powiększanie zdjęcia** w podglądzie i na stronie zdjęcia:
  - komputer: dwuklik w wybranym miejscu, kółko myszy, klawisze `+` `−` `0`, przeciąganie myszką;
  - telefon i tablet: dwa palce albo dwukrotne stuknięcie, przesuwanie jednym palcem;
  - przesunięcie palcem zmienia zdjęcie tylko wtedy, gdy nie jest powiększone;
  - działa razem z obrotem, a następne zdjęcie zawsze otwiera się w normalnej wielkości.

### Zmienione
- Telefon:
  - archiwum w dwóch kolumnach albumów, długie opisy skrócone do 3 linijek;
  - ciaśniejsze menu, „Wyloguj” zawsze widoczne;
  - zakładki panelu w jednym przewijanym wierszu, bieżąca od razu widoczna;
  - w tabeli „Uprawnienia” kolumna z nazwą albumu zostaje na miejscu przy przewijaniu w bok;
  - większe przyciski w „Tle logowania”.
- Przegląd 21 stron na 390, 820 i 1440 px: nigdzie nie ma przewijania w bok.

## 0.11.0 (2026-10-20) · ETAP 11: strona główna

### Dodane
- Strona główna ze zdjęciami rozrzuconymi jak odbitki na stole: spadają po kolei, lekko się unoszą i prostują po najechaniu.
- Zalogowana osoba widzi losowe zdjęcia ze swoich albumów (klik otwiera zdjęcie), licznik „3 albumy · 160 zdjęć” z polską odmianą i „Zalogowano jako …”.
- Animacje wyłącza ustawienie systemowe „ogranicz ruch”.

### Bezpieczeństwo
- Niezalogowana osoba widzi tylko zdjęcia wybrane w „Tle logowania” i żadnych liczb.

## 0.10.0 (2026-10-20) · ETAP 10: komentarze

### Dodane
- **Komentarze pod zdjęciami**, podpisane nickiem. Przycisk 💬 z liczbą komentarzy otwiera panel: na komputerze z prawej, na telefonie od dołu.
- Licznik komentarzy na miniaturach w galerii.
- `Ctrl+Enter` wysyła komentarz. Strzałki w polu tekstowym nie zmieniają zdjęcia, a `Esc` tylko wychodzi z pola.
- Autor usuwa swój komentarz, administrator każdy.
- Panel → Komentarze: najnowsze komentarze ze wszystkich albumów, z usuwaniem.
- Komentarze działają też bez JavaScriptu na stronie zdjęcia (`?komentarze=1`).
- Po usunięciu konta komentarze zostają, podpisane „konto usunięte”.

### Bezpieczeństwo
- Limit 2000 znaków i 10 komentarzy na minutę na osobę. Treść zawsze przechodzi przez escapowanie HTML.
- Cudzy komentarz wygląda dla zwykłej osoby jak nieistniejący (404).

## 0.9.0 (2026-10-20) · ETAP 9: cały album i oryginały PNG

### Dodane
- „Pobierz cały album (ZIP, 1,1 GB)” w galerii, z rozmiarem paczki od razu na przycisku.
- Panel → album: pole „Link do oryginałów PNG” (folder w Google Drive, tylko `https://`). Rodzina widzi link w galerii albumu, a dostęp ustawia się w Drive.
- Najwyżej 3 ZIP-y pobierane naraz (`ARCHIVEHUB_MAX_ZIP_DOWNLOADS`). Kolejna osoba dostaje prośbę, żeby spróbowała za kilka minut, więc strona nie zwalnia dla innych.

## 0.8.0 (2026-10-20) · ETAP 8: pobieranie zdjęć

### Dodane
- Przycisk ⤓ w podglądzie pobiera oryginał w pełnej rozdzielczości, osobno awers i rewers.
  - Nazwa pliku: `<album> - <zdjęcie>.jpg`, z polskimi literami (z wersją bez ogonków dla starych programów).
- „Zaznacz zdjęcia do pobrania” w galerii: pasek z liczbą zaznaczonych, „Zaznacz wszystkie”, „Pobierz ZIP”, „Anuluj”.
- ZIP ma w środku folder z nazwą albumu, a rewersy leżą obok jako `..._r.jpg`.
- ZIP jest wysyłany na bieżąco, bez składania na dysku serwera, także dla bardzo dużych paczek (ZIP64).
- Pobrane zdjęcie zawsze stoi tak jak w galerii: obrót, na który worker jeszcze nie zdążył, pobieranie robi od razu.
- Log, kto co pobrał.

### Bezpieczeństwo
- Każde pobranie przechodzi przez tę samą kontrolę dostępu co podgląd.

## 0.7.1 (2026-10-20) · ETAP 7b: obracanie zdjęć

### Dodane
- Przyciski ↺ ↻ w podglądzie dla każdego, kto ogląda album. Obrót zapisuje się od razu i widzą go wszyscy: w siatce, w podglądzie, na okładce i w panelu.
- Awers i rewers obraca się osobno.
- Worker obraca też same pliki (oryginał, podgląd, miniaturę), gdy przez 30 s nikt już nie klikał (`ARCHIVEHUB_ROTATION_DELAY_SECONDS`). Do tego czasu obraca przeglądarka.
- Po obróceniu pliku zmienia się jego adres (`?v=`), więc przeglądarka nie pokaże starej wersji.
- „Przetwórz ponownie” od razu obraca obraz ze skanu, bez podwójnej kompresji.
- W bazie zapisuje się, kto i kiedy ostatnio obrócił zdjęcie.

### Zmienione
- Panel → album (z niezmergowanego osobno PR #10):
  - długie nazwy plików łamią się w kafelku, więc końcówka `_1`, `_2` jest widoczna;
  - okładkę oznacza gwiazdka ★ na miniaturze zamiast linku „Okładka”.

## 0.7.0 (2026-10-20) · ETAP 7: galeria

### Dodane
- Galeria albumu: siatka miniatur ładowanych przy przewijaniu.
- Podgląd na cały ekran:
  - strzałki, klawisze i przesunięcie palcem na telefonie;
  - przycisk „Pokaż rewers / awers”;
  - „Wstecz” w przeglądarce zamyka podgląd;
  - sąsiednie zdjęcia wczytują się z wyprzedzeniem.
- Każde zdjęcie ma własny adres, który działa bez JavaScriptu i nadaje się do wysłania komuś z rodziny.
- Podgląd 2560 px, a oryginał nie jest wysyłany do samego oglądania.
- Przeglądarka trzyma zdjęcia w pamięci i pyta serwer tylko „czy coś się zmieniło”.

## 0.6.0 (2026-10-20) · ETAP 6: uprawnienia

### Dodane
- Panel → album: karta „Kto widzi ten album” z grupami do zaznaczenia i listą osób, które go teraz widzą.
- Panel → osoba: „Widzi albumy”.

### Bezpieczeństwo
- Każdy plik zdjęcia (miniatura, podgląd, oryginał, rewers) przechodzi przez jedno wspólne sprawdzenie dostępu.
- Testy prób dostępu obejmują: osobę bez grupy, wylogowaną osobę, wyłączone konto, zgadywanie numerów zdjęć i panel dla zwykłej osoby.

## 0.5.0 (2026-10-20) · ETAP 5: zarządzanie albumami

### Dodane
- Panel → album: nazwa wyświetlana, opis i „Ukryty” (album widzi tylko administrator).
- Wybór okładki spośród zdjęć albumu. Bez wybranej okładki (albo gdy jej plik zniknie) pokazuje się pierwsze zdjęcie.
- Kolejność albumów: strzałki ↑↓ i „Ułóż według nazw folderów” (01, 02 … 10 jak w Eksploratorze). Nowy album trafia na koniec.
- Archiwum dla rodziny: kafelki z okładką i opisem, w kolejności z panelu.

## 0.4.1 (2026-10-20) · ETAP 4b: pełna rozdzielczość

### Zmienione
- Ze skanu powstają trzy pliki:
  - oryginał JPEG w pełnej rozdzielczości (jakość 92, do pobrania);
  - podgląd 2560 px;
  - miniatura WebP 640 px.
  - Wcześniej był jeden JPEG 5000 px.
- Mniejsze zużycie pamięci: skan 108 Mpx mieści się w ok. 650 MB (wcześniej 1,2 GB).

### Dodane
- Panel → album: „Przetwórz ponownie” robi pliki od nowa ze skanów w udziale. Nazwa, opis i uprawnienia zostają.
- Albumy w starej wersji 5000 px worker sam ustawia w kolejce, jeśli skany leżą w udziale.
- Rozmiar albumu na dysku w panelu.
- Ustawienia `ARCHIVEHUB_ORIGINAL_QUALITY`, `ARCHIVEHUB_ORIGINAL_MAX_SIDE`, `ARCHIVEHUB_PREVIEW_MAX_SIDE`.

## 0.4.0 (2026-10-20) · ETAP 4: import albumów

### Dodane
- Nowy kontener `worker`. Co 30 s przegląda udział SMB `ArchiveImport`, a folder, który przez 10 minut się nie zmienia, zamienia w album.
- Ze skanu powstaje wersja do oglądania (JPEG bez EXIF/GPS, z profilem kolorów) i miniatura WebP. Obsługiwane formaty: JPEG, TIFF (też 16-bit), PNG. Uwzględniany jest obrót z EXIF.
- Rewersy po nazwie: `img…_2.png` + `img…_2_r.png`. Rewers dorzucony później dołącza do zdjęcia, a rewers bez awersu jest zgłaszany.
- Ponowne wrzucenie folderu dodaje tylko nowe pliki (porównanie nazwy i sumy kontrolnej).
- Uszkodzony plik nie przerywa importu, tylko trafia do listy „Pominięte”.
- Panel:
  - kolejka i wyniki importów;
  - „W kolejce importu” na stronie Start;
  - miniatury albumu z oznaczeniem rewersu;
  - zdjęcia, którym zniknął plik.
- Kolejność zdjęć jak w Eksploratorze Windows (1, 2, 10).

### Bezpieczeństwo
- Udział jest podpięty tylko do odczytu: aplikacja nigdy nie zmienia ani nie usuwa skanów.
- Miniatury dostaje tylko zalogowana osoba z dostępem do albumu.
- Nowy album nie jest widoczny dla rodziny, dopóki nie zaznaczysz go w Uprawnieniach (wyjątek: grupy „widzi wszystkie albumy”).

## 0.3.0 (2026-10-20) · ETAP 3: albumy w panelu, uprawnienia grup, tło logowania

### Dodane
- Każdy folder w bibliotece zdjęć to album.
  - „Synchronizuj archiwum” dodaje nowe foldery i zapisuje raport.
  - Zniknięty folder dostaje znacznik „brak folderu”, a nic nie jest usuwane.
  - Folder z `_` na początku jest ukryty.
- Panel → Uprawnienia: tabela albumy × grupy.
- Grupa „widzi wszystkie albumy”, także dodane w przyszłości.
- „Mam kod”: zalogowana osoba wpisuje kolejny kod i dołącza do następnej grupy.
- Archiwum pokazuje albumy widoczne dla danej osoby.
- Tło logowania:
  - siatka reagująca na kursor, z łagodnym śladem;
  - pod nią pływające zdjęcia, które można złapać i rzucić myszką albo palcem;
  - zdjęcia wgrywa się w Panel → Tło logowania;
  - szanuje „ogranicz ruch”.

### Bezpieczeństwo
- Zdjęcia tła są zmniejszane do 900 px i zapisywane od nowa bez EXIF/GPS. Leżą w `/data/tlo-logowania`, nigdy w repozytorium.

## 0.2.1 (2026-10-19) · poprawki po pierwszym wdrożeniu

### Zmienione
- Poradnik wdrożenia w kolejności, która zadziałała na serwerze: token tunelu → `.env` → start → adres `http://caddy:80`.
- Nowa sekcja „Wariant: TrueNAS SCALE”:
  - bez instalacji Dockera, z datasetem;
  - `curl` zamiast `git`;
  - wklejanie w web Shell;
  - stała pamięć w Hyper-V.
- Nowe wiersze w „Gdy coś nie działa”: stary DNS na komputerze, `Invalid service URL format`, „Unsupported”.
- cloudflared 2026.10.1.
- Pełniejszy test po wdrożeniu i opis hasła konta master.

### Dodane
- Limity pamięci kontenerów: aplikacja 768 MB (`ARCHIVEHUB_APP_MEMORY`), Caddy 128 MB, cloudflared 256 MB. Przy braku RAM-u ucierpi kontener, a nie NAS.

## 0.2.0 (2026-10-19) · ETAP 2: konta i logowanie

### Dodane
- Dołączanie kodem rodzinnym (np. `lipa-bocian-64`): nick, własne hasło i od razu przypisanie do grupy.
- Logowanie nickiem (wielkość liter bez znaczenia), zmiana własnego hasła, wylogowanie.
- Konto administratora („master”) i panel `/panel/`:
  - osoby: dodawanie, grupy, ustawianie hasła, blokada, usuwanie;
  - kody rodzinne: podpowiedź kodu, limit użyć, data ważności, wyłączanie;
  - grupy.
- Poradnik wdrożenia od zera w README.

### Bezpieczeństwo
- Limity nieudanych prób w oknie 15 minut:
  - logowanie: 20 na adres IP i 8 na nick;
  - kod rodzinny: 10 na adres IP.
- Panel dla innych osób wygląda jak nieistniejący (404). `/admin/` korzysta ze wspólnej strony logowania.

## 0.1.0 (2026-10-19) · ETAP 1: fundament

### Dodane
- Django 5.2 LTS, SQLite (tryb WAL), Gunicorn, Caddy i Docker Compose. Strona powitalna i `/healthz`.
- Cloudflare Tunnel jako opcja (`--profile tunnel`), bez otwierania portów, obok Nextclouda.
- Konfiguracja ze zmiennych środowiskowych (`.env.example`).
- Testy (pytest), ruff, GitHub Actions z budowaniem obrazu i sprawdzeniem startu kontenera.

### Bezpieczeństwo
- Hasła haszowane Argon2.
- W produkcji:
  - przekierowanie na HTTPS i HSTS;
  - bezpieczne ciasteczka;
  - Content-Security-Policy bez skryptów inline;
  - `noindex`.
- Kontener aplikacji działa jako zwykły użytkownik, nie root.

## 0.0 (2026-10-19) · ETAP 0: analiza i architektura

Bez kodu: analiza, wybór technologii, plan etapów 0–20. Repozytorium założone pustym commitem.

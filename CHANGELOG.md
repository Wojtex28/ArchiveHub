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

## 0.54.0 (2026-11-13) · ETAP 54: zdarzenia pod osią czasu, dodawanie z drzewa

- **„Gdzie pokazać”** w każdym zdarzeniu z życia: na osi czasu (według daty, z ikonką) albo pod osią jako zwykły tekst, np. „Miejsce zamieszkania: Boreczek 70 · 1950 – 1986”. Miejsce zamieszkania trafia domyślnie pod oś, także te wpisane wcześniej. Zmienisz to w „Popraw”.
- Zdarzenia pod osią i bez daty nie mają znaczka na pasku życia w widoku „Oś czasu” drzewa.
- **Zdarzenia w panelu bocznym drzewa**: lista zdarzeń osoby i „+ Dodaj zdarzenie” z tymi samymi polami co na karcie osoby (bez zdjęcia, które dodasz w „Popraw” na karcie).
- Miejsce, które powtarza tytuł zdarzenia, nie wyświetla się drugi raz.

## 0.52.1 (2026-11-13) · poprawka: dyskretne kropki osób na zdjęciu

- Kropki osób na zdjęciu są domyślnie ledwo widoczne i szare (10%), więc nie zasłaniają zdjęcia. Wyraźnieją płynnie, gdy kursor się do nich zbliża.
- Po najechaniu na kropkę pokazuje się, kto to jest, a po zjechaniu podpis znika (kliknięcie już go nie zostawia). Na telefonie kropki są półprzezroczyste, a stuknięcie pokazuje i chowa podpis.

## 0.52.0 (2026-11-13) · ETAP 50–52: kafelki i lista, „Moje albumy”, edycja albumu

### ETAP 50: kafelki albo lista
- **Przełącznik nad albumami** (≡ lista, ▦ kafelki), zapamiętywany w przeglądarce. Kafelki są po trzy w rzędzie, wyższe i z większą okładką; lista ma w każdym wierszu dużą okładkę, nazwę, lata i dłuższy opis.
- **Kolumna „Twoje” z lewej**: Ulubione i Twoje albumy z miniaturą i liczbą zdjęć. Na telefonie to przewijany pasek nad albumami.
- Nazwy z folderów rozkładają się lepiej: „Pociety” też znika, „95-96-97” to lata 1995–1997, a folder bez nazwy pokazuje się jako „Album 49”.

### ETAP 51: „Moje albumy”
- Pod Ulubionymi jest **„+ Utwórz swój album”**: wpisujesz nazwę i album jest gotowy. Widzisz go tylko Ty; zdjęcia zostają w swoich albumach.
- Kto ma swój album, po kliknięciu gwiazdki ☆ dostaje **okienko z listą**: Ulubione i jego albumy do zaznaczenia, a także pole „Nowy album…”. Kto nie ma, ma gwiazdkę jak dawniej (od razu do Ulubionych).
- Strona albumu z pobieraniem całości w ZIP, zmianą nazwy i usuwaniem (usunięcie nie rusza zdjęć).

### ETAP 52: edycja albumu
- Przycisk **✎ przy albumie** (na liście i nad zdjęciami albumu) otwiera edycję: nazwa, opis, **lata od–do** i **okładka** wybierana kliknięciem w zdjęcie. Nazwa z folderu jest już rozłożona na słowa, wystarczy poprawić polskie znaki. Edycję widzi tylko konto administratora.
- Wybór okładki przeniesiony z Panel → Albumy do edycji albumu (panel ma do niej przycisk).

## 0.49.1 (2026-11-12) · poprawka: mocniejsze pomniejszanie zdjęć

- **Zdjęcie można pomniejszyć poniżej rozmiaru ekranu** (do 30%): kółkiem myszy, rozsunięciem palców na touchpadzie albo telefonie, klawiszem „−”. Przy nietypowych proporcjach łatwiej je wtedy objąć wzrokiem. Dwuklik albo klawisz „0” wraca do zwykłego rozmiaru.
- **Przyciski „−” i „+” na pasku podglądu** (na komputerze), obok obracania.
- Obrócone zdjęcie mieści się w tych samych granicach co nieobrócone (na komputerze 90% miejsca); wcześniej dochodziło do samych krawędzi ekranu.

## 0.49.0 (2026-11-12) · ETAP 49: nowa lista albumów

### Zmienione
- **Czytelne nazwy albumów.** Nazwa z folderu („01_BrązowyZeZlotaObramowka97-04_Pocięte”) jest pokazywana jako „Brązowy ze Zlota Obramowka” z latami „1997–2004” i numerem „01” na okładce; końcówka „Pocięte” znika. Dane w bazie się nie zmieniają, a nazwa wpisana w Panel → Albumy zawsze wygrywa. Ta sama czytelna nazwa jest w nagłówku albumu i w przeglądarce zdjęć.
- **Nic nie wychodzi poza kartę**: długie nazwy łamią się i kończą wielokropkiem po dwóch linijkach (pełna nazwa w podpowiedzi). Na telefonie strona nie przesuwa się już w bok.
- **Okładka jako mozaika**: zdjęcie okładki i dwa kolejne obok. Na komputerze przesunięcie myszą po okładce pokazuje kolejne zdjęcia z albumu (kropki pod spodem mówią, które).
- **Pod nazwą konkretne informacje**: liczba zdjęć z poprawną odmianą, lata (z nazwy folderu albo z dat zdjęć) i liczba oznaczonych osób, np. „212 zdjęć · 1962–1968 · 14 osób”.
- **Ulubione jako pasek nad albumami** z miniaturami ostatnio oznaczonych zdjęć, zamiast kafelka udającego album.
- **Telefon**: jedna kolumna szerokich kart, okładka po lewej, opis po prawej.
- Karta lekko się unosi pod myszą; wygląd spójny w trybie jasnym i nocnym.

## 0.48.1 (2026-11-12) · poprawka: ikonka trybu nocnego

- Obok przełącznika trybu jest księżyc w trybie dziennym i słońce w trybie nocnym (zmienia się od razu po przełączeniu).

## 0.48.0 (2026-11-12) · ETAP 48: zdarzenia na osi czasu drzewa

- W widoku „Oś czasu” drzewa zdarzenia z życia z datą (zamieszkanie, nauka, praca, wojsko…) są małymi ikonkami na pasku życia osoby. Po najechaniu widać, co to i gdzie.
- Bez zmian w bazie.

## 0.47.0 (2026-11-12) · ETAP 47: miejsce ślubu, pochówek, zdjęcie przy zdarzeniu

- **Miejsce ślubu** przy parze (np. „parafia w Kraczkowej”), w panelu bocznym drzewa i na karcie osoby. Widać je w chronologii i przy partnerze („ślub 1950 (Kraczkowa)”).
- **Pochówek** (cmentarz, kwatera) jako pole przy śmierci, pokazuje się dopiero po włączeniu „Nie żyje”. Widać go na karcie osoby i w chronologii.
- **Zdjęcie przy zdarzeniu:** przy dodawaniu zdarzenia można wybrać jedno ze zdjęć tej osoby (np. dom, szkoła, wojsko). Miniatura w chronologii prowadzi do zdjęcia.
- **Panel → Drzewo → „Osoby bez płci”:** osoby, przy których płci nie dało się podpowiedzieć z imienia, z przyciskami „kobieta” i „mężczyzna”.
- Strona drzewa otwarta przed aktualizacją nie kasuje przy zapisie nowych pól (płeć, pochówek, miejsce ślubu).
- Aktualizacja dodaje trzy pola (migracje `albums.0018`, `family.0007`).

## 0.46.0 (2026-11-12) · ETAP 46: płeć, chronologia życia i zdarzenia

- **Chronologia na karcie osoby.** Oś czasu układa się sama z drzewa: urodzenie, śluby, narodziny dzieci, śmierć rodziców, partnera i dzieci, śmierć. Przy zdarzeniach widać wiek osoby.
- **Zdarzenia dopisywane ręcznie** przyciskiem „+ Dodaj zdarzenie”: miejsce zamieszkania, chrzest / ślub kościelny, nauka, praca, wojsko i wojna, przeprowadzka / emigracja, inne. Każde ma datę (także „od–do”), miejsce i notatkę; można je poprawić i usunąć.
- Zdarzenia są w historii zmian drzewa (Panel → Drzewo) i da się je cofnąć jak resztę.
- **Płeć osoby** (kobieta, mężczyzna, nie wiadomo) podpowiada się z imienia przy dodaniu osoby i jest do poprawienia w „Edytuj dane”. Osoby dodane wcześniej dostały ją tą samą regułą przy aktualizacji. Od płci zależą słowa w chronologii („urodziła się córka”, „śmierć ojca”).
- Data ślubu jest bardziej widoczna: przy partnerze jest „+ Data ślubu” zamiast „Ślub, rozwód”.
- Aktualizacja dodaje pole płci (migracja `albums.0017`) i tabelę zdarzeń (`family.0006`).

## 0.45.0 (2026-11-12) · ETAP 45: okno portretu i zdjęcia osoby według dat

- **Portret wybiera się w oknie.** W „Edytuj dane” zamiast długiego paska zdjęć jest podgląd i przycisk „Wybierz portret”. W oknie widać wszystkie zdjęcia z tą osobą, a wybrane zdjęcie można przesunąć i powiększyć pod kółkiem, żeby twarz była na środku.
- Jeśli osoba ma na zdjęciu punkt (ETAP 44), kadr od razu ustawia się na ten punkt.
- Ten sam kadr widać na kafelku w drzewie, w panelu bocznym, na liście osób i na karcie osoby. Portrety wybrane wcześniej zostają wyśrodkowane jak dotąd.
- **Zdjęcia na karcie osoby są ułożone od najnowszych**, z nagłówkami dziesięcioleci („1980–1989”), a zdjęcia bez daty są na końcu.
- Naprawione: tytuł karty osoby w zakładce przeglądarki zawierał fragment kodu strony.
- Aktualizacja dodaje trzy pola kadru do osób (migracja `albums.0016`), z wartościami domyślnymi.

## 0.44.0 (2026-11-12) · ETAP 44: punkty osób na zdjęciu

- **Osobę można wskazać punktem na zdjęciu.** W panelu zdjęcia, przy każdej osobie z „Kto jest na zdjęciu”, jest przycisk 📍: po nim jedno kliknięcie na zdjęciu stawia kropkę. Imię widać po najechaniu na kropkę (na telefonie po stuknięciu) albo na osobę na liście.
- Punkt można przesunąć (📍 i nowe kliknięcie) albo usunąć („Usuń punkt”). Kropki trzymają się miejsca przy powiększaniu i obracają się razem ze zdjęciem.
- **Zgodne wstecz:** osoby oznaczone wcześniej zostają bez punktu i nic się u nich nie zmienia. Zdjęcie osoby z listy „Kto” usuwa też jej punkt.
- Zmiany punktów widać w Panelu → Opisy, jak inne zmiany opisu.
- Aktualizacja dodaje jedną nową tabelę (migracja `albums.0015`), istniejących danych nie zmienia.

## 0.43.0 (2026-11-12) · ETAP 43: poprawki przy zdjęciach i osi czasu

- **Naprawione:** osoba dodana do zdjęcia przez „+ Dodaj nową osobę”, a potem zdjęta „×”, daje się dodać ponownie (wcześniej było „Ta osoba już jest na liście”).
- **Backspace nie usuwa już osób.** Osobę ze zdjęcia zdejmuje tylko „×” na jej etykiecie, więc jeden Backspace za dużo niczego nie kasuje.
- **„Kiedy” i „Gdzie” widać zawsze** w panelu zdjęcia (z napisem „nie wpisano”, gdy są puste), a przycisk nazywa się „Dodaj datę, miejsce i opis”.
- **Podgląd zdjęcia na komputerze** zajmuje najwyżej 90% miejsca, żeby na dużym ekranie nie było za blisko. Na telefonie bez zmian.
- **Oś czasu** na wąskim ekranie nie ściska się do szerokości okna, tylko przewija w bok, i ma zawsze widoczny pasek przewijania na dole.

## 0.42.0 (2026-11-10) · ETAP 42: ładniejsza karta osoby nad drzewem

- **Pasek u góry karty** z napisem „Karta osoby”, przyciskiem „Pełna strona ↗” i ×. Karta przewija się pod paskiem, więc pasek przewijania nie wchodzi już na przycisk zamykania.
- **Większe marginesy** od ramki do treści (2 rem na komputerze, 1,25 rem na telefonie).
- Urodzenie i śmierć w osobnych kafelkach, sekcje „Rodzina” i „Zdjęcia” oddzielone linią, nagłówki grup (Rodzice, Partnerzy…) mniejsze i spokojniejsze.
- Na telefonie mniejszy portret, a urodzenie i śmierć stoją obok siebie.
- W panelu bocznym drzewa „Nie żyje” i „Rozwód lub rozstanie” są przełącznikami jak w iOS, a pole „Rok ślubu” wygląda jak inne pola.
- **Pola śmierci schowane za przełącznikiem**: „Data śmierci” i „Miejsce śmierci” pojawiają się dopiero po włączeniu „Nie żyje” (w panelu drzewa i w formularzu). Wyłączenie przełącznika czyści te pola przy zapisie.

## 0.41.0 (2026-11-10) · ETAP 41: przełączniki jak w iOS

- **Tryb nocny to teraz przełącznik** (zielony, gdy włączony) z ikoną 🌙, na prawej krawędzi paska, w linii z tytułem strony. Na telefonie też stoi obok tytułu.
- **Pola „tak/nie” w formularzach wyglądają tak samo**: „Nie żyje” w danych osoby, „Rozwód lub rozstanie” przy parze, „Tylko zdjęcia bez opisu” w wyszukiwarce i pojedyncze opcje w Panelu (np. „widzi wszystkie albumy”).
- Listy wyboru wielu rzeczy (grupy przy albumie, tabela uprawnień) zostają zwykłymi kratkami, bo przy wielu pozycjach przełączniki są mniej czytelne.

## 0.40.0 (2026-11-09) · ETAP 40: tryb nocny

- **Tryb nocny** dla całej strony: ciemne, ciepłe tło zamiast papieru, jasny tekst, przyciski i linki w kolorze starej czerwieni rozjaśnionej do ciemnego tła. Działa w archiwum, albumach, ulubionych, wyszukiwarce, drzewie i osi czasu, w Panelu oraz na stronie logowania (kropki tła też ściemniają się).
- **Przełącznik w menu**: „🌙 Tryb nocny” / „☀️ Tryb dzienny”. Wybór zapamiętuje przeglądarka (ciasteczko `motyw` na rok), więc każdy domownik ustawia go u siebie. Przełącza się od razu, bez przeładowania; bez JavaScriptu działa jak zwykły formularz.
- **Bez wyboru strona idzie za ustawieniem telefonu/komputera**: jeśli system ma ciemny motyw, archiwum też otworzy się ciemne.
- Podgląd zdjęcia był i zostaje ciemny w obu trybach.
- W środku: każdy kolor w `site.css` jest teraz zmienną w `:root`, a tryb nocny podmienia tylko te zmienne (test pilnuje, żeby żadnej nie zabrakło).

## 0.39.0 (2026-11-09) · ETAP 39: połączenia bez uskoków

- **Bez „schodków” w liniach.** Gdy linia od rodziców schodzi prawie nad środkiem dziecka, linia dziecka wchodzi w kafelek dokładnie pod nią (do 48 px od środka), zamiast robić krótki uskok w bok.
- Jedno dziecko dokładnie pod rodzicami to jedna prosta kreska, bez kropek.

## 0.38.0 (2026-11-09) · ETAP 38: uporządkowany układ drzewa

Zamiast „jak najmniej przecięć za wszelką cenę” drzewo trzyma się kilku stałych zasad:

- **Rodzeństwo stoi razem, jednym blokiem**, od najstarszego. Dwie rodziny nie mają już kresek jedna nad drugą.
- **Małżeństwo łączące dwie rodziny stoi na styku ich bloków.** Taka osoba stoi na brzegu swojego rodzeństwa, nawet gdy nie jest najmłodsza, bo wtedy linie się nie krzyżują.
- **Odstępy mówią, kto do kogo należy:** rodzeństwo i pary stoją ciasno, między różnymi rodzinami jest większa przerwa.
- **Spokojniejszy wygląd:** linie par w tym samym brązowym kolorze co reszta (tylko grubsze), mniejsze i szare opisy „ślub 1950”.

## 0.37.0 (2026-11-09) · ETAP 37: linie drzewa w jednym kolorze

- **Bez kolorów rodzin.** Linie od rodziców do dzieci są wszystkie w jednym, stonowanym kolorze. Gdy linie dwóch rodzin biegną obok siebie, rozróżniają je osobne wysokości szyn i kropki w miejscach, gdzie dziecko odchodzi od szyny.

## 0.36.0 (2026-11-09) · ETAP 36: jedno drzewo, równiejszy układ

- **Bez widoku „Wokół osoby”.** Drzewo zawsze pokazuje wszystkich. Znikają przełącznik, znaczki ↑ ↓ i pasek na dole. Stare linki z `?wokol=` i `?zakres=` po prostu otwierają całe drzewo.
- **Teściowie przy swoich dzieciach.** Rodzice bez własnych rodziców w drzewie stoją rząd nad swoimi dziećmi, a nie w górnym rzędzie z najstarszym pokoleniem. Nie ciągną już długich linii przez całe drzewo.
- **Rodzice nad dziećmi.** Miejsca w rzędach są wyważane w obie strony: rodzice stoją nad środkiem dzieci, dzieci pod rodzicami. Linie są o 30–40% krótsze, a drzewo mniej rozjechane.
- **Mniej przecięć linii.** Kafelek może przejść w dowolne miejsce rzędu (nie tylko zamienić się z sąsiadem), a kolejność jest liczona z kilku punktów startowych i wygrywa ta z najmniejszą liczbą przecięć. Data urodzenia rodzeństwa dalej ustala kolejność od najstarszego.

## 0.35.0 (2026-11-09) · ETAP 35: drzewo wokół osoby, bez krzyżujących się linii

Pomysł z aplikacji Strom.

- **Widok „Wokół osoby” (domyślny).** Drzewo pokazuje wybraną osobę, jej przodków, rodzeństwo, partnerów i potomków z ich partnerami. Rodziców teściów i zięciów nie rysuje, więc linie się nie krzyżują.
- **Znaczki ↑ i ↓ na kafelku** mówią, ilu krewnych jest poza widokiem (rodzice, dzieci). Kliknięcie znaczka pokazuje drzewo wokół tej osoby. W panelu osoby jest też przycisk „Drzewo wokół tej osoby”.
- **Pasek na dole drzewa:** czyje drzewo widać, ile osób z całości, liczba pokoleń przodków i potomków (− / +).
- **„Całe drzewo”** pokazuje wszystkich naraz, jak dotąd. Tam przy małżeństwach dwóch rodzin linie mogą się przecinać.
- **Drzewo zawsze układa się samo.** Kafelków nie da się już przesuwać, a przycisk „Ułóż automatycznie” zniknął. Przeciągnięcie kafelka przesuwa widok. Przeciągnięcie „+” na drugą osobę dalej łączy rodzinę.
- Adres strony zapamiętuje widok (`?wokol=` osoba albo `?zakres=wszyscy`).

## 0.34.0 (2026-11-09) · ETAP 34: dane osoby w panelu bocznym, karta osoby nad drzewem

- **Panel boczny pokazuje wszystkie dane osoby:** datę i miejsce urodzenia, datę i miejsce śmierci oraz opis (dłuższy opis zwinięty, z „Więcej”).
- **„Edytuj dane” bez wychodzenia z drzewa.** Formularz wysuwa się jako nakładka na panel boczny (na telefonie od dołu). Po zapisaniu drzewo i oś czasu od razu się odświeżają, a błędy pokazują się przy polach. Działa też na osi czasu, np. dla osób bez daty urodzenia. Zmiana trafia do historii, jak dotąd.
- **Karta osoby i zdjęcia otwiera się w okienku nad drzewem**, bez przechodzenia na inną stronę. Kliknięcie krewnego w okienku przechodzi do jego karty i zaznacza go w drzewie. Esc albo × zamyka okienko.
- W okienku jest przycisk **„Pełna strona osoby ↗”**, który otwiera zwykłą stronę osoby w nowej karcie (np. żeby komuś wysłać link).
- Link „Pokaż w drzewie” ze strony osoby od razu otwiera jej panel boczny.

## 0.33.0 (2026-11-08) · ETAP 33: rodzeństwo

- **Dodawanie rodzeństwa bez rodziców.** Na karcie osoby i w drzewie jest nowy rodzaj połączenia „brat / siostra” (przycisk „+ Rodzeństwo” i uchwyt „+” po lewej stronie kafelka, który można też przeciągnąć na kogoś z drzewa).
- Gdy osoba ma już rodziców w drzewie, brat lub siostra zostaje po prostu ich dzieckiem, tak jak dotąd.
- Gdy rodziców jeszcze nie ma, rodzeństwo jest zapisane jako osobne połączenie i w drzewie łączy je przerywana klamra z podpisem „rodzeństwo”. Kafelki rodzeństwa stoją obok siebie w jednym pokoleniu, w kolejności urodzenia.
- Gdy później ktoś doda rodzica jednemu z rodzeństwa, ten rodzic trafia do całego rodzeństwa, a klamra zamienia się w zwykłe linie od rodziców.
- Połączenie rodzeństwa można usunąć (×) i cofnąć w Panelu → Drzewo, jak każdą zmianę.

## 0.32.0 (2026-11-08) · ETAP 32: pasy pokoleń i oś czasu w drzewie

Pomysły podpatrzone w aplikacji Strom, dopasowane do naszego drzewa.

### Dodane
- **Pasy pokoleń.** Za kafelkami leżą poziome pasy, po jednym na pokolenie, z podpisem przy lewej krawędzi: „1. pokolenie”, „2. pokolenie”… i lata urodzenia osób w tym pasie. Po kliknięciu osoby podpisy liczą się od niej: „Pokolenie dziadków”, „Pokolenie rodziców”, „Pokolenie: Jan Bereza”, „Pokolenie dzieci”, „Pokolenie wnuków”. Pasy idą za kafelkami także przy ręcznym ułożeniu. Podpis zostaje na ekranie przy przewijaniu, a przy mocnym pomniejszeniu (np. na telefonie) skraca się do „Pok. 1” albo „Rodzice”.
- **Oś czasu: drugi widok drzewa.** Przełącznik „Drzewo | Oś czasu” we wstążce. Każda osoba to pasek od roku urodzenia do roku śmierci, ułożone według dat urodzenia. Kolor paska to kolor jej pokolenia (ten sam co kropka przy pasie). Na pasku: złote kółko to ślub (przerywane: ślub zakończony rozwodem), kropka to urodzenie dziecka. Osoba żyjąca ma strzałkę do dziś, a nieznany rok śmierci (albo urodzenia) rozmywa koniec paska. Kliknięcie osoby otwiera tę samą kartę co w drzewie. Przyciski −, ⤢, + zmieniają skalę lat. Osoby bez żadnej daty są w liście „Bez dat” pod osią. Widok zapamiętuje się w adresie (`?widok=os`), więc odświeżenie zostawia oś.

### Zmienione
- Dane drzewa dla kanwy zawierają też rok śmierci osoby (potrzebny osi czasu).

---

## 0.31.0 (2026-11-06) · ETAP 31: kilku partnerów jednej osoby

### Dodane
- **Osoba z kilkoma partnerami stoi w środku**: pierwszy związek po lewej, drugi po prawej (kolejne na zmianę dalej od środka). Każda para ma własną linię, a dzieci schodzą ze środka swojej pary, więc widać, z którego związku jest które dziecko.
- **Rok ślubu i rozwód.** W drzewie po kliknięciu osoby, przy partnerze, jest „Ślub, rozwód”, a na karcie osoby to samo pod partnerem. Rok ślubu ustala kolejność związków (bez roku liczy się kolejność dodania). Para po rozwodzie lub rozstaniu ma linię przerywaną. Nad linią osoby z kilkoma partnerami jest opis, np. „1. ślub 1950”, „2. ślub 1960 rozwód”. Zmiany trafiają do historii i da się je cofnąć. Usunięcie pary i cofnięcie tego przywraca też rok ślubu i rozwód.

### Zmienione
- **Linia pary jest teraz ciągła** (była przerywana), bo przerywana oznacza rozwód. Gdy między partnerami stoi ktoś inny, linia przechodzi łukiem nad jego kafelkiem zamiast pod nim.
- Partnerzy na karcie osoby i w panelu bocznym drzewa są w kolejności związków.

---

## 0.30.0 (2026-11-06) · ETAP 30: drzewo według dat urodzenia, przełącznik „Nie żyje”

### Dodane
- **Przełącznik „Nie żyje” (†).** W drzewie, po kliknięciu osoby, jest pole „Nie żyje †” (dla kont z prawem edycji), a w „Edytuj dane” to samo pole nad datą śmierci. Kafelek osoby zmarłej jest przygaszony (szare tło, portret w odcieniach szarości), a lata mają †: „† 1918–1990”, „1946 – †” (data śmierci nieznana) albo „† nie żyje”. Wpisanie daty lub miejsca śmierci zaznacza przełącznik samo. Każda zmiana trafia do historii (Panel → Drzewo) i da się ją cofnąć. Osoby z wpisaną już datą śmierci mają przełącznik zaznaczony od razu po aktualizacji.

### Zmienione
- **„Ułóż automatycznie” bierze pod uwagę daty urodzenia.** Rodzeństwo stoi od najstarszego z lewej do najmłodszego z prawej. Kolejność urodzenia wygrywa z jednym-dwoma przecięciami linii, ale nie z większym bałaganem. Rodzeństwo bez daty urodzenia może stać gdziekolwiek.
- **Osobne gałęzie i pojedyncze osoby trafiają do rzędu swoich rówieśników** według roku urodzenia (np. ktoś urodzony w 1990 do rzędu wnuków), a nie zawsze do górnego rzędu.
- Już ułożone drzewo zostaje jak było. Nowy układ widać po kliknięciu „Ułóż automatycznie”.

---

## 0.29.0 (2026-11-02) · ETAP 29: osoby na zdjęciu na wierzchu, ulubione

### Dodane
- **Ulubione.** Gwiazdka ☆ nad zdjęciem w podglądzie dodaje je do „Ulubionych” konta, a ★ usuwa. Ulubione to prywatny album każdej osoby: jest w menu i jako pierwszy kafelek na stronie albumów. Całość pobierzesz jednym przyciskiem jako ZIP (oryginały z rewersami, w folderach albumów). W albumie ulubione zdjęcia mają małą gwiazdkę w rogu. Zdjęcie z albumu, do którego konto straci dostęp, znika z ulubionych.

### Zmienione
- **„Kto jest na zdjęciu” ma własną sekcję na górze panelu 💬**, nad opisem i komentarzami, z przyciskiem „Popraw osoby” i własnym zapisem. Opis (kiedy, gdzie, tagi) poprawia się osobno. Przy osobach z drzewa jest 🌳 z linkiem do ich karty (dla kont z dostępem do drzewa).

### Naprawione
- **Na telefonie podgląd zdjęcia nie powiększa już całej strony.** Gest dwóch palców w podglądzie powiększa tylko zdjęcie. Wcześniej, gdy palec trafił np. w pasek z przyciskami albo podpis, powiększała się cała strona, a potem nie było jak jej pomniejszyć (zostawało odświeżenie). Gdyby strona była już powiększona przed otwarciem podglądu, wraca do normalnej skali.

---

## 0.28.0 (2026-11-02) · ETAP 28: „Ułóż automatycznie” z jak najmniejszą liczbą przecięć

### Zmienione
- **„Ułóż automatycznie” szuka kolejności z najmniejszą liczbą przecięć linii.** Sprawdza różne kolejności rodzeństwa i par w każdym pokoleniu (od góry i od dołu drzewa, potem zamiany sąsiadów i odwrócenie par) i zostawia tę, w której linie rodzin najmniej się krzyżują. Dzieci stoją pod środkiem swoich rodziców.
- **Współmałżonek spoza rodziny staje po zewnętrznej stronie**, z dala od rodzeństwa partnera, żeby linia do rodzeństwa go nie przecinała.
- **Wysokości linii rodzin są dobierane tak, żeby się nie przecinały**, gdy kilka rodzin dzieli jedno pokolenie. Kolor dostają tylko linie, które naprawdę na siebie zachodzą.
- Przy niektórych układach, np. gdy rodzeństwo z jednej rodziny żeni się z rodzeństwem z drugiej, jedno przecięcie zostaje, bo nie da się go uniknąć na płaskim rysunku.

---

## 0.27.0 (2026-11-02) · ETAP 27: nazwisko rodowe na kafelku, czytelne linie rodzin

### Zmienione
- **Linie do dzieci nie zlewają się już między rodzinami.** Każda rodzina (para i jej dzieci) ma własną poziomą linię. Gdy linie dwóch rodzin zachodzą na siebie, leżą na różnych wysokościach i mają różne stonowane kolory, a kropki pokazują, gdzie dziecko odchodzi od linii. Wcześniej po „Ułóż automatycznie” wszystkie linie jednego pokolenia łączyły się w jedną i nie było widać, czyje jest które dziecko.
- **Nazwisko rodowe jest na kafelku drzewa w nawiasie, jaśniejszym kolorem**, zaraz po imieniu i nazwisku: „Helena Bereza (Kowalska)”. Druga linia kafelka to teraz tylko lata życia, więc już się nie ucina. Nazwisko rodowe wpisuje się jak dotąd w karcie osoby → „Popraw dane”.

---

## 0.26.0 (2026-11-02) · ETAP 26: imiennicy

### Naprawione
- **Druga osoba o tym samym imieniu i nazwisku nie łączy się już z pierwszą.** Wcześniej wpisanie w drzewie np. drugiego „Jan Bereza” podpinało istniejącego Jana pod nowe miejsce, a przy dziecku dokładało mu drugiego rodzica i parowało obcych rodziców, co rozsypywało drzewo.

### Dodane
- **Pytanie „Kogo dodajesz?”**, gdy wpisana nazwa jest już w archiwum (w drzewie albo na zdjęciach): „Tę osobę” z latami życia, rodzicami, partnerem i liczbą zdjęć albo „Inną osobę o tym samym imieniu i nazwisku”. Działa na kanwie, w formularzu „Dodaj osobę do drzewa” i na karcie osoby.
- **Imiennicy w opisie zdjęcia:** w polu „Kto” obaj są na liście z latami życia i zapisuje się ten wybrany. Na liście „Kto” pod zdjęciem imiennicy z drzewa mają lata życia.
- Zmiana imienia osoby na takie, które ktoś już ma, jest dozwolona; strona tylko o tym przypomina.
- Panel → Opisy: imiennicy z drzewa są podpisani („imiennik: lata · w drzewie”), a zmiana nazwy nie łączy dwóch osób z drzewa w jedną.

---

## 0.25.0 (2026-11-02) · ETAP 25: dziecko od pary rodziców, kanwa na cały ekran

### Zmienione
- **Dziecko dwojga rodziców ma jedną linię od środka pary**, a rodzice są połączeni linią pary. Wcześniej, gdy rodzice nie byli zaznaczeni jako para, do dziecka szły dwie osobne linie.
- **„+ Dziecko”** przy osobie z partnerem dodaje dziecko obojgu. W formularzu jest „Drugi rodzic” do wyboru (przy kilku partnerach albo „nie wiadomo”). Przeciągnięcie „+” dziecka na kogoś z drzewa też łączy go z parą, gdy rodzic ma jednego partnera.
- **Drugi rodzic dziecka zostaje parą z pierwszym** (także gdy się rozstali). Istniejące drzewo uzupełnia się samo przy aktualizacji.
- „+ Rodzic” znika, gdy osoba ma już dwoje rodziców.
- Każde dodatkowe połączenie (drugi rodzic, para) to osobny wpis w historii, który można cofnąć.
- **Kanwa drzewa na całą szerokość okna** i do jego dołu, bez ramki. Nad nią wstążka z tytułem i wszystkimi narzędziami („+ Osoba”, „Ułóż automatycznie”, powiększenie). Pomoc, osoby spoza drzewa i lista osób są pod kanwą.
- **Karta osoby wysuwa się z prawej krawędzi** nad kanwą (na telefonie od dołu), a widok przesuwa się tak, żeby wybrana osoba nie chowała się pod kartą. Esc zamyka kartę.

## 0.24.0 (2026-11-02) · ETAP 24: wybór osób na zdjęciu z listy

### Zmienione
- **„Kto jest na zdjęciu”** to teraz wybór z listy zamiast wpisywania nazw po przecinku. Po kilku literach lista podpowiada najpierw osoby z drzewa (z latami życia), potem pozostałe osoby ze zdjęć. Wyszukiwanie nie zwraca uwagi na wielkość liter ani polskie znaki („lucja” znajdzie „Łucję”).
- Nową osobę dodaje się tylko świadomie, przyciskiem „+ Dodaj nową osobę”, więc literówka nie tworzy dubla. Wpisane, ale niewybrane imię zatrzymuje zapis z prośbą o wybór.
- Wybrane osoby są kafelkami z „×”. Bez JavaScriptu zostaje dawne pole z nazwami po przecinku.

### Poprawione
- Zdjęcie osoby z jej ostatniego zdjęcia usuwało ją z archiwum, a razem z nią miejsce w drzewie i połączenia. Teraz osoby z drzewa (i z historią w drzewie) zostają.

## 0.23.0 (2026-11-02) · ETAP 23: drzewo rodzinne, historia zmian z przywracaniem

### Dodane
- **Panel → Drzewo:** wszystkie zmiany w drzewie od najnowszych (kto, kiedy, co; przy zmianie danych: było → jest), z filtrem po osobie i koncie.
- **„Przywróć” przy każdej zmianie:** usunięta osoba wraca razem z połączeniami (te, których już nie da się odtworzyć, np. bo dziecko ma w międzyczasie dwoje innych rodziców, aplikacja pomija i o tym pisze), zmienione dane wracają do poprzednich, usunięta relacja wraca, a dodana relacja albo osoba znika z drzewa.
- Przywrócenie też jest zmianą w historii, więc i je da się cofnąć. Cofnięta zmiana jest przekreślona, z datą i kontem, które ją cofnęło.
- Karta osoby (dla administratora): „Historia zmian” z historią tej osoby.
- **Panel → Osoby:** kolumna „Drzewo” i „Ustaw wszystkim”, czyli dostęp do drzewa dla wszystkich kont naraz (np. ukrycie drzewa przed premierą).

### Zmienione
- Połączenie dwóch osób w Panel → Opisy przenosi też ich historię w drzewie.

## 0.22.0 (2026-11-02) · ETAP 22: drzewo rodzinne, kanwa z przeciąganiem

### Dodane
- **Kanwa drzewa** (Drzewo): osoby jako kafelki z portretem, imieniem i latami życia; linie od rodziców do dzieci (od środka pary, gdy rodzice są parą) i przerywana linia między partnerami.
- **Przesuwanie i powiększanie:** przeciąganie tła albo jednym palcem; kółko myszy, dwa palce albo przyciski − / + oraz „Pokaż całe drzewo”.
- **Przeciąganie kafelków**; miejsce zapisuje się dla wszystkich.
- **Uchwyty „+” na wybranym kafelku:** u góry rodzic, z boku partner, na dole dziecko. Kliknięcie otwiera pole na imię (z podpowiedziami osób z archiwum), a przeciągnięcie „+” na inną osobę łączy je w rodzinę.
- **Panel osoby** obok kanwy (na telefonie pod nią): dane, link do karty ze zdjęciami, lista krewnych z usuwaniem połączeń, „+ Rodzic / Partner/ka / Dziecko”, „Usuń z drzewa”.
- **„Ułóż automatycznie”:** pokolenia w rzędach, pary obok siebie, rodzeństwo pod rodzicami. Nowe osoby same stają przy krewnych.
- **Osoby ze zdjęć spoza drzewa** pod kanwą: przeciągnij na drzewo albo kliknij.
- Karta osoby: „Pokaż w drzewie”.
- Bez JavaScriptu pod kanwą zostaje lista osób i karty.

## 0.21.0 (2026-11-02) · ETAP 21: drzewo rodzinne, dane i karta osoby

### Dodane
- **Drzewo rodzinne** (menu „Drzewo”). Węzeł drzewa to ta sama osoba, którą oznacza się na zdjęciach, więc jej zdjęcia pojawiają się w drzewie same.
- **Karta osoby:**
  - imię i nazwisko, nazwisko rodowe, data i miejsce urodzenia oraz śmierci (daty także przybliżone: „ok. 1920”, „lata 20.”), historia;
  - portret wybrany spośród zdjęć osoby;
  - rodzice, partnerzy i dzieci jako linki;
  - zdjęcia osoby z nazwą albumu, otwierane w galerii.
- **Relacje** rodzic–dziecko i para, z kontrolą błędów: najwyżej dwoje rodziców, bez pętli (nikt nie zostanie własnym przodkiem).
- **Lista osób w drzewie** z wyszukiwaniem oraz „Osoby ze zdjęć spoza drzewa”.
- **Dostęp per konto** (Panel → Osoby → konto → „Drzewo rodzinne”): oglądanie i edycja (domyślnie), tylko oglądanie, brak dostępu.
- **Historia zmian w drzewie:** każda zmiana jest zapisywana (kto, kiedy, co, stan przed i po), żeby w ETAPIE 23 dało się ją przejrzeć i cofnąć.

### Zmienione
- Panel → Opisy: połączenie dwóch osób przenosi też ich relacje i dane z drzewa; osoby z drzewa nie da się tam usunąć, dopóki jest w drzewie.

Etapy 18–20 (testy końcowe, udostępnienie rodzinie) czekają na import wszystkich albumów, dlatego numer wersji przeskakuje do 21.

## 0.17.0 (2026-10-27) · ETAP 17: import wszystkich albumów

### Dodane
- **Panel → Synchronizacja:**
  - album importowany w tej chwili: ile zdjęć z ilu, pasek postępu i szacowany czas do końca;
  - podsumowanie kolejki: ile folderów i zdjęć zostało i ile potrwa cały import;
  - wolne miejsce na dysku i ile zajmą czekające foldery, z ostrzeżeniem, gdy nie wystarczy;
  - lista „Foldery w udziale”: liczba zdjęć i rewersów, rozmiar skanów, stan (nowy, trwa kopiowanie, w kolejce, importowanie, zaimportowany, błąd) i rewersy bez zdjęcia głównego.
- **Kontrola miejsca:** album czeka, jeśli po jego imporcie zostałoby mniej niż 5 GB wolnego; import rusza sam, gdy miejsca przybędzie.
- README: „Import wszystkich albumów naraz”.

### Zmienione
- Worker importuje najwyżej jeden album na przejście, więc między albumami dalej obraca zdjęcia i robi kopię bazy.

## 0.16.1 (2026-10-27)

### Poprawione
- **Przesuwanie powiększonego zdjęcia:**
  - na touchpadzie przesuwanie dwoma palcami przesuwa powiększone zdjęcie, a rozsuwanie palców je powiększa i pomniejsza (kółko myszy dalej powiększa);
  - przeciąganie myszą nie urywa się, gdy kursor wyjedzie poza zdjęcie albo nad przyciski;
  - w Firefoksie przeciąganie nie chwyta już zdjęcia jak pliku.

## 0.16.0 (2026-10-27) · ETAP 16: przygotowanie produkcyjne

### Dodane
- **Panel → Stan serwera:**
  - sprawdza bazę danych, workera (import, obroty, kopie), ostatnią kopię bazy i wolne miejsce na dysku;
  - zawiera dziennik: logowania, zmiany zabezpieczeń, ostrzeżenia i błędy z ostatnich 90 dni, z filtrami „Problemy”, „Logowania i konta”, „Wszystko”.
- **Ostrzeżenie na Panel → Start**, gdy któreś sprawdzenie wymaga uwagi.
- **Adres dla monitoringu** `/healthz/pelny?klucz=…` (klucz w `.env`, `ARCHIVEHUB_STATUS_TOKEN`):
  - odpowiada 503, gdy coś nie działa;
  - darmowy UptimeRobot wysyła wtedy maila;
  - bez klucza adres nie istnieje.
- **Dane na osobnym datasecie:** `ARCHIVEHUB_DATA_PATH` w `.env` przenosi bazę i bibliotekę albumów z wolumenu Dockera do wskazanego katalogu, więc obejmują je snapshoty ZFS. Instrukcja przeniesienia jest w README.
- **README:**
  - sekcje „Monitoring” i „Odtwarzanie po awarii”: restart bez sieci, przywrócenie bazy, postawienie wszystkiego od zera z kopii na Google Drive;
  - nowe wiersze w „Gdy coś nie działa”.

### Zmienione
- Błędy 404 (boty zgadujące adresy) nie trafiają do dziennika w panelu, tylko do logów Dockera.

## 0.15.0 (2026-10-26) · ETAP 15: bezpieczeństwo i kopie zapasowe

### Dodane
- **Logowanie dwuskładnikowe dla konta master.** Oprócz hasła kod z aplikacji w telefonie (Google Authenticator, Microsoft Authenticator, Aegis i podobne):
  - włączanie: kod QR do zeskanowania (albo klucz do przepisania) i potwierdzenie pierwszym kodem;
  - 10 jednorazowych kodów zapasowych na wypadek zgubienia telefonu, do wygenerowania od nowa;
  - wyłączenie wymaga hasła i kodu; zmiana telefonu to wyłączenie i ponowne włączenie;
  - na serwerze `manage.py wylacz_2fa <nick>`, gdy zginie i telefon, i kody zapasowe.
- **Codzienna kopia bazy.** Worker raz na dobę (po 3:00) robi spójną kopię bazy na żywo i ją sprawdza:
  - kopie lądują w folderze `kopie/` obok `compose.yaml`, razem ze zdjęciami tła logowania;
  - zostaje 14 ostatnich dni i po jednej kopii z 12 ostatnich miesięcy;
  - `manage.py kopia_bazy` robi kopię od ręki (np. przed aktualizacją);
  - `manage.py przywroc_baze` pokazuje listę kopii i przywraca wybraną, a obecną bazę odkłada obok.
- **Panel → Start, sekcja „Bezpieczeństwo”:** stan logowania dwuskładnikowego i ostatniej kopii bazy, z ostrzeżeniem, gdy kopia jest starsza niż półtorej doby albo się nie udała.
- **README, „Kopie zapasowe”:** co jest kopiowane i gdzie, przywracanie bazy, snapshoty ZFS na TrueNAS i codzienna kopia folderu `kopie` na Google Drive (Cloud Sync).
- **Cotygodniowe sprawdzanie zależności** (`pip-audit` w GitHub Actions): czerwony wynik oznacza znaną lukę w którejś bibliotece.

### Zmienione
- Konto master nie wejdzie do panelu ani do panelu awaryjnego bez włączonego logowania dwuskładnikowego. Po zalogowaniu od razu trafia na ekran włączania.
- Sesja konta master trwa 30 dni zamiast roku; rodzina dalej loguje się raz na rok.
- Włączenie albo wyłączenie logowania dwuskładnikowego wylogowuje to konto na innych urządzeniach.
- Logi zapisują udane i nieudane logowania z adresem IP.
- Caddy odrzuca żądania większe niż 100 MB (tyle samo przepuszcza Cloudflare).

### Bezpieczeństwo
- Przegląd całej aplikacji: HTTPS i nagłówki, hasła, sesje, uprawnienia, XSS, CSRF, limity prób, logi i zależności. Wyniki są w raporcie z etapu 15.
- Kod z aplikacji działa tylko raz i najwyżej 5 błędnych prób na kwadrans; kody zapasowe są przechowywane jako skróty.

## 0.14.0 (2026-10-22) · ETAP 14: wyszukiwanie

### Dodane
- **Strona „Szukaj”** w menu górnym:
  - jedno pole tekstowe przeszukuje opisy, daty, miejsca, osoby, tagi, komentarze i nazwy albumów;
  - wielkość liter i polskie znaki nie mają znaczenia: „berezow” znajdzie „Berezów”, „lucja” znajdzie „Łucja”;
  - kilka słów zawęża wyniki: „jan wesele” to zdjęcia, na których są oba słowa.
- **Filtry** (pod „Więcej filtrów”): osoba, tag, miejsce, od roku, do roku, album i „Tylko zdjęcia bez opisu”. Pola podpowiadają nazwy, które już są w archiwum.
- **Lata działają z datami przybliżonymi:** „ok. 1965” pojawi się przy szukaniu lat 60.
- **Wyniki** są od najstarszych, a zdjęcia bez daty na końcu. Strony mają po 60 zdjęć.
  - Kliknięcie otwiera ten sam podgląd co w albumie: strzałki przechodzą po wynikach, a pasek pokazuje album danego zdjęcia.
  - Działają obracanie, pobieranie, opis i komentarze.
- **Pusta strona wyszukiwania** podpowiada:
  - dziesięciolecia, osoby i tagi z liczbą zdjęć (klik od razu szuka);
  - link „Zdjęcia bez opisu: N”, żeby rodzina wiedziała, co jeszcze opisać.
- **Opis zdjęcia prowadzi do wyszukiwania:** klik w osobę, tag, miejsce albo datę w panelu „Opis i komentarze” pokazuje wszystkie takie zdjęcia.

### Bezpieczeństwo
- Wyniki, podpowiedzi i liczby obejmują tylko albumy, które dana osoba widzi.

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

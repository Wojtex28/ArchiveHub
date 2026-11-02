// Pole „Kto jest na zdjęciu”: wybór osób z listy zamiast wpisywania nazw po przecinku.
// Osoby z drzewa są na górze listy. Nową osobę dodaje się tylko świadomym „+ Dodaj nową osobę”,
// więc literówka nie tworzy dubla. Pod spodem dalej jest zwykłe pole z nazwami po przecinku,
// które wysyła formularz (bez JavaScriptu to ono jest widoczne).
(function () {
  "use strict";

  var LIMIT = 40;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  // Bez wielkości liter i polskich znaków: „lucja” znajdzie „Łucję”.
  function fold(text) {
    return text.toLocaleLowerCase("pl").replace(/ł/g, "l").normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function clean(name) {
    return name.replace(/[,;\n]/g, " ").replace(/\s+/g, " ").trim();
  }

  function split(value) {
    var names = [], seen = {};
    value.split(/[,;\n]/).forEach(function (part) {
      var name = clean(part);
      var key = name.toLocaleLowerCase("pl");
      if (name && !seen[key]) { seen[key] = true; names.push(name); }
    });
    return names;
  }

  function init(input) {
    if (input.pickerReady) return;
    var source = document.getElementById(input.getAttribute("data-people-picker"));
    if (!source) return;
    input.pickerReady = true;
    var choices = JSON.parse(source.textContent);
    var known = {};
    choices.forEach(function (choice) { known[choice.name.toLocaleLowerCase("pl")] = choice; });
    var selected = split(input.value);
    var options = [], active = -1;

    var box = element("div", "picker");
    var chips = element("ul", "picker__chips");
    var search = element("input", "picker__search");
    var list = element("ul", "picker__list");
    var note = element("p", "picker__note");
    search.type = "text";
    search.id = input.id + "-szukaj";
    search.autocomplete = "off";
    search.placeholder = "Wpisz imię lub nazwisko";
    search.setAttribute("role", "combobox");
    search.setAttribute("aria-autocomplete", "list");
    search.setAttribute("aria-expanded", "false");
    list.id = input.id + "-lista";
    list.setAttribute("role", "listbox");
    list.hidden = true;
    note.setAttribute("role", "alert");
    note.hidden = true;
    search.setAttribute("aria-controls", list.id);
    box.append(chips, search, list, note);
    input.type = "hidden";
    input.removeAttribute("list");
    input.after(box);
    var label = input.form && input.form.querySelector("label[for='" + input.id + "']");
    if (label) label.htmlFor = search.id;

    function save() {
      input.value = selected.join(", ");
    }

    function drawChips() {
      chips.replaceChildren.apply(chips, selected.map(function (name, index) {
        var item = element("li", "picker__chip");
        var choice = known[name.toLocaleLowerCase("pl")];
        if (choice && choice.tree) item.classList.add("is-tree");
        item.append(element("span", "", name));
        var remove = element("button", "picker__remove", "×");
        remove.type = "button";
        remove.setAttribute("aria-label", "Usuń z opisu: " + name);
        remove.addEventListener("click", function () {
          selected.splice(index, 1);
          save(); drawChips();
          search.focus();
        });
        item.append(remove);
        return item;
      }));
    }

    function isSelected(name) {
      var key = name.toLocaleLowerCase("pl");
      return selected.some(function (other) { return other.toLocaleLowerCase("pl") === key; });
    }

    function close() {
      list.hidden = true;
      search.setAttribute("aria-expanded", "false");
      search.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function setActive(index) {
      var items = list.querySelectorAll("[role=option]");
      if (!items.length) return;
      active = (index + items.length) % items.length;
      items.forEach(function (item, i) { item.classList.toggle("is-active", i === active); });
      search.setAttribute("aria-activedescendant", items[active].id);
      items[active].scrollIntoView({ block: "nearest" });
    }

    function open() {
      var query = fold(clean(search.value));
      var matches = choices.filter(function (choice) {
        return !isSelected(choice.name) && (!query || fold(choice.name).indexOf(query) >= 0);
      });
      if (!query) matches = matches.filter(function (choice) { return choice.tree; });
      matches = matches.slice(0, LIMIT);
      options = matches.map(function (choice) { return { name: choice.name, years: choice.years, tree: choice.tree }; });
      var typed = clean(search.value);
      // „+ Dodaj nową” dopiero od trzech liter (albo gdy nic nie pasuje), żeby nie kusiło przy „be”.
      if (typed && !known[typed.toLocaleLowerCase("pl")] && (typed.length >= 3 || !options.length)) {
        options.push({ name: typed, fresh: true });
      }
      var nodes = [], heading = null;
      options.forEach(function (option, index) {
        var group = option.fresh ? "" : option.tree ? "W drzewie" : "Ze zdjęć, poza drzewem";
        if (group && group !== heading) {
          heading = group;
          var head = element("li", "picker__group", group);
          head.setAttribute("role", "presentation");
          nodes.push(head);
        }
        var item = element("li", "picker__option" + (option.fresh ? " picker__option--new" : ""));
        item.id = list.id + "-" + index;
        item.setAttribute("role", "option");
        item.setAttribute("data-index", index);
        if (option.fresh) {
          item.textContent = "+ Dodaj nową osobę: „" + option.name + "”";
        } else {
          item.append(element("span", "", option.name));
          if (option.years) item.append(element("span", "picker__years", option.years));
        }
        nodes.push(item);
      });
      if (!options.length) {
        var empty = element("li", "picker__empty", query ? "Ta osoba już jest na liście." : "Wpisz kilka liter imienia lub nazwiska.");
        empty.setAttribute("role", "presentation");
        nodes.push(empty);
      }
      list.replaceChildren.apply(list, nodes);
      list.hidden = false;
      search.setAttribute("aria-expanded", "true");
      active = -1;
      if (query && options.length) setActive(0);
    }

    function pick(index) {
      var option = options[index];
      if (!option) return;
      if (option.fresh) known[option.name.toLocaleLowerCase("pl")] = { name: option.name, tree: false };
      selected.push(option.name);
      save(); drawChips();
      search.value = "";
      note.hidden = true;
      open();
      search.focus();
    }

    search.addEventListener("input", function () { note.hidden = true; open(); });
    search.addEventListener("focus", open);
    search.addEventListener("blur", function () {
      window.setTimeout(function () { if (document.activeElement !== search) close(); }, 150);
    });
    search.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); if (list.hidden) open(); setActive(active + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); setActive(active - 1); }
      else if (event.key === "Enter") {
        if (!list.hidden && active >= 0) { event.preventDefault(); pick(active); }
        else if (clean(search.value)) event.preventDefault();
      } else if (event.key === "Escape" && !list.hidden) { event.preventDefault(); event.stopPropagation(); close(); }
      else if (event.key === "Backspace" && !search.value && selected.length) {
        selected.pop(); save(); drawChips();
      }
    });
    // Klik w listę nie zabiera kursora z pola wyszukiwania.
    list.addEventListener("mousedown", function (event) { event.preventDefault(); });
    list.addEventListener("click", function (event) {
      var item = event.target.closest("[role=option]");
      if (item) pick(Number(item.getAttribute("data-index")));
    });
    // Wpisane, ale niewybrane imię: zamiast cicho je zgubić, prosimy o wybór.
    if (input.form) {
      input.form.addEventListener("submit", function (event) {
        var typed = clean(search.value);
        if (!typed) return;
        var choice = known[typed.toLocaleLowerCase("pl")];
        if (choice) {
          if (!isSelected(choice.name)) selected.push(choice.name);
          search.value = "";
          save(); drawChips();
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        note.textContent = "Wybierz „" + typed + "” z listy albo kliknij „+ Dodaj nową osobę”.";
        note.hidden = false;
        search.focus();
        open();
      });
    }
    drawChips();
  }

  function scan(root) {
    if (root.querySelectorAll) root.querySelectorAll("[data-people-picker]").forEach(init);
  }

  scan(document);
  // Panel opisu w galerii przychodzi z serwera już po wczytaniu strony.
  new MutationObserver(function (records) {
    records.forEach(function (record) {
      record.addedNodes.forEach(function (node) { if (node.nodeType === 1) scan(node); });
    });
  }).observe(document.body, { childList: true, subtree: true });
})();

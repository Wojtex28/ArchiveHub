/* Tło strony logowania: siatka kwadracików połączonych cienkimi liniami,
   lekko reagująca na kursor (ślad powoli wygasa), a pod nią
   pływające zdjęcia, które można złapać i przesunąć (myszką lub palcem).
   Bez bibliotek; dane zdjęć przychodzą w <script type="application/json">. */
(() => {
  "use strict";

  const root = document.querySelector("[data-login-bg]");
  if (!root) return;

  const layer = root.querySelector(".login-bg__photos");
  const canvas = root.querySelector(".login-bg__grid");
  const ctx = canvas.getContext("2d");
  const dataNode = document.getElementById("login-photos");
  const photos = dataNode ? JSON.parse(dataNode.textContent) : [];
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const css = getComputedStyle(document.documentElement);
  const DOT = css.getPropertyValue("--grid-dot").trim() || "59 51 43";
  const DOT_ACTIVE = css.getPropertyValue("--grid-dot-active").trim() || "111 47 42";

  // reach: zasięg kursora (px), push: o ile odsuwa punkty, rise/fall: szybkość narastania i wygasania.
  const GRID = { spacing: 26, size: 2, reach: 170, push: 7, rise: 7, fall: 1.1 };
  const pointer = { x: -9999, y: -9999, active: false };

  let width = 0;
  let height = 0;
  let dpr = 1;
  let dots = [];
  let cols = 0;
  let rows = 0;
  let gridDirty = true;

  // --- Siatka kropek -------------------------------------------------------

  function buildGrid() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const s = width < 600 ? GRID.spacing - 4 : GRID.spacing;
    cols = Math.ceil(width / s) + 1;
    rows = Math.ceil(height / s) + 1;
    const offX = (width - (cols - 1) * s) / 2;
    const offY = (height - (rows - 1) * s) / 2;
    dots = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        dots.push({ x: offX + c * s, y: offY + r * s, dx: 0, dy: 0, glow: 0 });
      }
    }
    gridDirty = true;
  }

  function updateGrid(dt) {
    // Punkty lekko odsuwają się spod kursora i powoli wracają na miejsce, zostawiając ślad.
    const up = 1 - Math.exp(-dt * GRID.rise);
    const down = 1 - Math.exp(-dt * GRID.fall);
    let moving = false;
    for (const d of dots) {
      let tx = 0;
      let ty = 0;
      let tg = 0;
      if (pointer.active) {
        const ox = d.x - pointer.x;
        const oy = d.y - pointer.y;
        const dist = Math.hypot(ox, oy);
        if (dist < GRID.reach && dist > 0.001) {
          const f = (1 - dist / GRID.reach) ** 2;
          tx = (ox / dist) * f * GRID.push;
          ty = (oy / dist) * f * GRID.push;
          tg = f;
        }
      }
      const ease = tg > d.glow ? up : down;
      d.dx += (tx - d.dx) * ease;
      d.dy += (ty - d.dy) * ease;
      d.glow += (tg - d.glow) * ease;
      if (Math.abs(tx - d.dx) > 0.02 || Math.abs(ty - d.dy) > 0.02 || Math.abs(tg - d.glow) > 0.003) {
        moving = true;
      }
    }
    return moving;
  }

  function drawGrid() {
    ctx.clearRect(0, 0, width, height);
    const at = (r, c) => dots[r * cols + c];
    const px = (d) => d.x + d.dx;
    const py = (d) => d.y + d.dy;

    // Cieniutkie linie do sąsiada z prawej i z dołu: cała siatka jedną ścieżką.
    ctx.lineWidth = 0.5;
    ctx.strokeStyle = `rgb(${DOT} / 0.09)`;
    ctx.beginPath();
    const lit = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const d = at(r, c);
        for (const n of [c + 1 < cols ? at(r, c + 1) : null, r + 1 < rows ? at(r + 1, c) : null]) {
          if (!n) continue;
          ctx.moveTo(px(d), py(d));
          ctx.lineTo(px(n), py(n));
          const glow = (d.glow + n.glow) / 2;
          if (glow > 0.03) lit.push([d, n, glow]);
        }
      }
    }
    ctx.stroke();
    // Linie przy kursorze: w kolorze akcentu, wyraźniejsze.
    for (const [d, n, glow] of lit) {
      ctx.strokeStyle = `rgb(${DOT_ACTIVE} / ${glow * 0.45})`;
      ctx.beginPath();
      ctx.moveTo(px(d), py(d));
      ctx.lineTo(px(n), py(n));
      ctx.stroke();
    }

    // Kwadraciki w węzłach.
    const half = GRID.size / 2;
    ctx.fillStyle = `rgb(${DOT} / 0.3)`;
    for (const d of dots) {
      if (d.glow <= 0.03) ctx.fillRect(px(d) - half, py(d) - half, GRID.size, GRID.size);
    }
    for (const d of dots) {
      if (d.glow <= 0.03) continue;
      const size = GRID.size + d.glow * 1.5;
      ctx.fillStyle = `rgb(${DOT_ACTIVE} / ${0.3 + d.glow * 0.55})`;
      ctx.fillRect(px(d) - size / 2, py(d) - size / 2, size, size);
    }
  }

  // --- Zdjęcia ---------------------------------------------------------------

  const items = [];
  let topZ = 1;
  let dragging = null;

  function shuffle(list) {
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [list[i], list[j]] = [list[j], list[i]];
    }
    return list;
  }

  function avoidRect() {
    const card = document.querySelector(".auth .card");
    return card ? card.getBoundingClientRect() : null;
  }

  function placePhotos() {
    const mobile = width < 600;
    const chosen = shuffle(photos.slice()).slice(0, mobile ? 7 : 14);
    const base = Math.max(110, Math.min(240, Math.min(width, height) * (mobile ? 0.3 : 0.22)));
    const card = avoidRect();
    const placed = [];

    chosen.forEach((photo, index) => {
      const ratio = photo.w / photo.h;
      const w = ratio >= 1 ? base : base * Math.max(ratio, 0.65);
      const h = w / ratio;

      // Spośród kilku losowych miejsc wybieramy najdalsze od innych zdjęć i od okna logowania.
      let best = null;
      for (let i = 0; i < 14; i++) {
        const x = Math.random() * width;
        const y = Math.random() * height;
        let score = Math.min(...placed.map((p) => Math.hypot(p.x - x, p.y - y)), 9999);
        if (card && x > card.left - w * 0.4 && x < card.right + w * 0.4 && y > card.top - h * 0.4 && y < card.bottom + h * 0.4) {
          score *= 0.25;
        }
        if (!best || score > best.score) best = { x, y, score };
      }
      placed.push(best);

      const el = document.createElement("figure");
      el.className = "login-photo";
      el.style.width = `${w}px`;
      const img = document.createElement("img");
      img.src = photo.src;
      img.alt = "";
      img.draggable = false;
      img.decoding = "async";
      img.width = Math.round(w);
      img.height = Math.round(h);
      img.addEventListener("load", () => {
        setTimeout(() => el.classList.add("is-visible"), reduceMotion ? 0 : index * 90);
      });
      el.appendChild(img);
      layer.appendChild(el);

      const speed = 6 + Math.random() * 10;
      const heading = Math.random() * Math.PI * 2;
      const item = {
        el,
        w,
        h: h + 30,
        x: best.x,
        y: best.y,
        vx: Math.cos(heading) * speed,
        vy: Math.sin(heading) * speed,
        driftX: Math.cos(heading) * speed,
        driftY: Math.sin(heading) * speed,
        baseAngle: (Math.random() - 0.5) * 16,
        angle: 0,
        spin: (Math.random() - 0.5) * 2,
      };
      item.angle = item.baseAngle;
      el.style.zIndex = String(++topZ);
      bindDrag(item);
      items.push(item);
      render(item);
    });
  }

  function render(item) {
    item.el.style.transform = `translate(${item.x - item.w / 2}px, ${item.y - item.h / 2}px) rotate(${item.angle}deg)`;
  }

  function bindDrag(item) {
    item.el.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      item.el.setPointerCapture(event.pointerId);
      item.el.classList.add("is-dragging");
      item.el.style.zIndex = String(++topZ);
      dragging = {
        item,
        id: event.pointerId,
        offX: event.clientX - item.x,
        offY: event.clientY - item.y,
        lastX: event.clientX,
        lastY: event.clientY,
        lastT: performance.now(),
        vx: 0,
        vy: 0,
      };
    });

    item.el.addEventListener("pointermove", (event) => {
      if (!dragging || dragging.item !== item || dragging.id !== event.pointerId) return;
      const now = performance.now();
      const dt = Math.max((now - dragging.lastT) / 1000, 0.001);
      // Prędkość z ostatnich ruchów (średnia krocząca), żeby rzut był płynny.
      dragging.vx = dragging.vx * 0.6 + ((event.clientX - dragging.lastX) / dt) * 0.4;
      dragging.vy = dragging.vy * 0.6 + ((event.clientY - dragging.lastY) / dt) * 0.4;
      dragging.lastX = event.clientX;
      dragging.lastY = event.clientY;
      dragging.lastT = now;
      item.x = event.clientX - dragging.offX;
      item.y = event.clientY - dragging.offY;
    });

    const release = (event) => {
      if (!dragging || dragging.item !== item || dragging.id !== event.pointerId) return;
      const idle = performance.now() - dragging.lastT > 80;
      const limit = 1400;
      item.vx = idle ? 0 : Math.max(-limit, Math.min(limit, dragging.vx));
      item.vy = idle ? 0 : Math.max(-limit, Math.min(limit, dragging.vy));
      item.el.classList.remove("is-dragging");
      dragging = null;
    };
    item.el.addEventListener("pointerup", release);
    item.el.addEventListener("pointercancel", release);
  }

  function updatePhotos(dt) {
    const friction = Math.exp(-dt * 1.6);
    for (const item of items) {
      const held = dragging && dragging.item === item;
      if (!held) {
        if (reduceMotion) {
          item.vx *= friction;
          item.vy *= friction;
        } else {
          // Po rzucie zdjęcie zwalnia do swojego spokojnego dryfu.
          item.vx = item.driftX + (item.vx - item.driftX) * friction;
          item.vy = item.driftY + (item.vy - item.driftY) * friction;
        }
        item.x += item.vx * dt;
        item.y += item.vy * dt;

        // Zdjęcie może wyjść za krawędź najwyżej do połowy, potem odbija.
        const minX = -item.w * 0.25;
        const maxX = width + item.w * 0.25;
        const minY = -item.h * 0.25;
        const maxY = height + item.h * 0.25;
        if (item.x < minX || item.x > maxX) {
          item.x = Math.max(minX, Math.min(maxX, item.x));
          item.vx = -item.vx * 0.6;
          item.driftX = -item.driftX;
        }
        if (item.y < minY || item.y > maxY) {
          item.y = Math.max(minY, Math.min(maxY, item.y));
          item.vy = -item.vy * 0.6;
          item.driftY = -item.driftY;
        }
      }

      // Lekkie przechylenie w stronę ruchu, jak zdjęcie przesuwane po stole.
      const v = held ? dragging.vx : item.vx;
      const tilt = reduceMotion ? 0 : Math.max(-10, Math.min(10, v * 0.012));
      if (!reduceMotion && !held) item.baseAngle += item.spin * dt;
      item.angle += (item.baseAngle + tilt - item.angle) * (1 - Math.exp(-dt * 6));
      render(item);
    }
  }

  // --- Pętla -----------------------------------------------------------------

  function onPointer(event) {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    pointer.active = true;
    gridDirty = true;
  }

  window.addEventListener("pointermove", onPointer, { passive: true });
  window.addEventListener("pointerdown", onPointer, { passive: true });
  document.documentElement.addEventListener("pointerleave", () => {
    pointer.active = false;
    gridDirty = true;
  });
  window.addEventListener("pointerup", (event) => {
    if (event.pointerType !== "mouse") {
      pointer.active = false;
      gridDirty = true;
    }
  });

  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(buildGrid, 120);
  });

  let last = performance.now();
  function frame(now) {
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    if (gridDirty) {
      gridDirty = reduceMotion ? false : updateGrid(dt);
      if (reduceMotion) updateGrid(1);
      drawGrid();
    }
    updatePhotos(dt);
    requestAnimationFrame(frame);
  }

  buildGrid();
  placePhotos();
  root.classList.add("is-ready");
  requestAnimationFrame(frame);
})();

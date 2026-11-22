// Маркер выбранного пятна на карте потолка: щелчок и перетаскивание.
//
// Нажатие рядом с маркером Plotly не получает. Если указатель сдвинулся меньше
// чем на DRAG_THRESHOLD пикселей, это щелчок: точка профиля ставится в центр
// маркера. Иначе это перетаскивание: маркер сдвигается сразу, координаты
// не чаще раза в 60 мс уходят в Store joystick-live, и сервер перерисовывает
// карту потолка. После отпускания приходит final: true — ползунки X и Y
// получают новые значения, и поле пересчитывается один раз.
// Щелчки вдали от маркера обрабатывает сам Plotly (clickData → профиль).
(function () {
  const HIT_RADIUS = 24;
  const DRAG_THRESHOLD = 4;
  let press = null;
  let lastSent = 0;

  function graph() {
    const box = document.getElementById("ceiling-map");
    return box ? box.querySelector(".js-plotly-plot") : null;
  }

  function point(evt) {
    return evt.touches && evt.touches.length ? evt.touches[0]
      : evt.changedTouches && evt.changedTouches.length ? evt.changedTouches[0] : evt;
  }

  function pointer(gd, evt) {
    const fl = gd._fullLayout;
    const rect = gd.getBoundingClientRect();
    const p = point(evt);
    const px = p.clientX - rect.left - fl.xaxis._offset;
    const py = p.clientY - rect.top - fl.yaxis._offset;
    return { px, py, x: fl.xaxis.p2l(px), y: fl.yaxis.p2l(py) };
  }

  function setProps(id, props) {
    if (window.dash_clientside && window.dash_clientside.set_props) {
      window.dash_clientside.set_props(id, props);
    }
  }

  const round = (v) => Math.round(v * 100) / 100;

  function sendLive(x, y, final) {
    setProps("joystick-live", { data: { x: round(x), y: round(y), final, t: Date.now() } });
  }

  function start(evt) {
    const gd = graph();
    if (!gd || !gd._fullLayout || !gd.contains(evt.target)) return;
    const idx = gd.data.findIndex((t) => t.meta === "joystick");
    if (idx < 0) return;
    const fl = gd._fullLayout;
    const trace = gd.data[idx];
    const p = pointer(gd, evt);
    const mx = fl.xaxis.l2p(trace.x[0]);
    const my = fl.yaxis.l2p(trace.y[0]);
    if (Math.hypot(p.px - mx, p.py - my) > HIT_RADIUS) return;
    evt.preventDefault();
    evt.stopPropagation();
    press = { gd, idx, bounds: fl.meta || {}, startPx: p.px, startPy: p.py,
              x0: trace.x[0], y0: trace.y[0], x: trace.x[0], y: trace.y[0], dragging: false };
  }

  function move(evt) {
    if (!press) return;
    evt.preventDefault();
    evt.stopPropagation();
    const p = pointer(press.gd, evt);
    if (!press.dragging) {
      if (Math.hypot(p.px - press.startPx, p.py - press.startPy) < DRAG_THRESHOLD) return;
      press.dragging = true;
      document.body.classList.add("dragging-spot");
    }
    const b = press.bounds;
    press.x = Math.min(Math.max(p.x, b.xmin ?? -Infinity), b.xmax ?? Infinity);
    press.y = Math.min(Math.max(p.y, b.ymin ?? -Infinity), b.ymax ?? Infinity);
    Plotly.restyle(press.gd, { x: [[press.x]], y: [[press.y]] }, [press.idx]);
    const now = performance.now();
    if (now - lastSent > 60) {
      lastSent = now;
      sendLive(press.x, press.y, false);
    }
  }

  function end(evt) {
    if (!press) return;
    evt.preventDefault();
    evt.stopPropagation();
    if (press.dragging) {
      sendLive(press.x, press.y, true);
    } else {
      // Щелчок по маркеру: профиль — точно под центром пятна.
      setProps("profile-point", { data: [round(press.x0), round(press.y0)] });
    }
    press = null;
    document.body.classList.remove("dragging-spot");
  }

  document.addEventListener("mousedown", start, true);
  document.addEventListener("mousemove", move, true);
  document.addEventListener("mouseup", end, true);
  document.addEventListener("touchstart", start, { capture: true, passive: false });
  document.addEventListener("touchmove", move, { capture: true, passive: false });
  document.addEventListener("touchend", end, true);
})();

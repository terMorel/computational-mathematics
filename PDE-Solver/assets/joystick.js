// Двумерный «джойстик»: перетаскивание маркера выбранного пятна на карте потолка.
// Во время движения маркер сдвигается сразу, а координаты (не чаще раза в 60 мс)
// уходят в Store joystick-live — сервер перерисовывает карту потолка.
// После отпускания отправляется final: true — ползунки X и Y получают новые
// значения, и поле температуры пересчитывается.
(function () {
  const HIT_RADIUS = 28;
  let drag = null;
  let lastSent = 0;

  function graph() {
    const box = document.getElementById("ceiling-map");
    return box ? box.querySelector(".js-plotly-plot") : null;
  }

  function pointer(gd, evt) {
    const fl = gd._fullLayout;
    const rect = gd.getBoundingClientRect();
    const px = evt.clientX - rect.left - fl.xaxis._offset;
    const py = evt.clientY - rect.top - fl.yaxis._offset;
    return { px, py, x: fl.xaxis.p2l(px), y: fl.yaxis.p2l(py) };
  }

  function send(x, y, final) {
    if (window.dash_clientside && window.dash_clientside.set_props) {
      window.dash_clientside.set_props("joystick-live", {
        data: { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100, final, t: Date.now() },
      });
    }
  }

  function start(evt) {
    const gd = graph();
    if (!gd || !gd._fullLayout || !gd.contains(evt.target)) return;
    const idx = gd.data.findIndex((t) => t.meta === "joystick");
    if (idx < 0) return;
    const fl = gd._fullLayout;
    const trace = gd.data[idx];
    const p = pointer(gd, evt.touches ? evt.touches[0] : evt);
    const mx = fl.xaxis.l2p(trace.x[0]);
    const my = fl.yaxis.l2p(trace.y[0]);
    if (Math.hypot(p.px - mx, p.py - my) > HIT_RADIUS) return;
    evt.preventDefault();
    evt.stopPropagation();
    drag = { gd, idx, bounds: fl.meta || {}, x: trace.x[0], y: trace.y[0] };
    document.body.classList.add("dragging-spot");
  }

  function move(evt) {
    if (!drag) return;
    evt.preventDefault();
    evt.stopPropagation();
    const b = drag.bounds;
    const p = pointer(drag.gd, evt.touches ? evt.touches[0] : evt);
    drag.x = Math.min(Math.max(p.x, b.xmin ?? -Infinity), b.xmax ?? Infinity);
    drag.y = Math.min(Math.max(p.y, b.ymin ?? -Infinity), b.ymax ?? Infinity);
    Plotly.restyle(drag.gd, { x: [[drag.x]], y: [[drag.y]] }, [drag.idx]);
    const now = performance.now();
    if (now - lastSent > 60) {
      lastSent = now;
      send(drag.x, drag.y, false);
    }
  }

  function end(evt) {
    if (!drag) return;
    evt.preventDefault();
    evt.stopPropagation();
    send(drag.x, drag.y, true);
    drag = null;
    document.body.classList.remove("dragging-spot");
  }

  document.addEventListener("mousedown", start, true);
  document.addEventListener("mousemove", move, true);
  document.addEventListener("mouseup", end, true);
  document.addEventListener("touchstart", start, { capture: true, passive: false });
  document.addEventListener("touchmove", move, { capture: true, passive: false });
  document.addEventListener("touchend", end, true);
})();

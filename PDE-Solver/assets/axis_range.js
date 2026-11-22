// Plotly.react не обновляет диапазон оси, у которой задан связанный масштаб
// (scaleanchor). Срезы кладут нужный диапазон в layout.meta; после каждой
// перерисовки сверяем его с фактическим и при расхождении вызываем relayout.
(function () {
  const IDS = ["hslice", "vslice"];
  const close = (a, b) => Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;

  function fix(gd) {
    const meta = gd.layout && gd.layout.meta;
    if (!meta || !meta.xrange || !gd._fullLayout) return;
    const x = gd._fullLayout.xaxis.range;
    const y = gd._fullLayout.yaxis.range;
    if (!close(x, meta.xrange) || !close(y, meta.yrange)) {
      Plotly.relayout(gd, { "xaxis.range": meta.xrange.slice(), "yaxis.range": meta.yrange.slice() });
    }
  }

  function attach() {
    IDS.forEach((id) => {
      const box = document.getElementById(id);
      const gd = box && box.querySelector(".js-plotly-plot");
      if (gd && !gd.__axisRangeFix && gd.on) {
        gd.__axisRangeFix = true;
        gd.on("plotly_afterplot", () => fix(gd));
        fix(gd);
      }
    });
  }

  setInterval(attach, 500);
})();

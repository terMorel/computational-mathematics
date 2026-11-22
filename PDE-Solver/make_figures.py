"""Рисунки для README и слайдов: python make_figures.py

Те же функции, что и в стенде (figures.py). Сценарий «до/после» повторяет
действия из README: пятно 1 перенесено в (2,2; 2,0) м, A = 85 °C, горизонтальный
срез опущен с 2,3 до 1,6 м, щелчок по центру пятна ставит профиль в (2,2; 2,0) м.
Вертикальный срез не двигается (y = 1,65 м). Пары «до/после» — на одной шкале.
Скриншот работающего стенда делает screenshot.py.
"""

import copy
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from figures import (DEFAULT_PARAMS, DEFAULT_VIEW, ceiling_from_params, ceiling_grid,
                     ceiling_map_figure, fmt, hslice_figure, profile_figure, room_figure,
                     scale_for, slices_figure, value_at, vslice_figure)
from heat_room import LX, LY, LZ, WALLS, Grid, solve
from theme import INK, INK_2, SURFACE, base_layout, colorbar, heat_scale

HERE = Path(__file__).parent
OUT = HERE / "figures"
GRID = Grid.with_step(0.1)

DEMO_PARAMS = copy.deepcopy(DEFAULT_PARAMS)
DEMO_PARAMS["spots"][0][:2] = [2.2, 2.0]
DEMO_PARAMS["amp"] = 85.0
DEMO_VIEW = {**DEFAULT_VIEW, "z": 1.6, "profile": [2.2, 2.0]}


def save(fig, name, width, height, trim=False):
    fig.write_image(OUT / name, width=width, height=height, scale=2)
    if trim:   # у 3D-сцен Plotly оставляет широкие поля — обрезаем по фону
        from PIL import Image, ImageChops
        im = Image.open(OUT / name).convert("RGB")
        box = ImageChops.difference(im, Image.new("RGB", im.size, SURFACE)).getbbox()
        if box:
            pad = 30
            im.crop((max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width),
                     min(box[3] + pad, im.height))).save(OUT / name)
    print("  figures/" + name)


def scheme_figure(params, scale):
    """Схема: грани в цвете своей температуры, подписи и пример ребра и вершины."""
    x, y, Tc = ceiling_grid(params, 81, 61)
    X, Y = np.meshgrid(x, y, indexing="ij")
    common = dict(colorscale=heat_scale(scale), cmin=scale[0], cmax=scale[1], showscale=False,
                  hoverinfo="skip", lighting=dict(ambient=0.95, diffuse=0.08, specular=0.0, fresnel=0.0))
    a, b = np.meshgrid([0, 1], [0, 1], indexing="ij")

    def flat(t):
        return np.full(a.shape, t)

    fig = go.Figure()
    fig.add_trace(go.Surface(x=X, y=Y, z=np.full(X.shape, LZ), surfacecolor=Tc.T,
                             **{**common, "showscale": True, "colorbar": colorbar(len=0.6, x=0.95)}))
    fig.add_trace(go.Surface(x=a * LX, y=b * LY, z=flat(0.0), surfacecolor=flat(WALLS.floor), **common))
    fig.add_trace(go.Surface(x=flat(0.0), y=a * LY, z=b * LZ, surfacecolor=flat(WALLS.x0), **common))
    fig.add_trace(go.Surface(x=a * LX, y=flat(LY), z=b * LZ, surfacecolor=flat(WALLS.y1), **common))
    # Передние стены полупрозрачные, чтобы было видно внутренность.
    fig.add_trace(go.Surface(x=flat(LX), y=a * LY, z=b * LZ, surfacecolor=flat(WALLS.x1),
                             opacity=0.35, **common))
    fig.add_trace(go.Surface(x=a * LX, y=flat(0.0), z=b * LZ, surfacecolor=flat(WALLS.y0),
                             opacity=0.35, **common))
    xs, ys, zs = [], [], []
    for p, q in [((0, 0, 0), (LX, 0, 0)), ((LX, 0, 0), (LX, LY, 0)), ((LX, 0, 0), (LX, 0, LZ)),
                 ((0, 0, LZ), (LX, 0, LZ)), ((LX, 0, LZ), (LX, LY, LZ)), ((LX, LY, 0), (LX, LY, LZ)),
                 ((0, 0, 0), (0, LY, 0)), ((0, LY, 0), (LX, LY, 0)), ((0, 0, LZ), (0, LY, LZ)),
                 ((0, LY, LZ), (LX, LY, LZ)), ((0, LY, 0), (0, LY, LZ))]:
        xs += [p[0], q[0], None]; ys += [p[1], q[1], None]; zs += [p[2], q[2], None]
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=INK_2, width=3),
                               hoverinfo="skip"))
    # Ребро x = y = 0 и вершина (0, 0, 0) — пример правила на стыках.
    fig.add_trace(go.Scatter3d(x=[0, 0], y=[0, 0], z=[0, LZ], mode="lines",
                               line=dict(color="#2a78d6", width=12), hoverinfo="skip"))
    fig.add_trace(go.Scatter3d(x=[0], y=[0], z=[0], mode="markers",
                               marker=dict(size=7, color="#2a78d6"), hoverinfo="skip"))

    def note(x0, y0, z0, text, color=INK, **kw):
        # Подписи — аннотации сцены (SVG поверх WebGL), они не портят прозрачность.
        return dict(x=x0, y=y0, z=z0, text=text, showarrow=False, font=dict(size=19, color=color),
                    bgcolor="rgba(252,252,251,0.88)", borderpad=3, **kw)

    edge = (WALLS.x0 + WALLS.y0) / 2
    vertex = (WALLS.x0 + WALLS.y0 + WALLS.floor) / 3
    annotations = [
        note(0, LY / 2, LZ * 0.62, f"x = 0: {fmt(WALLS.x0, 0)} °C"),
        note(LX * 0.62, LY, LZ * 0.42, f"y = 3 м: {fmt(WALLS.y1, 0)} °C"),
        note(LX, LY / 2, LZ * 0.45, f"x = 4 м: {fmt(WALLS.x1, 0)} °C"),
        note(LX * 0.6, 0, LZ * 0.25, f"y = 0: {fmt(WALLS.y0, 0)} °C"),
        note(LX * 0.55, LY * 0.6, 0.0, f"пол: {fmt(WALLS.floor, 0)} °C"),
        note(LX / 2, LY / 2, LZ + 0.35, "потолок: формула, на краю 20 °C"),
        note(0, 0, LZ * 0.4, f"ребро x = y = 0:<br>({fmt(WALLS.x0, 0)} + {fmt(WALLS.y0, 0)}) / 2 = "
                             f"{fmt(edge, 0)} °C", color="#2a78d6", xanchor="left", xshift=16, align="left"),
        note(0, 0, 0, f"вершина (0, 0, 0):<br>({fmt(WALLS.x0, 0)} + {fmt(WALLS.y0, 0)} + {fmt(WALLS.floor, 0)}) / 3 = "
                      f"{fmt(vertex, 0)} °C", color="#2a78d6", xanchor="left", yanchor="top", xshift=16,
             yshift=-8, align="left"),
    ]
    fig.update_layout(**base_layout(
        showlegend=False, margin=dict(l=0, r=0, t=0, b=0),
        scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
                   aspectmode="data", annotations=annotations,
                   camera=dict(eye=dict(x=1.25, y=-1.55, z=0.85), center=dict(x=0.05, y=0, z=-0.1)))))
    return fig


def main():
    OUT.mkdir(exist_ok=True)
    print("Расчёт полей…")
    base = solve(GRID, ceiling_from_params(DEFAULT_PARAMS), tol=1e-8)
    demo = solve(GRID, ceiling_from_params(DEMO_PARAMS), tol=1e-8, start=base.T)
    scale = scale_for(DEFAULT_PARAMS)
    both = (scale[0], max(scale[1], scale_for(DEMO_PARAMS)[1]))   # общая шкала «до/после»
    print(f"  шкала: {scale}, для пары «до/после»: {both}")
    for name, sol, view in [("до", base, DEFAULT_VIEW), ("после", demo, DEMO_VIEW)]:
        x, y = view["profile"]
        print(f"  {name}: T({x}; {y}; z = {view['z']}) = {value_at(sol.T, GRID, x, y, view['z']):.1f} °C, "
              f"T на потолке = {value_at(sol.T, GRID, x, y, LZ):.1f} °C")
    print("Рисунки:")
    save(scheme_figure(DEFAULT_PARAMS, scale), "scheme.png", 1200, 820, trim=True)
    save(room_figure(base.T, GRID, DEFAULT_PARAMS, DEFAULT_VIEW, scale, title=" "), "room-3d.png",
         1200, 860, trim=True)
    save(ceiling_map_figure(DEFAULT_PARAMS, 0, DEFAULT_VIEW, scale, title="Потолок, z = 2,6 м"),
         "ceiling-map.png", 900, 640)
    save(hslice_figure(base.T, GRID, DEFAULT_VIEW, scale), "hslice.png", 900, 640)
    save(vslice_figure(base.T, GRID, DEFAULT_VIEW, scale), "vslice.png", 1000, 600)
    save(profile_figure(base.T, GRID, DEFAULT_VIEW, scale), "profile.png", 700, 700)
    save(slices_figure(base.T, GRID, [2.5, 2.2, 1.8, 1.3], scale), "slices.png", 1800, 520)
    save(slices_figure(base.T, GRID, [2.5, 2.2, 1.8, 1.3], scale, cols=2), "slices-grid.png", 1100, 980)
    # Сценарий живого показа: «до» и «после» на одной шкале.
    save(ceiling_map_figure(DEFAULT_PARAMS, 0, DEFAULT_VIEW, both,
                            title="До: A = 60 °C, пятно 1 в (1,32; 1,65) м"), "demo-before-ceiling.png", 900, 640)
    save(ceiling_map_figure(DEMO_PARAMS, 0, DEMO_VIEW, both,
                            title="После: A = 85 °C, пятно 1 в (2,2; 2,0) м"), "demo-after-ceiling.png", 900, 640)
    save(hslice_figure(base.T, GRID, DEFAULT_VIEW, both, title="До: срез z = 2,3 м (глубина 0,3 м)"),
         "demo-before-hslice.png", 900, 640)
    save(hslice_figure(demo.T, GRID, DEMO_VIEW, both, title="После: срез z = 1,6 м (глубина 1,0 м)"),
         "demo-after-hslice.png", 900, 640)


if __name__ == "__main__":
    main()

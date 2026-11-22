"""Рисунки для README и слайдов: python make_figures.py

Строит те же представления, что и приложение (общие функции из figures.py),
для исходных настроек и для «демонстрационного» шага: пятно 1 сдвинуто,
интенсивность увеличена, горизонтальный срез опущен.
Скриншот работающего приложения делает screenshot.py.
"""

import copy
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from figures import (DEFAULT_PARAMS, DEFAULT_VIEW, ceiling_from_params, ceiling_grid,
                     ceiling_map_figure, hslice_figure, profile_figure, room_figure,
                     slices_figure, vslice_figure)
from heat_room import LX, LY, LZ, Grid, solve
from theme import HEAT, INK, INK_2, SURFACE, T_MIN, base_layout, color_max, colorbar

HERE = Path(__file__).parent
OUT = HERE / "figures"
GRID = Grid.with_step(0.1)

DEMO_PARAMS = copy.deepcopy(DEFAULT_PARAMS)
DEMO_PARAMS["spots"][0][:2] = [2.2, 2.0]
DEMO_PARAMS["amp"] = 85.0
DEMO_VIEW = {**DEFAULT_VIEW, "z": 1.6, "pos": 2.0, "profile": [2.2, 2.0]}


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


def scheme_figure(params):
    """Схема комнаты: размеры, граничные условия и цветной потолок."""
    x, y, Tc = ceiling_grid(params, 81, 61)
    X, Y = np.meshgrid(x, y, indexing="ij")
    cmax = color_max(Tc.max())
    fig = go.Figure()
    fig.add_trace(go.Surface(x=X, y=Y, z=np.full(X.shape, LZ), surfacecolor=Tc.T, colorscale=HEAT,
                             cmin=T_MIN, cmax=cmax, colorbar=colorbar(len=0.6, x=0.92),
                             lighting=dict(ambient=1.0, diffuse=0.0, specular=0.0), hoverinfo="skip"))
    a, b = np.meshgrid([0, 1], [0, 1], indexing="ij")
    wall = dict(colorscale=[[0, "#f1ede4"], [1, "#f1ede4"]], showscale=False, hoverinfo="skip",
                lighting=dict(ambient=0.92, diffuse=0.12, specular=0.0, fresnel=0.0))
    fig.add_trace(go.Surface(x=a * LX, y=b * LY, z=np.zeros(a.shape), surfacecolor=np.zeros(a.shape), **wall))
    fig.add_trace(go.Surface(x=np.zeros(a.shape), y=a * LY, z=b * LZ, surfacecolor=np.zeros(a.shape), **wall))
    fig.add_trace(go.Surface(x=a * LX, y=np.full(a.shape, LY), z=b * LZ, surfacecolor=np.zeros(a.shape), **wall))
    xs, ys, zs = [], [], []
    for p, q in [((0, 0, 0), (LX, 0, 0)), ((LX, 0, 0), (LX, LY, 0)), ((LX, 0, 0), (LX, 0, LZ)),
                 ((0, 0, 0), (0, 0, LZ)), ((0, 0, LZ), (LX, 0, LZ)), ((LX, 0, LZ), (LX, LY, LZ)),
                 ((LX, LY, 0), (LX, LY, LZ)), ((0, 0, 0), (0, LY, 0)), ((0, LY, 0), (LX, LY, 0)),
                 ((0, 0, LZ), (0, LY, LZ)), ((0, LY, LZ), (LX, LY, LZ)), ((0, LY, 0), (0, LY, LZ))]:
        xs += [p[0], q[0], None]; ys += [p[1], q[1], None]; zs += [p[2], q[2], None]
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=INK_2, width=4),
                               hoverinfo="skip"))
    labels = [
        (LX / 2, -0.32, 0, "4 м"), (LX + 0.3, LY / 2, 0, "3 м"), (LX + 0.25, -0.25, LZ / 2, "2,6 м"),
        (LX / 2, LY / 2, LZ + 0.45, "потолок: T(x, y) — два пятна и волны"),
        (LX * 0.45, LY * 0.62, 0.02, "пол и стены: T = 20 °C"),
    ]
    fig.add_trace(go.Scatter3d(x=[l[0] for l in labels], y=[l[1] for l in labels], z=[l[2] for l in labels],
                               mode="text", text=[l[3] for l in labels],
                               textfont=dict(size=20, color=INK), hoverinfo="skip"))
    fig.update_layout(**base_layout(
        showlegend=False, margin=dict(l=0, r=0, t=0, b=0),
        scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
                   aspectmode="data", camera=dict(eye=dict(x=1.35, y=-1.45, z=0.95),
                                                  center=dict(x=0, y=0, z=-0.1)))))
    return fig


def main():
    OUT.mkdir(exist_ok=True)
    print("Расчёт исходного поля…")
    base = solve(GRID, ceiling_from_params(DEFAULT_PARAMS), tol=1e-8)
    demo = solve(GRID, ceiling_from_params(DEMO_PARAMS), tol=1e-8, start=base.T)
    cmax = color_max(ceiling_grid(DEFAULT_PARAMS)[2].max())
    cmax_demo = color_max(ceiling_grid(DEMO_PARAMS)[2].max())
    print("Рисунки:")
    save(scheme_figure(DEFAULT_PARAMS), "scheme.png", 1100, 760, trim=True)
    save(room_figure(base.T, GRID, DEFAULT_PARAMS, DEFAULT_VIEW, cmax, title=" "), "room-3d.png", 1200, 860, trim=True)
    save(ceiling_map_figure(DEFAULT_PARAMS, 0, DEFAULT_VIEW, cmax, title="Карта потолка, z = 2,6 м"),
         "ceiling-map.png", 900, 640)
    save(hslice_figure(base.T, GRID, DEFAULT_VIEW, cmax), "hslice.png", 900, 640)
    save(vslice_figure(base.T, GRID, DEFAULT_VIEW, cmax), "vslice.png", 1000, 600)
    save(profile_figure(base.T, GRID, DEFAULT_VIEW, cmax), "profile.png", 640, 640)
    save(slices_figure(base.T, GRID, [2.5, 2.2, 1.8, 1.3], cmax), "slices.png", 1800, 520)
    save(slices_figure(base.T, GRID, [2.5, 2.2, 1.8, 1.3], cmax, cols=2), "slices-grid.png", 1100, 980)
    # Демонстрационный шаг: те же виды после изменения настроек.
    save(room_figure(demo.T, GRID, DEMO_PARAMS, DEMO_VIEW, cmax_demo, title=" "), "demo-room-3d.png", 1200, 860, trim=True)
    save(ceiling_map_figure(DEMO_PARAMS, 0, DEMO_VIEW, cmax_demo, title="Пятно 1 сдвинуто, A = 85 °C"),
         "demo-ceiling-map.png", 900, 640)
    save(hslice_figure(demo.T, GRID, DEMO_VIEW, cmax_demo), "demo-hslice.png", 900, 640)
    save(profile_figure(demo.T, GRID, DEMO_VIEW, cmax_demo), "demo-profile.png", 640, 640)


if __name__ == "__main__":
    main()

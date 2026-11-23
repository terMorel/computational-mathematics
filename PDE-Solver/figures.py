"""Рисунки Plotly, общие для стенда, отчёта и слайдов.

Все виды одной комнаты рисуются на одной шкале scale = (cmin, cmax): от самой
холодной грани до максимума потолка, округлённого вверх до 5 °C.
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from heat_room import LX, LY, LZ, WALLS, Ceiling, Spot, ceiling_temperature
from theme import (ACCENT, AXIS, GRID, INK, INK_2, MUTED, SERIES, axis, base_layout,
                   colorbar, color_range, heat_scale)

DEFAULT_PARAMS = {
    "amp": 60.0,
    "m": 2,
    "n": 2,
    # Центры и ширины пятен в метрах: (x, y, σx·Lx, σy·Ly).
    "spots": [[0.33 * LX, 0.55 * LY, 0.16 * LX, 0.22 * LY],
              [0.72 * LX, 0.35 * LY, 0.13 * LX, 0.17 * LY]],
}

DEFAULT_VIEW = {"z": 2.3, "axis": "y", "pos": 1.65, "profile": [1.32, 1.65],
                "iso_on": False, "iso_t": 25.0}

DEFAULT_CAMERA = dict(eye=dict(x=1.08, y=-1.5, z=0.78), center=dict(x=0.0, y=0.0, z=-0.27),
                      up=dict(x=0, y=0, z=1))

# Порядок следов 3D-сцены: по этим номерам стенд обновляет срезы частично.
FLOOR, WALL_X0, WALL_YL, CEILING, HSLICE, VSLICE, ISO, PROFILE, EDGES = range(9)

HOVER_XY = "x = %{x:.2f} м<br>y = %{y:.2f} м<br>T = %{z:.1f} °C<extra></extra>"


def ceiling_from_params(params):
    spots = tuple(Spot(x / LX, y / LY, sx / LX, sy / LY) for x, y, sx, sy in params["spots"])
    return Ceiling(amplitude=float(params["amp"]), m=int(params["m"]), n=int(params["n"]),
                   spots=spots)


def ceiling_grid(params, nx=161, ny=121):
    x = np.linspace(0, LX, nx)
    y = np.linspace(0, LY, ny)
    return x, y, ceiling_temperature(x[None, :], y[:, None], ceiling_from_params(params))


def scale_for(params):
    return color_range(ceiling_grid(params)[2].max(), WALLS)


def fmt(value, digits=2):
    return f"{value:.{digits}f}".replace(".", ",")


# --- Срезы готового поля ---------------------------------------------------

def _between(coord, step, n):
    f = min(max(coord / step, 0.0), float(n))
    k = min(int(f), n - 1)
    return k, f - k


def layer_z(T, grid, z):
    k, t = _between(z, grid.steps[2], grid.nz)
    return (1 - t) * T[:, :, k] + t * T[:, :, k + 1]


def layer_y(T, grid, y):
    j, t = _between(y, grid.steps[1], grid.ny)
    return (1 - t) * T[:, j, :] + t * T[:, j + 1, :]


def layer_x(T, grid, x):
    i, t = _between(x, grid.steps[0], grid.nx)
    return (1 - t) * T[i, :, :] + t * T[i + 1, :, :]


def column(T, grid, x, y):
    """Температура вдоль вертикали над точкой (x, y) пола (билинейно по x, y)."""
    i, tx = _between(x, grid.steps[0], grid.nx)
    j, ty = _between(y, grid.steps[1], grid.ny)
    c = T[i:i + 2, j:j + 2, :]
    c = (1 - tx) * c[0] + tx * c[1]
    return (1 - ty) * c[0] + ty * c[1]


def value_at(T, grid, x, y, z):
    values = column(T, grid, x, y)
    k, t = _between(z, grid.steps[2], grid.nz)
    return float((1 - t) * values[k] + t * values[k + 1])


# --- Карта потолка ---------------------------------------------------------

def _spot_marker(x, y, label, selected):
    return go.Scatter(
        x=[x], y=[y], mode="markers+text", text=[label],
        textfont=dict(size=15 if selected else 13, color=INK, family="Arial Black, Arial"),
        marker=dict(size=34 if selected else 22, color="white",
                    line=dict(color=ACCENT if selected else INK, width=4 if selected else 2)),
        hovertemplate=(f"Пятно {label}{' (выбрано)' if selected else ''}<br>"
                       "x = %{x:.2f} м<br>y = %{y:.2f} м<extra></extra>"),
        meta="joystick" if selected else f"spot{label}", showlegend=False, cliponaxis=False)


def _slice_line_xy(view):
    if view["axis"] == "y":
        return go.Scatter(x=[0, LX], y=[view["pos"]] * 2, mode="lines",
                          line=dict(color=INK, width=2), hoverinfo="skip", showlegend=False)
    return go.Scatter(x=[view["pos"]] * 2, y=[0, LY], mode="lines",
                      line=dict(color=INK, width=2), hoverinfo="skip", showlegend=False)


def _profile_mark(x, y):
    return go.Scatter(x=[x], y=[y], mode="markers",
                      marker=dict(symbol="x-thin", size=18, color=ACCENT, line=dict(width=4, color=ACCENT)),
                      hovertemplate="Профиль: x = %{x:.2f} м, y = %{y:.2f} м<extra></extra>",
                      showlegend=False)


def _plan_axes(fig, title_x="x, м", title_y="y, м"):
    fig.update_xaxes(**axis(title_x, range=[0, LX], constrain="domain", showgrid=False,
                            dtick=1, mirror=True))
    fig.update_yaxes(**axis(title_y, range=[0, LY], scaleanchor="x", scaleratio=1,
                            constrain="domain", showgrid=False, dtick=1, mirror=True))


def _title(text, size=16):
    return dict(text=text, font=dict(size=size), x=0.01, xanchor="left")


def ceiling_map_figure(params, selected, view, scale=None, title=None):
    x, y, Tc = ceiling_grid(params)
    cmin, cmax = scale or color_range(Tc.max(), WALLS)
    fig = go.Figure(go.Heatmap(x=x, y=y, z=Tc, colorscale=heat_scale((cmin, cmax)), zmin=cmin, zmax=cmax,
                               colorbar=colorbar(len=0.9), hovertemplate=HOVER_XY, zsmooth="best"))
    fig.add_trace(_slice_line_xy(view))
    fig.add_trace(_profile_mark(*view["profile"]))
    for j in [1 - selected, selected]:   # выбранное пятно рисуем поверх
        sx, sy = params["spots"][j][:2]
        fig.add_trace(_spot_marker(sx, sy, str(j + 1), j == selected))
    fig.update_layout(**base_layout(
        title=_title(title or "Потолок · тащите пятно, щелчок — профиль"),
        dragmode=False, clickmode="event", margin=dict(l=52, r=8, t=40, b=46),
        meta={"xmin": 0.05 * LX, "xmax": 0.95 * LX, "ymin": 0.05 * LY, "ymax": 0.95 * LY}))
    _plan_axes(fig)
    return fig


# --- 3D-комната --------------------------------------------------------------

FLAT = dict(ambient=1.0, diffuse=0.0, specular=0.0, roughness=1.0, fresnel=0.0)


def _plane(x, y, z, color, scale, **extra):
    spec = dict(x=x, y=y, z=z, surfacecolor=color, colorscale=heat_scale(scale), cmin=scale[0], cmax=scale[1],
                showscale=False, lighting=FLAT,
                hovertemplate=("x = %{x:.2f} м, y = %{y:.2f} м, z = %{z:.2f} м<br>"
                               "T = %{surfacecolor:.1f} °C<extra></extra>"),
                contours=dict(x=dict(highlight=False), y=dict(highlight=False), z=dict(highlight=False)))
    spec.update(extra)
    return go.Surface(**spec)


def _face(axis_name, value, temperature, scale):
    """Грань с постоянной температурой: цвет по той же шкале, что и срезы."""
    a, b = np.meshgrid(np.linspace(0, 1, 2), np.linspace(0, 1, 2), indexing="ij")
    color = np.full(a.shape, temperature)
    light = dict(ambient=0.94, diffuse=0.1, specular=0.0, fresnel=0.0)
    if axis_name == "z":
        return _plane(a * LX, b * LY, np.full(a.shape, value), color, scale, lighting=light)
    if axis_name == "x":
        return _plane(np.full(a.shape, value), a * LY, b * LZ, color, scale, lighting=light)
    return _plane(a * LX, np.full(a.shape, value), b * LZ, color, scale, lighting=light)


def hslice_trace(T, grid, z, scale):
    x, y, _ = grid.axes
    X, Y = np.meshgrid(x, y, indexing="ij")
    return _plane(X, Y, np.full(X.shape, z), layer_z(T, grid, z), scale)


def vslice_trace(T, grid, view, scale):
    x, y, z = grid.axes
    if view["axis"] == "y":
        A, Z = np.meshgrid(x, z, indexing="ij")
        return _plane(A, np.full(A.shape, view["pos"]), Z, layer_y(T, grid, view["pos"]), scale)
    A, Z = np.meshgrid(y, z, indexing="ij")
    return _plane(np.full(A.shape, view["pos"]), A, Z, layer_x(T, grid, view["pos"]), scale)


def profile_trace(x, y):
    return go.Scatter3d(x=[x, x], y=[y, y], z=[0, LZ], mode="lines+markers",
                        line=dict(color=ACCENT, width=9), marker=dict(size=[0, 7], color=ACCENT),
                        hovertemplate="Профиль: x = %{x:.2f} м, y = %{y:.2f} м<extra></extra>",
                        showlegend=False)


def _edges():
    xs, ys, zs = [], [], []
    for a in (0, LX):
        for b in (0, LY):
            xs += [a, a, None]; ys += [b, b, None]; zs += [0, LZ, None]
    for a in (0, LX):
        for c in (0, LZ):
            xs += [a, a, None]; ys += [0, LY, None]; zs += [c, c, None]
    for b in (0, LY):
        for c in (0, LZ):
            xs += [0, LX, None]; ys += [b, b, None]; zs += [c, c, None]
    return go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=MUTED, width=3),
                        hoverinfo="skip", showlegend=False)


def iso_trace(T, grid, view, scale):
    x, y, z = grid.axes
    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    return go.Isosurface(
        x=X.ravel(), y=Y.ravel(), z=Z.ravel(), value=T.ravel(),
        isomin=view["iso_t"], isomax=view["iso_t"], surface=dict(count=1),
        caps=dict(x_show=False, y_show=False, z_show=False), opacity=0.55,
        colorscale=heat_scale(scale), cmin=scale[0], cmax=scale[1], showscale=False, visible=bool(view["iso_on"]),
        lighting=dict(ambient=0.6, diffuse=0.6, specular=0.15),
        hovertemplate="Изоповерхность T = %{value:.1f} °C<extra></extra>")


def _axis3d(title, upper):
    return dict(title=dict(text=title, font=dict(size=14, color=INK_2)), range=[0, upper],
                tickfont=dict(size=12, color=INK_2), gridcolor=GRID, zerolinecolor=AXIS,
                showbackground=False, showspikes=False, dtick=1)


def room_figure(T, grid, params, view, scale, revision=0, title=None, walls=WALLS):
    # uirevision должна быть «истинной», иначе Plotly не сохраняет повёрнутую камеру.
    revision = f"camera-{revision}"
    xc, yc, Tc = ceiling_grid(params, 121, 91)
    Xc, Yc = np.meshgrid(xc, yc, indexing="ij")
    traces = [None] * 9
    traces[FLOOR] = _face("z", 0.0, walls.floor, scale)
    traces[WALL_X0] = _face("x", 0.0, walls.x0, scale)
    traces[WALL_YL] = _face("y", LY, walls.y1, scale)
    # Потолок полупрозрачный: сквозь него видны срезы.
    traces[CEILING] = _plane(Xc, Yc, np.full(Xc.shape, LZ), Tc.T, scale, showscale=True, opacity=0.62,
                             colorbar=colorbar(len=0.75, x=0.98, y=0.5))
    traces[HSLICE] = hslice_trace(T, grid, view["z"], scale)
    traces[VSLICE] = vslice_trace(T, grid, view, scale)
    traces[ISO] = iso_trace(T, grid, view, scale)
    traces[PROFILE] = profile_trace(*view["profile"])
    traces[EDGES] = _edges()
    fig = go.Figure(traces)
    fig.update_layout(**base_layout(
        title=_title(title or "Комната: потолок, срезы, профиль"),
        margin=dict(l=0, r=0, t=36, b=0), uirevision=revision,
        scene=dict(xaxis=_axis3d("x, м", LX), yaxis=_axis3d("y, м", LY), zaxis=_axis3d("z, м", LZ),
                   aspectmode="data", camera=DEFAULT_CAMERA, uirevision=revision, dragmode="orbit")))
    return fig


# --- Тепловые карты срезов и профиль ---------------------------------------

def _section_layout(fig, title, x_title, y_title, x_max, y_max):
    # Plotly.react не меняет диапазон оси со связанным масштабом (scaleanchor), а у
    # вертикального среза он зависит от направления: 4 м или 3 м. Нужный диапазон
    # лежит в meta, и assets/axis_range.js выставляет его после перерисовки.
    fig.update_layout(**base_layout(title=_title(title), margin=dict(l=52, r=8, t=40, b=46),
                                    dragmode=False, meta={"xrange": [0, x_max], "yrange": [0, y_max]}))
    fig.update_xaxes(**axis(x_title, range=[0, x_max], constrain="domain", showgrid=False,
                            dtick=1, mirror=True))
    fig.update_yaxes(**axis(y_title, range=[0, y_max], scaleanchor="x", scaleratio=1,
                            constrain="domain", showgrid=False, dtick=1, mirror=True))


def hslice_figure(T, grid, view, scale, show_scale=True, title=None):
    x, y, _ = grid.axes
    fig = go.Figure(go.Heatmap(x=x, y=y, z=layer_z(T, grid, view["z"]).T, colorscale=heat_scale(scale),
                               zmin=scale[0], zmax=scale[1], zsmooth="best", hovertemplate=HOVER_XY,
                               showscale=show_scale, colorbar=colorbar(len=0.9)))
    fig.add_trace(_slice_line_xy(view))
    fig.add_trace(_profile_mark(*view["profile"]))
    _section_layout(fig, title or f"Срез z = {fmt(view['z'], 1)} м (глубина {fmt(LZ - view['z'], 1)} м)",
                    "x, м", "y, м", LX, LY)
    return fig


def vslice_figure(T, grid, view, scale, show_scale=True):
    x, y, z = grid.axes
    if view["axis"] == "y":
        horiz, values, name = x, layer_y(T, grid, view["pos"]), "x, м"
        title = f"Срез y = {fmt(view['pos'])} м"
        hover = "x = %{x:.2f} м<br>z = %{y:.2f} м<br>T = %{z:.1f} °C<extra></extra>"
        width, near, p = LX, abs(view["profile"][1] - view["pos"]) < 0.06, view["profile"][0]
    else:
        horiz, values, name = y, layer_x(T, grid, view["pos"]), "y, м"
        title = f"Срез x = {fmt(view['pos'])} м"
        hover = "y = %{x:.2f} м<br>z = %{y:.2f} м<br>T = %{z:.1f} °C<extra></extra>"
        width, near, p = LY, abs(view["profile"][0] - view["pos"]) < 0.06, view["profile"][1]
    fig = go.Figure(go.Heatmap(x=horiz, y=z, z=values.T, colorscale=heat_scale(scale), zmin=scale[0], zmax=scale[1],
                               zsmooth="best", hovertemplate=hover, showscale=show_scale,
                               colorbar=colorbar(len=0.9)))
    fig.add_trace(go.Scatter(x=[0, width], y=[view["z"]] * 2, mode="lines",
                             line=dict(color=INK, width=2), hoverinfo="skip", showlegend=False))
    if near:   # линия профиля лежит в плоскости среза
        fig.add_trace(go.Scatter(x=[p, p], y=[0, LZ], mode="lines", line=dict(color=ACCENT, width=3),
                                 hoverinfo="skip", showlegend=False))
    _section_layout(fig, title, name, "z, м", width, LZ)
    return fig


def profile_figure(T, grid, view, scale, title=None):
    _, _, z = grid.axes
    xp, yp = view["profile"]
    values = column(T, grid, xp, yp)
    zs = view["z"]
    ts = value_at(T, grid, xp, yp, zs)
    fig = go.Figure(go.Scatter(x=values, y=z, mode="lines", line=dict(color=ACCENT, width=3),
                               hovertemplate="z = %{y:.2f} м<br>T = %{x:.1f} °C<extra></extra>",
                               showlegend=False))
    fig.add_trace(go.Scatter(x=[scale[0], scale[1]], y=[zs, zs], mode="lines",
                             line=dict(color=INK, width=1.5), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[ts], y=[zs], mode="markers+text", text=[f"{fmt(ts, 1)} °C "],
                             textposition="top left", textfont=dict(size=15, color=INK),
                             marker=dict(size=11, color=ACCENT, line=dict(color="white", width=2)),
                             hoverinfo="skip", showlegend=False, cliponaxis=False))
    fig.add_trace(go.Scatter(x=[values[-1]], y=[LZ], mode="markers+text",
                             text=[f"потолок {fmt(values[-1], 1)} °C "], textposition="top left",
                             textfont=dict(size=14, color=INK_2),
                             marker=dict(size=9, color=ACCENT), hoverinfo="skip", showlegend=False,
                             cliponaxis=False))
    fig.update_layout(**base_layout(
        title=_title(title or f"T(z) под точкой ({fmt(xp)}; {fmt(yp)}) м"),
        margin=dict(l=52, r=14, t=40, b=46), dragmode=False))
    fig.update_xaxes(**axis("T, °C", range=[scale[0] - 0.5, scale[1]]))
    fig.update_yaxes(**axis("z, м", range=[0, LZ + 0.22], dtick=0.5))
    return fig


# --- Рисунки исследования -----------------------------------------------------

NAMES = {"jacobi": "Якоби", "seidel": "Зейдель", "sor": "SOR"}


def convergence_figure(solutions, tol):
    fig = go.Figure()
    for color, sol in zip(SERIES, solutions):
        label = NAMES[sol.method] + (f", ω = {fmt(sol.omega, 3)}" if sol.method == "sor" else "")
        fig.add_trace(go.Scatter(
            x=np.arange(len(sol.residuals)), y=sol.residuals, mode="lines", name=label,
            line=dict(color=color, width=2.5),
            hovertemplate=f"{label}<br>итерация %{{x}}<br>невязка %{{y:.2e}}<extra></extra>"))
        left = sol.method == "seidel"   # подпись Зейделя слева от конца линии
        fig.add_annotation(x=np.log10(max(sol.iterations, 1)), y=np.log10(sol.residuals[-1]),
                           text=f"<b>{label.split(',')[0]}</b>: {sol.iterations}", showarrow=False,
                           xanchor="right" if left else "left", yanchor="bottom",
                           xshift=-8 if left else 6, yshift=6, font=dict(size=16, color=INK))
    fig.add_hline(y=tol, line=dict(color=MUTED, width=1.5))
    power = int(round(np.log10(tol)))
    fig.add_annotation(x=0, y=np.log10(tol), text=f"порог 10<sup>{power}</sup>", showarrow=False,
                       xanchor="left", yanchor="top", yshift=-2, font=dict(size=15, color=INK_2))
    grid = solutions[0].grid
    fig.update_layout(**base_layout(
        title=_title(f"Невязка по итерациям · сетка {grid.nx} × {grid.ny} × {grid.nz} · старт 20 °C", 18),
        legend=dict(orientation="h", y=1.0, x=0.99, xanchor="right", yanchor="bottom", font=dict(size=15)),
        margin=dict(l=80, r=30, t=70, b=60)))
    last = max(sol.iterations for sol in solutions)
    fig.update_xaxes(**axis("номер итерации", type="log", dtick=1, range=[0, np.log10(last * 2.6)]))
    fig.update_yaxes(**axis("‖b − Av‖∞ / ‖b‖∞", type="log", exponentformat="power", dtick=2))
    return fig


def depth_figure(depths, curves, summary):
    """curves: [(подпись, доля амплитуды по глубине)]; summary — пересечения 10 %."""
    fig = go.Figure()
    crossings = sorted(summary[label]["tenth"]["depth"] for label, _ in curves)
    for color, (label, values) in zip(SERIES, curves):
        fig.add_trace(go.Scatter(x=depths, y=values, mode="lines", name=label,
                                 line=dict(color=color, width=3),
                                 hovertemplate=f"{label}<br>глубина %{{x:.2f}} м<br>"
                                               "доля амплитуды %{y:.0%}<extra></extra>"))
        d10 = summary[label]["tenth"]["depth"]
        fig.add_trace(go.Scatter(x=[d10], y=[0.1], mode="markers",
                                 marker=dict(size=11, color=color, line=dict(color="white", width=2)),
                                 hoverinfo="skip", showlegend=False))
        # Близкие точки подписываем в разные стороны, чтобы подписи не слипались.
        k = crossings.index(d10)
        left = k + 1 < len(crossings) and crossings[k + 1] - d10 < 0.3
        right = k > 0 and d10 - crossings[k - 1] < 0.3
        fig.add_annotation(x=d10, y=0.1, text=f"{fmt(d10, 2)} м", showarrow=False, yshift=18,
                           xanchor="right" if left else ("left" if right else "center"),
                           xshift=-4 if left else (4 if right else 0), font=dict(size=15, color=INK))
    k = summary["wave_k"]
    lz = max(depths)
    estimate = np.sinh(k * (lz - depths)) / np.sinh(k * lz)
    fig.add_trace(go.Scatter(x=depths, y=estimate, mode="lines",
                             name=f"одна гармоника k = {fmt(k, 2)} м⁻¹ (оценка)",
                             line=dict(color=MUTED, width=2, dash="dash"), hoverinfo="skip"))
    fig.add_hline(y=0.1, line=dict(color=MUTED, width=1.5))
    fig.add_annotation(x=lz, y=0.1, text="10 %", showarrow=False, xanchor="right", yanchor="bottom",
                       font=dict(size=15, color=INK_2))
    fig.update_layout(**base_layout(
        title=_title(f"Доля амплитуды слагаемого на срезе · сетка {summary['grid']} · "
                     "точки — интерполяция между слоями", 17),
        legend=dict(x=0.98, y=0.97, xanchor="right", yanchor="top", font=dict(size=15),
                    bgcolor="rgba(252,252,251,0.9)"),
        margin=dict(l=80, r=30, t=60, b=60)))
    fig.update_xaxes(**axis("глубина d от потолка, м", range=[0, lz], dtick=0.25))
    fig.update_yaxes(**axis("доля амплитуды на потолке", range=[0, 1.02], tickformat=".0%"))
    return fig


def slices_figure(T, grid, heights, scale, cols=None):
    """Горизонтальные срезы на разной глубине на общей шкале °C."""
    cols = cols or len(heights)
    rows = -(-len(heights) // cols)
    titles = [f"z = {fmt(z, 1)} м · глубина {fmt(LZ - z, 1)} м" for z in heights]
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles, horizontal_spacing=0.06,
                        vertical_spacing=0.14 if rows > 1 else 0.0)
    x, y, _ = grid.axes
    for n, z in enumerate(heights):
        row, col = n // cols + 1, n % cols + 1
        ref = "" if n == 0 else str(n + 1)
        fig.add_trace(go.Heatmap(x=x, y=y, z=layer_z(T, grid, z).T, colorscale=heat_scale(scale), zmin=scale[0],
                                 zmax=scale[1], zsmooth="best", hovertemplate=HOVER_XY,
                                 showscale=n == 0, colorbar=colorbar(len=0.9 if rows == 1 else 0.6)),
                      row=row, col=col)
        fig.update_xaxes(**axis("x, м" if row == rows else "", range=[0, LX], constrain="domain",
                                showgrid=False, dtick=1, mirror=True), row=row, col=col)
        fig.update_yaxes(**axis("y, м" if col == 1 else "", range=[0, LY], scaleanchor=f"x{ref}",
                                scaleratio=1, constrain="domain", showgrid=False, dtick=1, mirror=True),
                         row=row, col=col)
    fig.update_annotations(font=dict(size=18, color=INK))
    fig.update_layout(**base_layout(margin=dict(l=60, r=20, t=50, b=50)))
    return fig

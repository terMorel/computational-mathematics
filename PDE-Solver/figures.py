"""Построение рисунков Plotly: общие для приложения, отчёта и слайдов."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from heat_room import LX, LY, LZ, T_WALL, Ceiling, Spot, ceiling_temperature
from theme import (ACCENT, AXIS, GRID, HEAT, INK, INK_2, MUTED, SERIES, T_MIN,
                   axis, base_layout, color_max, colorbar)

DEFAULT_PARAMS = {
    "amp": 60.0,
    "m": 2,
    "n": 2,
    # Центры и ширины пятен в метрах: (x, y, σx, σy).
    "spots": [[0.33 * LX, 0.55 * LY, 0.16 * LX, 0.22 * LY],
              [0.72 * LX, 0.35 * LY, 0.13 * LX, 0.17 * LY]],
}

DEFAULT_VIEW = {"z": 2.3, "axis": "y", "pos": 1.65, "profile": [1.32, 1.65],
                "iso_on": False, "iso_t": 30.0}

DEFAULT_CAMERA = dict(eye=dict(x=1.08, y=-1.5, z=0.78), center=dict(x=0.0, y=0.0, z=-0.27),
                      up=dict(x=0, y=0, z=1))

# Порядок следов 3D-сцены: по этим номерам приложение обновляет срезы частично.
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
    """Температура вдоль вертикали над точкой (x, y) пола."""
    i, tx = _between(x, grid.steps[0], grid.nx)
    j, ty = _between(y, grid.steps[1], grid.ny)
    c = T[i:i + 2, j:j + 2, :]
    c = (1 - tx) * c[0] + tx * c[1]
    return (1 - ty) * c[0] + ty * c[1]


# --- Карта потолка --------------------------------------------------------

def _spot_marker(x, y, label, selected):
    size = 34 if selected else 22
    return go.Scatter(
        x=[x], y=[y], mode="markers+text", text=[label],
        textfont=dict(size=15 if selected else 13, color=INK, family="Arial Black, Arial"),
        marker=dict(size=size, color="white", line=dict(color=ACCENT if selected else INK,
                                                         width=4 if selected else 2)),
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
                            dtick=0.5, mirror=True))
    fig.update_yaxes(**axis(title_y, range=[0, LY], scaleanchor="x", scaleratio=1,
                            constrain="domain", showgrid=False, dtick=0.5, mirror=True))


def ceiling_map_figure(params, selected, view, cmax=None, title=None):
    x, y, Tc = ceiling_grid(params)
    cmax = cmax or color_max(Tc.max())
    fig = go.Figure(go.Heatmap(x=x, y=y, z=Tc, colorscale=HEAT, zmin=T_MIN, zmax=cmax,
                               colorbar=colorbar(len=0.9), hovertemplate=HOVER_XY, zsmooth="best"))
    fig.add_trace(_slice_line_xy(view))
    fig.add_trace(_profile_mark(*view["profile"]))
    order = [1 - selected, selected]
    for j in order:
        sx, sy = params["spots"][j][:2]
        fig.add_trace(_spot_marker(sx, sy, str(j + 1), j == selected))
    fig.update_layout(**base_layout(
        title=dict(text=title or "Потолок · перетащите выбранное пятно, щелчок — профиль",
                   font=dict(size=17), x=0.01, xanchor="left"),
        dragmode=False, clickmode="event", margin=dict(l=56, r=10, t=44, b=48),
        meta={"xmin": 0.05 * LX, "xmax": 0.95 * LX, "ymin": 0.05 * LY, "ymax": 0.95 * LY}))
    _plan_axes(fig)
    return fig


# --- 3D-комната -----------------------------------------------------------

def _plane(x, y, z, color, cmax, **extra):
    spec = dict(x=x, y=y, z=z, surfacecolor=color, colorscale=HEAT, cmin=T_MIN, cmax=cmax,
                showscale=False, hovertemplate=("x = %{x:.2f} м, y = %{y:.2f} м, "
                                                "z = %{z:.2f} м<br>T = %{surfacecolor:.1f} °C<extra></extra>"),
                lighting=dict(ambient=1.0, diffuse=0.0, specular=0.0, roughness=1.0, fresnel=0.0),
                contours=dict(x=dict(highlight=False), y=dict(highlight=False), z=dict(highlight=False)))
    spec.update(extra)
    return go.Surface(**spec)


def _wall(axis_name, value, cmax):
    a, b = np.meshgrid(np.linspace(0, 1, 2), np.linspace(0, 1, 2), indexing="ij")
    color = np.full(a.shape, T_WALL)
    if axis_name == "z":
        return _plane(a * LX, b * LY, np.full(a.shape, value), color, cmax,
                      lighting=dict(ambient=0.97, diffuse=0.06, specular=0.0, fresnel=0.0), hoverinfo="skip")
    if axis_name == "x":
        return _plane(np.full(a.shape, value), a * LY, b * LZ, color, cmax,
                      lighting=dict(ambient=0.9, diffuse=0.12, specular=0.0, fresnel=0.0), hoverinfo="skip")
    return _plane(a * LX, np.full(a.shape, value), b * LZ, color, cmax,
                  lighting=dict(ambient=0.93, diffuse=0.1, specular=0.0, fresnel=0.0), hoverinfo="skip")


def hslice_trace(T, grid, z, cmax):
    x, y, _ = grid.axes
    X, Y = np.meshgrid(x, y, indexing="ij")
    return _plane(X, Y, np.full(X.shape, z), layer_z(T, grid, z), cmax)


def vslice_trace(T, grid, view, cmax):
    x, y, z = grid.axes
    if view["axis"] == "y":
        A, Z = np.meshgrid(x, z, indexing="ij")
        return _plane(A, np.full(A.shape, view["pos"]), Z, layer_y(T, grid, view["pos"]), cmax)
    A, Z = np.meshgrid(y, z, indexing="ij")
    return _plane(np.full(A.shape, view["pos"]), A, Z, layer_x(T, grid, view["pos"]), cmax)


def profile_trace(x, y):
    return go.Scatter3d(x=[x, x], y=[y, y], z=[0, LZ], mode="lines+markers",
                        line=dict(color=ACCENT, width=9), marker=dict(size=[0, 7], color=ACCENT),
                        hovertemplate="Профиль под точкой<br>x = %{x:.2f} м, y = %{y:.2f} м<extra></extra>",
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


def iso_trace(T, grid, view, cmax):
    x, y, z = grid.axes
    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    return go.Isosurface(
        x=X.ravel(), y=Y.ravel(), z=Z.ravel(), value=T.ravel(),
        isomin=view["iso_t"], isomax=view["iso_t"], surface=dict(count=1),
        caps=dict(x_show=False, y_show=False, z_show=False), opacity=0.55,
        colorscale=HEAT, cmin=T_MIN, cmax=cmax, showscale=False, visible=bool(view["iso_on"]),
        lighting=dict(ambient=0.6, diffuse=0.6, specular=0.15),
        hovertemplate="Изоповерхность T = %{value:.1f} °C<extra></extra>")


def _axis3d(title, upper):
    return dict(title=dict(text=title, font=dict(size=15, color=INK_2)), range=[0, upper],
                tickfont=dict(size=13, color=INK_2), gridcolor=GRID, zerolinecolor=AXIS,
                showbackground=False, showspikes=False, dtick=1)


def room_figure(T, grid, params, view, cmax, revision=0, title=None):
    # uirevision должна быть «истинной», иначе Plotly не сохраняет повёрнутую камеру.
    revision = f"camera-{revision}"
    xc, yc, Tc = ceiling_grid(params, 121, 91)
    Xc, Yc = np.meshgrid(xc, yc, indexing="ij")
    traces = [None] * 9
    traces[FLOOR] = _wall("z", 0.0, cmax)
    traces[WALL_X0] = _wall("x", 0.0, cmax)
    traces[WALL_YL] = _wall("y", LY, cmax)
    # Потолок полупрозрачный: сквозь него видны срезы внутри комнаты.
    traces[CEILING] = _plane(Xc, Yc, np.full(Xc.shape, LZ), Tc.T, cmax, showscale=True, opacity=0.62,
                             colorbar=colorbar(len=0.75, x=0.98, y=0.5))
    traces[HSLICE] = hslice_trace(T, grid, view["z"], cmax)
    traces[VSLICE] = vslice_trace(T, grid, view, cmax)
    traces[ISO] = iso_trace(T, grid, view, cmax)
    traces[PROFILE] = profile_trace(*view["profile"])
    traces[EDGES] = _edges()
    fig = go.Figure(traces)
    fig.update_layout(**base_layout(
        title=dict(text=title or "Комната 4 × 3 × 2,6 м: потолок, срезы и профиль",
                   font=dict(size=17), x=0.01, xanchor="left"),
        margin=dict(l=0, r=0, t=40, b=0), uirevision=revision,
        scene=dict(xaxis=_axis3d("x, м", LX), yaxis=_axis3d("y, м", LY), zaxis=_axis3d("z, м", LZ),
                   aspectmode="data", camera=DEFAULT_CAMERA, uirevision=revision,
                   dragmode="orbit")))
    return fig


# --- Тепловые карты срезов и профиль -------------------------------------

def _section_layout(fig, title, x_title, y_title, x_max, y_max):
    fig.update_layout(**base_layout(title=dict(text=title, font=dict(size=17), x=0.01, xanchor="left"),
                                    margin=dict(l=56, r=10, t=44, b=48), dragmode=False))
    fig.update_xaxes(**axis(x_title, range=[0, x_max], constrain="domain", showgrid=False,
                            dtick=0.5, mirror=True))
    fig.update_yaxes(**axis(y_title, range=[0, y_max], scaleanchor="x", scaleratio=1,
                            constrain="domain", showgrid=False, dtick=0.5, mirror=True))


def hslice_figure(T, grid, view, cmax, show_scale=True):
    x, y, _ = grid.axes
    fig = go.Figure(go.Heatmap(x=x, y=y, z=layer_z(T, grid, view["z"]).T, colorscale=HEAT,
                               zmin=T_MIN, zmax=cmax, zsmooth="best", hovertemplate=HOVER_XY,
                               showscale=show_scale, colorbar=colorbar(len=0.9)))
    fig.add_trace(_slice_line_xy(view))
    fig.add_trace(_profile_mark(*view["profile"]))
    depth = LZ - view["z"]
    _section_layout(fig, f"Горизонтальный срез z = {fmt(view['z'], 1)} м "
                         f"({fmt(depth, 1)} м под потолком)", "x, м", "y, м", LX, LY)
    return fig


def vslice_figure(T, grid, view, cmax, show_scale=True):
    x, y, z = grid.axes
    if view["axis"] == "y":
        horiz, values, name = x, layer_y(T, grid, view["pos"]), "x, м"
        title = f"Вертикальный срез y = {fmt(view['pos'])} м"
        hover = "x = %{x:.2f} м<br>z = %{y:.2f} м<br>T = %{z:.1f} °C<extra></extra>"
        width, near = LX, abs(view["profile"][1] - view["pos"]) < 0.06
        p = view["profile"][0]
    else:
        horiz, values, name = y, layer_x(T, grid, view["pos"]), "y, м"
        title = f"Вертикальный срез x = {fmt(view['pos'])} м"
        hover = "y = %{x:.2f} м<br>z = %{y:.2f} м<br>T = %{z:.1f} °C<extra></extra>"
        width, near = LY, abs(view["profile"][0] - view["pos"]) < 0.06
        p = view["profile"][1]
    fig = go.Figure(go.Heatmap(x=horiz, y=z, z=values.T, colorscale=HEAT, zmin=T_MIN, zmax=cmax,
                               zsmooth="best", hovertemplate=hover, showscale=show_scale,
                               colorbar=colorbar(len=0.9)))
    fig.add_trace(go.Scatter(x=[0, width], y=[view["z"]] * 2, mode="lines",
                             line=dict(color=INK, width=2), hoverinfo="skip", showlegend=False))
    if near:
        fig.add_trace(go.Scatter(x=[p, p], y=[0, LZ], mode="lines", line=dict(color=ACCENT, width=3),
                                 hoverinfo="skip", showlegend=False))
    _section_layout(fig, title, name, "z, м", width, LZ)
    return fig


def profile_figure(T, grid, view, cmax):
    _, _, z = grid.axes
    xp, yp = view["profile"]
    values = column(T, grid, xp, yp)
    zs = view["z"]
    k, t = _between(zs, grid.steps[2], grid.nz)
    ts = (1 - t) * values[k] + t * values[k + 1]
    fig = go.Figure(go.Scatter(x=values, y=z, mode="lines", line=dict(color=ACCENT, width=3),
                               hovertemplate="z = %{y:.2f} м<br>T = %{x:.1f} °C<extra></extra>",
                               showlegend=False))
    fig.add_trace(go.Scatter(x=[T_MIN, cmax], y=[zs, zs], mode="lines", line=dict(color=INK, width=1.5),
                             hoverinfo="skip", showlegend=False))
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
        title=dict(text=f"Профиль T(z) под точкой ({fmt(xp)}; {fmt(yp)}) м",
                   font=dict(size=17), x=0.01, xanchor="left"),
        margin=dict(l=56, r=16, t=44, b=48), dragmode=False))
    fig.update_xaxes(**axis("T, °C", range=[T_MIN - 0.5, cmax]))
    fig.update_yaxes(**axis("z, м", range=[0, LZ + 0.22], dtick=0.5))
    return fig


# --- Рисунки исследования -------------------------------------------------

NAMES = {"jacobi": "Якоби", "seidel": "Зейдель", "sor": "SOR"}


def convergence_figure(solutions, tol):
    fig = go.Figure()
    for color, sol in zip(SERIES, solutions):
        label = NAMES[sol.method] + (f", ω = {fmt(sol.omega, 3)}" if sol.method == "sor" else "")
        fig.add_trace(go.Scatter(
            x=np.arange(len(sol.residuals)), y=sol.residuals, mode="lines", name=label,
            line=dict(color=color, width=2.5),
            hovertemplate=f"{label}<br>итерация %{{x}}<br>невязка %{{y:.2e}}<extra></extra>"))
        # Подпись у конца линии: Зейдель — слева от точки, чтобы не наехать на Якоби.
        left = sol.method == "seidel"
        fig.add_annotation(x=np.log10(max(sol.iterations, 1)), y=np.log10(sol.residuals[-1]),
                           text=f"<b>{label.split(',')[0]}</b>: {sol.iterations}", showarrow=False,
                           xanchor="right" if left else "left", yanchor="bottom",
                           xshift=-8 if left else 6, yshift=6, font=dict(size=15, color=INK))
    fig.add_hline(y=tol, line=dict(color=MUTED, width=1.5))
    power = int(round(np.log10(tol)))
    fig.add_annotation(x=0, y=np.log10(tol), text=f"порог 10<sup>{power}</sup>", showarrow=False,
                       xanchor="left", yanchor="top", yshift=-2, font=dict(size=15, color=INK_2))
    fig.update_layout(**base_layout(
        title=dict(text="Сходимость на сетке 40 × 30 × 26: относительная невязка", font=dict(size=18),
                   x=0.01, xanchor="left"),
        legend=dict(orientation="h", y=1.0, x=0.99, xanchor="right", yanchor="bottom",
                    font=dict(size=15)),
        margin=dict(l=80, r=30, t=70, b=60)))
    last = max(sol.iterations for sol in solutions)
    fig.update_xaxes(**axis("номер итерации", type="log", dtick=1, range=[0, np.log10(last * 2.6)]))
    fig.update_yaxes(**axis("‖b − Av‖∞ / ‖b‖∞", type="log", exponentformat="power", dtick=2))
    return fig


def depth_figure(depths, curves):
    """curves: [(подпись, амплитуды по глубине)], амплитуда нормирована на потолок."""
    fig = go.Figure()
    for color, (label, values) in zip(SERIES, curves):
        fig.add_trace(go.Scatter(x=depths, y=values, mode="lines", name=label,
                                 line=dict(color=color, width=3),
                                 hovertemplate=f"{label}<br>глубина %{{x:.1f}} м<br>"
                                               "доля от потолка %{y:.0%}<extra></extra>"))
        below = np.flatnonzero(np.asarray(values) <= 0.1)
        if below.size:
            d10 = depths[below[0]]
            fig.add_trace(go.Scatter(x=[d10], y=[0.1], mode="markers", marker=dict(size=10, color=color,
                                     line=dict(color="white", width=2)), hoverinfo="skip",
                                     showlegend=False))
            fig.add_annotation(x=d10, y=0.1, text=f"{fmt(d10, 2)} м", showarrow=False,
                               yshift=16, font=dict(size=15, color=INK))
    fig.add_hline(y=0.1, line=dict(color=MUTED, width=1.5))
    fig.add_annotation(x=depths[-1], y=0.1, text="10 % от потолка", showarrow=False,
                       xanchor="right", yanchor="bottom", font=dict(size=14, color=INK_2))
    fig.update_layout(**base_layout(
        title=dict(text="Как рисунок потолка гаснет с глубиной", font=dict(size=18),
                   x=0.01, xanchor="left"),
        legend=dict(orientation="h", y=1.0, x=0.99, xanchor="right", yanchor="bottom",
                    font=dict(size=15)),
        margin=dict(l=80, r=30, t=70, b=60)))
    fig.update_xaxes(**axis("расстояние от потолка, м", range=[0, max(depths)], dtick=0.25))
    fig.update_yaxes(**axis("амплитуда на срезе / на потолке", range=[0, 1.02], tickformat=".0%"))
    return fig


def slices_figure(T, grid, heights, cmax, cols=None):
    """Горизонтальные срезы на разной глубине на общей шкале °C."""
    cols = cols or len(heights)
    rows = -(-len(heights) // cols)
    titles = [f"z = {fmt(z, 1)} м · {fmt(LZ - z, 1)} м под потолком" for z in heights]
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles, horizontal_spacing=0.06,
                        vertical_spacing=0.14 if rows > 1 else 0.0)
    x, y, _ = grid.axes
    for n, z in enumerate(heights):
        row, col = n // cols + 1, n % cols + 1
        ref = "" if n == 0 else str(n + 1)
        fig.add_trace(go.Heatmap(x=x, y=y, z=layer_z(T, grid, z).T, colorscale=HEAT, zmin=T_MIN,
                                 zmax=cmax, zsmooth="best", hovertemplate=HOVER_XY,
                                 showscale=n == 0, colorbar=colorbar(len=0.9 if rows == 1 else 0.6)),
                      row=row, col=col)
        fig.update_xaxes(**axis("x, м" if row == rows else "", range=[0, LX], constrain="domain",
                                showgrid=False, dtick=1, mirror=True), row=row, col=col)
        fig.update_yaxes(**axis("y, м" if col == 1 else "", range=[0, LY], scaleanchor=f"x{ref}",
                                scaleratio=1, constrain="domain", showgrid=False, dtick=1, mirror=True),
                         row=row, col=col)
    fig.update_annotations(font=dict(size=17, color=INK))
    fig.update_layout(**base_layout(margin=dict(l=60, r=20, t=50, b=50)))
    return fig

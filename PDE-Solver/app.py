"""Демонстрационный стенд: стационарное поле температуры в комнате.

Запуск:  python app.py  →  http://127.0.0.1:8050
"""

import copy
import json
from collections import OrderedDict

from dash import Dash, Input, Output, Patch, State, ctx, dcc, html, no_update

from figures import (DEFAULT_PARAMS, DEFAULT_VIEW, HSLICE, ISO, PROFILE, VSLICE,
                     ceiling_from_params, ceiling_grid, ceiling_map_figure, fmt, hslice_figure,
                     hslice_trace, profile_figure, profile_trace, room_figure, vslice_figure,
                     vslice_trace)
from heat_room import LX, LY, Grid, solve
from theme import color_max

GRID = Grid.with_step(0.1)          # 40 × 30 × 26 шагов, 34 441 узел
TOLERANCE = 1e-6                    # относительная невязка для интерактивного пересчёта
FIELDS = OrderedDict()              # кэш рассчитанных полей: ключ параметров → решение
_last = {"T": None}

SLIDERS = ["spot-x", "spot-y", "spot-sx", "spot-sy", "amp", "wave-m", "wave-n"]


def params_key(params):
    """Ключ кэша: 60 и 60.0 — одни и те же параметры."""
    norm = {"amp": float(params["amp"]), "m": int(params["m"]), "n": int(params["n"]),
            "spots": [[round(float(v), 4) for v in spot] for spot in params["spots"]]}
    return json.dumps(norm, sort_keys=True)


def sci(value):
    mantissa, power = f"{value:.1e}".split("e")
    return f"{mantissa.replace('.', ',')}·10{str(int(power)).translate(str.maketrans('-0123456789', '⁻⁰¹²³⁴⁵⁶⁷⁸⁹'))}"


def field_for(params):
    key = params_key(params)
    if key not in FIELDS:
        sol = solve(GRID, ceiling_from_params(params), method="sor", tol=TOLERANCE, start=_last["T"])
        _last["T"] = sol.T
        _, _, Tc = ceiling_grid(params)
        FIELDS[key] = {"sol": sol, "cmax": color_max(Tc.max())}
        while len(FIELDS) > 24:
            FIELDS.popitem(last=False)
    FIELDS.move_to_end(key)
    return FIELDS[key]


def slider(id_, label, lo, hi, step, value, marks):
    return html.Div(className="control", children=[
        html.Div(className="control-head", children=[
            html.Span(label), html.Span(id=f"{id_}-out", className="control-value")]),
        dcc.Slider(id=id_, min=lo, max=hi, step=step, value=value, marks=marks,
                   updatemode="mouseup", included=False, allow_direct_input=False),
    ])


def marks(values, digits=1):
    return {v: {"label": fmt(v, digits) if digits else str(int(v))} for v in values}


s0 = DEFAULT_PARAMS["spots"][0]

controls = html.Aside(className="panel", children=[
    html.H2("Нагрев потолка"),
    dcc.RadioItems(id="spot-select", className="pills", value=0, inline=True,
                   options=[{"label": "Пятно 1", "value": 0}, {"label": "Пятно 2", "value": 1}]),
    slider("spot-x", "Центр X, м", 0.2, 3.8, 0.01, s0[0], marks([0.2, 2.0, 3.8])),
    slider("spot-y", "Центр Y, м", 0.15, 2.85, 0.01, s0[1], marks([0.15, 1.5, 2.85], 2)),
    slider("spot-sx", "Ширина по X, м", 0.2, 1.2, 0.02, s0[2], marks([0.2, 0.7, 1.2])),
    slider("spot-sy", "Ширина по Y, м", 0.15, 0.9, 0.01, s0[3], marks([0.15, 0.5, 0.9], 2)),
    slider("amp", "Интенсивность A, °C", 0, 100, 5, DEFAULT_PARAMS["amp"], marks([0, 50, 100], 0)),
    html.Div(className="pair", children=[
        slider("wave-m", "Волны m", 0, 6, 1, DEFAULT_PARAMS["m"], marks([0, 3, 6], 0)),
        slider("wave-n", "Волны n", 0, 6, 1, DEFAULT_PARAMS["n"], marks([0, 3, 6], 0)),
    ]),
    html.H2("Срезы"),
    slider("slice-z", "Горизонтальный срез z, м", 0.1, 2.5, 0.05, DEFAULT_VIEW["z"],
           marks([0.1, 1.3, 2.5])),
    dcc.RadioItems(id="vslice-axis", className="pills", value=DEFAULT_VIEW["axis"], inline=True,
                   options=[{"label": "Срез y = const", "value": "y"},
                            {"label": "Срез x = const", "value": "x"}]),
    slider("vslice-pos", "Вертикальный срез, м", 0.05, 2.95, 0.05, DEFAULT_VIEW["pos"],
           marks([0.05, 1.5, 2.95], 2)),
    html.H2("Изоповерхность"),
    dcc.Checklist(id="iso-on", className="switch", value=[],
                  options=[{"label": "Показать в 3D", "value": "on"}]),
    slider("iso-t", "Температура, °C", 21, 60, 0.5, DEFAULT_VIEW["iso_t"],
           marks([21, 40, 60], 0)),
    html.Button("Сбросить", id="reset", className="reset", n_clicks=0),
])

graph_config = {"displaylogo": False, "responsive": True,
                "modeBarButtonsToRemove": ["select2d", "lasso2d", "toImage"]}

app = Dash(__name__, title="Тепло от потолка — PDE-Solver", update_title=None)
app.layout = html.Div(className="page", children=[
    html.Header(className="top", children=[
        html.Div([
            html.H1("Как рисунок температуры на потолке меняется с глубиной?"),
            html.P("Стационарное поле ΔT = 0 в комнате 4 × 3 × 2,6 м · пол и стены 20 °C · "
                   "семиточечная схема, верхняя релаксация (SOR)"),
        ]),
        html.Div(id="status", className="status"),
    ]),
    html.Div(className="layout", children=[
        controls,
        html.Main(className="views", children=[
            html.Section(className="card scene", children=[
                dcc.Graph(id="room", config=graph_config, style={"height": "100%"})]),
            html.Section(className="card ceiling", children=[
                dcc.Graph(id="ceiling-map", config={**graph_config, "doubleClick": False,
                                                    "scrollZoom": False},
                          style={"height": "100%"})]),
            html.Section(className="card hslice", children=[
                dcc.Graph(id="hslice", config=graph_config, style={"height": "100%"})]),
            html.Section(className="card vslice", children=[
                dcc.Graph(id="vslice", config=graph_config, style={"height": "100%"})]),
            html.Section(className="card profile", children=[
                dcc.Graph(id="profile", config=graph_config, style={"height": "100%"})]),
        ]),
    ]),
    dcc.Store(id="params", data=copy.deepcopy(DEFAULT_PARAMS)),
    dcc.Store(id="field", data=None),
    dcc.Store(id="profile-point", data=list(DEFAULT_VIEW["profile"])),
    dcc.Store(id="joystick-live", data=None),
    dcc.Store(id="camera-rev", data=0),
    dcc.Store(id="room-ready", data=False),   # 3D-фигура построена — можно частично обновлять
])


# --- Параметры нагрева ----------------------------------------------------

@app.callback(Output("params", "data"),
              [Input(s, "value") for s in SLIDERS],
              State("spot-select", "value"), State("params", "data"),
              prevent_initial_call=True)   # иначе no_update при загрузке отменит первый расчёт
def commit(x, y, sx, sy, amp, m, n, selected, params):
    new = copy.deepcopy(params)
    new["spots"][selected] = [x, y, sx, sy]
    new.update(amp=amp, m=m, n=n)
    return no_update if new == params else new


@app.callback([Output(s, "value", allow_duplicate=True) for s in SLIDERS[:4]],
              Input("spot-select", "value"), State("params", "data"),
              prevent_initial_call=True)
def select_spot(selected, params):
    return params["spots"][selected]


@app.callback(Output("field", "data"), Output("status", "children"), Input("params", "data"))
def compute(params):
    entry = field_for(params)
    sol = entry["sol"]
    status = [html.B("SOR"), f" · сетка {GRID.nx}×{GRID.ny}×{GRID.nz} · ω = {fmt(sol.omega, 3)} · ",
              f"{sol.iterations} итер. · {fmt(sol.seconds, 2)} с · невязка {sci(sol.residual)}"]
    return {"key": params_key(params), "cmax": entry["cmax"]}, status


def current_field(field):
    entry = FIELDS.get(field["key"]) if field else None
    return entry["sol"].T if entry else None


def view_from(z, axis_name, pos, profile, iso_on, iso_t):
    return {"z": z, "axis": axis_name, "pos": pos, "profile": profile,
            "iso_on": bool(iso_on), "iso_t": iso_t}


# --- Карта потолка: обновляется и во время перетаскивания ------------------

@app.callback(Output("ceiling-map", "figure"),
              Input("params", "data"), Input("joystick-live", "data"),
              [Input(s, "drag_value") for s in SLIDERS],
              Input("spot-select", "value"), Input("profile-point", "data"),
              Input("vslice-axis", "value"), Input("vslice-pos", "drag_value"),
              State("vslice-pos", "value"))
def ceiling_map(params, live, x, y, sx, sy, amp, m, n, selected, profile, axis_name, pos_drag, pos):
    preview = copy.deepcopy(params)
    spot = preview["spots"][selected]
    trigger = ctx.triggered_id
    if trigger == "joystick-live" and live:
        spot[0], spot[1] = live["x"], live["y"]
    elif trigger in SLIDERS:
        value = dict(zip(SLIDERS, [x, y, sx, sy, amp, m, n]))[trigger]
        if value is not None:
            if trigger in SLIDERS[:4]:
                spot[SLIDERS.index(trigger)] = value
            else:
                preview[{"amp": "amp", "wave-m": "m", "wave-n": "n"}[trigger]] = value
    view = {"axis": axis_name, "pos": pos_drag if pos_drag is not None else pos, "profile": profile}
    return ceiling_map_figure(preview, selected, view)


@app.callback(Output("spot-x", "value", allow_duplicate=True),
              Output("spot-y", "value", allow_duplicate=True),
              Input("joystick-live", "data"), prevent_initial_call=True)
def joystick_release(live):
    """Отпускание маркера: одним вызовом двигаем оба ползунка — поле считается один раз."""
    if not live or not live.get("final"):
        return no_update, no_update
    return live["x"], live["y"]


@app.callback(Output("profile-point", "data"), Input("ceiling-map", "clickData"),
              prevent_initial_call=True)
def pick_profile(click):
    point = click["points"][0]
    return [round(min(max(point["x"], 0.05), LX - 0.05), 2),
            round(min(max(point["y"], 0.05), LY - 0.05), 2)]


# --- 3D-сцена: полный пересчёт только при новом поле ----------------------

@app.callback(Output("room", "figure"), Output("room-ready", "data"),
              Input("field", "data"), Input("camera-rev", "data"),
              State("params", "data"), State("slice-z", "value"), State("vslice-axis", "value"),
              State("vslice-pos", "value"), State("profile-point", "data"),
              State("iso-on", "value"), State("iso-t", "value"))
def room(field, revision, params, z, axis_name, pos, profile, iso_on, iso_t):
    T = current_field(field)
    if T is None:
        return no_update, no_update
    view = view_from(z, axis_name, pos, profile, iso_on, iso_t)
    return room_figure(T, GRID, params, view, field["cmax"], revision), True


@app.callback(Output("room", "figure", allow_duplicate=True),
              Input("slice-z", "drag_value"), Input("vslice-axis", "value"),
              Input("vslice-pos", "drag_value"),
              State("slice-z", "value"), State("vslice-pos", "value"), State("field", "data"),
              State("room-ready", "data"), prevent_initial_call=True)
def move_slices_3d(z_drag, axis_name, pos_drag, z, pos, field, ready):
    T = current_field(field)
    if T is None or not ready:
        return no_update
    view = {"z": z_drag if z_drag is not None else z, "axis": axis_name,
            "pos": pos_drag if pos_drag is not None else pos}
    patch = Patch()
    trigger = ctx.triggered_id
    if trigger == "slice-z":
        new = hslice_trace(T, GRID, view["z"], field["cmax"])
        patch["data"][HSLICE]["z"] = new.z
        patch["data"][HSLICE]["surfacecolor"] = new.surfacecolor
    else:
        new = vslice_trace(T, GRID, view, field["cmax"])
        for key in ("x", "y", "z", "surfacecolor"):
            patch["data"][VSLICE][key] = new[key]
    return patch


@app.callback(Output("room", "figure", allow_duplicate=True),
              Input("iso-on", "value"), Input("iso-t", "drag_value"), State("iso-t", "value"),
              State("room-ready", "data"), prevent_initial_call=True)
def iso_3d(iso_on, t_drag, t, ready):
    if not ready:
        return no_update
    t = t_drag if t_drag is not None else t
    patch = Patch()
    patch["data"][ISO]["visible"] = bool(iso_on)
    patch["data"][ISO]["isomin"] = t
    patch["data"][ISO]["isomax"] = t
    return patch


@app.callback(Output("room", "figure", allow_duplicate=True),
              Input("profile-point", "data"), State("room-ready", "data"), prevent_initial_call=True)
def profile_3d(profile, ready):
    if not ready:
        return no_update
    line = profile_trace(*profile)
    patch = Patch()
    patch["data"][PROFILE]["x"] = line.x
    patch["data"][PROFILE]["y"] = line.y
    return patch


# --- Тепловые карты срезов и профиль: из уже рассчитанного поля ----------

@app.callback(Output("hslice", "figure"), Output("vslice", "figure"), Output("profile", "figure"),
              Input("field", "data"), Input("slice-z", "drag_value"), Input("vslice-axis", "value"),
              Input("vslice-pos", "drag_value"), Input("profile-point", "data"),
              State("slice-z", "value"), State("vslice-pos", "value"))
def sections(field, z_drag, axis_name, pos_drag, profile, z, pos):
    T = current_field(field)
    if T is None:
        return no_update, no_update, no_update
    view = {"z": z_drag if z_drag is not None else z, "axis": axis_name,
            "pos": pos_drag if pos_drag is not None else pos, "profile": profile}
    cmax = field["cmax"]
    return (hslice_figure(T, GRID, view, cmax), vslice_figure(T, GRID, view, cmax),
            profile_figure(T, GRID, view, cmax))


# --- Подписи значений у ползунков ----------------------------------------

def _label(id_, digits, unit):
    @app.callback(Output(f"{id_}-out", "children"), Input(id_, "drag_value"), Input(id_, "value"))
    def show(drag, value):
        v = drag if drag is not None else value
        return f"{fmt(v, digits) if digits else int(v)}{unit}"


for _id, _d, _u in [("spot-x", 2, " м"), ("spot-y", 2, " м"), ("spot-sx", 2, " м"),
                    ("spot-sy", 2, " м"), ("amp", 0, " °C"), ("wave-m", 0, ""), ("wave-n", 0, ""),
                    ("slice-z", 2, " м"), ("vslice-pos", 2, " м"), ("iso-t", 1, " °C")]:
    _label(_id, _d, _u)


@app.callback(Output("vslice-pos", "max"), Output("vslice-pos", "marks"), Output("vslice-pos", "value"),
              Input("vslice-axis", "value"), State("vslice-pos", "value"), prevent_initial_call=True)
def vslice_range(axis_name, pos):
    upper = LY - 0.05 if axis_name == "y" else LX - 0.05
    return upper, marks([0.05, upper / 2, upper], 2), min(pos, upper)


# --- Сброс к исходному виду перед показом ---------------------------------

@app.callback(Output("params", "data", allow_duplicate=True),
              [Output(s, "value", allow_duplicate=True) for s in SLIDERS],
              Output("spot-select", "value", allow_duplicate=True),
              Output("slice-z", "value"), Output("vslice-axis", "value"),
              Output("vslice-pos", "value", allow_duplicate=True),
              Output("profile-point", "data", allow_duplicate=True),
              Output("iso-on", "value"), Output("iso-t", "value"),
              Output("camera-rev", "data"),
              Input("reset", "n_clicks"), State("camera-rev", "data"), prevent_initial_call=True)
def reset(_, revision):
    p = copy.deepcopy(DEFAULT_PARAMS)
    return (p, *p["spots"][0], p["amp"], p["m"], p["n"], 0, DEFAULT_VIEW["z"], DEFAULT_VIEW["axis"],
            DEFAULT_VIEW["pos"], list(DEFAULT_VIEW["profile"]), [], DEFAULT_VIEW["iso_t"],
            (revision or 0) + 1)


if __name__ == "__main__":
    field_for(DEFAULT_PARAMS)  # первое поле считаем до открытия страницы
    app.run(host="127.0.0.1", port=8050, debug=False)

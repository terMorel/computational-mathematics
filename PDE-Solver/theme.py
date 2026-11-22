"""Общий стиль приложения, рисунков отчёта и слайдов."""

FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif'

INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
PAGE = "#f4f3ef"

# Категориальные цвета (фиксированный порядок): синий, оранжевый, бирюзовый.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
ACCENT = SERIES[0]

# Семантическая «тепловая» шкала: от светлого (20 °C, фон) к тёмному (горячо).
HEAT = [
    [0.00, "#fbf7f0"],
    [0.10, "#fde9c4"],
    [0.24, "#fbcd82"],
    [0.40, "#f6a352"],
    [0.56, "#eb6834"],
    [0.72, "#c9432a"],
    [0.87, "#932a2b"],
    [1.00, "#561a2c"],
]

T_MIN = 20.0


def color_max(t_max):
    """Верхняя граница общей шкалы: максимум потолка, округлённый вверх до 5 °C."""
    return max(25.0, 5.0 * -(-float(t_max) // 5.0))


def base_layout(**extra):
    layout = dict(
        font=dict(family=FONT, size=15, color=INK),
        paper_bgcolor=SURFACE,   # сплошной фон: PNG читаются и в тёмной теме GitHub
        plot_bgcolor=SURFACE,
        separators=", ",
        margin=dict(l=60, r=20, t=48, b=52),
        hoverlabel=dict(font=dict(family=FONT, size=15), bgcolor="white", bordercolor=AXIS),
    )
    layout.update(extra)
    return layout


def axis(title, **extra):
    spec = dict(
        title=dict(text=title, font=dict(size=15, color=INK_2)),
        tickfont=dict(size=14, color=INK_2),
        gridcolor=GRID,
        linecolor=AXIS,
        zeroline=False,
        showline=True,
        ticks="outside",
        tickcolor=AXIS,
    )
    spec.update(extra)
    return spec


def colorbar(**extra):
    spec = dict(
        title=dict(text="T, °C", font=dict(size=15, color=INK_2)),
        tickfont=dict(size=14, color=INK_2),
        thickness=14,
        outlinewidth=0,
        ticks="outside",
        tickcolor=AXIS,
    )
    spec.update(extra)
    return spec

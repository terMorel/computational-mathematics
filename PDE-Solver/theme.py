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

# Шкала температуры. Фон 20 °C — светлый нейтральный цвет; теплее — от жёлтого
# к тёмно-бордовому, холоднее — к голубому. Положение 20 °C на шкале зависит от
# её пределов, поэтому палитра собирается под каждый диапазон (heat_scale).
NEUTRAL_T = 20.0
COLD = "#a9c8ea"
WARM = [
    [0.00, "#fbf7f0"],
    [0.10, "#fde9c4"],
    [0.24, "#fbcd82"],
    [0.40, "#f6a352"],
    [0.56, "#eb6834"],
    [0.72, "#c9432a"],
    [0.87, "#932a2b"],
    [1.00, "#561a2c"],
]


def color_range(t_max, walls):
    """Общие пределы шкалы: от самой холодной грани до максимума потолка
    (или самой тёплой стены), округлённого вверх до 5 °C."""
    upper = max(float(t_max), walls.warmest)
    return walls.coldest, max(25.0, 5.0 * -(-upper // 5.0))


def heat_scale(scale):
    """Палитра для пределов scale = (cmin, cmax) с нейтральным цветом при 20 °C."""
    cmin, cmax = scale
    f = min(max((NEUTRAL_T - cmin) / (cmax - cmin), 0.0), 1.0)
    stops = [[0.0, COLD]] if f > 0 else []
    stops += [[f + (1 - f) * p, color] for p, color in WARM]
    return stops


HEAT = WARM   # для мест, где 20 °C — нижний предел шкалы


def base_layout(**extra):
    layout = dict(
        font=dict(family=FONT, size=15, color=INK),
        paper_bgcolor=SURFACE,   # сплошной фон: PNG читаются и в тёмной теме GitHub
        plot_bgcolor=SURFACE,
        separators=", ",
        margin=dict(l=60, r=20, t=48, b=52),
        hoverlabel=dict(font=dict(family=FONT, size=15, color=INK), bgcolor="white", bordercolor=AXIS),
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

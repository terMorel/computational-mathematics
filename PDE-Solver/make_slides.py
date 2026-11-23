"""Презентация для защиты: python make_slides.py → presentation/PDE-Solver.pptx и .pdf

Числа берутся из results.json (study.py), поля — из нового расчёта. Графики для
слайдов экспортируются с крупным шрифтом, формулы рендерит matplotlib (mathtext).

Сборка идёт во временной папке. PPTX и PDF в presentation/ заменяются только вместе
и только после успешного экспорта PDF; при ошибке скрипт завершается с кодом 1,
а прежняя пара файлов остаётся нетронутой.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from figures import (DEFAULT_PARAMS, DEFAULT_VIEW, ceiling_from_params, ceiling_map_figure,
                     convergence_figure, depth_figure, fmt, hslice_figure, profile_compare_figure,
                     scale_for, slices_figure, vslice_figure)
from heat_room import DEFAULT_CEILING, WALLS, Grid, solve

HERE = Path(__file__).parent
OUT = HERE / "presentation"
NAME = "PDE-Solver"
TITLE = "Стационарное распределение температуры в комнате"
RESULTS = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
BUILD = None                     # временная папка сборки, задаётся в main()

FONT = "Arial"
INK = RGBColor(0x0B, 0x0B, 0x0B)
INK_2 = RGBColor(0x52, 0x51, 0x4E)
CARD = RGBColor(0xF4, 0xF3, 0xEF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x2E, 0x17, 0x20)        # тёмный конец тепловой шкалы
LIGHT_ON_DARK = RGBColor(0xE8, 0xDF, 0xD6)
ORANGE = RGBColor(0xF6, 0xA3, 0x52)
PANEL = RGBColor(0xFC, 0xFC, 0xFB)       # фон рисунков Plotly (theme.SURFACE)
RULE = RGBColor(0xE1, 0xE0, 0xD9)

W, H = 13.333, 7.5
M = 0.6


def nbsp(value):
    """Число не отрывается от единицы, «z = 1,6» — от знака, «4 × 3» — от знака умножения."""
    value = re.sub(r"([\d)]) (м⁻¹|м|°C|с|раз|итерац\w*|%|узл\w*)", "\\1\u00a0\\2", value)
    value = re.sub(r"\b([xyzAhkmnsωτρμΛ]) = ", "\\1\u00a0=\u00a0", value)
    value = re.sub(r"(\b[ijks]|\}) ([−+]) 1\b", "\\1\u00a0\\2\u00a01", value)   # «i − 1», «M_{x} − 1»
    value = value.replace("} = ", "}\u00a0=\u00a0")                                      # «λ_{max} = 1196,8»
    value = re.sub(r"\((\d+,\d+); (\d+,\d+)\)", "(\\1;\u00a0\\2)", value)  # координаты точки
    value = re.sub(r"(\d) (\d{3})\b", "\\1\u00a0\\2", value)                # 28 275
    for _ in range(2):   # «4 × 3 × 2,6»: соседние пары перекрываются
        value = re.sub(r"(\d) × (\d)", "\\1\u00a0×\u00a0\\2", value)
    value = re.sub(r" — (\d)", "\u00a0— \\1", value)
    value = value.replace("T(A) − T(0)", "T(A)\u00a0−\u00a0T(0)")
    value = re.sub(r"(?<![\w\u00a0])([вксуоаиВКСУОАИ]) ", "\\1\u00a0", value)   # «в комнате»
    return value


def num(value, digits):
    return fmt(value, digits)


def thousands(value):
    return f"{value:,}".replace(",", "\u00a0")


# --- Рисунки для слайдов ----------------------------------------------------

def enlarge(fig, factor):
    """Увеличить все шрифты фигуры Plotly в factor раз."""
    data = fig.to_dict()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("font", "tickfont", "textfont") and isinstance(value, dict) \
                        and isinstance(value.get("size"), (int, float)):
                    value["size"] = value["size"] * factor
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return go.Figure(data)


def export(fig, name, width, height, factor=1.35):
    path = BUILD / name
    enlarge(fig, factor).write_image(path, width=width, height=height, scale=3)
    return path


def untitled(fig, top=12):
    fig.update_layout(title_text="", margin_t=top)
    return fig


plt.rcParams.update({"mathtext.fontset": "custom", "mathtext.rm": "Arial",
                     "mathtext.it": "Arial:italic", "mathtext.bf": "Arial:bold",
                     "font.family": "Arial"})


def formula(name, tex, size=28):
    path = BUILD / f"formula-{name}.png"
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, tex, fontsize=size, color="#0b0b0b")
    fig.savefig(path, dpi=220, transparent=True, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return path


def stencil_picture():
    """Семиточечный шаблон «крест»: узел (m, l, n) и шесть соседей."""
    path = BUILD / "stencil.png"
    fig, ax = plt.subplots(figsize=(6.0, 5.4), dpi=220)
    ax.set_aspect("equal")
    ax.axis("off")
    d = (0.55, 0.38)                     # направление оси j на рисунке (перспектива)
    nodes = {  # подпись: (x, y узла, x и y подписи, выравнивание)
        "m − 1": (-1.6, 0.0, -2.0, 0.0, "right"),
        "m + 1": (1.6, 0.0, 2.0, 0.0, "left"),
        "l − 1": (-1.6 * d[0], -1.6 * d[1], -1.25, -1.0, "right"),
        "l + 1": (1.6 * d[0], 1.6 * d[1], 1.25, 1.0, "left"),
        "n − 1": (0.0, -1.6, 0.42, -1.6, "left"),
        "n + 1": (0.0, 1.6, 0.42, 1.6, "left"),
    }
    for x, y, *_ in nodes.values():
        ax.plot([0, x], [0, y], color="#898781", lw=2.5, zorder=1)
    for label, (x, y, tx, ty, ha) in nodes.items():
        ax.scatter([x], [y], s=900, zorder=3, color="white", edgecolors="#2a78d6", linewidths=3)
        ax.text(tx, ty, label, fontsize=21, ha=ha, va="center", color="#0b0b0b")
    ax.scatter([0], [0], s=1300, zorder=4, color="#eb6834", edgecolors="#0b0b0b", linewidths=2)
    ax.text(0.4, -0.45, "(m, l, n)", fontsize=21, ha="left", va="center", color="#0b0b0b")
    ax.set_xlim(-3.0, 3.0)
    ax.set_ylim(-2.1, 2.1)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, transparent=True)
    plt.close(fig)
    return path


# --- Примитивы слайда ---------------------------------------------------------

def background(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def text(slide, x, y, w, h, runs, size=18, color=INK, bold=False, anchor=MSO_ANCHOR.TOP,
         spacing=1.1, after=0, name=None):
    """runs: строка или список абзацев; абзац — строка или список (текст, {опции})."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        box.name = name
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paragraphs = [runs] if isinstance(runs, str) else runs
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = spacing
        p.space_after = Pt(after)
        for part, opts in ([(para, {})] if isinstance(para, str) else para):
            for piece, shift in scripts(nbsp(part)):
                r = p.add_run()
                r.text = piece
                r.font.name = FONT
                r.font.size = Pt(opts.get("size", size))
                r.font.bold = opts.get("bold", bold)
                r.font.color.rgb = opts.get("color", color)
                if shift:
                    r.font._element.set("baseline", shift)
    return box


def scripts(value):
    """Разметка индексов: «D_{h}» — нижний, «T^{(i)}» — верхний. Возвращает куски и сдвиг базовой линии."""
    out, pos = [], 0
    for match in re.finditer(r"([_^])\{([^}]*)\}", value):
        if match.start() > pos:
            out.append((value[pos:match.start()], None))
        out.append((match.group(2), "-25000" if match.group(1) == "_" else "30000"))
        pos = match.end()
    if pos < len(value):
        out.append((value[pos:], None))
    return out


def title(slide, value, color=INK, size=30):
    text(slide, M, 0.42, W - 2 * M, 0.8, value, size=size, bold=True, color=color, name="Title")


def card(slide, x, y, w, h, color=CARD):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.adjustments[0] = 0.03
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def panel(slide, x, y, w, h):
    """Подложка под рисунок Plotly: цвет фона рисунка и тонкая рамка."""
    shape = card(slide, x, y, w, h, color=PANEL)
    shape.line.color.rgb = RULE
    shape.line.width = Pt(0.75)
    return shape


def same_scale(slide, items):
    """Несколько формул в одном масштабе: items — (путь, x, y, w, h); по левому краю, по центру h."""
    sizes = [Image.open(path).size for path, *_ in items]
    k = min(min(w / iw, h / ih) for (_, _, _, w, h), (iw, ih) in zip(items, sizes))
    for (path, x, y, w, h), (iw, ih) in zip(items, sizes):
        slide.shapes.add_picture(str(path), Inches(x), Inches(y + (h - ih * k) / 2), Inches(iw * k), Inches(ih * k))


def picture(slide, path, x, y, w, h, align="center"):
    iw, ih = Image.open(path).size
    k = min(w / iw, h / ih)
    pw, ph = iw * k, ih * k
    px = x + (w - pw) / 2 if align == "center" else x
    return slide.shapes.add_picture(str(path), Inches(px), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))


def table(slide, x, y, rows, widths, size=18, row_h=0.5, first_left=True):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(sum(widths)),
                                   Inches(row_h * len(rows)))
    tbl = shape.table
    for j, cw in enumerate(widths):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = DARK if i == 0 else (WHITE if i % 2 else CARD)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if (j == 0 and first_left) else PP_ALIGN.RIGHT
            r = p.add_run()
            r.text = nbsp(str(value))
            r.font.name, r.font.size, r.font.bold = FONT, Pt(size), i == 0
            r.font.color.rgb = WHITE if i == 0 else INK
    return tbl


def notes(slide, value):
    slide.notes_slide.notes_text_frame.text = nbsp(value)


def new_slide(prs, heading, dark=False):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, DARK if dark else WHITE)
    title(s, heading, color=WHITE if dark else INK)
    return s


# --- Слайды -----------------------------------------------------------------

def timing_conditions(timing):
    machine = ", ".join(v for v in [timing["system"], timing["machine"], timing.get("cpu")] if v)
    return (f"Время — медиана {timing['repeats']} запусков на одном компьютере: {machine}; "
            f"Python {timing['python']}, numpy {timing['numpy']}.")


def build(path):
    r = RESULTS
    jac, sei, sor = r["methods"]
    gains = r["gains"]
    g = r["grid"]
    inc = r["increment_convergence"]
    full = r["full_field_convergence"]
    checks = r["checks"]
    decay = r["depth_decay"]
    spot1, spot2, wave = (decay[k] for k in decay if isinstance(decay[k], dict))
    slices = r["slices"]
    prof = r["profile"]
    by_depth = {round(row["depth"], 2): row for row in slices}
    deep, metre, top = by_depth[1.3], by_depth[1.0], by_depth[0.1]
    nodes = (g["nx"] + 1) * (g["ny"] + 1) * (g["nz"] + 1)

    print("Поля и рисунки для слайдов…")
    grid = Grid.with_step(0.1)
    base = solve(grid, ceiling_from_params(DEFAULT_PARAMS), tol=1e-10)
    flat = solve(grid, ceiling_from_params({**DEFAULT_PARAMS, "amp": 0.0}), tol=1e-10)
    scale = scale_for(DEFAULT_PARAMS)
    view = DEFAULT_VIEW

    cover = untitled(hslice_figure(base.T, grid, view, scale), top=14)
    cover.data = cover.data[:1]                       # только поле, без линий стенда
    img_cover = export(cover, "cover.png", 640, 480, 1.3)
    from make_figures import scheme_figure
    img_scheme = export(scheme_figure(DEFAULT_PARAMS, scale, short=True), "scheme.png", 820, 600, 1.25)
    ceiling = untitled(ceiling_map_figure(DEFAULT_PARAMS, 0, view, scale), top=14)
    ceiling.data = [ceiling.data[0]] + list(ceiling.data[3:])   # тепловая карта и пятна 1, 2
    img_ceiling = export(ceiling, "ceiling.png", 600, 440, 1.3)
    img_stencil = stencil_picture()
    solutions = [solve(grid, method=m, tol=r["tolerance"]) for m in ("jacobi", "seidel", "sor")]
    conv = untitled(convergence_figure(solutions, r["tolerance"]), top=60)
    # Подписи у концов линий на узком рисунке налезают друг на друга; числа — в таблице.
    conv.layout.annotations = [a for a in conv.layout.annotations if "<b>" not in a.text]
    conv.update_yaxes(title_text="относительная невязка")
    for trace in conv.data:   # параметр релаксации на слайдах обозначен τ
        trace.name = trace.name.replace("ω", "τ")
    img_conv = export(conv, "convergence.png", 700, 450, 1.3)
    heights = [row["z"] for row in slices]
    img_slices = export(slices_figure(base.T, grid, heights, scale, cols=2), "slices.png", 700, 600, 1.3)
    img_vslice = export(vslice_figure(base.T, grid, view, scale), "vslice.png", 600, 450, 1.3)
    img_profile = export(profile_compare_figure(base.T, flat.T, grid, view["profile"], view["z"], scale,
                                                DEFAULT_PARAMS["amp"]), "profile.png", 520, 540, 1.3)
    from study import depth_decay   # тот же расчёт, что и в отчёте
    depths, curves, summary = depth_decay(Grid.with_step(0.05))
    img_decay = export(untitled(depth_figure(depths, curves, summary), top=20), "depth.png", 760, 470, 1.3)

    f_ceiling = formula("ceiling", r"$\varphi_6(x, y) = 20 + A\,\sin^2(\pi u)\,\sin^2(\pi v)\,"
                                   r"\left(0{,}12 + 0{,}65\,G_1 + 0{,}30\,G_2 + 0{,}15\,R\right)$", 30)
    f_gauss = formula("gauss", r"$G_j = \exp\left(-\frac{1}{2}\left[\left(\frac{u - u_j}{\sigma_{xj}}\right)^2"
                               r" + \left(\frac{v - v_j}{\sigma_{yj}}\right)^2\right]\right)$", 24)
    f_wave = formula("wave", r"$R = \frac{1}{2}\,(1 + \sin 2\pi m u\;\cos 2\pi n v)$", 24)
    f_laplace = formula("laplace", r"$\Delta T = \frac{\partial^2 T}{\partial x^2} + \frac{\partial^2 T}{\partial y^2}"
                                   r" + \frac{\partial^2 T}{\partial z^2} = 0,\qquad (x, y, z) \in D$", 28)
    f_scheme = formula("scheme", r"$\Lambda_1 T_{mln} + \Lambda_2 T_{mln} + \Lambda_3 T_{mln} = 0,\quad (m, l, n) \in D_h;"
                                 r"\qquad \Lambda_1 T_{mln} = \frac{T_{m-1,l,n} - 2\,T_{mln} + T_{m+1,l,n}}{h^2}$", 26)
    f_grid_bc1 = formula("grid-bc1", r"$T_{0ln} = \varphi_1,\quad T_{M_x ln} = \varphi_2,\quad T_{m0n} = \varphi_3,"
                                     r"\quad T_{m M_y n} = \varphi_4,$", 26)
    f_grid_bc2 = formula("grid-bc2", r"$T_{ml0} = \varphi_5,\quad T_{ml M_z} = \varphi_6(x_m, y_l)$", 26)
    f_mean = formula("mean", r"$T_{mln} = \frac{1}{6}\,(T_{m-1,l,n} + T_{m+1,l,n} + T_{m,l-1,n} + T_{m,l+1,n}"
                             r" + T_{m,l,n-1} + T_{m,l,n+1})$", 26)
    f_trunc = formula("trunc", r"$\Lambda T - \Delta T = \frac{h^2}{12}\left(\frac{\partial^4 T}{\partial x^4}"
                               r" + \frac{\partial^4 T}{\partial y^4} + \frac{\partial^4 T}{\partial z^4}\right) + O(h^4)$", 26)
    f_eig = formula("eig", r"$\lambda_{pqr} = \frac{4}{h^2}\left(\sin^2\frac{p\pi}{2M_x} + \sin^2\frac{q\pi}{2M_y}"
                           r" + \sin^2\frac{r\pi}{2M_z}\right)$", 26)
    f_sums = formula("sums", r"$\Sigma^- T = T_{m-1,l,n} + T_{m,l-1,n} + T_{m,l,n-1},\qquad "
                             r"\Sigma^+ T = T_{m+1,l,n} + T_{m,l+1,n} + T_{m,l,n+1}$", 26)
    f_jacobi = formula("jacobi", r"$\frac{\Sigma^- T^{(i)} + \Sigma^+ T^{(i)} - 6\,T^{(i+1)}_{mln}}{h^2} = 0"
                                 r"\quad\Rightarrow\quad T^{(i+1)}_{mln} = \frac{1}{6}\left(\Sigma^- T^{(i)}"
                                 r" + \Sigma^+ T^{(i)}\right)$", 28)
    f_seidel = formula("seidel", r"$\frac{\Sigma^- T^{(i+1)} + \Sigma^+ T^{(i)} - 6\,T^{(i+1)}_{mln}}{h^2} = 0"
                                 r"\quad\Rightarrow\quad T^{(i+1)}_{mln} = \frac{1}{6}\left(\Sigma^- T^{(i+1)}"
                                 r" + \Sigma^+ T^{(i)}\right)$", 28)
    f_sor_matrix = formula("sor-matrix", r"$L\,T^{(i+1)} + U\,T^{(i)} + D\left(\frac{T^{(i+1)}}{\tau}"
                                         r" + \left(1 - \frac{1}{\tau}\right)T^{(i)}\right) = f,\qquad 1 < \tau < 2$", 28)
    f_sor = formula("sor", r"$T^{(i+1)}_{mln} = (1 - \tau)\,T^{(i)}_{mln} + \frac{\tau}{6}\left(\Sigma^- T^{(i+1)}"
                           r" + \Sigma^+ T^{(i)}\right)$", 28)

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    props = prs.core_properties
    props.title = TITLE
    props.subject = "Задача Дирихле для уравнения Лапласа; методы Якоби, Зейделя и верхней релаксации"
    props.keywords = "уравнение Лапласа; разностная схема; SOR"
    props.author = ""
    props.last_modified_by = ""

    # 1. Титул
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, DARK)
    text(s, M, 1.0, 5.9, 0.4, "ВЫЧИСЛИТЕЛЬНАЯ МАТЕМАТИКА", size=14, bold=True, color=ORANGE)
    text(s, M, 1.55, 5.9, 2.6, TITLE, size=40, bold=True, color=WHITE, spacing=1.0, name="Title")
    text(s, M, 4.35, 5.6, 1.6, "Задача Дирихле для уравнения Лапласа в комнате 4 × 3 × 2,6 м. "
                              "Разностная схема «крест», методы Якоби, Зейделя и верхней релаксации.",
         size=19, color=LIGHT_ON_DARK)
    card(s, 6.75, 1.0, 6.0, 5.05, color=RGBColor(0xFC, 0xFC, 0xFB))
    picture(s, img_cover, 6.85, 1.1, 5.8, 4.85)
    text(s, 6.75, 6.2, 6.0, 0.5, f"Рассчитанное поле на высоте {num(view['z'], 2)} м, A = "
                                 f"{num(DEFAULT_PARAMS['amp'], 0)} °C", size=15, color=LIGHT_ON_DARK)
    notes(s, "Ищем стационарное распределение температуры в комнате, у которой стены и пол имеют постоянные "
             "температуры, а потолок нагрет неравномерно. Справа — горизонтальный срез рассчитанного поля "
             "в 30 сантиметрах под потолком. В докладе: постановка, разностная схема, три итерационных метода, "
             "проверка точности и результаты.")

    # 2. Постановка задачи Дирихле
    s = new_slide(prs, "Постановка задачи Дирихле")
    panel(s, M, 1.4, 5.7, 5.55)
    picture(s, img_scheme, M + 0.1, 1.5, 5.5, 5.35)
    X = 6.65
    text(s, X, 1.4, W - M - X, 0.4, "Теплопроводность постоянна, источников нет:", size=16, color=INK_2)
    picture(s, f_laplace, X, 1.9, W - M - X, 0.7, align="left")
    text(s, X, 2.68, W - M - X, 0.4, "D = (0; Lx) × (0; Ly) × (0; Lz), Lx = 4 м, Ly = 3 м, Lz = 2,6 м.",
         size=16, color=INK_2)
    text(s, X, 3.12, W - M - X, 0.4, "Краевые условия первого рода T|_{Γ} = φ:", size=17, bold=True)
    w = WALLS
    table(s, X, 3.55, [["Грань", "Условие"],
                       ["x = 0", f"T(0, y, z) = φ₁ = {num(w.x0, 0)} °C"],
                       ["x = Lx", f"T(Lx, y, z) = φ₂ = {num(w.x1, 0)} °C"],
                       ["y = 0", f"T(x, 0, z) = φ₃ = {num(w.y0, 0)} °C"],
                       ["y = Ly", f"T(x, Ly, z) = φ₄ = {num(w.y1, 0)} °C"],
                       ["z = 0 (пол)", f"T(x, y, 0) = φ₅ = {num(w.floor, 0)} °C"],
                       ["z = Lz (потолок)", "T(x, y, Lz) = φ₆(x, y)"]],
          [2.2, W - M - X - 2.2], size=15, row_h=0.4)
    text(s, X, 6.45, W - M - X, 0.6, "На рёбрах φ разрывна: например, φ₁ = 16 °C, а φ₆ → 20 °C. "
                                     "Ищется ограниченное решение.", size=15, color=INK_2)
    notes(s, "Комната — параллелепипед D. Теплопроводность постоянна, источников нет, поэтому стационарная "
             "температура удовлетворяет уравнению Лапласа. На всей границе Γ заданы значения температуры — "
             "краевые условия первого рода, это задача Дирихле. Пять граней имеют постоянные температуры, "
             "на потолке задана функция φ₆, о ней следующий слайд. На рёбрах значения соседних граней разные, "
             "поэтому граничная функция там разрывна; внутри области решение гладкое и ограниченное.")

    # 3. Граничное условие на потолке
    s = new_slide(prs, "Граничное условие на потолке φ₆(x, y)")
    picture(s, f_ceiling, M, 1.35, W - 2 * M, 0.75, align="left")
    panel(s, M, 2.4, 6.1, 4.5)
    picture(s, img_ceiling, M + 0.1, 2.5, 5.9, 4.3)
    x1, y1 = DEFAULT_PARAMS["spots"][0][:2]
    x2, y2 = DEFAULT_PARAMS["spots"][1][:2]
    text(s, 7.1, 2.45, 5.6, 1.0, [[("u = x / 4 м, v = y / 3 м", {"bold": True, "color": INK}),
                                   (" — координаты на потолке от 0 до 1.", {})]], size=17, color=INK_2)
    picture(s, f_gauss, 7.1, 3.2, 5.6, 0.75, align="left")
    text(s, 7.1, 4.0, 5.6, 0.9, f"G₁, G₂ — пятна с центрами ({num(x1, 2)}; {num(y1, 2)}) м и "
                                f"({num(x2, 2)}; {num(y2, 2)}) м.", size=17, color=INK_2)
    picture(s, f_wave, 7.1, 4.75, 5.6, 0.6, align="left")
    text(s, 7.1, 5.45, 5.6, 1.5, [f"R — волновой узор, m = n = {DEFAULT_PARAMS['m']}. "
                                  f"A = {num(DEFAULT_PARAMS['amp'], 0)} °C — интенсивность нагрева.",
                                  "Множитель sin²πu · sin²πv равен нулю на краю: там температура "
                                  "потолка стремится к 20 °C."],
         size=17, color=INK_2, after=6)
    sx1, sy1 = DEFAULT_CEILING.spots[0].sx, DEFAULT_CEILING.spots[0].sy
    sx2, sy2 = DEFAULT_CEILING.spots[1].sx, DEFAULT_CEILING.spots[1].sy
    notes(s, "Температура потолка — фон 20 °C плюс нагрев. Нагрев состоит из постоянной части, двух гауссовых "
             "пятен и волнового узора. u и v — координаты на потолке, отнесённые к его длине и ширине. "
             f"Ширины пятен по u и v: {num(sx1, 2)} и {num(sy1, 2)} для первого, {num(sx2, 2)} и {num(sy2, 2)} "
             "для второго. Множитель из квадратов синусов обнуляет нагрев на краю потолка. "
             f"Максимум потолка — {num(checks['boundary_max'], 1)} °C.")

    # 4. Разностная задача
    s = new_slide(prs, "Разностная задача: схема «крест»")
    picture(s, img_stencil, M, 1.4, 3.7, 3.4)
    text(s, M, 4.95, 3.7, 2.0, [f"h = 0,1 м по x, y, z; M_{{x}} = {g['nx']}, M_{{y}} = {g['ny']}, "
                                f"M_{{z}} = {g['nz']}.",
                                f"Узлов {g['nx'] + 1} × {g['ny'] + 1} × {g['nz'] + 1} = {thousands(nodes)}; "
                                f"в D_{{h}} — {g['nx'] - 1} × {g['ny'] - 1} × {g['nz'] - 1} = {thousands(g['unknowns'])}."],
         size=15, color=INK_2, after=6)
    X = 4.6
    text(s, X, 1.4, W - M - X, 0.7, "Сетка: x_{m} = mh, y_{l} = lh, z_{n} = nh; D_{h} — внутренние узлы, "
                                    "Γ_{h} — узлы на гранях. Во внутренних узлах:", size=16, color=INK_2)
    picture(s, f_scheme, X, 2.1, W - M - X, 0.75, align="left")
    text(s, X, 2.95, W - M - X, 0.4, "Λ₂, Λ₃ — те же вторые разности по l и n. На Γ_{h}:", size=16, color=INK_2)
    same_scale(s, [(f_grid_bc1, X, 3.4, W - M - X, 0.45), (f_grid_bc2, X, 3.9, W - M - X, 0.45)])
    text(s, X, 4.45, W - M - X, 0.7, "В узлах рёбер и вершин — среднее пределов примыкающих граней; "
                                     "соседями узлов D_{h} они не бывают и в уравнения не входят.",
         size=16, color=INK_2)
    text(s, X, 5.3, W - M - X, 0.4, "Канонический вид при равных шагах:", size=16, color=INK_2)
    picture(s, f_mean, X, 5.7, W - M - X, 0.6, align="left")
    text(s, X, 6.45, W - M - X, 0.5, "Решение во внутреннем узле равно среднему шести соседей.", size=17, bold=True)
    notes(s, "Вводим равномерную сетку с шагом 10 сантиметров по всем осям. Вторые производные заменяем вторыми "
             "разностями на семиточечном шаблоне «крест»: Λ₁, Λ₂, Λ₃ — разностные операторы по трём "
             "направлениям. Неизвестны значения во внутренних узлах, их 28 275; значения на гранях известны из "
             "краевых условий и переходят в правую часть. Узлы рёбер и вершин имеют два или три крайних индекса, "
             "соседями внутренних узлов они не являются, поэтому правило средних на них на решение не влияет. "
             "Если выразить значение в узле из разностного уравнения, получаем канонический вид: среднее шести соседей.")

    # 5. Аппроксимация, устойчивость, спектр
    l_min, l_max = grid.spectrum_bounds()
    s = new_slide(prs, "Аппроксимация, устойчивость и спектр")
    blocks = [
        ("Аппроксимация", f_trunc, "Разложение по Тейлору до членов четвёртого порядка: схема второго порядка "
                                   "по h; Λ = Λ₁ + Λ₂ + Λ₃."),
        ("Принцип максимума", None, "Каждое решение ΛT = 0 в D_{h} достигает максимума и минимума на Γ_{h}: в узле "
                                    "D_{h} значение — среднее соседей. При φ = 0 решение только нулевое, поэтому "
                                    "система однозначно разрешима при любых φ, и ‖T‖_{C} ≤ max_{Γh}|φ| — "
                                    f"устойчивость. В расчёте: в D_{{h}} {num(checks['interior_min'], 2)}…"
                                    f"{num(checks['interior_max'], 2)} °C, на Γ_{{h}} "
                                    f"{num(checks['boundary_min'], 0)}…{num(checks['boundary_max'], 2)} °C."),
        ("Спектр", f_eig, f"Система Av = b, A = −Λ = A* > 0, {thousands(g['unknowns'])} неизвестных. "
                          f"λ_{{min}} = λ_{{111}} = {num(l_min, 2)} м⁻², λ_{{max}} = {num(l_max, 1)} м⁻², число "
                          f"обусловленности μ = λ_{{max}} / λ_{{min}} ≈ {l_max / l_min:.0f}."),
    ]
    ys = [1.4, 3.15, 4.9]
    hs = [1.6, 1.6, 1.85]
    for (head, img, body), y, h in zip(blocks, ys, hs):
        card(s, M, y, W - 2 * M, h)
        text(s, M + 0.25, y + 0.15, 2.6, 0.5, head, size=19, bold=True)
        if img is None:
            text(s, 3.4, y + 0.15, 9.1, h - 0.3, body, size=16, color=INK_2, anchor=MSO_ANCHOR.MIDDLE)
        else:
            picture(s, img, 3.4, y + 0.12, 9.1, 0.8, align="left")
            text(s, 3.4, y + 0.98, 9.1, h - 1.05, body, size=16, color=INK_2)
    notes(s, "Разложение проекции точного решения в ряд Тейлора показывает, что главный член погрешности "
             "аппроксимации пропорционален h², то есть схема второго порядка. Устойчивость доказывается через "
             "сеточный принцип максимума: в каждом внутреннем узле значение равно среднему соседей, поэтому "
             "внутри не может быть строгого максимума. Отсюда однородная задача имеет только нулевое решение, "
             "система однозначно разрешима, и решение ограничено граничными данными. Наш расчёт этому "
             "удовлетворяет. Собственные функции разностного оператора — произведения синусов, собственные "
             f"числа лежат от {num(l_min, 2)} до {num(l_max, 1)}; большое отношение крайних чисел объясняет медленную "
             "сходимость простых итераций: число обусловленности около 380.")

    # 6. Методы Якоби, Зейделя и верхней релаксации
    s = new_slide(prs, "Методы Якоби, Зейделя и верхней релаксации")
    picture(s, f_sums, M, 1.3, W - 2 * M, 0.5, align="left")
    text(s, M, 1.85, W - 2 * M, 0.4, "Везде (m, l, n) ∈ D_{h}, i — номер итерации; T^{(i+1)} = φ на Γ_{h}, "
                                     "T^{(0)} = 20 °C в D_{h}.", size=16, color=INK_2)
    rows = [("Якоби", 2.35, 1.0), ("Зейдель", 3.45, 1.0), ("Верхняя релаксация (SOR)", 4.55, 1.55)]
    for name, y, h in rows:
        card(s, M, y, W - 2 * M, h)
        text(s, M + 0.2, y, 2.2, h, name, size=18, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    same_scale(s, [(f_jacobi, 2.95, 2.42, 9.6, 0.86), (f_seidel, 2.95, 3.52, 9.6, 0.86),
                   (f_sor_matrix, 2.95, 4.62, 9.6, 0.7), (f_sor, 2.95, 5.35, 9.6, 0.7)])
    text(s, M, 6.22, W - 2 * M, 1.1, [
        "L, D, U — нижняя треугольная, диагональная и верхняя треугольная части матрицы системы. "
        "Обход узлов: (1, 1, 1), (1, 1, 2), …, (M_{x} − 1, M_{y} − 1, M_{z} − 1).",
        f"τ = 1 — метод Зейделя; τ = 2 / (1 + √(1 − ρ²)) = {num(sor['omega'], 3)}, где "
        f"ρ = 1 − h²λ_{{min}} / 6 = {num(g['jacobi_radius'], 4)} — спектральный радиус метода Якоби."],
         size=14, color=INK_2, after=3)
    notes(s, "Каждый метод получается из разностного уравнения: значения соседей берутся с разных итераций. "
             "Σ⁻ — сумма трёх соседей с меньшим индексом, Σ⁺ — с большим. В методе Якоби все соседи с прошлой "
             "итерации. В методе Зейделя узлы обходятся по порядку, и соседи с меньшим индексом уже пересчитаны "
             "на текущей итерации; метод неявный, но вычисляется явно благодаря порядку обхода. В методе верхней "
             "релаксации система записывается как (L + D + U)T = f, где L и U — нижняя и верхняя треугольные "
             "части, D — диагональ; параметр τ от 1 до 2. Расчётная формула — шаг Зейделя с множителем τ. "
             "Оптимальное τ выражается через спектральный радиус метода Якоби, а он — через наименьшее "
             "собственное число оператора. Проверка подбором: число итераций при τ = 1,75 — "
             f"{next(x['iterations'] for x in r['omega_scan'] if x['omega'] == 1.75)}, при 1,85 — "
             f"{next(x['iterations'] for x in r['omega_scan'] if x['omega'] == 1.85)}.")

    # 7. Сравнение итерационных методов
    s = new_slide(prs, "Сравнение итерационных методов")
    panel(s, M, 1.4, 7.4, 4.75)
    picture(s, img_conv, M + 0.1, 1.5, 7.2, 4.55)
    text(s, M, 6.3, 7.4, 0.9, f"Начальное поле 20 °C, остановка при ‖b − AT^{{(i)}}‖_{{C}} / ‖b‖_{{C}} ≤ 10⁻⁸: Якоби — "
                              f"{jac['iterations']}, Зейдель — {sei['iterations']}, SOR — "
                              f"{sor['iterations']} итераций.", size=16, bold=True)
    table(s, 8.35, 1.4, [["Метод", "τ", "Итераций", "Оценка"],
                         ["Якоби", "—", jac["iterations"], jac["predicted"]],
                         ["Зейдель", "1", sei["iterations"], sei["predicted"]],
                         ["SOR", num(sor["omega"], 3), sor["iterations"], sor["predicted"]]],
          [1.1, 0.85, 1.3, 1.13], size=15, row_h=0.46)
    text(s, 8.35, 3.35, 4.38, 0.6, "Оценка — ln ε⁻¹ / ln ρ⁻¹: ρ = 0,9947 (Якоби), ρ² (Зейдель), "
                                   "τ − 1 (SOR).", size=13, color=INK_2)
    table(s, 8.35, 4.0, [["Метод", "Время, с"],
                         ["Якоби", num(jac["seconds"], 3)], ["Зейдель", num(sei["seconds"], 3)],
                         ["SOR", num(sor["seconds"], 3)]], [2.75, 1.63], size=16, row_h=0.42)
    text(s, 8.35, 5.8, 4.38, 1.5, [timing_conditions(r["timing"]) + " SOR быстрее Якоби по времени в "
                                   f"{num(gains['time_jacobi_to_sor'], 1)} раза, Зейделя — в "
                                   f"{num(gains['time_seidel_to_sor'], 1)} раза."],
         size=13, color=INK_2)
    notes(s, "На графике — относительная невязка ‖b − AT‖ / ‖b‖ по номеру итерации, обе оси логарифмические. "
             "Все методы стартуют с одного поля и останавливаются на одном пороге. Оценка числа итераций "
             "по спектральному радиусу описывает самую медленную гармонику ошибки: для Якоби и Зейделя итераций "
             "меньше оценки, так как начальная невязка сосредоточена у потолка; для SOR немного больше, так "
             "как при оптимальном τ оператор перехода не диагонализуем. Зейдель вдвое быстрее Якоби по итерациям, "
             f"SOR — в {num(gains['iterations_jacobi_to_sor'], 0)} раза. По времени выигрыш меньше: шаг Якоби — "
             "одна векторная операция над всем массивом, шаги Зейделя и SOR идут последовательно по 91 "
             "диагональной плоскости узлов. Число итераций от компьютера не зависит, время — зависит.")

    # 8. Проверка точности по сетке
    s = new_slide(prs, "Проверка точности по сетке")
    card(s, M, 1.4, 6.15, 4.55)
    text(s, M + 0.25, 1.55, 5.7, 0.5, "Добавка от нагрева T(A) − T(0)", size=19, bold=True)
    table(s, M + 0.25, 2.15, [["h, м", "Сетка", "Ошибка, °C", "Порядок"]] +
          [[num(row["h"], 2), row["grid"], num(row["max_error"], 4 if row["max_error"] < 0.1 else 3),
            num(row["order"], 2) if "order" in row else "—"] for row in inc],
          [0.85, 2.15, 1.45, 1.2], size=16, row_h=0.46)
    text(s, M + 0.25, 4.15, 5.7, 1.7, "Эталон — ряд Фурье, ошибка — максимум по всем узлам. Данные добавки "
                                      "гладкие и на рёбрах равны нулю.", size=16, color=INK_2)
    card(s, 6.95, 1.4, 5.78, 4.55)
    text(s, 7.2, 1.55, 5.3, 0.5, "Полное поле вдали от граней", size=19, bold=True)
    table(s, 7.2, 2.15, [["Сетки, h в м", "Разность, °C"],
                         ["0,2 и 0,1", num(full["max_diffs"][0], 3)],
                         ["0,1 и 0,05", num(full["max_diffs"][1], 4)],
                         ["Порядок", num(full["order"], 2)]], [2.75, 2.5], size=16, row_h=0.46)
    text(s, 7.2, 4.15, 5.3, 1.7, f"Разности вложенных сеток в {thousands(full['nodes'])} общих узлах, "
                                 f"удалённых от всех граней не меньше чем на {num(full['margin_m'], 1)} м. "
                                 "У рёбер данные разрывны: эта оценка к ним не относится.",
         size=16, color=INK_2)
    text(s, M, 6.15, W - 2 * M, 1.0, f"Наблюдаемый порядок {num(inc[1]['order'], 2)} и "
                                     f"{num(inc[2]['order'], 2)} соответствует второму порядку схемы. "
                                     f"Внутри комнаты {num(checks['interior_min'], 2)}…"
                                     f"{num(checks['interior_max'], 2)} °C — в пределах значений на границе.",
         size=17, bold=True)
    notes(s, "Полное поле имеет разрывы данных на рёбрах, поэтому сравнивать его с эталоном неудобно. "
             "Нагрев потолка обращается в нуль на его краю, поэтому добавку от нагрева — разность расчётов "
             "с нагревом и без него — можно сравнить с рядом Фурье, решением непрерывной задачи. При уменьшении "
             "шага вдвое ошибка уменьшается почти в четыре раза. Для полного поля эталона нет: сравниваем "
             "решения на вложенных сетках в общих узлах, далёких от граней. Это локальная оценка, а не порядок "
             "у рёбер. Кроме того, точное решение сеточной системы найдено разделением переменных и совпадает "
             "с прямым решением собранной матрицы.")

    # 9. Температура на горизонтальных срезах
    s = new_slide(prs, "Температура на горизонтальных срезах")
    panel(s, M, 1.4, 6.9, 5.55)
    picture(s, img_slices, M + 0.1, 1.5, 6.7, 5.35)
    text(s, 7.8, 1.42, 4.93, 0.5, f"Одно поле, A = {num(DEFAULT_PARAMS['amp'], 0)} °C, общая шкала "
                                  f"{num(scale[0], 0)}–{num(scale[1], 0)} °C", size=16, color=INK_2)
    table(s, 7.8, 1.95, [["Глубина", "T внутри, °C", "T(A) − T(0)"]] +
          [[f"{num(row['depth'], 1)} м", f"{num(row['interior_min'], 2)}–{num(row['interior_max'], 2)}",
            f"до {num(row['increment_max'], 2)} °C"] for row in slices],
          [1.3, 1.95, 1.68], size=16, row_h=0.46)
    text(s, 7.8, 4.45, 4.93, 2.5, [
        f"Слой на глубине 1,3 м: внутренние узлы {num(deep['interior_min'], 2)}–{num(deep['interior_max'], 2)} °C, "
        f"вместе с узлами на стенах {num(deep['layer_min'], 2)}–{num(deep['layer_max'], 2)} °C.",
        f"На глубине 1 м волновой узор почти погас, но нагрев потолка ещё добавляет до "
        f"{num(metre['increment_max'], 2)} °C."], size=16, color=INK_2, after=8)
    notes(s, "Четыре горизонтальных среза одного поля на общей шкале. Под потолком хорошо видны оба пятна "
             "и волновой узор. С глубиной пятна расплываются, а узор исчезает. Последний столбец таблицы — "
             "разность между полем с нагревом и полем без нагрева, то есть влияние потолка в целом. "
             "Голубая полоса слева на каждом срезе — холодная стена x = 0. На глубине 1,3 м максимум "
             f"{num(deep['interior_max'], 2)} °C немного выше температуры тёплой стены 24 °C: там ещё "
             "сказывается нагрев потолка.")

    # 10. Температура по высоте
    s = new_slide(prs, "Температура по высоте")
    xp, yp = view["profile"]
    panel(s, M, 1.4, 6.6, 4.75)
    picture(s, img_vslice, M + 0.1, 1.5, 6.4, 4.55)
    panel(s, 7.45, 1.4, 5.28, 4.75)
    picture(s, img_profile, 7.55, 1.5, 5.08, 4.55)
    text(s, M, 6.3, W - 2 * M, 0.9, f"Под точкой ({num(xp, 2)}; {num(yp, 2)}) м при A = "
                                    f"{num(DEFAULT_PARAMS['amp'], 0)} °C: на высоте {num(prof['z'], 2)} м — "
                                    f"{num(prof['T'], 1)} °C, у потолка — {num(prof['T_ceiling'], 1)} °C; "
                                    f"без нагрева на той же высоте — {num(prof['T_zero_amplitude'], 1)} °C.",
         size=17, bold=True)
    notes(s, f"Слева — вертикальный срез y = {num(view['pos'], 2)} м. Он проходит через центр первого пятна; "
             f"синяя линия — вертикаль над точкой ({num(xp, 2)}; {num(yp, 2)}) м, чёрная — высота "
             f"{num(prof['z'], 2)} м. Справа — температура вдоль этой вертикали. Сплошная кривая — с нагревом, "
             "пунктир — без нагрева, когда поле создают только стены и пол. Разница кривых быстро уменьшается "
             "к полу.")

    # 11. Затухание неоднородностей с глубиной
    s = new_slide(prs, "Затухание неоднородностей с глубиной")
    panel(s, M, 1.4, 7.7, 4.85)
    picture(s, img_decay, M + 0.1, 1.5, 7.5, 4.65)
    text(s, M, 6.4, 7.7, 0.8, f"Глубина, на которой остаётся 10 % амплитуды: волны — "
                              f"{num(wave['tenth']['depth'], 2)} м, пятно 2 — {num(spot2['tenth']['depth'], 2)} м, "
                              f"пятно 1 — {num(spot1['tenth']['depth'], 2)} м.", size=17, bold=True)
    text(s, 8.6, 1.45, 4.13, 5.6, [
        [("Компонента", {"bold": True, "color": INK})],
        "Вклад одного слагаемого формулы в T(A) − T(0); у волн — только колеблющаяся часть R.",
        [("Нормировка", {"bold": True, "color": INK})],
        f"Максимум |компоненты| на срезе делится на её собственный максимум на потолке: пятно 1 — "
        f"{num(spot1['ceiling_amplitude'], 1)} °C, пятно 2 — {num(spot2['ceiling_amplitude'], 1)} °C, "
        f"волны — {num(wave['ceiling_amplitude'], 1)} °C.",
        [("Пунктир", {"bold": True, "color": INK})],
        f"Оценка для одной гармоники с k = {num(decay['wave_k'], 2)} м⁻¹."],
         size=15, color=INK_2, after=6)
    notes(s, f"Каждая кривая — доля амплитуды своей компоненты, сетка {summary['grid']}, глубина 10 % найдена "
             "интерполяцией между слоями. Для одной гармоники затухание описывается отношением гиперболических "
             f"синусов и даёт 10 % на глубине {num(decay['wave_tenth_estimate'], 2)} м; волновая компонента "
             "близка к этой оценке. Пятна состоят из многих гармоник с малыми волновыми числами и проникают "
             "глубже.")

    # 12. Выводы
    s = new_slide(prs, "Выводы", dark=True)
    conclusions = [
        ("Температура с глубиной",
         f"Максимум внутри слоя падает с {num(top['interior_max'], 2)} °C на глубине 0,1 м до "
         f"{num(deep['interior_max'], 2)} °C на 1,3 м. В метре под потолком нагрев добавляет не больше "
         f"{num(metre['increment_max'], 2)} °C."),
        ("Мелкий узор гаснет быстрее пятен",
         f"Волны m = n = 2 теряют 90 % амплитуды за {num(wave['tenth']['depth'], 2)} м, пятна — за "
         f"{num(spot2['tenth']['depth'], 2)} и {num(spot1['tenth']['depth'], 2)} м."),
        ("Сравнение методов",
         f"SOR с τ = {num(sor['omega'], 3)} сходится за {sor['iterations']} итераций против "
         f"{sei['iterations']} у Зейделя и {jac['iterations']} у Якоби при пороге 10⁻⁸; по времени — "
         f"в {num(gains['time_jacobi_to_sor'], 1)} раза быстрее Якоби."),
    ]
    for n, (head, body) in enumerate(conclusions):
        y = 1.6 + n * 1.7
        text(s, M, y, W - 2 * M, 0.5, head, size=20, bold=True, color=ORANGE)
        text(s, M, y + 0.5, W - 2 * M, 1.1, body, size=21, color=LIGHT_ON_DARK)
    notes(s, "Нагрев потолка заметен в верхней части комнаты, а ниже метра поле определяют в основном стены. "
             "Чем мельче деталь нагрева, тем ближе к потолку она гаснет. Из трёх методов верхняя релаксация "
             "с оптимальным параметром требует на порядок меньше итераций.")

    prs.save(path)
    return len(prs.slides._sldIdLst)


# --- Экспорт PDF ------------------------------------------------------------

def export_pdf(pptx, pdf):
    """PDF из pptx в путь pdf: LibreOffice, иначе PowerPoint (Windows — pywin32, macOS — AppleScript).
    Если ни один способ недоступен или экспорт не удался — исключение."""
    soffice = (shutil.which("soffice") or shutil.which("libreoffice")
               or next((p for p in [r"C:\Program Files\LibreOffice\program\soffice.exe",
                                    "/Applications/LibreOffice.app/Contents/MacOS/soffice"]
                        if Path(p).exists()), None))
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf.parent), str(pptx)],
                       check=True, timeout=300)
        produced = pdf.parent / (pptx.stem + ".pdf")
        if produced != pdf and produced.exists():
            produced.replace(pdf)
        return "LibreOffice"
    if sys.platform == "win32":
        import win32com.client   # pip install pywin32
        app = win32com.client.Dispatch("PowerPoint.Application")
        deck = app.Presentations.Open(str(pptx.resolve()), WithWindow=False)
        try:
            deck.SaveAs(str(pdf.resolve()), 32)   # 32 — ppSaveAsPDF
        finally:
            deck.Close()
            app.Quit()
        return "PowerPoint"
    if sys.platform == "darwin" and Path("/Applications/Microsoft PowerPoint.app").exists():
        # PowerPoint на macOS работает в песочнице: файлы кладём в его контейнер.
        box = Path.home() / "Library/Containers/com.microsoft.Powerpoint/Data/Documents/pde-solver-export"
        box.mkdir(parents=True, exist_ok=True)
        src, dst = box / pptx.name, box / pdf.name
        try:
            dst.unlink(missing_ok=True)
            shutil.copy(pptx, src)
            script = (f'tell application "Microsoft PowerPoint"\n open POSIX file "{src}"\n delay 3\n'
                      f' save active presentation in POSIX file "{dst}" as save as PDF\n delay 2\n'
                      f' close active presentation saving no\nend tell')
            subprocess.run(["osascript", "-e", script], check=True, timeout=300)
            shutil.copy(dst, pdf)
        finally:
            shutil.rmtree(box, ignore_errors=True)
        return "PowerPoint"
    raise RuntimeError("нет LibreOffice и PowerPoint")


def pdf_pages(path):
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"{path.name} — не PDF")
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


def install(src, dst):
    """Заменить dst новым файлом атомарно: сначала копия рядом, затем переименование."""
    part = dst.with_name(dst.name + ".part")
    shutil.copy(src, part)
    os.replace(part, dst)


def main():
    global BUILD
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pde-slides-") as tmp:
        BUILD = Path(tmp)
        pptx, pdf = BUILD / f"{NAME}.pptx", BUILD / f"{NAME}.pdf"
        slides = build(pptx)
        print(f"PPTX собран: {slides} слайдов. Экспорт PDF…")
        try:
            tool = export_pdf(pptx, pdf)
            if not pdf.exists():
                raise RuntimeError("файл PDF не появился")
            pages = pdf_pages(pdf)
            if pages and pages != slides:
                raise RuntimeError(f"в PDF {pages} страниц, а слайдов {slides}")
        except Exception as error:   # сообщаем и не трогаем прежнюю пару PPTX + PDF
            keep = OUT / "build"
            keep.mkdir(exist_ok=True)
            shutil.copy(pptx, keep / pptx.name)
            print(f"Ошибка: PDF не создан ({error}).\n"
                  f"presentation/{NAME}.pptx и presentation/{NAME}.pdf не изменены. Новый PPTX — "
                  f"presentation/build/{pptx.name}: его можно сохранить как PDF вручную.", file=sys.stderr)
            sys.exit(1)
        install(pptx, OUT / pptx.name)
        install(pdf, OUT / pdf.name)
        print(f"Сохранено: presentation/{pptx.name} и presentation/{pdf.name} "
              f"({pages or '?'} страниц, экспорт — {tool}).")


if __name__ == "__main__":
    main()

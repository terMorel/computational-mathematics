"""Презентация для защиты: python make_slides.py → presentation/PDE-Solver.pptx и .pdf

Числа берутся из results.json (study.py), поля — из нового расчёта. Графики для
слайдов экспортируются с крупным шрифтом, формулы рендерит matplotlib (mathtext).

Сборка идёт во временной папке. PPTX и PDF в presentation/ заменяются только вместе
и только после успешного экспорта PDF; при ошибке скрипт завершается с кодом 1,
а прежняя пара файлов остаётся нетронутой.
"""

import json
from math import log, log10, sqrt
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
from matplotlib.patches import Patch, Rectangle
import numpy as np
import plotly.graph_objects as go
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

import theme
from figures import (DEFAULT_PARAMS, DEFAULT_VIEW, ceiling_from_params, ceiling_map_figure,
                     convergence_figure, depth_figure, fmt, hslice_figure, profile_compare_figure,
                     scale_for, slices_figure, vslice_figure)
from heat_room import DEFAULT_CEILING, Grid, solve

HERE = Path(__file__).parent
OUT = HERE / "presentation"
NAME = "PDE-Solver"
TITLE = "Стационарное распределение температуры в комнате"
RESULTS = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
BUILD = None

FONT = "Arial"
INK = RGBColor(0x0B, 0x0B, 0x0B)
INK_2 = RGBColor(0x52, 0x51, 0x4E)
MUTED = RGBColor(0x89, 0x87, 0x81)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PAPER = RGBColor(0xF7, 0xF5, 0xF0)
PANEL = RGBColor(0xFC, 0xFC, 0xFB)
RULE = RGBColor(0xE1, 0xE0, 0xD9)
HEAD = RGBColor(0xEE, 0xEA, 0xE3)
ZEBRA = RGBColor(0xF6, 0xF4, 0xEF)
TINT = RGBColor(0xFB, 0xE7, 0xD6)
TERRA = RGBColor(0xB0, 0x45, 0x26)
DARK = RGBColor(0x2E, 0x17, 0x20)
DARK_CARD = RGBColor(0x42, 0x28, 0x33)
LIGHT_ON_DARK = RGBColor(0xE8, 0xDF, 0xD6)
FOOT_ON_DARK = RGBColor(0xA8, 0x95, 0x9C)
ORANGE = RGBColor(0xF6, 0xA3, 0x52)

W, H = 13.333, 7.5
M = 0.6
TOP = 1.45


def nbsp(value):
    """Число не отрывается от единицы, «z = 1,6» — от знака, «4 × 3» — от знака умножения."""
    value = re.sub(r"([\d)]) (м⁻¹|м⁻²|м|°C|с|раз|итерац\w*|%|узл\w*)", "\\1\u00a0\\2", value)
    value = re.sub(r"\b([xyzAhkmnsωτρμΛpd]) = ", "\\1\u00a0=\u00a0", value)
    value = re.sub(r"(\b[ijks]|\}) ([−+]) 1\b", "\\1\u00a0\\2\u00a01", value)
    value = value.replace("} = ", "}\u00a0=\u00a0")
    value = re.sub(r"\((\d+,\d+); (\d+,\d+)\)", "(\\1;\u00a0\\2)", value)
    value = re.sub(r"(\d) (\d{3})\b", "\\1\u00a0\\2", value)
    for _ in range(2):
        value = re.sub(r"(\d) × (\d)", "\\1\u00a0×\u00a0\\2", value)
    value = re.sub(r" — (\d)", "\u00a0— \\1", value)
    value = value.replace("T(A) − T(0)", "T(A)\u00a0−\u00a0T(0)")
    value = re.sub(r"(?<![\w\u00a0])([вксуоаиВКСУОАИ]) ", "\\1\u00a0", value)
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


def formula(name, tex, size=26):
    """Формула в PNG. Все формулы рендерятся одним кеглем; на слайде их выравнивает same_scale."""
    path = BUILD / f"formula-{name}.png"
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, tex, fontsize=size, color="#0b0b0b")
    fig.savefig(path, dpi=220, transparent=True, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return path


def stencil_picture():
    """Семиточечный шаблон «крест»: узел (m, l, n) и шесть соседей."""
    path = BUILD / "stencil.png"
    fig, ax = plt.subplots(figsize=(5.4, 4.8), dpi=220)
    ax.set_aspect("equal")
    ax.axis("off")
    r, d = 1.55, (0.58, 0.4)
    nodes = {
        r"$m-1$": (-r, 0.0, -r - 0.36, 0.0, "right", "center"),
        r"$m+1$": (r, 0.0, r + 0.36, 0.0, "left", "center"),
        r"$l-1$": (-r * d[0], -r * d[1], -r * d[0] - 0.3, -r * d[1] - 0.2, "right", "top"),
        r"$l+1$": (r * d[0], r * d[1], r * d[0] + 0.3, r * d[1] + 0.2, "left", "bottom"),
        r"$n-1$": (0.0, -r, 0.36, -r, "left", "center"),
        r"$n+1$": (0.0, r, 0.36, r, "left", "center"),
    }
    for x, y, *_ in nodes.values():
        ax.plot([0, x], [0, y], color=theme.AXIS, lw=3.2, zorder=1, solid_capstyle="round")
    for label, (x, y, tx, ty, ha, va) in nodes.items():
        ax.scatter([x], [y], s=560, zorder=3, color="#dbe8f7", edgecolors=theme.ACCENT, linewidths=2.6)
        ax.text(tx, ty, label, fontsize=19, ha=ha, va=va, color=theme.INK)
    ax.scatter([0], [0], s=980, zorder=4, color=theme.SERIES[1], edgecolors="white", linewidths=3)
    ax.text(0.3, -0.36, r"$(m,\,l,\,n)$", fontsize=19, ha="left", va="top", color=theme.INK)
    ax.set_xlim(-2.75, 2.75)
    ax.set_ylim(-2.0, 2.0)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, transparent=True)
    plt.close(fig)
    return path


def matrix_picture(nx=3, ny=3, nz=4):
    """Портрет матрицы системы для маленькой сетки: L, D и U своими цветами."""
    path = BUILD / "matrix.png"
    n = nx * ny * nz
    colors = {"L": theme.SERIES[0], "D": theme.SERIES[1], "U": theme.SERIES[2]}

    def index(m, l, k):
        return (m * ny + l) * nz + k

    fig, ax = plt.subplots(figsize=(4.2, 4.6), dpi=220)
    ax.add_patch(Rectangle((0, 0), n, n, facecolor="white", edgecolor=theme.AXIS, lw=1.2))
    for m in range(nx):
        for l in range(ny):
            for k in range(nz):
                i = index(m, l, k)
                ax.add_patch(Rectangle((i + 0.1, i + 0.1), 0.8, 0.8, facecolor=colors["D"], edgecolor="none"))
                for dm, dl, dk in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                    mm, ll, kk = m + dm, l + dl, k + dk
                    if 0 <= mm < nx and 0 <= ll < ny and 0 <= kk < nz:
                        j = index(mm, ll, kk)
                        ax.add_patch(Rectangle((j + 0.1, i + 0.1), 0.8, 0.8, edgecolor="none",
                                               facecolor=colors["L" if j < i else "U"]))
    ax.set_xlim(-0.5, n + 0.5)
    ax.set_ylim(n + 0.5, -0.5)
    ax.set_aspect("equal")
    ax.axis("off")
    handles = [Patch(color=colors[p], label=f"${p}$") for p in "LDU"]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False,
              fontsize=20, handlelength=1.0, handleheight=1.0, columnspacing=1.6)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, transparent=True)
    plt.close(fig)
    return path


def tau_figure(r, grid):
    """Число итераций от параметра τ: расчёт и оценка ln ε⁻¹ / ln ρ⁻¹(τ)."""
    rho, opt, tol = grid.jacobi_radius(), grid.optimal_omega(), r["tolerance"]

    def rho_tau(t):
        if t <= opt:
            return ((t * rho + sqrt(max(t * t * rho * rho - 4 * (t - 1), 0.0))) / 2) ** 2
        return t - 1

    taus = np.unique(np.append(np.linspace(1.0, 1.98, 400), opt))
    estimate = [log(1 / tol) / log(1 / rho_tau(t)) for t in taus]
    _, sei, sor = r["methods"]
    points = sorted([(1.0, sei["iterations"]), (sor["omega"], sor["iterations"])]
                    + [(x["omega"], x["iterations"]) for x in r["omega_scan"]])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=taus, y=estimate, mode="lines", name="оценка по ρ(τ)",
                             line=dict(color=theme.MUTED, width=2, dash="dash")))
    fig.add_trace(go.Scatter(x=[p[0] for p in points], y=[p[1] for p in points], mode="lines+markers",
                             name="расчёт", line=dict(color=theme.ACCENT, width=2.5),
                             marker=dict(size=10, color=theme.ACCENT, line=dict(color="white", width=2))))
    fig.add_trace(go.Scatter(x=[sor["omega"]], y=[sor["iterations"]], mode="markers", showlegend=False,
                             marker=dict(size=15, color=theme.SERIES[1], line=dict(color="white", width=2.5))))
    fig.add_annotation(x=sor["omega"], y=log10(sor["iterations"]), yanchor="top", yshift=-14, showarrow=False,
                       text=f"τ<sub>opt</sub> = {fmt(sor['omega'], 3)}: <b>{sor['iterations']}</b>",
                       font=dict(size=15, color=theme.INK))
    fig.add_annotation(x=1.0, y=log10(sei["iterations"]), xanchor="left", yanchor="top", xshift=8, yshift=-6,
                       showarrow=False, text=f"τ = 1, Зейдель: <b>{sei['iterations']}</b>",
                       font=dict(size=15, color=theme.INK))
    fig.update_layout(**theme.base_layout(
        legend=dict(x=0.98, y=0.98, xanchor="right", yanchor="top", font=dict(size=15),
                    bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=78, r=24, t=16, b=60)))
    fig.update_xaxes(**theme.axis("параметр релаксации τ", range=[0.96, 2.0], dtick=0.2))
    ticks = [100, 200, 500, 1000, 2000]
    fig.update_yaxes(**theme.axis("число итераций", type="log", tickvals=ticks,
                                  ticktext=[thousands(t) for t in ticks], range=[log10(60), log10(2600)]))
    return fig


def order_figure(inc, full):
    """Ошибка добавки и разность полного поля по шагу сетки, обе оси логарифмические."""
    h = [row["h"] for row in inc]
    err = [row["max_error"] for row in inc]
    c = 0.55 * err[1] / h[1] ** 2
    ref = [0.045, 0.22]
    marker = dict(size=10, line=dict(color="white", width=2))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=h, y=err, mode="lines+markers", name="добавка: ошибка к ряду Фурье",
                             line=dict(color=theme.ACCENT, width=2.5), marker={**marker, "color": theme.ACCENT}))
    fig.add_trace(go.Scatter(x=full["steps"][1:], y=full["max_diffs"], mode="lines+markers",
                             name="полное поле: разность сеток h и 2h",
                             line=dict(color=theme.SERIES[1], width=2.5),
                             marker={**marker, "color": theme.SERIES[1]}))
    fig.add_trace(go.Scatter(x=ref, y=[c * v * v for v in ref], mode="lines", name="наклон 2: C·h²",
                             line=dict(color=theme.MUTED, width=2, dash="dash")))
    fig.update_layout(**theme.base_layout(
        legend=dict(x=0.02, y=0.98, xanchor="left", yanchor="top", font=dict(size=15), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=78, r=24, t=16, b=60)))
    xt = [0.05, 0.1, 0.2]
    fig.update_xaxes(**theme.axis("шаг сетки h, м", type="log", tickvals=xt, ticktext=[fmt(t, 2) for t in xt],
                                  range=[log10(0.04), log10(0.25)]))
    yt = [0.005, 0.01, 0.03, 0.1, 0.3]
    fig.update_yaxes(**theme.axis("максимум по узлам, °C", type="log", tickvals=yt,
                                  ticktext=[fmt(t, 3).rstrip("0").rstrip(",") for t in yt],
                                  range=[log10(0.004), log10(0.8)]))
    return fig


# --- Примитивы слайда ---------------------------------------------------------

def background(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


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


def pieces(para):
    """Абзац — строка (куски между ** выделяются жирным) или список (текст, {опции})."""
    if isinstance(para, str):
        return [(part, {"bold": True} if k % 2 else {}) for k, part in enumerate(para.split("**")) if part]
    return para


def fill(p, para, size, color, bold, tracking=None):
    for part, opts in pieces(para):
        for piece, shift in scripts(nbsp(part)):
            r = p.add_run()
            r.text = piece
            r.font.name = FONT
            r.font.size = Pt(opts.get("size", size))
            r.font.bold = opts.get("bold", bold)
            r.font.color.rgb = opts.get("color", color)
            if shift:
                r.font._element.set("baseline", shift)
            if tracking:
                r.font._element.set("spc", str(tracking))


def text(slide, x, y, w, h, runs, size=18, color=INK, bold=False, anchor=MSO_ANCHOR.TOP,
         spacing=1.1, after=0, name=None, align=None, tracking=None):
    """runs: строка или список абзацев."""
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
        if align:
            p.alignment = align
        fill(p, para, size, color, bold, tracking)
    return box


def card(slide, x, y, w, h, color=PANEL, line=RULE):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.adjustments[0] = min(0.12 / min(w, h), 0.5)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(0.75)
    shape.shadow.inherit = False
    return shape


def takeaway(slide, x, y, w, h, value, size=16):
    """Короткий вывод под графиком или таблицей: плашка, ключевые числа выделены жирным."""
    card(slide, x, y, w, h, color=TINT, line=None)
    text(slide, x + 0.25, y, w - 0.5, h, value, size=size, color=INK, anchor=MSO_ANCHOR.MIDDLE)


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


def badge(slide, x, y, value, d=0.34):
    dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    dot.fill.solid()
    dot.fill.fore_color.rgb = TERRA
    dot.line.fill.background()
    dot.shadow.inherit = False
    tf = dot.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    fill(p, str(value), 13, WHITE, True)


def steps(slide, x, y, w, items, gap=0.18, size=15):
    """Цепочка вывода: номер шага, подпись, под ней формулы; номера соединены линией.

    items — (подпись, [(формула, высота), …], строк подписи). Все формулы цепочки
    в одном масштабе. Возвращает нижний край последнего шага."""
    boxes, tops = [], []
    cy = y
    for label, formulas, lines in items:
        tops.append(cy)
        label_h = 0.3 * lines
        text(slide, x + 0.55, cy + 0.02, w - 0.55, label_h, label, size=size, color=INK_2)
        cy += label_h + 0.06
        for path, fh in formulas:
            boxes.append((path, x + 0.55, cy, w - 0.55, fh))
            cy += fh + 0.04
        cy += gap
    if len(tops) > 1:
        line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x + 0.17), Inches(tops[0] + 0.17),
                                          Inches(x + 0.17), Inches(tops[-1] + 0.17))
        line.line.color.rgb = RULE
        line.line.width = Pt(2)
    for k, top in enumerate(tops, start=1):
        badge(slide, x, top, k)
    if boxes:
        same_scale(slide, boxes)
    return cy - gap


def table(slide, x, y, rows, widths, size=16, row_h=0.46, align=None):
    """Таблица в светлом стиле: шапка на сером, строки через одну. align — 'l'/'r' по столбцам."""
    align = align or ["l"] + ["r"] * (len(widths) - 1)
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
            cell.fill.fore_color.rgb = HEAD if i == 0 else (PANEL if i % 2 else ZEBRA)
            cell.margin_left = cell.margin_right = Inches(0.12)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if align[j] == "l" else PP_ALIGN.RIGHT
            fill(p, str(value), size - (1 if i == 0 else 0), INK_2 if i == 0 else INK, i == 0)
    return tbl


def notes(slide, value):
    slide.notes_slide.notes_text_frame.text = nbsp(value)


def new_slide(prs, heading, section=None, dark=False):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, DARK if dark else PAPER)
    if section:
        text(s, M, 0.4, 9.0, 0.25, section.upper(), size=12, bold=True, color=ORANGE if dark else TERRA,
             tracking=150)
    text(s, M, 0.66, W - 2 * M, 0.6, heading, size=28, bold=True, color=WHITE if dark else INK, name="Title")
    return s


def footers(prs):
    """Колонтитул: название работы и номер слайда; на титуле не ставится."""
    total = len(prs.slides._sldIdLst)
    for k, s in enumerate(prs.slides, start=1):
        if k == 1:
            continue
        color = FOOT_ON_DARK if s.background.fill.fore_color.rgb == DARK else MUTED
        text(s, M, 7.08, 8.0, 0.25, TITLE, size=10, color=color)
        text(s, W - M - 1.5, 7.08, 1.5, 0.25, f"{k} / {total}", size=10, color=color, align=PP_ALIGN.RIGHT)


# --- Слайды -----------------------------------------------------------------

def timing_conditions(timing):
    where = f" ({timing['cpu']})" if timing.get("cpu") else ""
    return f"Время — медиана {timing['repeats']} запусков на одном компьютере{where}."


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
    amp = num(DEFAULT_PARAMS["amp"], 0)

    print("Поля и рисунки для слайдов…")
    grid = Grid.with_step(0.1)
    base = solve(grid, ceiling_from_params(DEFAULT_PARAMS), tol=1e-10)
    flat = solve(grid, ceiling_from_params({**DEFAULT_PARAMS, "amp": 0.0}), tol=1e-10)
    scale = scale_for(DEFAULT_PARAMS)
    view = DEFAULT_VIEW
    l_min, l_max = grid.spectrum_bounds()

    cover = untitled(hslice_figure(base.T, grid, view, scale), top=14)
    cover.data = cover.data[:1]
    img_cover = export(cover, "cover.png", 640, 480, 1.3)
    from make_figures import scheme_figure
    img_scheme = export(scheme_figure(DEFAULT_PARAMS, scale, short=True), "scheme.png", 820, 600, 1.25)
    ceiling = untitled(ceiling_map_figure(DEFAULT_PARAMS, 0, view, scale), top=14)
    ceiling.data = [ceiling.data[0]] + list(ceiling.data[3:])
    img_ceiling = export(ceiling, "ceiling.png", 600, 440, 1.3)
    img_stencil = stencil_picture()
    img_matrix = matrix_picture()
    img_tau = export(tau_figure(r, grid), "tau.png", 600, 520, 1.3)
    solutions = [solve(grid, method=m, tol=r["tolerance"]) for m in ("jacobi", "seidel", "sor")]
    conv = untitled(convergence_figure(solutions, r["tolerance"]), top=60)
    conv.layout.annotations = [a for a in conv.layout.annotations if "<b>" not in a.text]
    conv.update_yaxes(title_text="относительная невязка")
    for trace in conv.data:
        trace.name = trace.name.replace("ω", "τ")
    img_conv = export(conv, "convergence.png", 700, 450, 1.3)
    img_order = export(order_figure(inc, full), "order.png", 600, 540, 1.3)
    heights = [row["z"] for row in slices]
    img_slices = export(slices_figure(base.T, grid, heights, scale, cols=2), "slices.png", 700, 600, 1.3)
    img_vslice = export(vslice_figure(base.T, grid, view, scale), "vslice.png", 600, 420, 1.3)
    img_profile = export(profile_compare_figure(base.T, flat.T, grid, view["profile"], view["z"], scale,
                                                DEFAULT_PARAMS["amp"]), "profile.png", 520, 500, 1.3)
    from study import depth_decay
    depths, curves, summary = depth_decay(Grid.with_step(0.05))
    img_decay = export(untitled(depth_figure(depths, curves, summary), top=20), "depth.png", 760, 470, 1.3)

    F = {name: formula(name, tex) for name, tex in {
        "fourier": r"$\mathbf{q} = -\kappa\,\nabla T$",
        "balance": r"$c\rho\,\dfrac{\partial T}{\partial t} = -\mathrm{div}\,\mathbf{q} = \kappa\,\Delta T$",
        "laplace": r"$\Delta T = \dfrac{\partial^2 T}{\partial x^2} + \dfrac{\partial^2 T}{\partial y^2}"
                   r" + \dfrac{\partial^2 T}{\partial z^2} = 0$",
        "dirichlet": r"$T\,|_{\Gamma} = \varphi$",
        "ceiling": r"$\varphi_6(x, y) = 20 + A\,\sin^2(\pi u)\,\sin^2(\pi v)\,"
                   r"\left(0{,}12 + 0{,}65\,G_1 + 0{,}30\,G_2 + 0{,}15\,R\right)$",
        "gauss": r"$G_j = \exp\left(-\dfrac{1}{2}\left[\left(\dfrac{u - u_j}{\sigma_{xj}}\right)^2"
                 r" + \left(\dfrac{v - v_j}{\sigma_{yj}}\right)^2\right]\right)$",
        "wave": r"$R = \dfrac{1}{2}\,(1 + \sin 2\pi m u\;\cos 2\pi n v),\qquad m = n = %d$" % DEFAULT_PARAMS["m"],
        "uv": r"$u = x / L_x,\qquad v = y / L_y,\qquad A = %s\,^{\circ}\mathrm{C}$" % amp,
        "cap": r"$\sin^2(\pi u)\,\sin^2(\pi v)$",
        "taylor": r"$T(x \pm h) = T \pm h\,T' + \dfrac{h^2}{2}\,T'' \pm \dfrac{h^3}{6}\,T''' + \dfrac{h^4}{24}\,T^{(4)}"
                  r" + \ldots$",
        "second": r"$\Lambda_1 T = \dfrac{T(x+h) - 2\,T(x) + T(x-h)}{h^2} = T'' + \dfrac{h^2}{12}\,T^{(4)} + O(h^4)$",
        "scheme": r"$\Lambda_1 T_{mln} + \Lambda_2 T_{mln} + \Lambda_3 T_{mln} = 0\ \ \mathrm{в}\ D_h,"
                  r"\qquad T_{mln} = \varphi\ \ \mathrm{на}\ \Gamma_h$",
        "mean": r"$T_{mln} = \dfrac{1}{6}\,(T_{m-1,l,n} + T_{m+1,l,n} + T_{m,l-1,n} + T_{m,l+1,n}"
                r" + T_{m,l,n-1} + T_{m,l,n+1})$",
        "maxp": r"$\min_{\Gamma_h}\varphi \;\leq\; T_{mln} \;\leq\; \max_{\Gamma_h}\varphi$",
        "stab": r"$\Vert T \Vert_C \;\leq\; \max_{\Gamma_h} |\varphi|$",
        "eigf": r"$v_{mln} = \sin\dfrac{p\pi m}{M_x}\,\sin\dfrac{q\pi l}{M_y}\,\sin\dfrac{r\pi n}{M_z}$",
        "eig": r"$\lambda_{pqr} = \dfrac{4}{h^2}\left(\sin^2\dfrac{p\pi}{2M_x} + \sin^2\dfrac{q\pi}{2M_y}"
               r" + \sin^2\dfrac{r\pi}{2M_z}\right)$",
        "jacobi-m": r"$D\,T^{(i+1)} = f - (L + U)\,T^{(i)}$",
        "jacobi": r"$T^{(i+1)}_{mln} = \dfrac{1}{6}\left(\Sigma^- T^{(i)} + \Sigma^+ T^{(i)}\right)$",
        "seidel-m": r"$(D + L)\,T^{(i+1)} = f - U\,T^{(i)}$",
        "seidel": r"$T^{(i+1)}_{mln} = \dfrac{1}{6}\left(\Sigma^- T^{(i+1)} + \Sigma^+ T^{(i)}\right)$",
        "sor-m": r"$(D + \tau L)\,T^{(i+1)} = \tau f - \left(\tau U + (\tau - 1)\,D\right) T^{(i)}$",
        "sor": r"$T^{(i+1)}_{mln} = (1 - \tau)\,T^{(i)}_{mln} + \dfrac{\tau}{6}\left(\Sigma^- T^{(i+1)}"
               r" + \Sigma^+ T^{(i)}\right)$",
        "err": r"$e^{(i+1)} = B\,e^{(i)} \quad\Rightarrow\quad \Vert e^{(i)} \Vert \approx \rho(B)^{\,i}\,"
               r"\Vert e^{(0)} \Vert$",
        "N": r"$N(\varepsilon) \approx \dfrac{\ln \varepsilon^{-1}}{\ln \rho^{-1}}$",
        "rho": r"$\rho_J = 1 - \dfrac{h^2 \lambda_{\min}}{6},\qquad \rho_S = \rho_J^{\,2},"
               r"\qquad \rho_\tau = \tau_{\mathrm{opt}} - 1$",
        "topt": r"$\tau_{\mathrm{opt}} = \dfrac{2}{1 + \sqrt{1 - \rho_J^{\,2}}}$",
        "increment": r"$\Delta U = 0,\qquad U\,|_{z = L_z} = \varphi_6 - 20$",
        "series": r"$U = \sum_{p,\,q} c_{pq}\,\sin\dfrac{p\pi x}{L_x}\,\sin\dfrac{q\pi y}{L_y}\;"
                  r"\dfrac{\sinh k_{pq} z}{\sinh k_{pq} L_z}$",
        "kpq": r"$k_{pq} = \pi\sqrt{(p/L_x)^2 + (q/L_y)^2}$",
        "order": r"$e_h \approx C h^{\,p} \quad\Rightarrow\quad p = \log_2 \dfrac{e_{2h}}{e_h}$",
        "mode": r"$\dfrac{\sinh k z}{\sinh k L_z} \approx e^{-k d},\qquad k = \sqrt{\alpha^2 + \beta^2}$",
        "kwave": r"$k = 2\pi\sqrt{(m/L_x)^2 + (n/L_y)^2} = %s\ \mathrm{м}^{-1}$" % fmt(decay["wave_k"], 2).replace(",", "{,}"),
    }.items()}

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
    text(s, M, 1.0, 5.9, 0.4, "ВЫЧИСЛИТЕЛЬНАЯ МАТЕМАТИКА", size=13, bold=True, color=ORANGE, tracking=200)
    text(s, M, 1.5, 5.9, 2.6, TITLE, size=40, bold=True, color=WHITE, spacing=1.0, name="Title")
    text(s, M, 4.3, 5.6, 1.6, "Задача Дирихле для уравнения Лапласа: разностная схема «крест» и итерационные "
                              "методы Якоби, Зейделя и верхней релаксации.", size=18, color=LIGHT_ON_DARK)
    card(s, 6.75, 1.0, 6.0, 5.05, line=None)
    picture(s, img_cover, 6.85, 1.1, 5.8, 4.85)
    text(s, 6.75, 6.2, 6.0, 0.5, f"Рассчитанное поле на высоте {num(view['z'], 2)} м, A = {amp} °C",
         size=14, color=LIGHT_ON_DARK)
    notes(s, "Тема работы — стационарное распределение температуры в комнате. Стены и пол держат постоянную "
             "температуру, потолок нагрет неравномерно. Справа — то, что получилось в итоге: горизонтальный срез "
             "рассчитанного поля в 30 сантиметрах под потолком. Расскажу, откуда берётся уравнение, как оно "
             "заменяется разностной схемой, от чего зависит скорость итерационных методов, как "
             "проверялась точность и что показал расчёт.")

    # 2. Уравнение Лапласа и задача Дирихле
    s = new_slide(prs, "Уравнение Лапласа и задача Дирихле", "1 · Постановка")
    card(s, M, TOP, 5.7, 5.45)
    picture(s, img_scheme, M + 0.1, TOP + 0.1, 5.5, 5.25)
    X = 6.75
    bottom = steps(s, X, TOP, W - M - X, [
        ("Закон Фурье: тепло течёт от тёплого к холодному", [(F["fourier"], 0.42)], 1),
        ("Баланс энергии в малом объёме", [(F["balance"], 0.66)], 1),
        ("Стационарный режим без источников в D", [(F["laplace"], 0.66)], 1),
        ("На границе Γ задана температура — задача Дирихле", [(F["dirichlet"], 0.42)], 1),
    ])
    text(s, X, bottom + 0.25, W - M - X, 6.9 - bottom - 0.25,
         "D — комната 4 × 3 × 2,6 м. Стены и пол — постоянные φ₁…φ₅ (на рисунке), потолок — функция φ₆(x, y). "
         "На рёбрах пределы соседних граней различаются, поэтому ищем ограниченное решение.",
         size=15, color=INK_2)
    notes(s, "Откуда уравнение. По закону Фурье поток тепла направлен против градиента температуры. Баланс "
             "энергии в малом объёме даёт уравнение теплопроводности: скорость нагрева пропорциональна лапласиану. "
             "Если режим установился и источников нет, производная по времени равна нулю, остаётся уравнение "
             "Лапласа. Чтобы решение было единственным, на всей границе задаём температуру — это краевые условия "
             "первого рода, задача Дирихле. Пять граней держат постоянные температуры, они подписаны на рисунке; "
             "потолок задан функцией. На рёбрах значения соседних граней разные, но внутри решение гладкое "
             "и ограниченное.")

    # 3. Температура потолка
    s = new_slide(prs, "Температура потолка φ₆(x, y)", "1 · Постановка")
    picture(s, F["ceiling"], M, TOP, W - 2 * M, 0.72, align="left")
    card(s, M, 2.4, 6.0, 4.5)
    picture(s, img_ceiling, M + 0.1, 2.5, 5.8, 4.3)
    X = 6.95
    RW = W - M - X
    same_scale(s, [(F["uv"], X, 2.4, RW, 0.4), (F["cap"], X, 3.22, RW, 0.46),
                   (F["gauss"], X, 4.34, RW, 0.64), (F["wave"], X, 5.38, RW, 0.5)])
    for y, h, caption in ((2.84, 0.28, "Координаты на потолке от 0 до 1 и сила нагрева."),
                          (3.72, 0.52, "«Колпак»: обнуляет нагрев на краю, и потолок непрерывно переходит "
                                       "в фон 20 °C, как у пола."),
                          (5.0, 0.28, "Два гауссовых пятна — крупный масштаб."),
                          (5.9, 0.28, "Волновой узор — мелкий масштаб.")):
        text(s, X, y, RW, h, caption, size=15, color=INK_2)
    text(s, X, 6.3, RW, 0.6, "Разные масштабы взяты специально: видно, как быстро крупные и мелкие "
                             "детали гаснут вглубь.", size=14, color=INK_2)
    x1, y1 = DEFAULT_PARAMS["spots"][0][:2]
    x2, y2 = DEFAULT_PARAMS["spots"][1][:2]
    sx1, sy1 = DEFAULT_CEILING.spots[0].sx, DEFAULT_CEILING.spots[0].sy
    sx2, sy2 = DEFAULT_CEILING.spots[1].sx, DEFAULT_CEILING.spots[1].sy
    notes(s, "Потолок — фон 20 °C плюс нагрев. Нагрев умножен на квадраты синусов: этот «колпак» равен нулю "
             "на краю потолка, поэтому потолок плавно переходит к температуре фона. Внутри колпака — постоянная "
             f"часть, два гауссовых пятна с центрами ({num(x1, 2)}; {num(y1, 2)}) и ({num(x2, 2)}; {num(y2, 2)}) м "
             f"и шириной {num(sx1, 2)}–{num(sy2, 2)} в долях размера потолка, и волновой узор. Пятна — крупный "
             "масштаб, волны — мелкий; дальше увидим, что мелкие детали гаснут гораздо ближе к потолку. "
             f"Максимум потолка — {num(checks['boundary_max'], 1)} °C.")

    # 4. Разностная схема «крест»
    s = new_slide(prs, "Разностная схема «крест»", "2 · Разностная схема")
    card(s, M, TOP, 3.95, 3.6)
    picture(s, img_stencil, M + 0.15, TOP + 0.15, 3.65, 3.3)
    text(s, M, 5.25, 3.95, 1.65, [f"**h = 0,1 м** — шаг по x, y и z",
                                  f"**{g['nx'] + 1} × {g['ny'] + 1} × {g['nz'] + 1} = {thousands(nodes)}** узлов",
                                  f"**{thousands(g['unknowns'])}** неизвестных во внутренних узлах D_{{h}}"],
         size=15, color=INK_2, after=6)
    X = 4.95
    bottom = steps(s, X, TOP, W - M - X, [
        ("Ряд Тейлора в соседних узлах", [(F["taylor"], 0.58)], 1),
        ("Складываем два ряда: нечётные члены сокращаются, ошибка — O(h²)", [(F["second"], 0.7)], 1),
        ("Так по каждой оси — разностная задача на сетке", [(F["scheme"], 0.42)], 1),
        ("При равных шагах — значение в узле равно среднему шести соседей", [(F["mean"], 0.62)], 1),
    ])
    text(s, X + 0.55, bottom + 0.2, W - M - X - 0.55, 6.9 - bottom - 0.2,
         "Это разностный аналог теоремы о среднем для гармонических функций. Узлы рёбер и вершин получают "
         "среднее пределов соседних граней и в уравнения не входят.", size=14, color=INK_2)
    notes(s, "Как получается схема. Раскладываем температуру в соседних узлах в ряд Тейлора. Если сложить "
             "разложения вперёд и назад, нечётные степени сокращаются, и вторая разность приближает вторую "
             "производную с ошибкой порядка h квадрат. Делаем так по трём осям и получаем семиточечный шаблон "
             f"«крест». Шаг 10 сантиметров, неизвестных {thousands(g['unknowns'])}, на гранях значения известны из "
             "краевых условий. При равных шагах из уравнения следует, что значение в узле — среднее шести соседей: "
             "это сеточный аналог теоремы о среднем для гармонических функций. Узлы рёбер соседями внутренних "
             "узлов не бывают, поэтому правило средних на них на решение не влияет.")

    # 5. Свойства разностной задачи
    s = new_slide(prs, "Принцип максимума и спектр", "2 · Разностная схема")
    CW = (W - 2 * M - 0.3) / 2
    A, B = M, M + CW + 0.3
    for x0, head in ((A, "Принцип максимума"), (B, "Спектр оператора Λ")):
        card(s, x0, TOP, CW, 5.45)
        text(s, x0 + 0.35, TOP + 0.3, CW - 0.7, 0.4, head, size=19, bold=True)
    IW = CW - 0.7
    text(s, A + 0.35, 2.25, IW, 0.62, "Значение во внутреннем узле — среднее соседей, поэтому строгого "
                                       "максимума внутри нет:", size=15, color=INK_2)
    text(s, A + 0.35, 3.62, IW, 0.62, "**Единственность.** При φ = 0 решение только нулевое: система "
                                       "однозначно разрешима.", size=15, color=INK_2)
    text(s, A + 0.35, 4.38, IW, 0.32, "**Устойчивость.** Решение ограничено данными:", size=15, color=INK_2)
    text(s, A + 0.35, 5.6, IW, 0.95, f"В расчёте: внутри {num(checks['interior_min'], 2)}…"
                                      f"{num(checks['interior_max'], 2)} °C, на границе "
                                      f"{num(checks['boundary_min'], 0)}…{num(checks['boundary_max'], 2)} °C.",
         size=14, color=INK_2)
    text(s, B + 0.35, 2.25, IW, 0.62, "Разделение переменных: собственные функции — произведения синусов,",
         size=15, color=INK_2)
    text(s, B + 0.35, 3.62, IW, 0.32, "собственные числа:", size=15, color=INK_2)
    text(s, B + 0.35, 4.95, IW, 1.6, f"λ_{{min}} = {num(l_min, 2)} м⁻², λ_{{max}} = {num(l_max, 1)} м⁻²: число "
                                     f"обусловленности μ ≈ {l_max / l_min:.0f}. Скорость простых итераций "
                                     "определяет λ_{min} — гладкая ошибка гаснет медленнее всего.",
         size=14, color=INK_2)
    same_scale(s, [(F["maxp"], A + 0.35, 2.92, IW, 0.62), (F["stab"], A + 0.35, 4.78, IW, 0.62),
                   (F["eigf"], B + 0.35, 2.92, IW, 0.62), (F["eig"], B + 0.35, 4.0, IW, 0.78)])
    notes(s, "Два свойства разностной задачи. Первое — принцип максимума: раз значение в узле равно среднему "
             "соседей, внутри не может быть строгого максимума или минимума, они достигаются на границе. Отсюда "
             "однородная задача имеет только нулевое решение, значит система однозначно разрешима, и решение "
             "непрерывно зависит от граничных данных — это устойчивость. Наш расчёт этому удовлетворяет. "
             "Второе — спектр. Разделение переменных показывает, что собственные функции — произведения синусов, "
             "а собственные числа выписываются явно. Отношение крайних чисел около 380: система плохо обусловлена, "
             "и от наименьшего собственного числа зависит скорость итераций — это пригодится дальше.")

    # 6. Методы
    s = new_slide(prs, "Методы Якоби, Зейделя и верхней релаксации", "3 · Итерационные методы")
    card(s, M, TOP, 3.55, 3.85)
    picture(s, img_matrix, M + 0.2, TOP + 0.15, 3.15, 3.55)
    text(s, M, 5.45, 3.55, 1.45, ["**A = L + D + U** — нижняя треугольная, диагональная и верхняя треугольная "
                                  "части матрицы системы AT = f.",
                                  "Σ⁻T, Σ⁺T — суммы трёх соседей с меньшими и большими индексами."],
         size=13, color=INK_2, after=4)
    X = 4.45
    RW = W - M - X
    rows = [("Якоби", "все соседи с прошлой итерации", "jacobi"),
            ("Зейдель", "соседи m − 1, l − 1, n − 1 уже пересчитаны", "seidel"),
            ("Верхняя релаксация", "шаг Зейделя, умноженный на τ", "sor")]
    boxes = []
    for k, (name, idea, key) in enumerate(rows):
        y = TOP + k * 1.65
        card(s, X, y, RW, 1.5)
        text(s, X + 0.3, y + 0.14, RW - 0.6, 0.32, [[(name, {"bold": True, "color": INK}),
                                                    (f" — {idea}", {})]], size=16, color=INK_2)
        boxes += [(F[f"{key}-m"], X + 0.3, y + 0.52, RW - 0.6, 0.4), (F[key], X + 0.3, y + 0.94, RW - 0.6, 0.5)]
    same_scale(s, boxes)
    text(s, X, 6.42, RW, 0.5, "τ = 1 — метод Зейделя, 1 < τ < 2 — верхняя релаксация. Узлы обходятся "
                              "по возрастанию m, l, n.", size=14, color=INK_2)
    notes(s, "Откуда берутся методы. Матрицу системы раскладываем на три части: нижнюю треугольную L, диагональ D "
             "и верхнюю треугольную U — на рисунке портрет такой матрицы для маленькой сетки. Если оставить слева "
             "только диагональ, получится метод Якоби: все соседи берутся с прошлой итерации. Если оставить "
             "слева нижний треугольник с диагональю, получится метод Зейделя: при обходе по порядку соседи "
             "с меньшими индексами уже пересчитаны. Верхняя релаксация берёт шаг Зейделя и удлиняет его в τ раз; "
             "при τ = 1 это Зейдель. Нижняя строка каждой карточки — та же формула, записанная для одного узла; "
             "так она и запрограммирована.")

    # 7. Сходимость и выбор τ
    s = new_slide(prs, "Скорость сходимости и выбор τ", "3 · Итерационные методы")
    LW = 6.05
    steps(s, M, TOP, LW, [
        ("Ошибка e^{(i)} = T^{(i)} − T умножается на матрицу перехода B", [(F["err"], 0.45)], 1),
        ("Отсюда число итераций до точности ε", [(F["N"], 0.66)], 1),
        ("Спектральные радиусы — из спектра оператора Λ", [(F["rho"], 0.56)], 1),
        ("Оптимальный параметр верхней релаксации", [(F["topt"], 0.7)], 1),
    ], gap=0.12)
    takeaway(s, M, 6.0, LW, 0.9,f"ρ_{{J}} = {num(g['jacobi_radius'], 4)} → τ_{{opt}} = {num(sor['omega'], 3)}, "
                                  f"ρ_{{τ}} = {num(sor['omega'] - 1, 3)}: оценка **{sor['predicted']}** итераций "
                                  f"вместо {sei['predicted']} у Зейделя.", size=15)
    card(s, 6.95, TOP, W - M - 6.95, 4.75)
    picture(s, img_tau, 7.05, TOP + 0.1, W - M - 7.15, 4.55)
    text(s, 6.95, 6.32, W - M - 6.95, 0.6, "Точки — расчёт с порогом 10⁻⁸, пунктир — оценка N(ε) с ρ(τ). "
                                           "Минимум — у τ_{opt}, правее оценка почти точна.", size=13, color=INK_2)
    notes(s, "Скорость сходимости определяет спектральный радиус. Ошибка на каждой итерации умножается на матрицу "
             "перехода, поэтому после i шагов она уменьшается примерно как спектральный радиус в степени i. "
             "Отсюда число итераций — логарифм требуемой точности, делённый на логарифм обратного радиуса. "
             "Радиус метода Якоби выражается через наименьшее собственное число оператора, у Зейделя он равен "
             "его квадрату — поэтому итераций вдвое меньше. Для верхней релаксации есть оптимальный параметр: "
             f"при нём радиус равен τ − 1. У нас это τ = {num(sor['omega'], 3)}. Справа проверка: число итераций "
             "при разных τ. Минимум там, где предсказывает теория; правее оптимума оценка почти совпадает "
             "с расчётом, левее расчёт сходится быстрее оценки, потому что начальная ошибка сосредоточена "
             "у потолка, а не в самой медленной гармонике.")

    # 8. Сравнение итерационных методов
    s = new_slide(prs, "Сравнение итерационных методов", "3 · Итерационные методы")
    card(s, M, TOP, 7.4, 4.55)
    picture(s, img_conv, M + 0.1, TOP + 0.1, 7.2, 4.35)
    takeaway(s, M, 6.12, 7.4, 0.78, f"Зейдель вдвое быстрее Якоби (ρ² вместо ρ), верхняя релаксация — "
                                     f"в **{num(gains['iterations_jacobi_to_sor'], 0)}** раза по числу итераций.")
    X = 8.3
    RW = W - M - X
    table(s, X, TOP, [["Метод", "Оценка", "Расчёт"],
                      ["Якоби", jac["predicted"], jac["iterations"]],
                      ["Зейдель", sei["predicted"], sei["iterations"]],
                      ["SOR", sor["predicted"], sor["iterations"]]],
          [1.63, 1.35, 1.45], size=16, row_h=0.44)
    text(s, X, 3.33, RW, 0.6, "Итерации от старта 20 °C до относительной невязки 10⁻⁸; оценка — "
                              "ln ε⁻¹ / ln ρ⁻¹.", size=13, color=INK_2)
    table(s, X, 4.05, [["Метод", "Время, с"],
                       ["Якоби", num(jac["seconds"], 3)], ["Зейдель", num(sei["seconds"], 3)],
                       ["SOR", num(sor["seconds"], 3)]], [2.6, 1.83], size=16, row_h=0.4)
    text(s, X, 5.75, RW, 1.15, timing_conditions(r["timing"]) + " По времени SOR быстрее Якоби в "
                               f"{num(gains['time_jacobi_to_sor'], 1)} раза.", size=12, color=INK_2)
    notes(s, "На графике — относительная невязка по номеру итерации, обе оси логарифмические. Все методы "
             "стартуют с одного поля и останавливаются на одном пороге. Число итераций ведёт себя так, как "
             "предсказывает спектральный радиус: Зейдель вдвое быстрее Якоби, верхняя релаксация — на порядок. "
             "По времени выигрыш меньше: шаг Якоби — одна векторная операция над всем массивом, а Зейдель "
             "и верхняя релаксация идут последовательно по 91 диагональной плоскости узлов. Число итераций "
             "от компьютера не зависит, время — зависит, поэтому условия замера указаны.")

    # 9. Проверка точности по сетке
    s = new_slide(prs, "Проверка точности по сетке", "4 · Точность")
    LW = 6.1
    bottom = steps(s, M, TOP, LW, [
        ("Добавка U = T(A) − T(0): на стенах и полу U = 0", [(F["increment"], 0.42)], 1),
        ("Точное решение — ряд Фурье", [(F["series"], 0.8), (F["kpq"], 0.42)], 1),
        ("Порядок — по ошибкам e_{h} на двух сетках", [(F["order"], 0.62)], 1),
    ], gap=0.1)
    takeaway(s, M, bottom + 0.2, LW, 0.78, f"p = **{num(inc[1]['order'], 2)}** и **{num(inc[2]['order'], 2)}** — "
                                           "второй порядок, как и следует из разложения Тейлора.")
    text(s, M, bottom + 1.1, LW, 6.9 - bottom - 1.1,
         f"Полное поле: разности вложенных сеток в {thousands(full['nodes'])} узлах не ближе "
         f"{num(full['margin_m'], 1)} м к граням, p = {num(full['order'], 2)}; к рёбрам эта оценка не относится.",
         size=13, color=INK_2)
    card(s, 6.95, TOP, W - M - 6.95, 5.45)
    picture(s, img_order, 7.05, TOP + 0.1, W - M - 7.15, 5.25)
    notes(s, "Как проверить точность. У полного поля разрывы на рёбрах, поэтому сравниваем другую величину — "
             "добавку от нагрева, разность расчётов с нагревом и без. Стены у обоих расчётов одинаковые и "
             "вычитаются, остаётся задача с нулём на стенах и полу и гладкой функцией на потолке. Её точное "
             "решение — ряд Фурье: синусы по x и y и гиперболические синусы по высоте. Считаем максимальную "
             "ошибку на трёх сетках. Если ошибка ведёт себя как C h в степени p, порядок находится как "
             "логарифм отношения ошибок на сетках с шагами 2h и h. Получается почти ровно два: при уменьшении "
             "шага вдвое ошибка падает в четыре раза, как и обещает разложение Тейлора. На графике обе линии "
             "параллельны пунктиру с наклоном два.")

    # 10. Температура на горизонтальных срезах
    s = new_slide(prs, "Температура на горизонтальных срезах", "5 · Результаты")
    card(s, M, TOP, 6.9, 5.45)
    picture(s, img_slices, M + 0.1, TOP + 0.1, 6.7, 5.25)
    X = 7.8
    RW = W - M - X
    text(s, X, TOP, RW, 0.3, f"Одно поле, A = {amp} °C, общая шкала {num(scale[0], 0)}–{num(scale[1], 0)} °C",
         size=14, color=INK_2)
    text(s, X, 2.0, RW, 3.1, ["**Поле сглаживается с глубиной**, потому что температура в каждом узле — "
                              "среднее соседей: пики потолка расплываются, а новых экстремумов внутри "
                              "не возникает.",
                              "Мелкие детали гаснут быстрее крупных: вклад гармоники с волновым числом k "
                              "убывает как e^{−kd}.",
                              "Ниже метра поле задают в основном стены: холодная x = 0 и тёплая x = 4 м."],
         size=15, color=INK_2, after=8)
    takeaway(s, X, 5.35, RW, 1.55, f"Максимум внутри слоя: **{num(top['interior_max'], 2)} °C** на глубине 0,1 м, "
                                    f"**{num(deep['interior_max'], 2)} °C** на 1,3 м. На глубине 1 м нагрев "
                                    f"потолка добавляет не больше **{num(metre['increment_max'], 2)} °C**.", size=15)
    notes(s, "Четыре горизонтальных среза одного поля на общей шкале. Под потолком видны оба пятна и волновой "
             "узор; с глубиной пятна расплываются, а узор исчезает. Это прямое следствие уравнения: значение "
             "в узле — среднее соседей, поэтому острые детали сглаживаются, а мелкие гаснут быстрее крупных. "
             "Голубая полоса слева — холодная стена x = 0. На глубине 1,3 м внутренние узлы слоя лежат в "
             f"пределах {num(deep['interior_min'], 2)}–{num(deep['interior_max'], 2)} °C, вместе с узлами на стенах — "
             f"{num(deep['layer_min'], 2)}–{num(deep['layer_max'], 2)} °C; максимум немного выше температуры "
             "тёплой стены, там ещё сказывается нагрев потолка.")

    # 11. Температура по высоте
    s = new_slide(prs, "Температура по высоте", "5 · Результаты")
    xp, yp = view["profile"]
    card(s, M, TOP, 6.6, 4.5)
    picture(s, img_vslice, M + 0.1, TOP + 0.1, 6.4, 4.3)
    card(s, 7.45, TOP, 5.28, 4.5)
    picture(s, img_profile, 7.55, TOP + 0.1, 5.08, 4.3)
    takeaway(s, M, 6.1, W - 2 * M, 0.8, f"Под точкой ({num(xp, 2)}; {num(yp, 2)}) м на высоте {num(prof['z'], 2)} м — "
                                        f"**{num(prof['T'], 1)} °C**, у потолка — {num(prof['T_ceiling'], 1)} °C, без "
                                        f"нагрева — {num(prof['T_zero_amplitude'], 1)} °C. Кривая круто падает "
                                        "у потолка: каждая гармоника нагрева гаснет как e^{−kd}.", size=15)
    notes(s, f"Слева — вертикальный срез y = {num(view['pos'], 2)} м через центр первого пятна; синяя линия — "
             f"вертикаль над точкой ({num(xp, 2)}; {num(yp, 2)}) м, чёрная — высота {num(prof['z'], 2)} м. Справа — "
             "температура вдоль этой вертикали. Сплошная кривая — с нагревом, пунктир — без нагрева, когда поле "
             "создают только стены и пол. Кривая выпуклая и круто падает у потолка: решение складывается из "
             "гармоник, каждая из которых убывает с глубиной экспоненциально.")

    # 12. Затухание неоднородностей с глубиной
    s = new_slide(prs, "Затухание неоднородностей с глубиной", "5 · Результаты")
    card(s, M, TOP, 7.45, 4.6)
    picture(s, img_decay, M + 0.1, TOP + 0.1, 7.25, 4.4)
    takeaway(s, M, 6.15, 7.45, 0.75, f"10 % амплитуды остаётся на глубине: волны — **{num(wave['tenth']['depth'], 2)} м**, "
                                     f"пятно 2 — **{num(spot2['tenth']['depth'], 2)} м**, пятно 1 — "
                                     f"**{num(spot1['tenth']['depth'], 2)} м**.", size=15)
    X = 8.4
    RW = W - M - X
    text(s, X, TOP, RW, 0.35, "Одна гармоника потолка", size=17, bold=True)
    text(s, X, 1.85, RW, 0.62, "sin αx · sin βy на потолке убывает вглубь экспоненциально, d — глубина:",
         size=14, color=INK_2)
    text(s, X, 3.3, RW, 0.35, "Волны m = n = 2", size=17, bold=True)
    same_scale(s, [(F["mode"], X, 2.5, RW, 0.66), (F["kwave"], X, 3.68, RW, 0.5)])
    text(s, X, 4.25, RW, 1.1, f"10 % остаётся при d = ln 10 / k ≈ {num(decay['wave_tenth_estimate'], 2)} м, "
                              f"по расчёту — {num(wave['tenth']['depth'], 2)} м. Пятна широкие, в них малые k, "
                              "поэтому они проникают глубже.", size=14, color=INK_2)
    text(s, X, 5.45, RW, 1.45, [[("Нормировка. ", {"bold": True, "color": INK}),
                                 ("Каждая кривая — максимум модуля компоненты на срезе, делённый на её "
                                  "максимум на потолке.", {})]], size=14, color=INK_2)
    notes(s, "Откуда берётся затухание. Если на потолке одна гармоника — произведение синусов с волновыми "
             "числами альфа и бета, — уравнение Лапласа решается разделением переменных, и по высоте она меняется "
             "как отношение гиперболических синусов, то есть почти как экспонента от глубины с показателем k. "
             f"Для волнового узора k = {num(decay['wave_k'], 2)} обратного метра, и 10 % амплитуды остаётся на "
             f"глубине около {num(decay['wave_tenth_estimate'], 2)} м — расчёт даёт {num(wave['tenth']['depth'], 2)}. "
             "Пятна широкие, в их разложении преобладают малые k, поэтому они проникают почти на метр глубже. "
             f"Каждая кривая нормирована на свой максимум на потолке, сетка {summary['grid']}.")

    # 13. Выводы
    s = new_slide(prs, "Выводы", dark=True)
    conclusions = [
        ("Температура с глубиной", f"{num(top['interior_max'], 1)} → {num(deep['interior_max'], 1)} °C",
         f"Максимум слоя на глубине 0,1 и 1,3 м. В метре под потолком нагрев добавляет не больше "
         f"{num(metre['increment_max'], 2)} °C."),
        ("Мелкий узор гаснет быстрее", f"{num(wave['tenth']['depth'], 2)} м",
         f"Волны теряют 90 % амплитуды; пятнам нужно {num(spot2['tenth']['depth'], 2)} и "
         f"{num(spot1['tenth']['depth'], 2)} м: затухание идёт как e^{{−kd}}."),
        ("Сравнение методов", f"{sor['iterations']} итераций",
         f"Верхняя релаксация с τ = {num(sor['omega'], 3)} против {sei['iterations']} у Зейделя и "
         f"{jac['iterations']} у Якоби; по времени в {num(gains['time_jacobi_to_sor'], 1)} раза быстрее Якоби."),
        ("Точность схемы", f"p ≈ {num(inc[2]['order'], 2)}",
         "Ошибка убывает как h², как и предсказывает разложение Тейлора."),
    ]
    CW, CH = (W - 2 * M - 0.3) / 2, (6.9 - TOP - 0.3) / 2
    for k, (head, big, body) in enumerate(conclusions):
        x, y = M + (k % 2) * (CW + 0.3), TOP + (k // 2) * (CH + 0.3)
        card(s, x, y, CW, CH, color=DARK_CARD, line=None)
        text(s, x + 0.35, y + 0.28, CW - 0.7, 0.35, head, size=16, bold=True, color=LIGHT_ON_DARK)
        text(s, x + 0.35, y + 0.68, CW - 0.7, 0.6, big, size=32, bold=True, color=ORANGE)
        text(s, x + 0.35, y + 1.42, CW - 0.7, CH - 1.55, body, size=15, color=LIGHT_ON_DARK)
    notes(s, "Итоги. Нагрев потолка заметен в верхней части комнаты, а ниже метра поле определяют в основном "
             "стены. Чем мельче деталь нагрева, тем ближе к потолку она гаснет — это следует из разделения "
             "переменных. Из трёх методов верхняя релаксация с оптимальным параметром требует на порядок меньше "
             "итераций, как и предсказывает спектральный радиус. Схема имеет второй порядок, и расчёт это "
             "подтверждает.")

    footers(prs)
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
        import win32com.client
        app = win32com.client.Dispatch("PowerPoint.Application")
        deck = app.Presentations.Open(str(pptx.resolve()), WithWindow=False)
        try:
            deck.SaveAs(str(pdf.resolve()), 32)
        finally:
            deck.Close()
            app.Quit()
        return "PowerPoint"
    if sys.platform == "darwin" and Path("/Applications/Microsoft PowerPoint.app").exists():
        box = Path.home() / "Library/Containers/com.microsoft.Powerpoint/Data/Documents/pde-solver-export"
        box.mkdir(parents=True, exist_ok=True)
        # Копия с уникальным именем, и обращаемся к ней по имени: презентации, открытые
        # в PowerPoint пользователем (в том числе прежний PDE-Solver.pptx), не затрагиваются.
        tag = f"pde-export-{os.getpid()}"
        src, dst = box / f"{tag}.pptx", box / f"{tag}.pdf"
        try:
            dst.unlink(missing_ok=True)
            shutil.copy(pptx, src)
            script = (f'tell application "Microsoft PowerPoint"\n open POSIX file "{src}"\n delay 3\n'
                      f' save presentation "{src.name}" in POSIX file "{dst}" as save as PDF\n delay 2\n'
                      f' close presentation "{src.name}" saving no\nend tell')
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
        except Exception as error:
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

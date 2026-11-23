"""Презентация для защиты: python make_slides.py → presentation/PDE-Solver.pptx и .pdf

Числа берутся из results.json (study.py), поля — из нового расчёта. Графики для
слайдов экспортируются отдельно, с крупным шрифтом: подписи должны читаться
с места при показе на экране. Формулы рендерит matplotlib (mathtext).
PDF экспортируется через LibreOffice или PowerPoint (export_pdf).
"""

import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

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
                     convergence_figure, depth_figure, fmt, hslice_figure, profile_figure,
                     scale_for, slices_figure, value_at)
from heat_room import LZ, WALLS, Grid, solve
from make_figures import DEMO_PARAMS, DEMO_VIEW, scheme_figure

HERE = Path(__file__).parent
FIG = HERE / "figures"
OUT = HERE / "presentation"
BUILD = OUT / "build"            # промежуточные PNG; в git не попадают
RESULTS = json.loads((HERE / "results.json").read_text(encoding="utf-8"))

FONT = "Arial"
INK = RGBColor(0x0B, 0x0B, 0x0B)
INK_2 = RGBColor(0x52, 0x51, 0x4E)
CARD = RGBColor(0xF4, 0xF3, 0xEF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x2E, 0x17, 0x20)        # тёмный конец тепловой шкалы
LIGHT_ON_DARK = RGBColor(0xE8, 0xDF, 0xD6)
HEAT = RGBColor(0xEB, 0x68, 0x34)
BLUE = RGBColor(0x2A, 0x78, 0xD6)

W, H = 13.333, 7.5
M = 0.6


def nbsp(value):
    """Число не отрывается от единицы, а «4 × 3» — от знака умножения."""
    value = re.sub(r"([\d)]) (м⁻¹|м|°C|с|раз|итерац\w*|%)", "\\1\u00a0\\2", value)
    value = re.sub(r"\b([xyzA]) = ", "\\1\u00a0=\u00a0", value)          # «z = 1,6 м» целиком
    value = re.sub(r"\((\d+,\d+); (\d+,\d+)\)", "(\\1;\u00a0\\2)", value)  # координаты точки
    for _ in range(2):   # «4 × 3 × 2,6»: соседние пары перекрываются
        value = re.sub(r"(\d) × (\d)", "\\1\u00a0×\u00a0\\2", value)
    return value


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
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / name
    enlarge(fig, factor).write_image(path, width=width, height=height, scale=3)
    return path


def untitled(fig, top=12, scale_bar=True):
    fig.update_layout(title_text="", margin_t=top)
    if not scale_bar:
        fig.update_traces(showscale=False, selector=dict(type="heatmap"))
    return fig


plt.rcParams.update({"mathtext.fontset": "custom", "mathtext.rm": "Arial",
                     "mathtext.it": "Arial:italic", "mathtext.bf": "Arial:bold",
                     "font.family": "Arial"})


def formula(name, tex, size=30):
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / f"{name}.png"
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, tex, fontsize=size, color="#0b0b0b")
    fig.savefig(path, dpi=220, transparent=True, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return path


def stencil_picture():
    """Семиточечный шаблон: центр, соседи с новыми и прежними значениями."""
    path = BUILD / "stencil.png"
    fig, ax = plt.subplots(figsize=(6.2, 5.6), dpi=220)
    ax.set_aspect("equal")
    ax.axis("off")
    d = (0.55, 0.38)                     # направление оси j на рисунке (перспектива)
    nodes = {  # подпись: (x, y узла, новое ли значение, x и y подписи, выравнивание)
        "i−1": (-1.6, 0.0, True, -2.35, 0.0, "center"),
        "i+1": (1.6, 0.0, False, 2.35, 0.0, "center"),
        "j−1": (-1.6 * d[0], -1.6 * d[1], True, -1.55, -1.05, "center"),
        "j+1": (1.6 * d[0], 1.6 * d[1], False, 1.55, 1.05, "center"),
        "k−1": (0.0, -1.6, True, 0.45, -1.6, "left"),
        "k+1": (0.0, 1.6, False, 0.45, 1.6, "left"),
    }
    for x, y, *_ in nodes.values():
        ax.plot([0, x], [0, y], color="#898781", lw=2.5, zorder=1)
    for label, (x, y, new, tx, ty, ha) in nodes.items():
        ax.scatter([x], [y], s=900, zorder=3, color="#2a78d6" if new else "white",
                   edgecolors="#2a78d6", linewidths=3)
        ax.text(tx, ty, label, fontsize=22, ha=ha, va="center", color="#0b0b0b")
    ax.scatter([0], [0], s=1300, zorder=4, color="#eb6834", edgecolors="#0b0b0b", linewidths=2)
    ax.text(0.38, -0.5, "(i, j, k)", fontsize=22, ha="left", va="center", color="#0b0b0b")
    ax.scatter([-2.3], [-2.55], s=420, color="#2a78d6", edgecolors="#2a78d6", linewidths=3)
    ax.text(-2.0, -2.55, "уже пересчитаны (s + 1)", fontsize=19, va="center")
    ax.scatter([-2.3], [-3.15], s=420, color="white", edgecolors="#2a78d6", linewidths=3)
    ax.text(-2.0, -3.15, "прежние значения (s)", fontsize=19, va="center")
    ax.set_xlim(-2.8, 2.8)
    ax.set_ylim(-3.5, 2.3)
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
            r = p.add_run()
            r.text = nbsp(part)
            r.font.name = FONT
            r.font.size = Pt(opts.get("size", size))
            r.font.bold = opts.get("bold", bold)
            r.font.color.rgb = opts.get("color", color)
    return box


def title(slide, value, color=INK, size=28):
    text(slide, M, 0.4, W - 2 * M, 1.0, value, size=size, bold=True, color=color, name="Title")


def card(slide, x, y, w, h, color=CARD):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.adjustments[0] = 0.04
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def picture(slide, path, x, y, w, h, align="center"):
    iw, ih = Image.open(path).size
    k = min(w / iw, h / ih)
    pw, ph = iw * k, ih * k
    px = x + (w - pw) / 2 if align == "center" else x
    return slide.shapes.add_picture(str(path), Inches(px), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))


def table(slide, x, y, w, rows, widths, size=18, row_h=0.52):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
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
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
            r = p.add_run()
            r.text = nbsp(str(value))
            r.font.name, r.font.size, r.font.bold = FONT, Pt(size), i == 0
            r.font.color.rgb = WHITE if i == 0 else INK
    return tbl


def notes(slide, value):
    slide.notes_slide.notes_text_frame.text = value


# --- Слайды -----------------------------------------------------------------

def build():
    r = RESULTS
    jac, sei, sor = r["methods"]
    gains = r["gains"]
    inc = r["increment_convergence"]
    full = r["full_field_convergence"]
    checks, zero = r["checks"], r["zero_amplitude"]
    decay = r["depth_decay"]
    spot1, spot2, wave = (decay[k] for k in decay if isinstance(decay[k], dict))
    timing = r["timing"]

    print("Поля и рисунки для слайдов…")
    grid = Grid.with_step(0.1)
    base = solve(grid, ceiling_from_params(DEFAULT_PARAMS), tol=1e-8)
    demo = solve(grid, ceiling_from_params(DEMO_PARAMS), tol=1e-8, start=base.T)
    scale = scale_for(DEFAULT_PARAMS)
    both = (scale[0], max(scale[1], scale_for(DEMO_PARAMS)[1]))
    xp, yp = DEMO_VIEW["profile"]
    t_slice = value_at(demo.T, grid, xp, yp, DEMO_VIEW["z"])
    t_top = value_at(demo.T, grid, xp, yp, LZ)

    img_scheme = export(scheme_figure(DEFAULT_PARAMS, scale), "scheme.png", 820, 600, 1.3)
    solutions = [solve(grid, method=m, tol=r["tolerance"]) for m in ("jacobi", "seidel", "sor")]
    conv = untitled(convergence_figure(solutions, r["tolerance"]), top=60)
    # Подписи у концов линий на узком рисунке налезают друг на друга; числа — в таблице.
    conv.layout.annotations = [a for a in conv.layout.annotations if "<b>" not in a.text]
    img_conv = export(conv, "convergence.png", 660, 470, 1.3)
    from study import depth_decay   # тот же расчёт, что и в отчёте
    depths, curves, summary = depth_decay(Grid.with_step(0.05))
    img_decay = export(untitled(depth_figure(depths, curves, summary), top=70), "depth.png", 780, 450, 1.3)
    img_slices = export(slices_figure(base.T, grid, [2.5, 2.2, 1.8, 1.3], scale, cols=2),
                        "slices.png", 700, 600, 1.3)
    maps = {}
    for key, params, view, sol in [("before", DEFAULT_PARAMS, DEFAULT_VIEW, base),
                                   ("after", DEMO_PARAMS, DEMO_VIEW, demo)]:
        last = key == "after"
        maps[key + "-ceiling"] = export(untitled(ceiling_map_figure(params, 0, view, both), scale_bar=last),
                                        f"{key}-ceiling.png", 470 if last else 400, 300, 1.45)
        maps[key + "-hslice"] = export(untitled(hslice_figure(sol.T, grid, view, both), scale_bar=last),
                                       f"{key}-hslice.png", 470 if last else 400, 300, 1.45)
    img_profile = export(untitled(profile_figure(demo.T, grid, DEMO_VIEW, both)), "profile.png", 380, 470, 1.45)
    img_stencil = stencil_picture()
    f_ceiling1 = formula("ceiling1", r"$T_{\mathrm{пот}} = 20 + A\,\sin^2\!\pi u\,\sin^2\!\pi v\;\cdot$", 30)
    f_ceiling2 = formula("ceiling2", r"$\cdot\,(0{,}12 + 0{,}65\,G_1 + 0{,}30\,G_2 + 0{,}15\,R)$", 30)
    f_sor1 = formula("sor1", r"$T^{s+1}_{ijk} = (1-\omega)\,T^{s}_{ijk} + \omega\,\tilde T_{ijk}$", 34)
    f_sor2 = formula("sor2", r"$\tilde T_{ijk} = \frac{\sum_6\, c\, T_{\mathrm{сосед}}}{\sum_6\, c},"
                             r"\qquad c = h^{-2}\ \mathrm{по\ оси\ соседа}$", 30)

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]
    prs.core_properties.title = "Как рисунок температуры на потолке меняется с глубиной?"

    # 1. Титул
    s = prs.slides.add_slide(blank)
    background(s, DARK)
    text(s, M, 0.9, 5.8, 0.4, "ВЫЧИСЛИТЕЛЬНАЯ МАТЕМАТИКА · PDE-SOLVER", size=14, bold=True,
         color=RGBColor(0xF6, 0xA3, 0x52))
    text(s, M, 1.45, 5.7, 2.8, "Как рисунок температуры на потолке меняется с глубиной?",
         size=40, bold=True, color=WHITE, spacing=1.0, name="Title")
    text(s, M, 4.4, 5.5, 1.6, "Стационарное поле в комнате 4 × 3 × 2,6 м: стены 16–24 °C, пол 20 °C, "
                              "потолок нагрет двумя пятнами и волнами", size=19, color=LIGHT_ON_DARK)
    text(s, M, 6.3, 5.7, 0.5, "Уравнение Лапласа · схема «крест» · метод верхней релаксации",
         size=15, color=RGBColor(0xB9, 0xA9, 0xA8))
    card(s, 6.45, 1.95, 6.3, 3.62, color=RGBColor(0xFB, 0xF7, 0xF0))
    picture(s, FIG / "app.png", 6.55, 2.05, 6.1, 3.42)
    notes(s, "Нужно найти стационарное поле температуры в комнате и проследить, как рисунок нагрева "
             "потолка ослабевает с удалением от него. Справа — стенд, который покажу в конце.")

    # 2. Условия
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Условия: стены и пол постоянны, потолок нагрет")
    card(s, M, 1.35, 6.9, 5.55)
    picture(s, img_scheme, M + 0.1, 1.45, 6.7, 5.35)
    text(s, 7.8, 1.4, 4.95, 0.45, "Внутри ΔT = 0, источников нет", size=19, bold=True)
    picture(s, f_ceiling1, 7.8, 2.0, 4.95, 0.5, align="left")
    picture(s, f_ceiling2, 7.8, 2.55, 4.95, 0.5, align="left")
    text(s, 7.8, 3.2, 4.95, 0.75, "A = 60 °C, волны m = n = 2; у края потолка T → 20 °C.",
         size=17, color=INK_2)
    text(s, 7.8, 4.0, 4.95, 0.45, "Стыки граней", size=19, bold=True)
    text(s, 7.8, 4.5, 4.95, 2.4, [
        "Ребро — среднее двух граней: x = y = 0 даёт (16 + 18) / 2 = 17 °C.",
        "Вершина — среднее трёх: (16 + 18 + 20) / 3 = 18 °C.",
        "В уравнения внутренних узлов рёбра и вершины не входят."], size=17, color=INK_2, after=8)
    notes(s, "Данные Дирихле заданы на открытых гранях. На ребре пределы соседних граней различаются, "
             "и для решения внутри значения на рёбрах не нужны. В сетке принято правило средних. "
             "Соседи внутреннего узла в семиточечном шаблоне меняют один индекс, поэтому лежат только на "
             "открытых гранях; рёбра и вершины нужны лишь для рисунков. Тест подставляет на них 1000 °C — "
             "решение не меняется.")

    # 3. Метод
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Схема «крест»: узел пересчитывается по шести соседям")
    picture(s, img_stencil, M, 1.35, 5.6, 5.6)
    picture(s, f_sor1, 6.5, 1.55, 6.25, 0.6, align="left")
    picture(s, f_sor2, 6.5, 2.3, 6.25, 0.9, align="left")
    text(s, 6.5, 3.5, 6.2, 3.4, [
        "Соседи с меньшим индексом уже пересчитаны на этой итерации, с большим — ещё нет.",
        f"ω = 1 — метод Зейделя; для сетки {r['grid']['nx']} × {r['grid']['ny']} × {r['grid']['nz']} "
        f"оптимум ω = {fmt(r['grid']['optimal_omega'], 3)}.",
        "Метод Якоби берёт всех соседей с прошлой итерации.",
        "Остановка: ‖b − Av‖∞ / ‖b‖∞ ≤ 10⁻⁸, старт — 20 °C внутри."], size=19, color=INK_2, after=10)
    notes(s, "Оптимальный ω найден по теореме Янга через спектральный радиус метода Якоби, вывод — в README. "
             "Узлы одной плоскости i + j + k = const обновляются вместе: их соседи лежат на соседних "
             "плоскостях, поэтому порядок совпадает с поточечным обходом из учебника (§14.2.5).")

    # 4. Сходимость
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, f"Итераций до невязки 10⁻⁸: Якоби {jac['iterations']}, SOR {sor['iterations']}")
    card(s, M, 1.45, 7.3, 5.4)
    picture(s, img_conv, M + 0.1, 1.55, 7.1, 5.2)
    table(s, 8.2, 1.55, 4.55, [["Метод", "Итераций", "Время, с"],
                               ["Якоби", jac["iterations"], fmt(jac["seconds"], 2)],
                               ["Зейдель", sei["iterations"], fmt(sei["seconds"], 2)],
                               ["SOR", sor["iterations"], fmt(sor["seconds"], 2)]], [1.55, 1.5, 1.5])
    text(s, 8.2, 3.85, 4.55, 3.0, [
        f"Время — медиана {timing['repeats']} запусков, Apple M5 Pro, Python {timing['python']}, "
        f"numpy {timing['numpy']}.",
        f"SOR быстрее Якоби в {fmt(gains['iterations_jacobi_to_sor'], 0)} раз по итерациям и в "
        f"{fmt(gains['time_jacobi_to_sor'], 1)} раза по времени: проход SOR идёт по 91 плоскости, "
        "проход Якоби — одно векторное действие."], size=16, color=INK_2, after=8)
    notes(s, f"Сетка 40 × 30 × 26, общий старт 20 °C. Оценка по спектральному радиусу: Якоби {jac['predicted']}, "
             f"Зейдель {sei['predicted']}, SOR {sor['predicted']} итераций. Подбор ω: минимум итераций около 1,81–1,85. "
             f"Зейдель быстрее Якоби в {fmt(gains['iterations_jacobi_to_seidel'], 2)} раза по итерациям: ρ(Зейдель) = ρ(Якоби)².")

    # 5. Проверка точности
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Проверка: шаг вдвое меньше — ошибка в 4 раза меньше")
    table(s, M, 1.5, 7.0, [["Шаг h, м", "Сетка", "Ошибка, °C", "Порядок"]] +
          [[fmt(row["h"], 2), row["grid"], fmt(row["max_error"], 4 if row["max_error"] < 0.1 else 3),
            fmt(row["order"], 2) if "order" in row else "—"] for row in inc], [1.4, 2.4, 1.7, 1.5])
    text(s, M, 3.75, 7.0, 3.0, [
        "Ошибка — максимум по узлам для добавки от нагрева: T(A) − T(A = 0). Её данные гладкие, "
        "эталон — ряд Фурье.",
        f"Полное поле на скачках у рёбер точнее не сравнить; в узлах дальше 0,5 м от граней разности "
        f"вложенных сеток {fmt(full['max_diffs'][0], 3)} и {fmt(full['max_diffs'][1], 4)} °C, порядок "
        f"{fmt(full['order'], 2)}."], size=16, color=INK_2, after=10)
    card(s, 8.0, 1.5, 4.73, 4.1)
    text(s, 8.3, 1.75, 4.2, 5.0, [
        [("Граница", {"bold": True, "color": INK, "size": 19})],
        "Грани, рёбра и вершины — отклонение 0 °C.",
        [("Принцип максимума", {"bold": True, "color": INK, "size": 19})],
        f"Внутри {fmt(checks['interior_min'], 2)}…{fmt(checks['interior_max'], 2)} °C, на границе "
        f"{fmt(checks['boundary_min'], 0)}…{fmt(checks['boundary_max'], 2)} °C.",
        [("A = 0", {"bold": True, "color": INK, "size": 19})],
        f"Потолок 20 °C, внутри {fmt(zero['interior_min'], 1)}…{fmt(zero['interior_max'], 1)} °C: "
        "поле создают стены."], size=16, color=INK_2, after=6)
    notes(s, "Точное решение сеточной системы получено разделением переменных для всех шести граней и совпадает "
             "с независимо собранной матрицей до 10⁻¹³. SOR отличается от него на 6·10⁻⁷ °C при пороге 10⁻⁸.")

    # 6. Срезы
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Срезы на одной шкале: с глубиной пятна расплываются")
    card(s, M, 1.35, 8.6, 5.55)
    picture(s, img_slices, M + 0.1, 1.42, 8.4, 5.4)
    text(s, 9.55, 1.6, 3.2, 0.5, "Максимум на срезе", size=19, bold=True)
    peaks = []
    for z in (2.5, 2.2, 1.8, 1.3):
        k = round(z / grid.steps[2])
        peaks.append(f"глубина {fmt(LZ - z, 1)} м — {fmt(base.T[1:-1, 1:-1, k].max(), 1)} °C")
    text(s, 9.55, 2.15, 3.2, 2.4, peaks, size=18, color=INK_2, after=6)
    text(s, 9.55, 4.6, 3.2, 2.2, "На глубине 1,3 м поле лежит в пределах стен 16–24 °C: рисунок потолка "
                                 "почти не виден.", size=16, color=INK_2)
    notes(s, "Голубой край слева на каждом срезе — холодная стена x = 0 (16 °C). Цвет и шкала те же, что в стенде.")

    # 7. Затухание
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, f"Глубина 10 %: узор {fmt(wave['tenth']['depth'], 2)} м, пятна "
             f"{fmt(spot2['tenth']['depth'], 2)} и {fmt(spot1['tenth']['depth'], 2)} м")
    card(s, M, 1.35, 9.0, 5.55)
    picture(s, img_decay, M + 0.1, 1.45, 8.8, 5.35)
    text(s, 9.95, 1.5, 2.8, 5.3, [
        "Компонента — добавка T(A) − T(A = 0) от одного слагаемого; у волн — только осциллирующая часть.",
        "Доля — максимум |компоненты| на срезе, делённый на максимум на потолке.",
        "Точки — интерполяция между слоями сетки 0,05 м.",
        f"Пунктир — оценка для одной гармоники k = {fmt(decay['wave_k'], 2)} м⁻¹."],
         size=15, color=INK_2, after=8)
    notes(s, f"Амплитуды на потолке: пятно 1 — {fmt(spot1['ceiling_amplitude'], 1)} °C, пятно 2 — "
             f"{fmt(spot2['ceiling_amplitude'], 1)} °C, волны — {fmt(wave['ceiling_amplitude'], 1)} °C. "
             f"Для гармоники sinh k(Lz − d)/sinh kLz даёт 10 % на {fmt(decay['wave_tenth_estimate'], 2)} м; "
             "пятна состоят из многих низких гармоник и одной экспонентой не описываются.")

    # 8. Живой показ
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Живой показ: сдвиг пятна, A = 85 °C, срез на 1,6 м")
    text(s, M, 1.3, 3.6, 0.7, [[("До: ", {"bold": True, "color": INK}),
                                ("A = 60 °C, пятно 1 в (1,32; 1,65) м, z = 2,3 м", {})]],
         size=15, color=INK_2)
    text(s, 4.35, 1.3, 4.2, 0.7, [[("После: ", {"bold": True, "color": HEAT}),
                                   ("A = 85 °C, пятно 1 в (2,2; 2,0) м, z = 1,6 м", {})]],
         size=15, color=INK_2)
    picture(s, maps["before-ceiling"], M, 2.05, 3.6, 2.45)
    picture(s, maps["after-ceiling"], 4.35, 2.05, 4.2, 2.45)
    picture(s, maps["before-hslice"], M, 4.55, 3.6, 2.45)
    picture(s, maps["after-hslice"], 4.35, 4.55, 4.2, 2.45)
    card(s, 8.85, 1.3, 3.88, 5.7)
    text(s, 9.05, 1.42, 3.5, 0.9, f"Профиль под ({fmt(xp, 1)}; {fmt(yp, 1)}) м", size=17, bold=True)
    picture(s, img_profile, 8.95, 1.9, 3.7, 4.55)
    text(s, 9.05, 6.45, 3.5, 0.5, f"z = 1,6 м: {fmt(t_slice, 1)} °C; потолок {fmt(t_top, 1)} °C",
         size=15, color=INK_2)
    notes(s, "Перед показом нажать «Сбросить». 1) Перетащить маркер пятна 1 на карте потолка в (2,2; 2,0) м. "
             "2) Ползунок A: 60 → 85 °C, шкала всех видов станет 16–90 °C. 3) Горизонтальный срез: 2,3 → 1,6 м. "
             f"4) Щёлкнуть по центру маркера пятна 1: профиль под (2,2; 2,0) м, на высоте 1,6 м — "
             f"{fmt(t_slice, 1)} °C. Все карты на слайде — на одной шкале 16–90 °C.")

    # 9. Результаты
    s = prs.slides.add_slide(blank)
    background(s, DARK)
    title(s, "Результаты", color=WHITE, size=34)
    results = [
        (f"{fmt(100 * spot1['fraction_at_depth']['1.0'], 0)} %",
         f"амплитуды пятна 1 остаётся на глубине 1 м; у пятна 2 — "
         f"{fmt(100 * spot2['fraction_at_depth']['1.0'], 0)} %, у осциллирующей части волн — "
         f"{fmt(100 * wave['fraction_at_depth']['1.0'], 0)} %. Измерено для добавки T(A) − T(A = 0), "
         "сетка 80 × 60 × 52."),
        (f"{sor['iterations']}",
         f"итераций SOR (ω = {fmt(sor['omega'], 3)}) до невязки 10⁻⁸ против {jac['iterations']} у Якоби и "
         f"{sei['iterations']} у Зейделя; сетка 40 × 30 × 26, старт 20 °C."),
        (f"{fmt(inc[-1]['order'], 2)}",
         f"порядок сходимости по сетке: ошибка добавки относительно ряда Фурье "
         f"{fmt(inc[0]['max_error'], 3)} → {fmt(inc[1]['max_error'], 3)} → {fmt(inc[2]['max_error'], 3)} °C "
         "при h = 0,2 → 0,1 → 0,05 м."),
    ]
    for i, (big, body) in enumerate(results):
        y = 1.75 + i * 1.75
        text(s, M, y, 2.6, 1.3, big, size=44, bold=True, color=RGBColor(0xF6, 0xA3, 0x52),
             anchor=MSO_ANCHOR.MIDDLE)
        text(s, 3.4, y, 9.3, 1.3, body, size=19, color=LIGHT_ON_DARK, anchor=MSO_ANCHOR.MIDDLE)
    notes(s, "Мелкие детали нагрева гаснут у самого потолка, крупные проникают глубже; в метре под потолком "
             "поле определяют в основном стены.")

    OUT.mkdir(exist_ok=True)
    path = OUT / "PDE-Solver.pptx"
    prs.save(path)
    print("Сохранено:", path.relative_to(HERE))
    return path


# --- Экспорт PDF ------------------------------------------------------------

def export_pdf(pptx):
    """PDF рядом с PPTX: LibreOffice, иначе PowerPoint (Windows — pywin32, macOS — AppleScript)."""
    pdf = pptx.with_suffix(".pdf")
    soffice = (shutil.which("soffice") or shutil.which("libreoffice")
               or next((p for p in [r"C:\Program Files\LibreOffice\program\soffice.exe",
                                    "/Applications/LibreOffice.app/Contents/MacOS/soffice"]
                        if Path(p).exists()), None))
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pptx.parent), str(pptx)],
                       check=True, timeout=300)
        return pdf
    if sys.platform == "win32":
        try:
            import win32com.client
        except ImportError:
            win32com = None
        if win32com:
            app = win32com.client.Dispatch("PowerPoint.Application")
            deck = app.Presentations.Open(str(pptx.resolve()), WithWindow=False)
            deck.SaveAs(str(pdf.resolve()), 32)   # 32 — ppSaveAsPDF
            deck.Close()
            app.Quit()
            return pdf
    if sys.platform == "darwin" and Path("/Applications/Microsoft PowerPoint.app").exists():
        # PowerPoint на macOS работает в песочнице: файл кладём в его контейнер.
        box = Path.home() / "Library/Containers/com.microsoft.Powerpoint/Data/Documents/pde-solver-export"
        box.mkdir(parents=True, exist_ok=True)
        src, dst = box / pptx.name, box / pdf.name
        shutil.copy(pptx, src)
        dst.unlink(missing_ok=True)
        script = (f'tell application "Microsoft PowerPoint"\n open POSIX file "{src}"\n delay 3\n'
                  f' save active presentation in POSIX file "{dst}" as save as PDF\n delay 2\n'
                  f' close active presentation saving no\nend tell')
        subprocess.run(["osascript", "-e", script], check=True, timeout=300)
        shutil.copy(dst, pdf)
        shutil.rmtree(box, ignore_errors=True)
        return pdf
    print("PDF не создан: нет LibreOffice и PowerPoint. Откройте PPTX и сохраните как PDF вручную.")
    return None


if __name__ == "__main__":
    pptx = build()
    pdf = export_pdf(pptx)
    if pdf:
        print("Сохранено:", pdf.relative_to(HERE))

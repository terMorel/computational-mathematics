"""Презентация для защиты: python make_slides.py → presentation/PDE-Solver.pptx

Использует рисунки из figures/ (make_figures.py, study.py, screenshot.py) и числа из
results.json. Формулы рендерятся matplotlib (mathtext) в PNG. PDF-версию
экспортирует PowerPoint (см. README).
"""

import json
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).parent
FIG = HERE / "figures"
OUT = HERE / "presentation"
FORMULAS = OUT / "formulas"
RESULTS = json.loads((HERE / "results.json").read_text())

FONT = "Arial"
INK = RGBColor(0x0B, 0x0B, 0x0B)
INK_2 = RGBColor(0x52, 0x51, 0x4E)
MUTED = RGBColor(0x89, 0x87, 0x81)
CARD = RGBColor(0xF4, 0xF3, 0xEF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x2E, 0x17, 0x20)        # тёмный конец тепловой шкалы
HEAT = RGBColor(0xEB, 0x68, 0x34)        # оранжевый акцент (середина шкалы)
BLUE = RGBColor(0x2A, 0x78, 0xD6)        # акцент управления, как в приложении
SOFT = RGBColor(0xF6, 0xD9, 0xC4)

W, H = 13.333, 7.5
M = 0.6                                   # поля слайда


def fmt(value, digits=2):
    return f"{value:.{digits}f}".replace(".", ",")


def nbsp(value):
    """Число не отрывается от единицы, а «4 × 3» — от знака умножения."""
    value = re.sub(r"(\d) (м⁻¹|м|°C|с|раз|итераций)", "\\1\u00a0\\2", value)
    for _ in range(2):   # «4 × 3 × 2,6»: соседние пары перекрываются
        value = re.sub(r"(\d) × (\d)", "\\1\u00a0×\u00a0\\2", value)
    return value


# --- Формулы ---------------------------------------------------------------

plt.rcParams.update({"mathtext.fontset": "custom", "mathtext.rm": "Arial",
                     "mathtext.it": "Arial:italic", "mathtext.bf": "Arial:bold",
                     "font.family": "Arial"})


def formula(name, tex, size=30, color="#0b0b0b"):
    FORMULAS.mkdir(parents=True, exist_ok=True)
    path = FORMULAS / f"{name}.png"
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, tex, fontsize=size, color=color)
    fig.savefig(path, dpi=220, transparent=True, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return path


# --- Примитивы слайда -------------------------------------------------------

def background(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def text(slide, x, y, w, h, runs, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=1.1, name=None):
    """runs: строка или список абзацев; абзац — строка или список (текст, {опции})."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        box.name = name
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paragraphs = [runs] if isinstance(runs, str) else runs
    paragraphs = [nbsp(p) if isinstance(p, str) else [(nbsp(t), o) for t, o in p] for p in paragraphs]
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        parts = [(para, {})] if isinstance(para, str) else para
        for part, opts in parts:
            r = p.add_run()
            r.text = part
            f = r.font
            f.name = FONT
            f.size = Pt(opts.get("size", size))
            f.bold = opts.get("bold", bold)
            f.italic = opts.get("italic", False)
            f.color.rgb = opts.get("color", color)
        if isinstance(para, list) and para and para[0][1].get("space_after"):
            p.space_after = Pt(para[0][1]["space_after"])
    return box


def title(slide, value, color=INK):
    text(slide, M, 0.42, W - 2 * M, 0.9, value, size=32, bold=True, color=color,
         anchor=MSO_ANCHOR.TOP, name="Title")


def card(slide, x, y, w, h, color=CARD, radius=0.04):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.adjustments[0] = radius
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def picture(slide, path, x, y, w, h, align="center"):
    """Вписывает картинку в прямоугольник с сохранением пропорций."""
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    px = x + (w - pw) / 2 if align == "center" else x
    py = y + (h - ph) / 2
    return slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(pw), Inches(ph))


def framed(slide, path, x, y, w, h, pad=0.12, caption=None):
    card(slide, x, y, w, h)
    inner_h = h - 2 * pad - (0.42 if caption else 0)
    picture(slide, path, x + pad, y + pad, w - 2 * pad, inner_h)
    if caption:
        text(slide, x + 0.2, y + h - 0.46, w - 0.4, 0.4, caption, size=14, color=INK_2)


def badge(slide, x, y, label, color=HEAT, d=0.52, size=20):
    dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    dot.fill.solid()
    dot.fill.fore_color.rgb = color
    dot.line.fill.background()
    dot.shadow.inherit = False
    tf = dot.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FONT, Pt(size), True, WHITE


def stat(slide, x, y, w, value, label, color=INK):
    text(slide, x, y, w, 0.75, value, size=40, bold=True, color=color)
    text(slide, x, y + 0.78, w, 0.6, label, size=15, color=INK_2)


def table(slide, x, y, w, rows, widths, size=15, header_fill=DARK):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                                   Inches(0.46 * len(rows)))
    tbl = shape.table
    for j, cw in enumerate(widths):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(0.46)
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if i == 0 else (WHITE if i % 2 else CARD)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.paragraphs[0].text = ""
            r = tf.paragraphs[0].add_run()
            r.text = str(value)
            r.font.name, r.font.size = FONT, Pt(size)
            r.font.bold = i == 0
            r.font.color.rgb = WHITE if i == 0 else INK
            tf.paragraphs[0].alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
    return tbl


def notes(slide, value):
    slide.notes_slide.notes_text_frame.text = value


# --- Слайды ----------------------------------------------------------------

def build():
    r = RESULTS
    methods = {m["method"]: m for m in r["methods"]}
    jac, sei, sor = methods["Якоби"], methods["Зейдель"], methods["SOR"]
    grids = r["grid_convergence"]
    decay = r["depth_decay"]
    names = [k for k in decay if isinstance(decay[k], dict)]
    spot1, spot2, wave = (decay[n] for n in names)
    checks = r["checks"]
    g = r["grid"]

    f_ceiling = formula("ceiling", r"$T_{\mathrm{пот}} = 20 + A\,\sin^2\!\pi u\,\sin^2\!\pi v\,"
                                   r"\left(0{,}12 + 0{,}65\,G_1 + 0{,}30\,G_2 + 0{,}15\,R\right)$", 30)
    f_gauss = formula("gauss", r"$G_j = \exp\!\left(-\frac{1}{2}\left[\left(\frac{u-u_j}{\sigma_{xj}}\right)^2"
                               r" + \left(\frac{v-v_j}{\sigma_{yj}}\right)^2\right]\right),\quad"
                               r"R = \frac{1 + \sin 2\pi m u\,\cos 2\pi n v}{2}$", 26)
    f_scheme = formula("scheme", r"$\frac{T_{i-1,j,k} - 2T_{ijk} + T_{i+1,j,k}}{h_x^2} + "
                                 r"\frac{T_{i,j-1,k} - 2T_{ijk} + T_{i,j+1,k}}{h_y^2} + "
                                 r"\frac{T_{i,j,k-1} - 2T_{ijk} + T_{i,j,k+1}}{h_z^2} = 0$", 26)
    f_sor = formula("sor", r"$T^{s+1}_{ijk} = (1-\omega)\,T^{s}_{ijk} + \omega\,"
                           r"\frac{c_x\,(T^{s+1}_{i-1} + T^{s}_{i+1}) + c_y\,(T^{s+1}_{j-1} + T^{s}_{j+1})"
                           r" + c_z\,(T^{s+1}_{k-1} + T^{s}_{k+1})}{2\,(c_x + c_y + c_z)},\quad c_x = h_x^{-2}$", 24)
    f_omega = formula("omega", r"$\omega_{\mathrm{опт}} = \frac{2}{1 + \sqrt{1 - \rho_J^2}},\qquad"
                               r"\rho_J = \frac{c_x \cos\frac{\pi}{N_x} + c_y \cos\frac{\pi}{N_y} + "
                               r"c_z \cos\frac{\pi}{N_z}}{c_x + c_y + c_z}$", 24)
    f_decay = formula("decay", r"$\theta_{pq}(d) \propto \frac{\sinh k_{pq}(L_z - d)}{\sinh k_{pq} L_z}"
                               r"\approx e^{-k_{pq} d},\qquad k_{pq} = \pi\sqrt{(p/L_x)^2 + (q/L_y)^2}$", 24)

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]
    prs.core_properties.title = "Как рисунок температуры на потолке меняется с глубиной?"

    # 1. Титул
    s = prs.slides.add_slide(blank)
    background(s, DARK)
    text(s, M, 0.9, 5.8, 0.4, "ВЫЧИСЛИТЕЛЬНАЯ МАТЕМАТИКА · PDE-SOLVER", size=14, bold=True,
         color=RGBColor(0xF6, 0xA3, 0x52))
    text(s, M, 1.45, 5.6, 2.8, "Как рисунок температуры на потолке меняется с глубиной?",
         size=40, bold=True, color=WHITE, spacing=1.0, name="Title")
    text(s, M, 4.45, 5.4, 1.4, ["Стационарное поле температуры в комнате 4 × 3 × 2,6 м:",
                                "уравнение Лапласа, схема «крест», метод верхней релаксации"],
         size=18, color=RGBColor(0xE8, 0xDF, 0xD6))
    text(s, M, 6.45, 5.6, 0.4, "Интерактивный стенд на Dash и Plotly", size=14,
         color=RGBColor(0xB9, 0xA9, 0xA8))
    card(s, 6.45, 1.95, 6.3, 3.62, color=RGBColor(0xFB, 0xF7, 0xF0))
    picture(s, FIG / "app.png", 6.55, 2.05, 6.1, 3.42)
    notes(s, "Вопрос доклада: что остаётся от сложного рисунка нагрева потолка на разной глубине "
             "комнаты. Справа — работающее приложение, которое я покажу вживую.")

    # 2. Постановка
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Постановка: стены и пол 20 °C, потолок с рисунком")
    framed(s, FIG / "scheme.png", M, 1.45, 5.6, 5.45)
    text(s, 6.6, 1.5, 6.1, 0.5, "Внутри комнаты  ΔT = 0", size=22, bold=True)
    text(s, 6.6, 2.05, 6.1, 0.5, "Нормированные координаты u = x / Lx, v = y / Ly", size=16, color=INK_2)
    picture(s, f_ceiling, 6.6, 2.6, 6.1, 0.75, align="left")
    picture(s, f_gauss, 6.6, 3.45, 6.1, 0.85, align="left")
    card(s, 6.6, 4.6, 6.1, 2.3)
    text(s, 6.85, 4.78, 5.7, 2.0, [
        [("По умолчанию", {"bold": True, "size": 17, "space_after": 6})],
        "A = 60 °C, волны m = n = 2",
        "Пятно 1: центр (0,33; 0,55), ширины 0,16 и 0,22",
        "Пятно 2: центр (0,72; 0,35), ширины 0,13 и 0,17",
        "Множитель sin²πu·sin²πv сводит потолок к 20 °C у стен",
    ], size=16, spacing=1.2)
    notes(s, "Задача Дирихле для уравнения Лапласа. Граничные данные непрерывны: у стен потолок плавно "
             "переходит в 20 °C.")

    # 3. Метод
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Метод: семиточечный «крест» и верхняя релаксация")
    text(s, M, 1.45, 7.6, 0.4, "Схема второго порядка (лекция 14, Лобанов и Петров)",
         size=16, color=INK_2)
    picture(s, f_scheme, M, 1.95, 7.7, 0.75, align="left")
    text(s, M, 3.0, 7.6, 0.4, "SOR: обход узлов как в методе Зейделя, ω — параметр релаксации",
         size=16, color=INK_2)
    picture(s, f_sor, M, 3.5, 7.7, 0.75, align="left")
    text(s, M, 4.55, 7.6, 0.4, "Оптимальный ω — по спектральному радиусу метода Якоби", size=16, color=INK_2)
    picture(s, f_omega, M, 5.05, 7.7, 0.85, align="left")
    text(s, M, 6.2, 7.6, 0.7, "Узлы одной плоскости i + j + k = const обновляются вместе: их соседи лежат "
                               "на соседних плоскостях, поэтому порядок совпадает с поточечным обходом.",
         size=14, color=INK_2)
    card(s, 8.75, 1.45, 3.98, 5.45)
    stat(s, 9.05, 1.7, 3.5, f"{g['nx']} × {g['ny']} × {g['nz']}", "шагов сетки, h = 0,1 м")
    stat(s, 9.05, 3.35, 3.5, f"{g['unknowns']:,}".replace(",", " "), "неизвестных в системе")
    stat(s, 9.05, 5.0, 3.5, fmt(g["optimal_omega"], 3), f"оптимальный ω; ρ Якоби = {fmt(g['jacobi_radius'], 4)}",
         color=HEAT)
    notes(s, "Метод Зейделя — частный случай SOR при ω = 1. Оптимальный параметр берём из теоремы Янга.")

    # 4. Сходимость
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    ratio = jac["iterations"] / sor["iterations"]
    title(s, f"SOR сходится в {ratio:.0f} раз быстрее метода Якоби")
    framed(s, FIG / "convergence.png", M, 1.95, 7.0, 3.95)
    text(s, 7.95, 1.45, 4.8, 0.5, f"Порог невязки 10⁻⁸, сетка {g['nx']} × {g['ny']} × {g['nz']}",
         size=15, color=INK_2)
    table(s, 7.95, 1.95, 4.78, [
        ["Метод", "Итераций", "Оценка", "Время, с"],
        ["Якоби", jac["iterations"], jac["predicted"], fmt(jac["seconds"], 2)],
        ["Зейдель", sei["iterations"], sei["predicted"], fmt(sei["seconds"], 2)],
        ["SOR", sor["iterations"], sor["predicted"], fmt(sor["seconds"], 2)],
    ], [1.3, 1.3, 1.08, 1.1])
    text(s, 7.95, 4.05, 4.78, 2.9, [
        [("Зейдель вдвое быстрее Якоби: ", {"bold": True}), ("ρ(Зейдель) = ρ(Якоби)², как в теории.", {})],
        [("SOR: ", {"bold": True}), (f"число итераций растёт как N, а не N²; при ω = 1,5 нужно "
                                       f"{next(o['iterations'] for o in r['omega_scan'] if o['omega'] == 1.5)}"
                                       f" итераций, при ω = 1,95 — "
                                       f"{next(o['iterations'] for o in r['omega_scan'] if o['omega'] == 1.95)}.", {})],
        [("Оценка: ", {"bold": True}), ("ln(1/ε) / ln(1/ρ) по спектральному радиусу.", {})],
    ], size=15, spacing=1.15)
    notes(s, "Все три метода сходятся к одному решению: отклонение от прямого решения методом Фурье "
             "меньше 10⁻⁴ °C.")

    # 5. Проверки
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    order = grids[-1]["order"]
    title(s, "Проверки: границы точны, второй порядок")
    rows = [["Шаг h, м", "Сетка", "Ошибка, °C", "Разность с грубой, °C", "Порядок"]]
    for row in grids:
        rows.append([fmt(row["h"], 2), row["grid"], fmt(row["max_error_vs_fourier"], 4),
                     fmt(row["max_diff_vs_coarser"], 4) if "max_diff_vs_coarser" in row else "—",
                     fmt(row["order"], 2) if "order" in row else "—"])
    table(s, M, 1.55, 7.6, rows, [1.25, 1.65, 1.45, 2.15, 1.1])
    text(s, M, 3.6, 7.6, 1.5, [
        "Ошибка — максимум отклонения от решения дифференциальной задачи рядом Фурье "
        "(метод собственных функций).",
        "При вдвое меньшем шаге ошибка падает примерно в 4 раза — второй порядок схемы.",
    ], size=15, color=INK_2, spacing=1.2)
    card(s, M, 5.3, 7.6, 1.6)
    text(s, M + 0.25, 5.45, 7.1, 1.4, [
        [("Сеточный принцип максимума: ", {"bold": True}),
         (f"внутри {fmt(checks['interior_min'], 2)} … {fmt(checks['interior_max'], 1)} °C, "
          f"потолок до {fmt(checks['ceiling_max'], 1)} °C.", {})],
        [("Вложенные сетки: ", {"bold": True}),
         ("значения в общих узлах h = 0,1 и 0,05 м различаются меньше чем на "
          f"{fmt(grids[-1]['max_diff_vs_coarser'], 3)} °C.", {})],
    ], size=15, spacing=1.2)
    card(s, 8.75, 1.55, 3.98, 5.35)
    stat(s, 9.05, 1.8, 3.5, f"{checks['walls_and_floor_max_dev']:.0f} °C", "отклонение от 20 °C на полу и стенах")
    stat(s, 9.05, 3.5, 3.5, f"{checks['ceiling_max_dev']:.0f} °C", "отклонение от формулы на потолке")
    stat(s, 9.05, 5.2, 3.5, fmt(order, 2), "порядок сходимости по сетке (теория — 2)", color=HEAT)
    notes(s, "Граничные значения записаны в сеточную функцию явно и не меняются итерациями.")

    # 6. Приложение
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Четыре связанных вида на общей шкале °C")
    framed(s, FIG / "room-3d.png", M, 1.45, 6.4, 5.45, caption="3D: потолок, два среза и линия профиля")
    framed(s, FIG / "ceiling-map.png", 7.2, 1.45, 5.53, 2.7, pad=0.08,
           caption="Карта потолка: маркер пятна — джойстик")
    framed(s, FIG / "vslice.png", 7.2, 4.3, 3.4, 2.6, pad=0.08, caption="Вертикальный срез")
    framed(s, FIG / "profile.png", 10.75, 4.3, 1.98, 2.6, pad=0.08, caption="Профиль T(z)")
    notes(s, "Карта потолка — джойстик пятна; щелчок выбирает вертикаль профиля. Срезы двигаются "
             "одновременно в 3D и на 2D-картах, поле при этом не пересчитывается.")

    # 7. Ответ на вопрос
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, f"Мелкий узор гаснет за {fmt(wave['depth_10'], 1)} м, пятна видны до "
             f"{fmt(spot1['depth_10'], 1)} м")
    framed(s, FIG / "slices-grid.png", M, 1.45, 6.2, 5.45)
    framed(s, FIG / "depth-decay.png", 7.0, 1.45, 5.73, 3.45, pad=0.08)
    picture(s, f_decay, 7.05, 5.1, 5.6, 0.62, align="left")
    text(s, 7.05, 5.9, 5.65, 1.0, [
        f"Узор m = n = 2: k ≈ {fmt(decay['wave_k'], 1)} м⁻¹, 10 % на глубине {fmt(decay['wave_depth_10_theory'], 2)} м "
        f"по теории и {fmt(wave['depth_10'], 2)} м в расчёте.",
    ], size=15, color=INK_2, spacing=1.15)
    notes(s, "Каждая гармоника потолка затухает как sinh(k(Lz − d))/sinh(kLz). Чем мельче рисунок, "
             "тем больше k и тем быстрее он исчезает. Широкие пятна несут низкие гармоники и проникают глубже.")

    # 8. Живой показ
    s = prs.slides.add_slide(blank)
    background(s, WHITE)
    title(s, "Живой показ: четыре действия на стенде")
    steps = [
        ("Передвинуть пятно 1", "Перетащить маркер на карте потолка в (2,2; 2,0) м — карта обновляется на лету"),
        ("Изменить интенсивность", "A: 60 → 85 °C. После отпускания SOR пересчитывает поле за доли секунды"),
        ("Опустить срез", "Горизонтальный срез 2,3 → 1,6 м: он движется и в 3D, и на карте"),
        ("Сравнить поле", "Волны исчезли, пятно осталось; профиль под пятном — на той же шкале"),
    ]
    for i, (head, body) in enumerate(steps):
        y = 1.55 + i * 1.33
        badge(s, M, y, str(i + 1))
        text(s, M + 0.75, y - 0.02, 4.6, 0.4, head, size=19, bold=True)
        text(s, M + 0.75, y + 0.42, 4.6, 0.8, body, size=15, color=INK_2, spacing=1.1)
    text(s, 6.15, 1.42, 3.2, 0.3, "До", size=14, bold=True, color=MUTED)
    text(s, 9.5, 1.42, 3.2, 0.3, "После", size=14, bold=True, color=HEAT)
    framed(s, FIG / "ceiling-map.png", 6.15, 1.75, 3.2, 2.5, pad=0.06)
    framed(s, FIG / "demo-ceiling-map.png", 9.5, 1.75, 3.2, 2.5, pad=0.06)
    framed(s, FIG / "hslice.png", 6.15, 4.4, 3.2, 2.5, pad=0.06)
    framed(s, FIG / "demo-hslice.png", 9.5, 4.4, 3.2, 2.5, pad=0.06)
    notes(s, "Перед показом нажать «Сбросить». Порядок: пятно, интенсивность, срез, сравнение профиля.")

    # 9. Выводы
    s = prs.slides.add_slide(blank)
    background(s, DARK)
    text(s, M, 0.55, W - 2 * M, 0.9, "Выводы", size=36, bold=True, color=WHITE, name="Title")
    points = [
        ("Рисунок сглаживается с глубиной",
         f"Узор m = n = 2 теряет 90 % амплитуды за {fmt(wave['depth_10'], 2)} м, узкое пятно — за "
         f"{fmt(spot2['depth_10'], 2)} м, широкое — за {fmt(spot1['depth_10'], 2)} м. Ниже середины комнаты "
         "поле почти не зависит от деталей потолка."),
        ("Теория совпадает с расчётом",
         "Гармоника потолка затухает как exp(−kd): чем мельче деталь, тем больше k и тем ближе к потолку она гаснет."),
        ("SOR — метод для интерактива",
         f"{sor['iterations']} итераций против {jac['iterations']} у Якоби и {sei['iterations']} у Зейделя; "
         "с прошлым полем как начальным приближением пересчёт занимает доли секунды."),
        ("Решение проверено",
         f"Границы выполнены точно, ошибка относительно ряда Фурье убывает со вторым порядком ({fmt(order, 2)})."),
    ]
    for i, (head, body) in enumerate(points):
        x = M + (i % 2) * 6.2
        y = 1.75 + (i // 2) * 2.55
        card(s, x, y, 5.9, 2.3, color=RGBColor(0x43, 0x25, 0x30))
        badge(s, x + 0.3, y + 0.3, str(i + 1), d=0.5, size=18)
        text(s, x + 1.0, y + 0.3, 4.7, 0.5, head, size=20, bold=True, color=WHITE)
        text(s, x + 1.0, y + 0.85, 4.65, 1.4, body, size=15, color=RGBColor(0xE8, 0xDF, 0xD6), spacing=1.15)
    notes(s, "Ответ на вопрос доклада: с глубиной остаются только крупные черты нагрева.")

    OUT.mkdir(exist_ok=True)
    path = OUT / "PDE-Solver.pptx"
    prs.save(path)
    print("Сохранено:", path.relative_to(HERE))


if __name__ == "__main__":
    build()

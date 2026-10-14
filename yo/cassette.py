"""Кассета вместо кота: анимация и эквалайзер оверлея.

Здесь только геометрия: каждый кадр — список фигур (многоугольники, овалы,
линии). Tk-оверлей и превью на PIL рисуют один и тот же список, поэтому
анимацию можно проверить без окна.

Оверлей прозрачен по ключу #00FF01 без полупрозрачности, поэтому затухание
сделано уменьшением, а не альфой, и ни один цвет не близок к ключу.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# Режимы кассеты.
STOPPED = "stopped"  # нет микрофона, подсказка или ошибка: стоит, глаза закрыты
WAIT = "wait"  # микрофон ещё открывается: катушки ползут, REC не горит
REC = "rec"  # Ёхо слушает: катушки крутятся от голоса, REC мигает
BUSY = "busy"  # загрузка модели или перевода: быстрая перемотка

BODY = "#f59e0b"
BODY_DARK = "#b45309"
OUTLINE = "#3b2410"
LABEL = "#fef3c7"
LABEL_STRIPE = "#f43f5e"
LABEL_STRIPE_2 = "#fb923c"
WINDOW = "#1c1917"
TAPE = "#6b3f1d"
TAPE_SHINE = "#a16207"
REEL = "#f5f5f4"
HUB = "#292524"
REC_ON = "#f43f5e"
REC_OFF = "#57534e"
MOUTH = "#7c2d12"
NOTE = ("#fde68a", "#fb7185", "#fdba74")

EQ_BARS = 19
EQ_BAR_W = 4.0
EQ_GAP = 3.0
EQ_LOW = (245, 158, 11)  # тихо — янтарь
EQ_HIGH = (244, 63, 94)  # громко — розовый
EQ_IDLE = "#78624a"
EQ_CAP = "#fde68a"

TAPE_CYCLE_SEC = 45.0  # столько «играет» сторона, потом перемотка
REWIND_SEC = 2.2


@dataclass
class Shape:
    kind: str  # poly | oval | line
    points: list[float]
    fill: str = ""
    outline: str = ""
    width: float = 1.0


@dataclass
class _Note:
    x: float
    y: float
    vx: float
    life: float
    color: str
    tilt: float


@dataclass
class CassetteAnim:
    """Состояние анимации. update() раз в кадр, shapes() — что рисовать."""

    t: float = 0.0
    mode: str = WAIT
    loud: float = 0.0  # сглаженная громкость голоса 0..1
    reel_angle: float = 0.0
    reel_speed: float = 0.0  # оборотов в секунду
    tape: float = 0.0  # 0 — вся лента слева, 1 — справа
    rewinding: bool = False
    blink_at: float = 3.0
    eyelid: float = 0.0  # 0 открыто, 1 закрыто
    bounce: float = 0.0
    bounce_v: float = 0.0
    notes: list[_Note] = field(default_factory=list)
    _note_acc: float = 0.0
    rng: random.Random = field(default_factory=lambda: random.Random(7))

    def update(self, dt: float, mode: str, loud: float) -> None:
        dt = max(0.0, min(0.1, float(dt)))
        self.t += dt
        self.mode = mode
        target = max(0.0, min(1.0, float(loud))) if mode == REC else 0.0
        # Быстрая атака, медленный спад — рот и прыжки не дрожат.
        k = 0.5 if target > self.loud else 0.12
        self.loud += (target - self.loud) * min(1.0, k * dt * 60.0)

        if mode == REC:
            if self.rewinding:
                want = -5.0
            else:
                want = 0.55 + 2.6 * self.loud
        elif mode == BUSY:
            want = 4.0
        elif mode == WAIT:
            want = 0.2
        else:
            want = 0.0
        self.reel_speed += (want - self.reel_speed) * min(1.0, 6.0 * dt)
        self.reel_angle = (self.reel_angle + self.reel_speed * dt * 360.0) % 360.0

        if mode == REC:
            if self.rewinding:
                self.tape -= dt / REWIND_SEC
                if self.tape <= 0.0:
                    self.tape = 0.0
                    self.rewinding = False
            else:
                self.tape += dt * (0.4 + 1.6 * self.loud) / TAPE_CYCLE_SEC
                if self.tape >= 1.0:
                    self.tape = 1.0
                    self.rewinding = True
        elif mode == BUSY:
            self.tape = (self.tape + dt / 8.0) % 1.0

        # Моргание раз в 3–6 секунд; во сне глаза закрыты.
        if mode == STOPPED:
            lid = 1.0
        else:
            since = self.t - self.blink_at
            if since > 0.18:
                self.blink_at = self.t + 3.0 + self.rng.random() * 3.0
                since = -1.0
            lid = 1.0 - abs(since / 0.09 - 1.0) if 0.0 <= since <= 0.18 else 0.0
        self.eyelid += (lid - self.eyelid) * min(1.0, 30.0 * dt)

        # Пружина: громкий слог подбрасывает кассету.
        kick = self.loud * 9.0 if mode == REC else 0.0
        self.bounce_v += (-(self.bounce) * 160.0 - self.bounce_v * 14.0 + kick * 30.0) * dt
        self.bounce += self.bounce_v * dt
        self.bounce = max(-6.0, min(6.0, self.bounce))

        for note in self.notes:
            note.life -= dt / 1.6
            note.y -= dt * 26.0
            note.x += note.vx * dt
        self.notes = [n for n in self.notes if n.life > 0.0]
        if mode == REC and self.loud > 0.25 and not self.rewinding:
            self._note_acc += dt * (0.8 + 3.0 * self.loud)
            while self._note_acc >= 1.0 and len(self.notes) < 6:
                self._note_acc -= 1.0
                side = -1.0 if self.rng.random() < 0.5 else 1.0
                self.notes.append(
                    _Note(
                        x=100.0 + side * (40.0 + self.rng.random() * 18.0),
                        y=34.0,
                        vx=side * (6.0 + self.rng.random() * 10.0),
                        life=1.0,
                        color=self.rng.choice(NOTE),
                        tilt=side * 0.25,
                    )
                )
        else:
            self._note_acc = 0.0

    def rec_lit(self) -> bool:
        if self.mode != REC:
            return False
        if self.loud > 0.25:
            return True
        return (self.t % 1.0) < 0.6

    def shapes(self, cx: float = 100.0, top: float = 4.0, height: float = 118.0) -> list[Shape]:
        """Кассета по центру cx в полосе [top, top + height]."""
        out: list[Shape] = []
        w, h = 140.0, 88.0
        base_y = top + height - 8.0  # низ кассеты
        breathe = math.sin(self.t * 2.0 * math.pi * 0.45) * (1.2 if self.mode != STOPPED else 0.4)
        lift = -max(0.0, self.bounce) * 1.4 + breathe
        squash = 1.0 - 0.05 * max(0.0, -self.bounce) / 6.0 + 0.04 * self.loud
        sx = 1.0 + (1.0 - squash) * 0.6
        tilt = math.sin(self.t * 1.7) * 1.5 * self.loud
        y0 = base_y - h

        def tf(px: float, py: float) -> tuple[float, float]:
            # Сжатие к низу, лёгкий наклон и подпрыгивание.
            dx = (px - cx) * sx
            dy = (py - base_y) * squash
            ang = math.radians(tilt)
            rx = dx * math.cos(ang) - dy * math.sin(ang)
            ry = dx * math.sin(ang) + dy * math.cos(ang)
            return cx + rx, base_y + ry + lift

        def poly(pts, fill, outline=OUTLINE, width=1.5):
            flat: list[float] = []
            for px, py in pts:
                qx, qy = tf(px, py)
                flat += [qx, qy]
            out.append(Shape("poly", flat, fill, outline, width))

        def oval(ox, oy, rx, ry, fill, outline=OUTLINE, width=1.5):
            pts = [(ox + rx * math.cos(a), oy + ry * math.sin(a)) for a in _angles(24)]
            poly(pts, fill, outline, width)

        def line(pts, fill, width):
            flat: list[float] = []
            for px, py in pts:
                qx, qy = tf(px, py)
                flat += [qx, qy]
            out.append(Shape("line", flat, fill, "", width))

        # Тень под кассетой сжимается, когда она в воздухе.
        sh = 1.0 - min(0.5, max(0.0, self.bounce) / 10.0)
        out.append(
            Shape(
                "oval",
                [cx - 56 * sh, base_y + 2, cx + 56 * sh, base_y + 7],
                "#1a1410",
                "",
                0,
            )
        )

        x0 = cx - w / 2
        poly(_rrect(x0, y0, w, h, 10), BODY, OUTLINE, 2.0)
        # Винтики по углам.
        for sx_, sy_ in ((x0 + 8, y0 + 8), (x0 + w - 8, y0 + 8), (x0 + 8, y0 + h - 8), (x0 + w - 8, y0 + h - 8)):
            oval(sx_, sy_, 2.2, 2.2, BODY_DARK, OUTLINE, 1.0)
        # Наклейка с полосками.
        lx, ly, lw, lh = x0 + 14, y0 + 9, w - 28, 50
        poly(_rrect(lx, ly, lw, lh, 6), LABEL, OUTLINE, 1.5)
        poly(_rrect(lx + 4, ly + 4, lw - 8, 5, 2), LABEL_STRIPE, "", 0)
        poly(_rrect(lx + 4, ly + 11, lw - 8, 3, 1.5), LABEL_STRIPE_2, "", 0)

        # Окно с лентой: катушки — это глаза.
        wx, wy, ww, wh = cx - 40, ly + 18, 80, 24
        poly(_rrect(wx, wy, ww, wh, 12), WINDOW, OUTLINE, 1.5)
        lcx, rcx, rcy = cx - 24, cx + 24, wy + wh / 2
        r_min, r_max = 6.0, 10.5
        left_r = r_min + (r_max - r_min) * (1.0 - self.tape)
        right_r = r_min + (r_max - r_min) * self.tape
        line([(lcx, rcy + left_r - 0.5), (rcx, rcy + right_r - 0.5)], TAPE, 2.0)
        # Блик бегущей ленты.
        run = (self.reel_angle / 360.0) % 1.0
        hx = lcx + (rcx - lcx) * run
        line([(hx - 3, rcy + (left_r + right_r) / 2 - 0.5), (hx + 3, rcy + (left_r + right_r) / 2 - 0.5)], TAPE_SHINE, 2.0)
        for rx_, r_ in ((lcx, left_r), (rcx, right_r)):
            oval(rx_, rcy, r_, r_, TAPE, "", 0)
            oval(rx_, rcy, 5.2, 5.2, REEL, OUTLINE, 1.0)
            for k in range(3):
                a = math.radians(self.reel_angle + k * 120.0)
                tx, ty = rx_ + math.cos(a) * 3.6, rcy + math.sin(a) * 3.6
                poly([(tx - 1.1, ty - 1.1), (tx + 1.1, ty - 1.1), (tx + 1.1, ty + 1.1), (tx - 1.1, ty + 1.1)], HUB, "", 0)
            oval(rx_, rcy, 1.6, 1.6, HUB, "", 0)
        # Веки: наклейка наползает на окно сверху.
        if self.eyelid > 0.04:
            lid_h = wh * min(1.0, self.eyelid)
            poly(_rrect(wx, wy, ww, max(2.0, lid_h), min(12.0, lid_h / 2)), LABEL, OUTLINE, 1.2)
            if self.eyelid > 0.85:
                for ex in (lcx, rcx):
                    line(_arc(ex, wy + lid_h - 3, 6, 0.0, math.pi, 8), OUTLINE, 1.6)

        # Рот под окном открывается от голоса.
        my = wy + wh + 4.5
        if self.mode == REC and self.loud > 0.06:
            open_h = 1.5 + 5.5 * self.loud
            oval(cx, my + open_h / 2, 5 + 2 * self.loud, open_h / 2 + 0.8, MOUTH, OUTLINE, 1.0)
        else:
            line(_arc(cx, my - 1.5, 5, 0.15 * math.pi, 0.85 * math.pi, 8), MOUTH, 1.8)

        # Низ кассеты с отверстиями.
        poly([(cx - 40, y0 + h), (cx - 34, y0 + h - 18), (cx + 34, y0 + h - 18), (cx + 40, y0 + h)], BODY_DARK, OUTLINE, 1.5)
        for hx_ in (cx - 20, cx + 20):
            oval(hx_, y0 + h - 8, 2.6, 2.6, WINDOW, "", 0)
        for hx_ in (cx - 6, cx + 6):
            oval(hx_, y0 + h - 6, 1.6, 1.6, WINDOW, "", 0)

        # REC в правом верхнем углу.
        rec_color = REC_ON if self.rec_lit() else REC_OFF
        pulse = 1.0 + (0.25 * self.loud if self.mode == REC else 0.0)
        oval(x0 + w - 4, y0 - 2, 5.0 * pulse, 5.0 * pulse, rec_color, OUTLINE, 1.2)

        # Ноты летят от кассеты, пока человек говорит.
        for note in self.notes:
            s = 0.4 + 0.6 * note.life
            out.extend(_note(note.x - 100.0 + cx, note.y - 40.0 + top + 18.0 + lift, s, note.color, note.tilt))
        return out


def _angles(n: int) -> list[float]:
    return [2.0 * math.pi * i / n for i in range(n)]


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def _rrect(x: float, y: float, w: float, h: float, r: float) -> list[tuple[float, float]]:
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    pts: list[tuple[float, float]] = []
    corners = ((x + w - r, y + r, -0.5), (x + w - r, y + h - r, 0.0), (x + r, y + h - r, 0.5), (x + r, y + r, 1.0))
    for ccx, ccy, start in corners:
        for i in range(7):
            a = math.pi * (start + 0.5 * i / 6)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def _note(x: float, y: float, s: float, color: str, tilt: float) -> list[Shape]:
    s *= 1.5
    head = [x - 4 * s, y + 6 * s, x + 2 * s, y + 10 * s]
    stem = [x + 1.5 * s, y + 8 * s, x + 1.5 * s + tilt * 4, y - 6 * s]
    flag = [x + 1.5 * s + tilt * 4, y - 6 * s, x + 6 * s + tilt * 4, y - 2 * s]
    return [
        Shape("oval", head, color, "", 0),
        Shape("line", stem, color, "", max(1.2, 1.8 * s / 1.5)),
        Shape("line", flag, color, "", max(1.2, 1.8 * s / 1.5)),
    ]


@dataclass
class Equalizer:
    """Симметричный эквалайзер: середина — низкие частоты голоса, края — высокие."""

    bars: list[float] = field(default_factory=lambda: [0.0] * EQ_BARS)
    caps: list[float] = field(default_factory=lambda: [0.0] * EQ_BARS)
    t: float = 0.0

    def update(self, dt: float, loud: float, bands: list[float] | None, active: bool) -> None:
        dt = max(0.0, min(0.1, float(dt)))
        self.t += dt
        loud = max(0.0, min(1.0, float(loud))) if active else 0.0
        bands = list(bands or [])
        peak = max(bands) if bands else 0.0
        half = EQ_BARS // 2
        for i in range(EQ_BARS):
            d = abs(i - half)
            if bands and peak > 1e-6:
                bi = min(len(bands) - 1, int(round(d * (len(bands) - 1) / max(1, half))))
                tone = bands[bi] / peak
            else:
                tone = 1.0 - d / (half + 1.0)
            target = loud * (0.3 + 0.7 * tone) * (1.0 - 0.35 * d / (half + 1.0))
            if active and loud < 0.04:
                # Тишина: еле заметное дыхание, чтобы было видно, что Ёхо слушает.
                target = 0.05 + 0.03 * (0.5 + 0.5 * math.sin(self.t * 3.0 + i * 0.55))
            k = 0.6 if target > self.bars[i] else 0.16
            self.bars[i] += (target - self.bars[i]) * min(1.0, k * dt * 60.0)
            if self.bars[i] >= self.caps[i]:
                self.caps[i] = self.bars[i]
            else:
                self.caps[i] = max(self.bars[i], self.caps[i] - dt * 0.6)

    def width(self) -> float:
        return EQ_BARS * EQ_BAR_W + (EQ_BARS - 1) * EQ_GAP

    def shapes(self, x: float, y: float, height: float) -> list[Shape]:
        out: list[Shape] = []
        mid = y + height / 2.0
        for i, amp in enumerate(self.bars):
            bx = x + i * (EQ_BAR_W + EQ_GAP)
            h = max(3.0, min(1.0, amp) * height * 0.92)
            color = _mix(EQ_LOW, EQ_HIGH, min(1.0, amp * 1.4)) if amp > 0.1 else EQ_IDLE
            out.append(Shape("poly", _flat(_rrect(bx, mid - h / 2, EQ_BAR_W, h, 2.0)), color, "", 0))
            cap = self.caps[i]
            if cap > 0.14 and cap - amp > 0.03:
                ch = min(1.0, cap) * height * 0.92 / 2.0 + 2.5
                for cy in (mid - ch, mid + ch - 1.6):
                    out.append(Shape("poly", _flat(_rrect(bx, cy, EQ_BAR_W, 1.6, 0.8)), EQ_CAP, "", 0))
        return out


def _flat(pts: list[tuple[float, float]]) -> list[float]:
    flat: list[float] = []
    for px, py in pts:
        flat += [px, py]
    return flat


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> str:
    t = max(0.0, min(1.0, t))
    r, g, bl = (int(round(a[k] + (b[k] - a[k]) * t)) for k in range(3))
    return f"#{r:02x}{g:02x}{bl:02x}"


def mode_for(*, visible_live: bool, status: str, hint: str, mic_missing: bool) -> str:
    """Какой режим кассеты показать по состоянию оверлея."""
    status = (status or "").strip()
    if mic_missing or (hint or "").strip() or status.startswith("ошибка"):
        return STOPPED
    if status.startswith("загрузка") or status in {"перевод"}:
        return BUSY
    return REC if visible_live else WAIT

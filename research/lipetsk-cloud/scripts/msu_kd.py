"""Суточный аналог Erbs / Reindl-2 по актинометрии MOSCOW UNIV. (WRDC).

Не часовая формула. Вход — суточный индекс ясности Kt = H/H0
и sin высоты Солнца в полдень. Выход — Kd = Hd/H, затем обрезать в [0, 1].

H0: Duffie & Beckman, Gsc = 1367 Вт/м², φ = 55.70° с.ш.
"""

from __future__ import annotations

import math

K1 = 0.23
K2 = 0.65
LAT_DEG = 55.70
GSC = 1367.0


def _clip(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def msu_erbs(kt: float) -> float:
    """Только Kt, как суточный Эрбс."""
    if kt <= K1:
        kd = 1.0169 - 0.1571 * kt
    elif kt <= K2:
        kd = 0.9556 + 1.0802 * kt - 4.8082 * kt**2 + 2.6467 * kt**3
    else:
        kd = 1.2851 - 1.4514 * kt
    return _clip(kd)


def msu_reindl(kt: float, sin_alpha_noon: float) -> float:
    """Kt и sin высоты Солнца в полдень. Лучше МГУ-Эрбса на независимых годах."""
    s = sin_alpha_noon
    if kt <= K1:
        kd = 1.0349 - 0.1636 * kt - 0.0420 * s
    elif kt <= K2:
        kd = 1.4718 - 1.4351 * kt - 0.2363 * s
    else:
        kd = 1.4146 - 1.4475 * kt - 0.2004 * s
    return _clip(kd)


def sin_alpha_noon(day_of_year: int, lat_deg: float = LAT_DEG) -> float:
    lat = math.radians(lat_deg)
    dec = math.radians(23.45) * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))
    return min(1.0, max(0.0, math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec)))


def h0_mj(day_of_year: int, lat_deg: float = LAT_DEG) -> float:
    lat = math.radians(lat_deg)
    dec = math.radians(23.45) * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))
    e0 = 1.0 + 0.033 * math.cos(math.radians(360.0 * day_of_year / 365.0))
    arg = min(1.0, max(-1.0, -math.tan(lat) * math.tan(dec)))
    ws = math.acos(arg)
    geo = math.cos(lat) * math.cos(dec) * math.sin(ws) + ws * math.sin(lat) * math.sin(dec)
    return (24.0 * 3600.0 / math.pi) * GSC * e0 * geo / 1_000_000.0

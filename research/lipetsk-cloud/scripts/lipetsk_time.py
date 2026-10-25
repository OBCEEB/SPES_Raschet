#!/usr/bin/env python3
"""Шкалы времени исходных файлов Конь-Колодезя и аэропорта Липецк.

Весь расчёт ведётся в MSK (UTC+3, без перехода на летнее время).
Метки в исходных файлах — UTC:
  - минутки пиранометра yymmdd.csv: суточный ход GHI совпадает с геометрией
    Солнца только после сдвига +3 ч (audit/timing_impact.json);
  - ASMG c_YYYYMM.csv: смены облачности совпадают с METAR UUOL (UTC)
    по меткам файла (docs/MASTER_single_agent_plan.md, §1.2).
Перевод делать один раз, при чтении исходного файла.
"""

from __future__ import annotations

from datetime import datetime, timedelta

PYRANOMETER_FILE_TZ_H = 0.0
ASMG_FILE_TZ_H = 0.0
MSK_H = 3.0


def pyranometer_to_msk(t_file: datetime) -> datetime:
    return t_file + timedelta(hours=MSK_H - PYRANOMETER_FILE_TZ_H)


def asmg_to_msk(t_file: datetime) -> datetime:
    return t_file + timedelta(hours=MSK_H - ASMG_FILE_TZ_H)

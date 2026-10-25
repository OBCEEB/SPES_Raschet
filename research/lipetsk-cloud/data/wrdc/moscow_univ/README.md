# MOSCOW UNIV. — архив WRDC

Станция метеообсерватории МГУ, в каталоге WRDC без индекса WMO.

| Поле | Значение |
| --- | --- |
| Название | MOSCOW UNIV. |
| Широта | 55°42'N (55.70°) |
| Долгота | 37°30'E (37.50°) |
| Высота | 192 м |
| Приборы | global TT/M, diffuse TT/M, balance BT/M, sunshine SS/C |

Источник: [WRDC](http://wrdc.mgo.rssi.ru/wrdccgi/protect.exe?data_list_full_protected/root_index_ru_2025.html), дерево `data_list_full_protected` (страницы с гиперссылками на годы; публичный `data_list` года только текстом).

- Рассеянная (DHI): [каталог](http://wrdc.mgo.rssi.ru/wrdccgi/protect.exe?data_list_full_protected/d/russia/moscow_univ_/moscow_univ_.html) — 1990–2025
- Суммарная, Europe (GHI): [каталог](http://wrdc.mgo.rssi.ru/wrdccgi/protect.exe?data_list_full_protected/t6/russia/moscow_univ_/moscow_univ_.html) — 1971–2025
- Флаги качества: [quality_flags](http://wrdc.mgo.rssi.ru/WWWROOTNEW_2025/WRDCCGI_new/quality_flags_ru_new.html). `F=0` — норма, не «нет данных».

Единицы исходных таблиц: **Дж/см²·сут**. В CSV продублированы МДж/м² (`/100`) и кВт·ч/м² (`/360`).

## Что лежит в папке

| Файл | Содержание |
| --- | --- |
| `csv/daily_ghi.csv` | Сутки GHI, 1971–2025 |
| `csv/daily_dhi.csv` | Сутки DHI, 1990–2025 |
| `csv/daily.csv` | Оба продукта в длинном виде |
| `csv/daily_ghi_dhi.csv` | Пересечение дат: GHI, DHI, прямая `beam = GHI − DHI`, `kd = DHI/GHI` |
| `csv/monthly.csv` | Месячные SUM/MEAN из таблиц WRDC |
| `csv/annual.csv` | Годовые суммы; пусто, если нет всех 12 месяцев |
| `csv/climatology_monthly.csv` | Средние по полным годам: GHI 1971–2024; GHI+DHI 1991–2020 и 1991–2024 |
| `models/` | МГУ-Эрбс и МГУ-Рейндл: формулы, метрики, суточный Kt/Kd |
| `raw/` | Исходные HTML каталогов и годов (повторно качать не обязательно) |

Пробелы в каталоге (не ошибки парсера):

- DHI с октября 1990
- 2022: нет сентября (и GHI, и DHI)
- 2025: в WRDC пока январь–сентябрь
- 2026 в каталоге серый, файлов нет

Полных календарных лет: GHI 53 (1971–2021, 2023–2024), оба продукта 33 (1991–2021, 2023–2024).

## Перекачать

Из корня репозитория, Python 3, без сторонних пакетов:

```bash
python3 scripts/download_wrdc_moscow_univ.py
```

Уже скачанные HTML не трогает. Chrome не нужен: `protect.exe` отдаёт те же таблицы обычным GET.

## МГУ-Эрбс и МГУ-Рейндл

Суточный `Kd(Kt)` по этому ряду, не часовой Эрбс. Формулы: [models/FORMULAS.md](models/FORMULAS.md). Переподобрать:

```bash
python3 scripts/fit_diffuse_fraction.py
```

Готовая функция: `scripts/msu_kd.py` (`msu_reindl(kt, sin_alpha_noon)`).

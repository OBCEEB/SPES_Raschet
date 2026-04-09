# SPES_Raschet

WinForms-приложение для выбора населенного пункта на карте РФ и расчета параметров солнечной инсоляции по табличным данным.

## Возможности

- выбор региона на карте и выбор населенного пункта из списка;
- отображение справочных таблиц (почасовая радиация, положение Солнца, суточные итоги);
- расчет интерполированных значений для выбранных координат;
- визуализация результатов в виде таблиц и графиков;
- фильтрация направлений на графике инсоляции.

## Технологии

- .NET 6 (`net6.0-windows7.0`)
- Windows Forms
- `System.Windows.Forms.DataVisualization` (графики)
- CSV + JSON как источники данных

## Быстрый старт

1. Установить .NET SDK 6+.
2. Перейти в папку проекта.
3. Выполнить:

```bash
dotnet build SPES_Raschet.csproj
dotnet run --project SPES_Raschet.csproj
```

## Данные

Приложение использует файлы:

- `settlements.csv`
- `regions_bounds.json`
- `DailyTotalData.csv`
- `IrradianceData.csv`
- `SunPosition_Altitude.csv`
- `SunPosition_Azimuth.csv`

Файлы автоматически копируются в output при сборке (`CopyToOutputDirectory=PreserveNewest`).

## Структура проекта

- `Form1.cs` — главная форма, карта, справочник, запуск расчетов
- `CalculationResultsForm.cs` — результаты расчета и графики
- `SettlementListForm.cs` — выбор населенного пункта
- `GeoDataHandler.cs` — загрузка геоданных и границ регионов
- `GeoProcessor.cs` — сопоставление регионов карты и справочника
- `GeoMapRenderer.cs` — отрисовка карты и hit-testing
- `SolarData.cs` — модели данных и импорт табличных данных
- `MathTools.cs` — интерполяция
- `Program.cs` — точка входа и инициализация кодировок

## Версионирование

Используется SemVer: `MAJOR.MINOR.PATCH` (см. `docs/VERSIONING.md`).

Текущая базовая версия: `0.1.0`.

## UI-сообщения

Для единообразного стиля текстов в интерфейсе используйте `docs/MESSAGE_STYLE_GUIDE.md`.

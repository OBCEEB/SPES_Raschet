using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

// =======================================================================
// 1. КЛАСС РЕЗУЛЬТАТА ЗАГРУЗКИ
// =======================================================================

/// <summary>
/// Простая модель для передачи статуса и сообщения о результате операции загрузки данных.
/// </summary>
public class LoadingResult
{
    public bool Success { get; set; }
    public string Message { get; set; } = string.Empty;

    /// <summary>
    /// Создает успешный результат загрузки.
    /// </summary>
    public static LoadingResult Ok() => new LoadingResult { Success = true, Message = "Данные успешно загружены." };

    /// <summary>
    /// Создает ошибочный результат загрузки с указанным сообщением.
    /// </summary>
    public static LoadingResult Fail(string message) => new LoadingResult { Success = false, Message = message };
}

// =======================================================================
// 2. МОДЕЛИ ДАННЫХ
// =======================================================================

/// <summary>
/// Модель для почасовой инсоляции (Таблица 1: Широта, Час, Значения по направлениям).
/// </summary>
public class IrradianceData
{
    public double Latitude { get; set; }
    public int StartHour { get; set; }
    /// <summary>Словарь, где ключ — направление (напр., "Ю пр"), значение — инсоляция (Вт*ч/м²).</summary>
    public Dictionary<string, double> Values { get; set; } = new Dictionary<string, double>();
}

/// <summary>
/// Модель для положения Солнца (Таблица 2: Высота h и Азимут Ac) по часу и долготе.
/// </summary>
public class SunPositionData
{
    public double Longitude { get; set; }
    public int StartHour { get; set; }
    public double Altitude { get; set; }  // h (Высота Солнца)
    public double Azimuth { get; set; }  // Ac (Азимут Солнца)
    public override string ToString() => $"Lon: {Longitude}, Hour: {StartHour}, h: {Altitude}° Ac: {Azimuth}°";
}

/// <summary>
/// Модель для суточных итогов горизонтальной инсоляции (Таблица 3).
/// </summary>
public class DailyTotalData
{
    public double Latitude { get; set; }
    public double DailyTotalHorizontalIrradiance { get; set; } // Сумма Вт*ч/м² за день
}

// =======================================================================
// 3. СТАТИЧЕСКОЕ ХРАНИЛИЩЕ ДАННЫХ
// =======================================================================

/// <summary>
/// Статический класс для хранения всех загруженных данных, доступных по всему приложению.
/// </summary>
public static class DataStore
{
    /// <summary>Хранилище данных почасовой инсоляции (Таблица 1).</summary>
    public static List<IrradianceData> IrradianceList { get; set; } = new List<IrradianceData>();
    /// <summary>Хранилище данных о положении Солнца (Таблица 2).</summary>
    public static List<SunPositionData> SunPositionList { get; set; } = new List<SunPositionData>();
    /// <summary>Хранилище данных суточных итогов (Таблица 3).</summary>
    public static List<DailyTotalData> DailyTotalList { get; set; } = new List<DailyTotalData>();
}

// =======================================================================
// 4. КЛАСС ИМПОРТА ДАННЫХ
// =======================================================================

/// <summary>
/// Статический класс, отвечающий за чтение, парсинг и валидацию данных из CSV-файлов.
/// </summary>
public static class DataImporter
{
    private const char Separator = ';';
    private const double MissingValue = -1.0;
    private const string MissingValueString = "-1";

    // --- Вспомогательные методы ---

    /// <summary>
    /// Безопасно парсит строку в double, используя InvariantCulture и CurrentCulture, 
    /// и обрабатывает пустые строки или "-1" как отсутствующее значение.
    /// </summary>
    private static double ParseDouble(string s)
    {
        // Значение -1 или пустая строка всегда означают отсутствие данных
        if (string.IsNullOrWhiteSpace(s) || s == MissingValueString)
        {
            return MissingValue;
        }

        // 1. Попытка парсинга с InvariantCulture (использует точку как десятичный разделитель)
        if (double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out double result))
        {
            return result;
        }

        // 2. Если не сработало, попытка парсинга с CurrentCulture (может использовать запятую)
        if (double.TryParse(s, NumberStyles.Any, CultureInfo.CurrentCulture, out result))
        {
            return result;
        }

        // Если парсинг не удался
        Debug.WriteLine($"Предупреждение: Не удалось распарсить число '{s}'. Возвращено MissingValue.");
        return MissingValue;
    }

    /// <summary>
    /// Читает все строки файла, обрабатывая ошибки "Файл не найден" и проблемы кодировки.
    /// </summary>
    private static string[] ReadFileLines(string fileName, List<string> errors)
    {
        string fullPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, fileName);

        if (!File.Exists(fullPath))
        {
            errors.Add($"Файл не найден: {fileName}");
            return new string[0];
        }

        try
        {
            // Сначала пробуем UTF-8
            var lines = File.ReadAllLines(fullPath, Encoding.UTF8);

            // Если обнаружены знаки замены ('\uFFFD'), пробуем Windows-1251
            if (lines.Length > 0 && lines[0].Contains('\uFFFD'))
            {
                lines = File.ReadAllLines(fullPath, Encoding.GetEncoding(1251));
                Debug.WriteLine($"Кодировка файла {fileName} исправлена на Windows-1251.");
            }
            return lines;
        }
        catch (Exception ex)
        {
            errors.Add($"Критическая ошибка чтения файла {fileName}. Детали: {ex.Message}");
            return new string[0];
        }
    }

    // --- Методы загрузки данных ---

    /// <summary>
    /// Парсит и загружает данные суточных итогов (Таблица 3).
    /// </summary>
    public static void LoadDailyTotalData(string[] lines)
    {
        // Предполагается, что очистка DataStore уже выполнена в LoadAllData
        if (lines.Length <= 1) return;

        foreach (var line in lines.Skip(1)) // Пропускаем заголовок
        {
            var parts = line.Split(Separator);
            if (parts.Length < 2) continue;

            double lat = ParseDouble(parts[0]);
            double total = ParseDouble(parts[1]);

            if (lat != MissingValue && total != MissingValue)
            {
                DataStore.DailyTotalList.Add(new DailyTotalData
                {
                    Latitude = lat,
                    DailyTotalHorizontalIrradiance = total
                });
            }
        }
    }

    /// <summary>
    /// Парсит таблицу положения Солнца (матрица Час x Долгота) для одного параметра (h или Ac).
    /// </summary>
    private static Dictionary<(int Hour, double Lon), double> ParseSunPositionTable(string[] lines)
    {
        var data = new Dictionary<(int Hour, double Lon), double>();
        if (lines.Length <= 1) return data;

        // Определяем долготы из заголовка (первая строка)
        var headerParts = lines[0].Split(Separator);
        var longitudes = headerParts.Skip(1).Select(s => ParseDouble(s)).Where(lon => lon != MissingValue).ToList();

        for (int i = 1; i < lines.Length; i++)
        {
            var parts = lines[i].Split(Separator);
            if (parts.Length <= 1) continue;

            // Определяем начальный час из первой колонки
            if (!int.TryParse(parts[0].Trim(), out int startHour)) continue;

            // Обходим колонки с данными
            for (int j = 1; j < parts.Length; j++)
            {
                if (j - 1 >= longitudes.Count) break; // Защита от выхода за пределы списка долгот

                double value = ParseDouble(parts[j]);
                double longitude = longitudes[j - 1];

                if (value != MissingValue)
                {
                    data.Add((startHour, longitude), value);
                }
            }
        }
        return data;
    }

    /// <summary>
    /// Загружает и объединяет данные Высоты (h) и Азимута (Ac) в единый список SunPositionData (Таблица 2).
    /// </summary>
    public static void LoadAndCombineSunPositionData(string[] altitudeLines, string[] azimuthLines)
    {
        DataStore.SunPositionList.Clear();

        var altitudeData = ParseSunPositionTable(altitudeLines);
        var azimuthData = ParseSunPositionTable(azimuthLines);

        // Объединение данных по общему ключу (Час, Долгота)
        foreach (var key in altitudeData.Keys)
        {
            if (azimuthData.TryGetValue(key, out double azimuth))
            {
                DataStore.SunPositionList.Add(new SunPositionData
                {
                    StartHour = key.Hour,
                    Longitude = key.Lon,
                    Altitude = altitudeData[key],
                    Azimuth = azimuth
                });
            }
        }
    }

    /// <summary>
    /// Парсит и загружает данные почасовой инсоляции по направлениям (Таблица 1).
    /// </summary>
    public static void LoadIrradianceData(string[] lines)
    {
        DataStore.IrradianceList.Clear();
        if (lines.Length <= 1) return;

        var headerParts = lines[0].Split(Separator);
        // Извлекаем названия направлений из заголовка, начиная с третьего столбца
        var directionKeys = headerParts.Skip(2).Select(s => s.Trim()).ToList();

        foreach (var line in lines.Skip(1)) // Пропускаем заголовок
        {
            var parts = line.Split(Separator);
            if (parts.Length < directionKeys.Count + 2) continue; // +2: Широта и Час

            double lat = ParseDouble(parts[0]);
            if (!int.TryParse(parts[1].Trim(), out int startHour)) continue;
            if (lat == MissingValue) continue;

            var dataEntry = new IrradianceData { Latitude = lat, StartHour = startHour };

            // Заполнение словаря IrradianceData.Values
            for (int i = 0; i < directionKeys.Count; i++)
            {
                double value = ParseDouble(parts[i + 2]);
                var key = directionKeys[i];

                if (value != MissingValue && !dataEntry.Values.ContainsKey(key))
                {
                    dataEntry.Values.Add(key, value);
                }
            }

            if (dataEntry.Values.Any())
            {
                DataStore.IrradianceList.Add(dataEntry);
            }
        }
    }

    // --- Главный метод загрузки ---

    /// <summary>
    /// Запускает полную загрузку всех данных из CSV-файлов.
    /// Возвращает LoadingResult, содержащий статус и сообщение для пользователя.
    /// </summary>
    public static LoadingResult LoadAllData()
    {
        // 1. Очистка хранилища перед загрузкой
        DataStore.DailyTotalList.Clear();
        DataStore.IrradianceList.Clear();
        DataStore.SunPositionList.Clear();

        var errors = new List<string>(); // Список для сбора ошибок чтения файлов

        // 2. Чтение всех файлов с проверкой на ошибки и кодировку
        var dailyTotalLines = ReadFileLines("DailyTotalData.csv", errors);
        var irradianceLines = ReadFileLines("IrradianceData.csv", errors);
        var altitudeLines = ReadFileLines("SunPosition_Altitude.csv", errors);
        var azimuthLines = ReadFileLines("SunPosition_Azimuth.csv", errors);

        // Если были ошибки на этапе чтения файлов, сразу возвращаем Fail
        if (errors.Any())
        {
            return LoadingResult.Fail("Ошибка чтения CSV файлов:\n\n" + string.Join("\n", errors));
        }

        // 3. Парсинг данных
        try
        {
            LoadDailyTotalData(dailyTotalLines);
            LoadIrradianceData(irradianceLines);
            LoadAndCombineSunPositionData(altitudeLines, azimuthLines);
        }
        catch (Exception ex)
        {
            // Ловим неожиданные ошибки парсинга (например, дубликаты ключей)
            return LoadingResult.Fail("Ошибка парсинга данных:\n\n" + ex.Message);
        }

        // 4. Финальная проверка, что данные загружены
        if (!DataStore.IrradianceList.Any() || !DataStore.SunPositionList.Any() || !DataStore.DailyTotalList.Any())
        {
            errors.Add("Внимание: Загрузка завершена, но одна или несколько таблиц пусты. Проверьте, что CSV-файлы содержат корректные данные.");
            return LoadingResult.Fail(string.Join("\n", errors));
        }

        // 5. Успех
        Debug.WriteLine($"Загрузка солнечных данных завершена успешно. Радиация: {DataStore.IrradianceList.Count}, Положение Солнца: {DataStore.SunPositionList.Count}, Суточные итоги: {DataStore.DailyTotalList.Count}");
        return LoadingResult.Ok();
    }
}
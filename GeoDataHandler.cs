using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text;
using SPES_Raschet.Services;

namespace SPES_Raschet
{
    public class SettlementData
    {
        public string Region { get; set; } = "";
        public string District { get; set; } = "";
        public string CityOrSettlement { get; set; } = "";
        public double Latitude { get; set; }
        public double Longitude { get; set; }
        public int TimeZoneOffset { get; set; }
        public int CenterFlag { get; set; }
        public override string ToString() => $"{CityOrSettlement} ({Region})";
    }

    public static class GeoDataHandler
    {
        public static List<SettlementData> SettlementList { get; private set; } = new List<SettlementData>();

        public static Dictionary<string, Dictionary<string, List<List<double>>>> RegionBoundaries { get; private set; }
            = new Dictionary<string, Dictionary<string, List<List<double>>>>();

        private const string SettlementsFileName = "settlements.csv";
        private const string RegionsBoundsFileName = "regions_bounds.json";

        private static string[] ReadAllLinesWithEncodingFallback(string path)
        {
            var lines = File.ReadAllLines(path, Encoding.UTF8);

            // If decoding produced replacement symbols, retry with Windows-1251.
            if (lines.Any(l => l.Contains('\uFFFD')))
            {
                lines = File.ReadAllLines(path, Encoding.GetEncoding(1251));
            }

            return lines;
        }

        private static string? ResolveDataFilePath(string fileName)
        {
            // Primary location for published/debug app assets.
            string baseDir = AppContext.BaseDirectory;
            string candidate = Path.Combine(baseDir, fileName);
            if (File.Exists(candidate)) return candidate;

            // Fallback to current working directory.
            candidate = Path.Combine(Environment.CurrentDirectory, fileName);
            if (File.Exists(candidate)) return candidate;

            // Fallback: try near project root when launched from IDE.
            string? dir = baseDir;
            for (int i = 0; i < 5 && !string.IsNullOrEmpty(dir); i++)
            {
                dir = Directory.GetParent(dir)?.FullName;
                if (string.IsNullOrEmpty(dir)) break;
                candidate = Path.Combine(dir, fileName);
                if (File.Exists(candidate)) return candidate;
            }

            return null;
        }

        public static void LoadSettlementData()
        {
            try
            {
                string? settlementsPath = ResolveDataFilePath(SettlementsFileName);
                if (settlementsPath == null)
                {
                    UiMessageService.Error(
                        "Ошибка данных",
                        $"Не найден файл данных: {SettlementsFileName}.\n\nПроверьте, что файл находится в папке программы.",
                        null);
                    return;
                }

                string[] lines = ReadAllLinesWithEncodingFallback(settlementsPath);

                SettlementList.Clear();
                foreach (var line in lines.Skip(1))
                {
                    var parts = line.Split(',');
                    if (parts.Length < 20) continue;

                    string regionType = parts[1].Trim();
                    string regionName = parts[2].Trim();
                    if (string.IsNullOrWhiteSpace(regionName)) continue;

                    SettlementList.Add(new SettlementData
                    {
                        Region = $"{regionType}|{regionName}",
                        District = parts[4].Trim(),
                        CityOrSettlement = !string.IsNullOrWhiteSpace(parts[6]) ? parts[6].Trim() : parts[8].Trim(),

                        // Используем NumberStyles.Any для надежности в .NET 6
                        Latitude = double.TryParse(parts[17].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double lat) ? lat : 0,
                        Longitude = double.TryParse(parts[18].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double lon) ? lon : 0,

                        TimeZoneOffset = int.TryParse(parts[16].Trim().Replace("UTC+", "").Replace("UTC", ""), out int tz) ? tz : 0,
                        CenterFlag = int.TryParse(parts[12].Trim(), out int flag) ? flag : 0
                    });
                }
                Debug.WriteLine($"Загружено {SettlementList.Count} НП.");
            }
            catch (Exception ex)
            {
                UiMessageService.Error(
                    "Ошибка данных",
                    $"Не удалось прочитать файл населенных пунктов.\n\n{ex.Message}",
                    null);
            }
        }

        public static void LoadRegionBoundariesFromGeoJson(string fileName = RegionsBoundsFileName)
        {
            try
            {
                string? regionsPath = ResolveDataFilePath(fileName);
                if (regionsPath == null)
                {
                    return;
                }

                string jsonString = File.ReadAllText(regionsPath);

                // Нечувствительность к регистру и мягкий парсинг JSON повышают
                // устойчивость при отличиях в формате данных.
                var options = new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true,
                    ReadCommentHandling = JsonCommentHandling.Skip,
                    AllowTrailingCommas = true
                };

                RegionBoundaries = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, List<List<double>>>>>(jsonString, options)
                                   ?? new Dictionary<string, Dictionary<string, List<List<double>>>>();

                Debug.WriteLine($"Загружено {RegionBoundaries.Count} границ регионов.");
            }
            catch (Exception ex)
            {
                UiMessageService.Error(
                    "Ошибка данных",
                    $"Не удалось прочитать файл границ регионов.\n\n{ex.Message}",
                    null);
            }
        }

        public static void LoadAllGeoData()
        {
            LoadSettlementData();
            LoadRegionBoundariesFromGeoJson();
        }
    }
}
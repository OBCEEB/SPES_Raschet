using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace SPES_Raschet.Services
{
    public sealed class CfoLoadResult
    {
        public bool Success { get; set; }
        public string Message { get; set; } = string.Empty;
    }

    public static class CfoClimateDataService
    {
        public const string CfoSettlementsFileName = "cfo_settlements.csv";
        public const string CfoBoundariesFileName = "regions_bounds_cfo.json";

        private static readonly List<SettlementData> _settlements = new List<SettlementData>();
        private static Dictionary<string, Dictionary<string, List<List<double>>>> _regionBoundaries
            = new Dictionary<string, Dictionary<string, List<List<double>>>>();

        public static IReadOnlyList<SettlementData> Settlements => _settlements;
        public static Dictionary<string, Dictionary<string, List<List<double>>>> RegionBoundaries => _regionBoundaries;

        public static bool HasRequiredFiles()
        {
            return ResolveDataFilePath(CfoSettlementsFileName) != null
                && ResolveDataFilePath(CfoBoundariesFileName) != null;
        }

        public static IReadOnlyList<string> GetMissingFiles()
        {
            var missing = new List<string>();
            if (ResolveDataFilePath(CfoSettlementsFileName) == null)
                missing.Add(CfoSettlementsFileName);
            if (ResolveDataFilePath(CfoBoundariesFileName) == null)
                missing.Add(CfoBoundariesFileName);
            return missing;
        }

        public static CfoLoadResult LoadAll()
        {
            try
            {
                var settlementsPath = ResolveDataFilePath(CfoSettlementsFileName);
                var boundariesPath = ResolveDataFilePath(CfoBoundariesFileName);
                _settlements.Clear();
                _regionBoundaries = new Dictionary<string, Dictionary<string, List<List<double>>>>();

                if (boundariesPath != null)
                    LoadBoundaries(boundariesPath);
                if (settlementsPath != null)
                    LoadSettlements(settlementsPath);

                if (settlementsPath == null || boundariesPath == null)
                {
                    return new CfoLoadResult
                    {
                        Success = false,
                        Message = "Не найдены файлы cfo_settlements.csv и/или regions_bounds_cfo.json."
                    };
                }

                return new CfoLoadResult
                {
                    Success = _settlements.Count > 0 && _regionBoundaries.Count > 0,
                    Message = _settlements.Count > 0 && _regionBoundaries.Count > 0
                        ? "Данные ЦФО загружены."
                        : "Файлы ЦФО загружены, но содержат недостаточно данных."
                };
            }
            catch (Exception ex)
            {
                return new CfoLoadResult
                {
                    Success = false,
                    Message = $"Ошибка загрузки ЦФО данных: {ex.Message}"
                };
            }
        }

        public static List<SettlementData> GetSettlementsByRegion(string regionName)
        {
            if (_settlements.Count == 0)
                return new List<SettlementData>();

            var target = Normalize(regionName);
            return _settlements
                .Where(s =>
                {
                    var region = Normalize(s.Region);
                    return region.Contains(target) || target.Contains(region);
                })
                .ToList();
        }

        public static SettlementData? FindNearestSettlement(double latitude, double longitude, double maxDistanceKm = 40)
        {
            if (_settlements.Count == 0)
                return null;

            SettlementData? best = null;
            double bestDistance = double.MaxValue;
            foreach (var settlement in _settlements)
            {
                double distance = HaversineKm(
                    latitude,
                    longitude,
                    settlement.Latitude,
                    settlement.Longitude);

                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    best = settlement;
                }
            }

            if (best == null || bestDistance > maxDistanceKm)
                return null;
            return best;
        }

        private static void LoadSettlements(string path)
        {
            var lines = ReadAllLinesWithEncodingFallback(path);
            _settlements.Clear();
            if (lines.Length <= 1)
                return;

            var header = lines[0].Split(',').Select(x => x.Trim().ToLowerInvariant()).ToArray();
            int idxRegion = Array.IndexOf(header, "region");
            int idxSettlement = Array.IndexOf(header, "settlement");
            int idxLat = Array.IndexOf(header, "latitude");
            int idxLon = Array.IndexOf(header, "longitude");
            int idxTz = Array.IndexOf(header, "timezone");

            if (idxRegion < 0 || idxSettlement < 0 || idxLat < 0 || idxLon < 0)
                return;

            foreach (var line in lines.Skip(1))
            {
                if (string.IsNullOrWhiteSpace(line))
                    continue;

                var parts = line.Split(',');
                if (parts.Length <= Math.Max(Math.Max(idxRegion, idxSettlement), Math.Max(idxLat, idxLon)))
                    continue;

                var region = parts[idxRegion].Trim();
                var settlement = parts[idxSettlement].Trim();

                if (!double.TryParse(parts[idxLat].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out var lat))
                    continue;
                if (!double.TryParse(parts[idxLon].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out var lon))
                    continue;

                int tz = 0;
                if (idxTz >= 0 && idxTz < parts.Length)
                    int.TryParse(parts[idxTz].Trim(), out tz);

                _settlements.Add(new SettlementData
                {
                    Region = region,
                    District = string.Empty,
                    CityOrSettlement = settlement,
                    Latitude = lat,
                    Longitude = lon,
                    TimeZoneOffset = tz,
                    CenterFlag = 0
                });
            }
        }

        private static void LoadBoundaries(string path)
        {
            var json = File.ReadAllText(path);
            var options = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true,
                ReadCommentHandling = JsonCommentHandling.Skip,
                AllowTrailingCommas = true
            };

            _regionBoundaries =
                JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, List<List<double>>>>>(json, options)
                ?? new Dictionary<string, Dictionary<string, List<List<double>>>>();
        }

        private static string[] ReadAllLinesWithEncodingFallback(string path)
        {
            var lines = File.ReadAllLines(path, Encoding.UTF8);
            if (lines.Any(l => l.Contains('\uFFFD')))
                lines = File.ReadAllLines(path, Encoding.GetEncoding(1251));
            return lines;
        }

        private static string Normalize(string value)
        {
            return value.Trim().ToLowerInvariant();
        }

        private static double HaversineKm(double lat1, double lon1, double lat2, double lon2)
        {
            const double radius = 6371.0;
            double dLat = ToRad(lat2 - lat1);
            double dLon = ToRad(lon2 - lon1);
            double a = Math.Pow(Math.Sin(dLat / 2), 2)
                     + Math.Cos(ToRad(lat1)) * Math.Cos(ToRad(lat2)) * Math.Pow(Math.Sin(dLon / 2), 2);
            double c = 2 * Math.Atan2(Math.Sqrt(a), Math.Sqrt(1 - a));
            return radius * c;
        }

        private static double ToRad(double value)
        {
            return value * Math.PI / 180.0;
        }

        private static string? ResolveDataFilePath(string fileName)
        {
            string baseDir = AppContext.BaseDirectory;
            string candidate = Path.Combine(baseDir, fileName);
            if (File.Exists(candidate))
                return candidate;

            candidate = Path.Combine(Environment.CurrentDirectory, fileName);
            if (File.Exists(candidate))
                return candidate;

            string? dir = baseDir;
            for (int i = 0; i < 5 && !string.IsNullOrEmpty(dir); i++)
            {
                dir = Directory.GetParent(dir)?.FullName;
                if (string.IsNullOrEmpty(dir))
                    break;
                candidate = Path.Combine(dir, fileName);
                if (File.Exists(candidate))
                    return candidate;
            }

            return null;
        }
    }
}

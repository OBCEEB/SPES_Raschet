using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Microsoft.Data.Sqlite;

namespace SPES_Raschet.Services.Meteo
{
    /// <summary>
    /// Импорт архива CSV (радиация + АСМГ) в локальную SQLite.
    /// </summary>
    public static class MeteoArchiveImporter
    {
        private const int InsertBatchSize = 120;

        private static readonly CultureInfo Ru = CultureInfo.GetCultureInfo("ru-RU");
        private static readonly Encoding Win1251 = Encoding.GetEncoding(1251);

        private readonly struct PendingRow
        {
            public readonly long StationId;
            public readonly long DatasetId;
            public readonly string ObsTime;
            public readonly object? Q1;
            public readonly object? Q2;
            public readonly object? Q3;
            public readonly object? NgoM;
            public readonly object? Q4;

            public PendingRow(long stationId, long datasetId, string obsTime, object? q1, object? q2, object? q3, object? ngoM, object? q4)
            {
                StationId = stationId;
                DatasetId = datasetId;
                ObsTime = obsTime;
                Q1 = q1;
                Q2 = q2;
                Q3 = q3;
                NgoM = ngoM;
                Q4 = q4;
            }
        }

        private readonly struct ImportTarget
        {
            public readonly string RegionName;
            public readonly string ParameterName;
            public readonly bool IsAsmg;

            public ImportTarget(string regionName, string parameterName, bool isAsmg)
            {
                RegionName = regionName;
                ParameterName = parameterName;
                IsAsmg = isAsmg;
            }
        }

        /// <summary>
        /// Полный импорт: очищает все наблюдения и заново заливает CSV из архива.
        /// </summary>
        public static MeteoImportResult ImportArchive(
            string archiveRoot,
            IProgress<string>? progress = null,
            bool clearExistingObservations = true)
        {
            var sw = Stopwatch.StartNew();
            if (string.IsNullOrWhiteSpace(archiveRoot) || !Directory.Exists(archiveRoot))
            {
                return new MeteoImportResult
                {
                    Success = false,
                    Message = "Папка с архивом не найдена: " + archiveRoot,
                    Elapsed = sw.Elapsed
                };
            }

            var dbPath = MeteoDbPaths.GetDatabaseFilePath();
            Directory.CreateDirectory(Path.GetDirectoryName(dbPath)!);

            int files = 0;
            int rows = 0;

            try
            {
                using var connection = new SqliteConnection("Data Source=" + dbPath);
                connection.Open();
                MeteoSchema.EnsureCreated(connection);

                using (var pragma = connection.CreateCommand())
                {
                    pragma.CommandText = "PRAGMA cache_size = -200000; PRAGMA temp_store = MEMORY;";
                    pragma.ExecuteNonQuery();
                }

                var csvFiles = Directory.EnumerateFiles(archiveRoot, "*.csv", SearchOption.AllDirectories)
                    .OrderBy(p => p, StringComparer.OrdinalIgnoreCase)
                    .ToList();

                if (csvFiles.Count == 0)
                {
                    return new MeteoImportResult
                    {
                        Success = false,
                        Message = "CSV-файлы не найдены (проверьте вложенность регион/параметр/год).",
                        Elapsed = sw.Elapsed
                    };
                }

                using var tx = connection.BeginTransaction();

                if (clearExistingObservations)
                {
                    using var delObs = connection.CreateCommand();
                    delObs.Transaction = tx;
                    delObs.CommandText = "DELETE FROM meteo_observation;";
                    delObs.ExecuteNonQuery();
                }

                var stationCache = new Dictionary<string, long>(StringComparer.Ordinal);
                var datasetCache = new Dictionary<string, long>(StringComparer.Ordinal);
                var buffer = new List<PendingRow>(InsertBatchSize);

                void FlushFullBatches()
                {
                    while (buffer.Count >= InsertBatchSize)
                    {
                        var chunk = buffer.GetRange(0, InsertBatchSize);
                        ExecuteInsertBatch(connection, tx, chunk);
                        buffer.RemoveRange(0, InsertBatchSize);
                        rows += InsertBatchSize;
                    }
                }

                foreach (var path in csvFiles)
                {
                    if (!TryResolveImportTarget(archiveRoot, path, out var target))
                        continue;

                    if (!stationCache.TryGetValue(target.RegionName, out var stationId))
                    {
                        stationId = UpsertStation(connection, tx, target.RegionName);
                        stationCache[target.RegionName] = stationId;
                    }

                    var dsKey = target.RegionName + "\u001f" + target.ParameterName;
                    if (!datasetCache.TryGetValue(dsKey, out var datasetId))
                    {
                        datasetId = UpsertDataset(connection, tx, stationId, target.ParameterName);
                        datasetCache[dsKey] = datasetId;
                    }

                    ReadCsvIntoBuffer(path, stationId, datasetId, target.IsAsmg, buffer);

                    FlushFullBatches();

                    files++;
                    if (files % 50 == 0)
                        progress?.Report($"Импорт: {files}/{csvFiles.Count} файлов, строк: {rows + buffer.Count}");
                }

                if (buffer.Count > 0)
                {
                    ExecuteInsertBatch(connection, tx, buffer);
                    rows += buffer.Count;
                    buffer.Clear();
                }

                // Сжимаем базу под расчет коллекторов:
                // оставляем только моменты, где есть и радиация, и НГО.
                using (var prune = connection.CreateCommand())
                {
                    prune.Transaction = tx;
                    prune.CommandText = @"
DELETE FROM meteo_observation
WHERE q_mjm2 IS NULL
   OR ngo_m IS NULL;";
                    prune.ExecuteNonQuery();
                }

                tx.Commit();
                sw.Stop();

                return new MeteoImportResult
                {
                    Success = true,
                    Message = $"Готово. База: {dbPath}",
                    FilesProcessed = files,
                    RowsInserted = rows,
                    Elapsed = sw.Elapsed
                };
            }
            catch (Exception ex)
            {
                sw.Stop();
                return new MeteoImportResult
                {
                    Success = false,
                    Message = ex.Message,
                    FilesProcessed = files,
                    RowsInserted = rows,
                    Elapsed = sw.Elapsed
                };
            }
        }

        private static void ExecuteInsertBatch(SqliteConnection connection, SqliteTransaction tx, List<PendingRow> chunk)
        {
            var sb = new StringBuilder(512 + chunk.Count * 48);
            sb.AppendLine("INSERT INTO meteo_observation (station_id, dataset_id, obs_time, q_mjm2, t_deg_c, q_mj, ngo_m, ssd_s) VALUES ");
            for (int i = 0; i < chunk.Count; i++)
            {
                if (i > 0)
                    sb.AppendLine(",");
                sb.Append('(').Append("$st").Append(i).Append(',')
                    .Append("$ds").Append(i).Append(',')
                    .Append("$t").Append(i).Append(',')
                    .Append("$a").Append(i).Append(',')
                    .Append("$b").Append(i).Append(',')
                    .Append("$c").Append(i).Append(',')
                    .Append("$e").Append(i).Append(',')
                    .Append("$d").Append(i).Append(')');
            }
            sb.AppendLine();
            sb.AppendLine("ON CONFLICT(station_id, dataset_id, obs_time) DO UPDATE SET");
            sb.AppendLine("  q_mjm2 = COALESCE(excluded.q_mjm2, meteo_observation.q_mjm2),");
            sb.AppendLine("  t_deg_c = COALESCE(excluded.t_deg_c, meteo_observation.t_deg_c),");
            sb.AppendLine("  q_mj = COALESCE(excluded.q_mj, meteo_observation.q_mj),");
            sb.AppendLine("  ngo_m = COALESCE(excluded.ngo_m, meteo_observation.ngo_m),");
            sb.AppendLine("  ssd_s = COALESCE(excluded.ssd_s, meteo_observation.ssd_s);");

            using var cmd = connection.CreateCommand();
            cmd.Transaction = tx;
            cmd.CommandText = sb.ToString();
            for (int i = 0; i < chunk.Count; i++)
            {
                var r = chunk[i];
                cmd.Parameters.Add("$st" + i, SqliteType.Integer).Value = r.StationId;
                cmd.Parameters.Add("$ds" + i, SqliteType.Integer).Value = r.DatasetId;
                cmd.Parameters.Add("$t" + i, SqliteType.Text).Value = r.ObsTime;
                cmd.Parameters.Add("$a" + i, SqliteType.Real).Value = r.Q1 ?? (object)DBNull.Value;
                cmd.Parameters.Add("$b" + i, SqliteType.Real).Value = r.Q2 ?? (object)DBNull.Value;
                cmd.Parameters.Add("$c" + i, SqliteType.Real).Value = r.Q3 ?? (object)DBNull.Value;
                cmd.Parameters.Add("$e" + i, SqliteType.Real).Value = r.NgoM ?? (object)DBNull.Value;
                cmd.Parameters.Add("$d" + i, SqliteType.Real).Value = r.Q4 ?? (object)DBNull.Value;
            }

            cmd.ExecuteNonQuery();
        }

        private static void ReadCsvIntoBuffer(string path, long stationId, long datasetId, bool isAsmg, List<PendingRow> buffer)
        {
            using var sr = new StreamReader(path, Win1251, detectEncodingFromByteOrderMarks: true);
            if (!isAsmg)
                _ = sr.ReadLine();
            string? line;
            while ((line = sr.ReadLine()) != null)
            {
                if (string.IsNullOrWhiteSpace(line))
                    continue;
                var parts = line.Split(';');
                if (parts.Length < 2)
                    continue;

                if (isAsmg)
                {
                    if (!TryParseAsmgTimestamp(parts, out var dt))
                        continue;
                    var ts = dt.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
                    object? ngoM = TryParseNgoMeters(parts, 29, out var ngo) ? ngo : null; // AD = 30th column
                    buffer.Add(new PendingRow(stationId, datasetId, ts, null, null, null, ngoM, null));
                }
                else
                {
                    var t0 = parts[0].Trim().Trim('"');
                    if (!DateTime.TryParse(t0, Ru, DateTimeStyles.AssumeLocal, out var dt))
                        continue;

                    var ts = dt.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
                    object? v1 = TryParseDoubleRu(parts, 1, out var d1) ? d1 : null;
                    object? v2 = TryParseDoubleRu(parts, 2, out var d2) ? d2 : null;
                    object? v3 = TryParseDoubleRu(parts, 3, out var d3) ? d3 : null;
                    object? v4 = TryParseDoubleRu(parts, 4, out var d4) ? d4 : null;
                    buffer.Add(new PendingRow(stationId, datasetId, ts, v1, v2, v3, null, v4));
                }
            }
        }

        private static bool TryResolveImportTarget(string archiveRoot, string path, out ImportTarget target)
        {
            target = default;
            var rel = Path.GetRelativePath(archiveRoot, path);
            var segments = rel.Split(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar },
                StringSplitOptions.RemoveEmptyEntries);
            if (segments.Length == 0)
                return false;

            // Обратная совместимость: старый плоский формат АСМГ:
            // метеорология/Климат АМСГ Липецк 2021-2025/c_202101.csv
            if (segments.Length == 2 && segments[1].StartsWith("c_", StringComparison.OrdinalIgnoreCase))
            {
                var region = NormalizeRegionName(segments[0]);
                target = new ImportTarget(region, "Суммарная солнечная радиация", isAsmg: true);
                return true;
            }

            // Текущий формат: регион/категория/год/месяц/file.csv
            if (segments.Length >= 3)
            {
                var region = NormalizeRegionName(segments[0]);
                var category = segments[1].Trim();
                bool isNgoCategory = category.Equals("НГО", StringComparison.OrdinalIgnoreCase);
                // НГО и радиация должны лежать в одном dataset (совмещение по timestamp).
                var parameter = "Суммарная солнечная радиация";
                if (!isNgoCategory)
                    parameter = category;
                target = new ImportTarget(region, parameter, isAsmg: isNgoCategory);
                return true;
            }

            return false;
        }

        private static string NormalizeRegionName(string raw)
        {
            var s = raw.Trim();
            if (s.Contains("Липецк", StringComparison.OrdinalIgnoreCase))
                return "липецкая область";
            return s;
        }

        private static bool TryParseAsmgTimestamp(IReadOnlyList<string> parts, out DateTime dt)
        {
            dt = default;
            if (parts.Count < 8)
                return false;
            if (!int.TryParse(parts[3].Trim(), out var y) ||
                !int.TryParse(parts[4].Trim(), out var m) ||
                !int.TryParse(parts[5].Trim(), out var d) ||
                !int.TryParse(parts[6].Trim(), out var hh) ||
                !int.TryParse(parts[7].Trim(), out var mm))
                return false;
            try
            {
                dt = new DateTime(y, m, d, hh, mm, 0);
                return true;
            }
            catch
            {
                return false;
            }
        }

        private static long UpsertStation(SqliteConnection connection, SqliteTransaction tx, string regionDisplayName)
        {
            var code = MeteoIdentifiers.StationCode(regionDisplayName);
            using (var cmd = connection.CreateCommand())
            {
                cmd.Transaction = tx;
                cmd.CommandText = @"
INSERT INTO meteo_station (code, display_name, region_subject)
VALUES ($c, $n, $r)
ON CONFLICT(code) DO UPDATE SET
  display_name = excluded.display_name,
  region_subject = excluded.region_subject;";
                cmd.Parameters.AddWithValue("$c", code);
                cmd.Parameters.AddWithValue("$n", regionDisplayName);
                cmd.Parameters.AddWithValue("$r", regionDisplayName);
                cmd.ExecuteNonQuery();
            }

            using var sel = connection.CreateCommand();
            sel.Transaction = tx;
            sel.CommandText = "SELECT id FROM meteo_station WHERE code = $c;";
            sel.Parameters.AddWithValue("$c", code);
            return (long)sel.ExecuteScalar()!;
        }

        private static long UpsertDataset(SqliteConnection connection, SqliteTransaction tx, long stationId, string parameterDisplayName)
        {
            var code = MeteoIdentifiers.DatasetCode(stationId, parameterDisplayName);
            using (var cmd = connection.CreateCommand())
            {
                cmd.Transaction = tx;
                cmd.CommandText = @"
INSERT INTO meteo_dataset (station_id, code, display_name, parameter_kind)
VALUES ($st, $c, $n, $k)
ON CONFLICT(station_id, code) DO UPDATE SET
  display_name = excluded.display_name,
  parameter_kind = excluded.parameter_kind;";
                cmd.Parameters.AddWithValue("$st", stationId);
                cmd.Parameters.AddWithValue("$c", code);
                cmd.Parameters.AddWithValue("$n", parameterDisplayName);
                cmd.Parameters.AddWithValue("$k", parameterDisplayName);
                cmd.ExecuteNonQuery();
            }

            using var sel = connection.CreateCommand();
            sel.Transaction = tx;
            sel.CommandText = "SELECT id FROM meteo_dataset WHERE station_id = $st AND code = $c;";
            sel.Parameters.AddWithValue("$st", stationId);
            sel.Parameters.AddWithValue("$c", code);
            return (long)sel.ExecuteScalar()!;
        }

        private static bool TryParseDoubleRu(IReadOnlyList<string> parts, int index, out double value)
        {
            value = 0;
            if (index >= parts.Count)
                return false;
            var s = parts[index].Trim().Trim('"');
            if (string.IsNullOrWhiteSpace(s))
                return false;
            if (s is "/" or "\\" or "-" or "—" or "–")
                return false;

            if (double.TryParse(s, NumberStyles.Float, Ru, out value))
                return true;
            return double.TryParse(s.Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }

        private static bool TryParseNgoMeters(IReadOnlyList<string> parts, int index, out double value)
        {
            if (!TryParseDoubleRu(parts, index, out value))
                return false;

            // АМСГ-сентинелы "нет данных" для НГО.
            if (value >= 9000)
                return false;
            return true;
        }
    }
}

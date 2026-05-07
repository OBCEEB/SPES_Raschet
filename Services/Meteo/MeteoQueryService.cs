using System;
using System.Collections.Generic;
using System.Data;
using System.Globalization;
using System.IO;
using Microsoft.Data.Sqlite;

namespace SPES_Raschet.Services.Meteo
{
    /// <summary>Чтение и агрегирование метеоданных из локальной SQLite.</summary>
    public static class MeteoQueryService
    {
        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        public static MeteoDatabaseSummary GetSummary()
        {
            var path = MeteoDbPaths.GetDatabaseFilePath();
            if (!File.Exists(path))
            {
                return new MeteoDatabaseSummary
                {
                    DatabasePath = path,
                    Exists = false
                };
            }

            using var connection = OpenReadOnly(path);
            return new MeteoDatabaseSummary
            {
                DatabasePath = path,
                Exists = true,
                StationCount = ScalarLong(connection, "SELECT COUNT(*) FROM meteo_station;"),
                DatasetCount = ScalarLong(connection, "SELECT COUNT(*) FROM meteo_dataset;"),
                ObservationCount = ScalarLong(connection, "SELECT COUNT(*) FROM meteo_observation;")
            };
        }

        public static IReadOnlyList<MeteoStationInfo> ListStations()
        {
            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return Array.Empty<MeteoStationInfo>();

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText =
                "SELECT id, code, display_name, region_subject, timezone_iana FROM meteo_station ORDER BY display_name;";
            using var reader = cmd.ExecuteReader();
            var list = new List<MeteoStationInfo>();
            while (reader.Read())
            {
                list.Add(new MeteoStationInfo
                {
                    Id = reader.GetInt64(0),
                    Code = reader.GetString(1),
                    DisplayName = reader.GetString(2),
                    RegionSubject = reader.IsDBNull(3) ? null : reader.GetString(3),
                    TimezoneIana = reader.IsDBNull(4) ? "Europe/Moscow" : reader.GetString(4)
                });
            }

            return list;
        }

        public static IReadOnlyList<MeteoDatasetInfo> ListDatasets(long stationId)
        {
            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return Array.Empty<MeteoDatasetInfo>();

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText =
                "SELECT id, station_id, code, display_name, parameter_kind FROM meteo_dataset WHERE station_id = $s ORDER BY display_name;";
            cmd.Parameters.AddWithValue("$s", stationId);
            using var reader = cmd.ExecuteReader();
            var list = new List<MeteoDatasetInfo>();
            while (reader.Read())
            {
                list.Add(new MeteoDatasetInfo
                {
                    Id = reader.GetInt64(0),
                    StationId = reader.GetInt64(1),
                    Code = reader.GetString(2),
                    DisplayName = reader.GetString(3),
                    ParameterKind = reader.IsDBNull(4) ? null : reader.GetString(4)
                });
            }

            return list;
        }

        /// <summary>Точное совпадение с именем региона при импорте (например «липецкая область»).</summary>
        public static long? TryGetStationIdByDisplayName(string displayName)
        {
            if (string.IsNullOrWhiteSpace(displayName) || !File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return null;

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = "SELECT id FROM meteo_station WHERE display_name = $n LIMIT 1;";
            cmd.Parameters.AddWithValue("$n", displayName.Trim());
            var o = cmd.ExecuteScalar();
            return o is long l ? l : o is int i ? i : null;
        }

        public static long? TryGetDatasetId(long stationId, string parameterDisplayName)
        {
            if (string.IsNullOrWhiteSpace(parameterDisplayName) || !File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return null;

            var code = MeteoIdentifiers.DatasetCode(stationId, parameterDisplayName.Trim());
            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = "SELECT id FROM meteo_dataset WHERE station_id = $st AND code = $c LIMIT 1;";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$c", code);
            var o = cmd.ExecuteScalar();
            return o is long l ? l : o is int i ? i : null;
        }

        /// <summary>
        /// Минутный ряд за полуинтервал [inclusiveFrom, exclusiveTo) в локальном времени, как в CSV.
        /// </summary>
        public static IReadOnlyList<MeteoObservationRow> GetObservations(
            long stationId,
            long datasetId,
            DateTime inclusiveFrom,
            DateTime exclusiveTo,
            int? maxRows = null)
        {
            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return Array.Empty<MeteoObservationRow>();

            var from = inclusiveFrom.ToString("yyyy-MM-dd HH:mm:ss", Inv);
            var to = exclusiveTo.ToString("yyyy-MM-dd HH:mm:ss", Inv);

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            var limitSql = maxRows is > 0 and int lim ? " LIMIT " + lim.ToString(Inv) : string.Empty;
            cmd.CommandText =
                "SELECT obs_time, q_mjm2, t_deg_c, q_mj, ngo_m, ssd_s FROM meteo_observation " +
                "WHERE station_id = $st AND dataset_id = $ds AND obs_time >= $f AND obs_time < $t " +
                "ORDER BY obs_time" + limitSql + ";";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$ds", datasetId);
            cmd.Parameters.AddWithValue("$f", from);
            cmd.Parameters.AddWithValue("$t", to);

            using var reader = cmd.ExecuteReader();
            var list = new List<MeteoObservationRow>();
            while (reader.Read())
            {
                var ts = DateTime.ParseExact(reader.GetString(0), "yyyy-MM-dd HH:mm:ss", Inv, DateTimeStyles.AssumeLocal);
                list.Add(new MeteoObservationRow
                {
                    TimestampLocal = ts,
                    Qmjm2 = ReadNullableDouble(reader, 1),
                    TdegC = ReadNullableDouble(reader, 2),
                    Qmj = ReadNullableDouble(reader, 3),
                    NgoMeters = ReadNullableDouble(reader, 4),
                    SsdSeconds = ReadNullableDouble(reader, 5)
                });
            }

            return list;
        }

        /// <summary>Суточные суммы/средние за [firstDay, lastDay] включительно.</summary>
        public static IReadOnlyList<MeteoDailyAggregate> GetDailyAggregates(
            long stationId,
            long datasetId,
            DateOnly firstDay,
            DateOnly lastDay)
        {
            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return Array.Empty<MeteoDailyAggregate>();

            var from = firstDay.ToString("yyyy-MM-dd", Inv) + " 00:00:00";
            var toExclusive = lastDay.AddDays(1).ToString("yyyy-MM-dd", Inv) + " 00:00:00";

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = @"
SELECT substr(obs_time, 1, 10) AS d,
       COUNT(*) AS cnt,
       SUM(CASE WHEN q_mjm2 IS NOT NULL THEN 1 ELSE 0 END) AS qnn,
       SUM(q_mj) AS sqmj,
       SUM(ssd_s) AS sssd,
       AVG(t_deg_c) AS avgt
FROM meteo_observation
WHERE station_id = $st AND dataset_id = $ds
  AND obs_time >= $f AND obs_time < $t
GROUP BY d
ORDER BY d;";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$ds", datasetId);
            cmd.Parameters.AddWithValue("$f", from);
            cmd.Parameters.AddWithValue("$t", toExclusive);

            using var reader = cmd.ExecuteReader();
            return ReadDailyAggregates(reader);
        }

        /// <summary>Месячные агрегаты за [firstMonth, lastMonth] включительно (по календарным месяцам).</summary>
        public static IReadOnlyList<MeteoMonthlyAggregate> GetMonthlyAggregates(
            long stationId,
            long datasetId,
            DateOnly firstMonth,
            DateOnly lastMonth)
        {
            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return Array.Empty<MeteoMonthlyAggregate>();

            var from = new DateOnly(firstMonth.Year, firstMonth.Month, 1).ToString("yyyy-MM-dd", Inv) + " 00:00:00";
            var endMonth = new DateOnly(lastMonth.Year, lastMonth.Month, 1);
            var toExclusive = endMonth.AddMonths(1).ToString("yyyy-MM-dd", Inv) + " 00:00:00";

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = @"
SELECT CAST(strftime('%Y', obs_time) AS INTEGER),
       CAST(strftime('%m', obs_time) AS INTEGER),
       COUNT(*) AS cnt,
       SUM(CASE WHEN q_mjm2 IS NOT NULL THEN 1 ELSE 0 END) AS qnn,
       AVG(q_mjm2) AS avq1,
       SUM(q_mj) AS sqmj,
       SUM(ssd_s) AS sssd,
       AVG(t_deg_c) AS avgt
FROM meteo_observation
WHERE station_id = $st AND dataset_id = $ds
  AND obs_time >= $f AND obs_time < $t
GROUP BY 1, 2
ORDER BY 1, 2;";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$ds", datasetId);
            cmd.Parameters.AddWithValue("$f", from);
            cmd.Parameters.AddWithValue("$t", toExclusive);

            using var reader = cmd.ExecuteReader();
            var list = new List<MeteoMonthlyAggregate>();
            while (reader.Read())
            {
                list.Add(new MeteoMonthlyAggregate
                {
                    Year = reader.GetInt32(0),
                    Month = reader.GetInt32(1),
                    RowCount = reader.GetInt32(2),
                    Qmjm2NonNullCount = reader.GetInt32(3),
                    AvgQmjm2 = ReadNullableDouble(reader, 4),
                    SumQmj = ReadNullableDouble(reader, 5),
                    SumSsdSeconds = ReadNullableDouble(reader, 6),
                    AvgTdegC = ReadNullableDouble(reader, 7)
                });
            }

            return list;
        }

        /// <summary>Покрытие НГО+радиации по месяцам для оценки пригодности расчётов.</summary>
        public static IReadOnlyList<MeteoMonthlyCoverage> GetMonthlyCoverage(
            long stationId,
            long datasetId,
            DateOnly firstMonth,
            DateOnly lastMonth)
        {
            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return Array.Empty<MeteoMonthlyCoverage>();

            var from = new DateOnly(firstMonth.Year, firstMonth.Month, 1).ToString("yyyy-MM-dd", Inv) + " 00:00:00";
            var endMonth = new DateOnly(lastMonth.Year, lastMonth.Month, 1);
            var toExclusive = endMonth.AddMonths(1).ToString("yyyy-MM-dd", Inv) + " 00:00:00";

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = @"
SELECT CAST(strftime('%Y', obs_time) AS INTEGER) AS y,
       CAST(strftime('%m', obs_time) AS INTEGER) AS m,
       COUNT(*) AS total_rows,
       SUM(CASE WHEN q_mjm2 IS NOT NULL THEN 1 ELSE 0 END) AS rad_rows,
       SUM(CASE WHEN ngo_m IS NOT NULL THEN 1 ELSE 0 END) AS ngo_rows,
       SUM(CASE WHEN q_mjm2 IS NOT NULL AND ngo_m IS NOT NULL THEN 1 ELSE 0 END) AS both_rows
FROM meteo_observation
WHERE station_id = $st AND dataset_id = $ds
  AND obs_time >= $f AND obs_time < $t
GROUP BY 1, 2
ORDER BY 1, 2;";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$ds", datasetId);
            cmd.Parameters.AddWithValue("$f", from);
            cmd.Parameters.AddWithValue("$t", toExclusive);

            using var reader = cmd.ExecuteReader();
            var list = new List<MeteoMonthlyCoverage>();
            while (reader.Read())
            {
                list.Add(new MeteoMonthlyCoverage
                {
                    Year = reader.GetInt32(0),
                    Month = reader.GetInt32(1),
                    TotalRows = reader.GetInt32(2),
                    RadiationRows = reader.GetInt32(3),
                    NgoRows = reader.GetInt32(4),
                    RadiationAndNgoRows = reader.GetInt32(5)
                });
            }

            return list;
        }

        /// <summary>
        /// Таблица записей радиации+облачности (НГО) для отображения в UI.
        /// </summary>
        public static DataTable GetRadiationAndNgoTable(long stationId, long datasetId, int? year = null)
        {
            var dt = new DataTable("MeteoRadiationNgo");
            dt.Columns.Add("Дата и время", typeof(string));
            dt.Columns.Add("Радиация Q, МДж/м²", typeof(double));
            dt.Columns.Add("НГО, м", typeof(double));

            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return dt;

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = @"
SELECT obs_time, q_mjm2, ngo_m
FROM meteo_observation
WHERE station_id = $st AND dataset_id = $ds
  AND ($y IS NULL OR CAST(strftime('%Y', obs_time) AS INTEGER) = $y)
  AND (q_mjm2 IS NOT NULL OR ngo_m IS NOT NULL)
ORDER BY obs_time;";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$ds", datasetId);
            var yearParam = cmd.Parameters.Add("$y", SqliteType.Integer);
            yearParam.Value = year.HasValue ? year.Value : DBNull.Value;

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                var row = dt.NewRow();
                row[0] = reader.GetString(0);
                row[1] = reader.IsDBNull(1) ? DBNull.Value : reader.GetDouble(1);
                row[2] = reader.IsDBNull(2) ? DBNull.Value : reader.GetDouble(2);
                dt.Rows.Add(row);
            }

            return dt;
        }

        public static int GetRadiationAndNgoCount(long stationId, long datasetId, int? year = null)
        {
            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return 0;

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = @"
SELECT COUNT(*)
FROM meteo_observation
WHERE station_id = $st AND dataset_id = $ds
  AND ($y IS NULL OR CAST(strftime('%Y', obs_time) AS INTEGER) = $y)
  AND (q_mjm2 IS NOT NULL OR ngo_m IS NOT NULL);";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$ds", datasetId);
            var yearParam = cmd.Parameters.Add("$y", SqliteType.Integer);
            yearParam.Value = year.HasValue ? year.Value : DBNull.Value;

            var o = cmd.ExecuteScalar();
            return o is long l ? (int)Math.Min(int.MaxValue, l) : o is int i ? i : 0;
        }

        public static DataTable GetRadiationAndNgoTablePage(
            long stationId,
            long datasetId,
            int? year,
            int offset,
            int pageSize)
        {
            var dt = new DataTable("MeteoRadiationNgoPage");
            dt.Columns.Add("Дата и время", typeof(string));
            dt.Columns.Add("Радиация Q, МДж/м²", typeof(double));
            dt.Columns.Add("НГО, м", typeof(double));

            if (!File.Exists(MeteoDbPaths.GetDatabaseFilePath()))
                return dt;

            using var connection = OpenReadOnly(MeteoDbPaths.GetDatabaseFilePath());
            using var cmd = connection.CreateCommand();
            cmd.CommandText = @"
SELECT obs_time, q_mjm2, ngo_m
FROM meteo_observation
WHERE station_id = $st AND dataset_id = $ds
  AND ($y IS NULL OR CAST(strftime('%Y', obs_time) AS INTEGER) = $y)
  AND (q_mjm2 IS NOT NULL OR ngo_m IS NOT NULL)
ORDER BY obs_time
LIMIT $lim OFFSET $off;";
            cmd.Parameters.AddWithValue("$st", stationId);
            cmd.Parameters.AddWithValue("$ds", datasetId);
            var yearParam = cmd.Parameters.Add("$y", SqliteType.Integer);
            yearParam.Value = year.HasValue ? year.Value : DBNull.Value;
            cmd.Parameters.AddWithValue("$lim", pageSize);
            cmd.Parameters.AddWithValue("$off", offset);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                var row = dt.NewRow();
                row[0] = reader.GetString(0);
                row[1] = reader.IsDBNull(1) ? DBNull.Value : reader.GetDouble(1);
                row[2] = reader.IsDBNull(2) ? DBNull.Value : reader.GetDouble(2);
                dt.Rows.Add(row);
            }

            return dt;
        }

        private static List<MeteoDailyAggregate> ReadDailyAggregates(SqliteDataReader reader)
        {
            var list = new List<MeteoDailyAggregate>();
            while (reader.Read())
            {
                var d = DateOnly.Parse(reader.GetString(0), Inv);
                list.Add(new MeteoDailyAggregate
                {
                    Date = d,
                    RowCount = reader.GetInt32(1),
                    Qmjm2NonNullCount = reader.GetInt32(2),
                    SumQmj = ReadNullableDouble(reader, 3),
                    SumSsdSeconds = ReadNullableDouble(reader, 4),
                    AvgTdegC = ReadNullableDouble(reader, 5)
                });
            }

            return list;
        }

        private static SqliteConnection OpenReadOnly(string path)
        {
            var connection = new SqliteConnection("Data Source=" + path + ";Mode=ReadOnly;Cache=Shared");
            connection.Open();
            return connection;
        }

        private static long ScalarLong(SqliteConnection connection, string sql)
        {
            using var cmd = connection.CreateCommand();
            cmd.CommandText = sql;
            var o = cmd.ExecuteScalar();
            return o switch
            {
                long l => l,
                int i => i,
                _ => 0
            };
        }

        private static double? ReadNullableDouble(SqliteDataReader reader, int ordinal)
        {
            if (reader.IsDBNull(ordinal))
                return null;
            return reader.GetDouble(ordinal);
        }
    }
}

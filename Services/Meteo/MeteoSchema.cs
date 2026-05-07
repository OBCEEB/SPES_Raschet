using System;
using Microsoft.Data.Sqlite;

namespace SPES_Raschet.Services.Meteo
{
    internal static class MeteoSchema
    {
        public static void EnsureCreated(SqliteConnection connection)
        {
            using (var pragma = connection.CreateCommand())
            {
                pragma.CommandText = "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;";
                pragma.ExecuteNonQuery();
            }

            using var cmd = connection.CreateCommand();
            cmd.CommandText = @"
CREATE TABLE IF NOT EXISTS meteo_station (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  region_subject TEXT,
  latitude REAL,
  longitude REAL,
  timezone_iana TEXT NOT NULL DEFAULT 'Europe/Moscow'
);

CREATE TABLE IF NOT EXISTS meteo_dataset (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  station_id INTEGER NOT NULL REFERENCES meteo_station(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  display_name TEXT NOT NULL,
  parameter_kind TEXT,
  schema_version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(station_id, code)
);

CREATE TABLE IF NOT EXISTS meteo_observation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  station_id INTEGER NOT NULL REFERENCES meteo_station(id) ON DELETE CASCADE,
  dataset_id INTEGER NOT NULL REFERENCES meteo_dataset(id) ON DELETE CASCADE,
  obs_time TEXT NOT NULL,
  q_mjm2 REAL,
  t_deg_c REAL,
  q_mj REAL,
  ngo_m REAL,
  ssd_s REAL,
  UNIQUE(station_id, dataset_id, obs_time)
);

CREATE INDEX IF NOT EXISTS ix_meteo_obs_station_time ON meteo_observation(station_id, obs_time);
CREATE INDEX IF NOT EXISTS ix_meteo_obs_dataset_time ON meteo_observation(dataset_id, obs_time);
CREATE INDEX IF NOT EXISTS ix_meteo_obs_time ON meteo_observation(obs_time);
";
            cmd.ExecuteNonQuery();

            EnsureNgoColumn(connection);
        }

        private static void EnsureNgoColumn(SqliteConnection connection)
        {
            bool hasNgo = false;
            using (var cmd = connection.CreateCommand())
            {
                cmd.CommandText = "PRAGMA table_info(meteo_observation);";
                using var reader = cmd.ExecuteReader();
                while (reader.Read())
                {
                    if (string.Equals(reader.GetString(1), "ngo_m", StringComparison.OrdinalIgnoreCase))
                    {
                        hasNgo = true;
                        break;
                    }
                }
            }

            if (hasNgo)
                return;

            using var alter = connection.CreateCommand();
            alter.CommandText = "ALTER TABLE meteo_observation ADD COLUMN ngo_m REAL;";
            alter.ExecuteNonQuery();
        }
    }
}

using System;
using System.IO;

namespace SPES_Raschet.Services.Meteo
{
    /// <summary>
    /// Пути к локальной SQLite и сырым CSV архивам (рядом с исполняемым файлом).
    /// </summary>
    public static class MeteoDbPaths
    {
        public static string GetDataDirectory()
        {
            var dir = Path.Combine(AppContext.BaseDirectory, "Data");
            Directory.CreateDirectory(dir);
            return dir;
        }

        public static string GetDatabaseFilePath()
            => Path.Combine(GetDataDirectory(), "spes_meteo.sqlite");

        /// <summary>Папка «метеорология» с подкаталогами регион/параметр/год/…</summary>
        public static string GetDefaultMeteorologyArchivePath()
            => Path.Combine(AppContext.BaseDirectory, "метеорология");
    }
}

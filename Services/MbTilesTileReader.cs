using System;
using System.Collections.Generic;
using System.IO;
using SQLite;

namespace SPES_Raschet.Services
{
    public sealed class MbTilesTileReader : IDisposable
    {
        private readonly SQLiteConnection _connection;
        private readonly Dictionary<string, byte[]?> _cache = new Dictionary<string, byte[]?>();
        public int MaxZoom { get; }
        public int MinZoom { get; }

        public MbTilesTileReader(string mbTilesPath)
        {
            if (!File.Exists(mbTilesPath))
                throw new FileNotFoundException("MBTiles file not found.", mbTilesPath);

            _connection = new SQLiteConnection(mbTilesPath, SQLiteOpenFlags.ReadOnly);
            MaxZoom = ResolveMaxZoom();
            MinZoom = ResolveMinZoom();
        }

        public byte[]? GetTileBytes(int zoom, int x, int yOsm)
        {
            if (zoom < 0)
                return null;

            int max = 1 << zoom;
            if (x < 0 || x >= max || yOsm < 0 || yOsm >= max)
                return null;

            // MBTiles stores rows in TMS orientation.
            int yTms = max - 1 - yOsm;
            string key = $"{zoom}/{x}/{yTms}";
            if (_cache.TryGetValue(key, out var cached))
                return cached;

            var bytes = _connection.ExecuteScalar<byte[]>(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                zoom, x, yTms);

            _cache[key] = bytes;
            return bytes;
        }

        public void Dispose()
        {
            _connection.Dispose();
        }

        private int ResolveMaxZoom()
        {
            try
            {
                var metadataZoom = _connection.ExecuteScalar<string>(
                    "SELECT value FROM metadata WHERE name='maxzoom' LIMIT 1");
                if (!string.IsNullOrWhiteSpace(metadataZoom) && int.TryParse(metadataZoom, out var zFromMetadata))
                    return zFromMetadata;
            }
            catch
            {
                // ignored, fallback below
            }

            try
            {
                var zFromTiles = _connection.ExecuteScalar<int?>("SELECT MAX(zoom_level) FROM tiles");
                if (zFromTiles.HasValue)
                    return zFromTiles.Value;
            }
            catch
            {
                // ignored
            }

            return 9;
        }

        private int ResolveMinZoom()
        {
            try
            {
                var metadataZoom = _connection.ExecuteScalar<string>(
                    "SELECT value FROM metadata WHERE name='minzoom' LIMIT 1");
                if (!string.IsNullOrWhiteSpace(metadataZoom) && int.TryParse(metadataZoom, out var zFromMetadata))
                    return zFromMetadata;
            }
            catch
            {
                // ignored
            }

            try
            {
                var zFromTiles = _connection.ExecuteScalar<int?>("SELECT MIN(zoom_level) FROM tiles");
                if (zFromTiles.HasValue)
                    return zFromTiles.Value;
            }
            catch
            {
                // ignored
            }

            return 0;
        }
    }
}

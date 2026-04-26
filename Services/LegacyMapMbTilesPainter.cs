using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;

namespace SPES_Raschet.Services
{
    /// <summary>
    /// Рисует MBTiles-подложку для вкладки «старые данные» (обзор РФ, низкая детализация).
    /// </summary>
    public sealed class LegacyMapMbTilesPainter : IDisposable
    {
        private const int MaxTileCacheEntries = 256;
        private readonly MbTilesTileReader _reader;
        private readonly Dictionary<(int z, int tx, int ty), Bitmap> _tileCache = new();
        private readonly LinkedList<(int z, int tx, int ty)> _tileCacheOrder = new();
        private readonly Dictionary<(int z, int tx, int ty), LinkedListNode<(int z, int tx, int ty)>> _tileCacheNodes = new();

        public LegacyMapMbTilesPainter(MbTilesTileReader reader)
        {
            _reader = reader ?? throw new ArgumentNullException(nameof(reader));
        }

        /// <summary>
        /// Вписывает прямоугольник worldBounds (мировые пиксели Mercator) в окно с равномерным масштабом.
        /// </summary>
        public void Paint(Graphics g, int width, int height, int zoom, RectangleF worldBounds)
        {
            if (width <= 0 || height <= 0 || worldBounds.Width < 1 || worldBounds.Height < 1)
                return;

            RussiaOverviewMapTransform.Compute(new Size(width, height), worldBounds, out float s, out float offX, out float offY);

            int maxPixels = MercatorTileMath.TileSize * (1 << zoom);
            float worldRight = worldBounds.Right;
            float worldBottom = worldBounds.Bottom;
            int startTileX = (int)Math.Floor(worldBounds.Left / MercatorTileMath.TileSize);
            int endTileX = (int)Math.Floor((worldRight - 0.001f) / MercatorTileMath.TileSize);
            int startTileY = (int)Math.Floor(worldBounds.Top / MercatorTileMath.TileSize);
            int endTileY = (int)Math.Floor((worldBottom - 0.001f) / MercatorTileMath.TileSize);

            g.InterpolationMode = InterpolationMode.HighQualityBilinear;
            g.PixelOffsetMode = PixelOffsetMode.Half;

            for (int ty = startTileY; ty <= endTileY; ty++)
            {
                for (int tx = startTileX; tx <= endTileX; tx++)
                {
                    if (tx < 0 || ty < 0)
                        continue;
                    if (tx * MercatorTileMath.TileSize >= maxPixels || ty * MercatorTileMath.TileSize >= maxPixels)
                        continue;

                    var bmp = GetCachedTileBitmap(zoom, tx, ty);
                    if (bmp == null)
                        continue;

                    float tileLeft = tx * MercatorTileMath.TileSize;
                    float tileTop = ty * MercatorTileMath.TileSize;
                    var dest = new RectangleF(
                        (tileLeft - worldBounds.Left) * s + offX,
                        (tileTop - worldBounds.Top) * s + offY,
                        MercatorTileMath.TileSize * s,
                        MercatorTileMath.TileSize * s);
                    g.DrawImage(bmp, dest);
                }
            }
        }

        private void TouchCacheKey((int z, int tx, int ty) key)
        {
            if (!_tileCacheNodes.TryGetValue(key, out var node))
                return;
            _tileCacheOrder.Remove(node);
            _tileCacheNodes[key] = _tileCacheOrder.AddLast(key);
        }

        private void EvictOldestCacheEntry()
        {
            if (_tileCacheOrder.First == null)
                return;
            var key = _tileCacheOrder.First.Value;
            _tileCacheOrder.RemoveFirst();
            _tileCacheNodes.Remove(key);
            if (_tileCache.Remove(key, out var old))
                old.Dispose();
        }

        private Bitmap? GetCachedTileBitmap(int z, int tx, int ty)
        {
            var key = (z, tx, ty);
            if (_tileCache.TryGetValue(key, out var cached))
            {
                TouchCacheKey(key);
                return cached;
            }

            var bytes = _reader.GetTileBytes(z, tx, ty);
            if (bytes == null || bytes.Length == 0)
                return null;

            Bitmap decoded;
            using (var ms = new MemoryStream(bytes))
            using (var src = Image.FromStream(ms))
            {
                decoded = new Bitmap(MercatorTileMath.TileSize, MercatorTileMath.TileSize, PixelFormat.Format32bppPArgb);
                using (var g = Graphics.FromImage(decoded))
                    g.DrawImage(src, 0, 0, MercatorTileMath.TileSize, MercatorTileMath.TileSize);
            }

            while (_tileCache.Count >= MaxTileCacheEntries)
                EvictOldestCacheEntry();

            _tileCache[key] = decoded;
            _tileCacheNodes[key] = _tileCacheOrder.AddLast(key);
            return decoded;
        }

        public void Dispose()
        {
            foreach (var bmp in _tileCache.Values)
                bmp.Dispose();
            _tileCache.Clear();
            _tileCacheOrder.Clear();
            _tileCacheNodes.Clear();
        }
    }
}

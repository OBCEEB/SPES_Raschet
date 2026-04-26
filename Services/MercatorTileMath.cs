using System;
using System.Collections.Generic;
using System.Drawing;

namespace SPES_Raschet.Services
{
    /// <summary>
    /// Web Mercator (как у OSM / MBTiles) для согласования растровой подложки и полигонов регионов.
    /// </summary>
    public static class MercatorTileMath
    {
        public const int TileSize = 256;

        public static double ToMercatorLongitude(double lonFromData)
        {
            double L = lonFromData;
            if (L < 0) L += 360;
            if (L > 180) L -= 360;
            return L;
        }

        public static PointF LatLonToPixel(double lat, double lonMercator, int zoom)
        {
            double n = Math.Pow(2.0, zoom);
            double x = (lonMercator + 180.0) / 360.0 * TileSize * n;
            double latRad = lat * Math.PI / 180.0;
            double y = (1.0 - Math.Asinh(Math.Tan(latRad)) / Math.PI) / 2.0 * TileSize * n;
            return new PointF((float)x, (float)y);
        }

        public static (double lat, double lonMercator) PixelToLatLon(PointF pixel, int zoom)
        {
            double n = Math.Pow(2.0, zoom);
            double lon = pixel.X / (TileSize * n) * 360.0 - 180.0;
            double y = pixel.Y / (TileSize * n);
            double mercY = Math.PI * (1.0 - 2.0 * y);
            double lat = Math.Atan(Math.Sinh(mercY)) * 180.0 / Math.PI;
            return (lat, lon);
        }

        public static PointF ClampCenter(PointF center, int zoom)
        {
            float max = TileSize * (1 << zoom);
            float x = Math.Clamp(center.X, 0, max);
            float y = Math.Clamp(center.Y, 0, max);
            return new PointF(x, y);
        }
    }

    /// <summary>
    /// Равномерное вписывание mercator-прямоугольника в окно (подложка и полигоны — одна и та же математика).
    /// Сжатие только по X ломает соответствие растровой карты и границ.
    /// </summary>
    public static class RussiaOverviewMapTransform
    {
        public static void Compute(Size client, RectangleF worldBounds, out float scale, out float offX, out float offY)
        {
            scale = Math.Min(client.Width / worldBounds.Width, client.Height / worldBounds.Height) * 0.98f;
            float drawnW = worldBounds.Width * scale;
            float drawnH = worldBounds.Height * scale;
            offX = (client.Width - drawnW) / 2f;
            offY = (client.Height - drawnH) / 2f;
        }

        public static void WorldToScreen(
            float worldX,
            float worldY,
            RectangleF worldBounds,
            float scale,
            float offX,
            float offY,
            out float sx,
            out float sy)
        {
            sx = (worldX - worldBounds.Left) * scale + offX;
            sy = (worldY - worldBounds.Top) * scale + offY;
        }

        public static void ScreenToWorld(
            float sx,
            float sy,
            RectangleF worldBounds,
            float scale,
            float offX,
            float offY,
            out float worldX,
            out float worldY)
        {
            worldX = (sx - offX) / scale + worldBounds.Left;
            worldY = (sy - offY) / scale + worldBounds.Top;
        }
    }

    /// <summary>
    /// Прямоугольник в мировых пикселях Web Mercator на заданном zoom, охватывающий все границы (+ поля).
    /// Используем максимальный zoom из пакета: кадр вписывается в окно масштабированием (как старая «вписать РФ»).
    /// </summary>
    public static class RussiaMercatorFit
    {
        public static (int zoom, RectangleF worldBounds) FitWorldBounds(
            Dictionary<string, Dictionary<string, List<List<double>>>> boundaries,
            int minZoom,
            int maxZoom)
        {
            var pts = CollectPoints(boundaries);
            minZoom = Math.Clamp(minZoom, 0, 14);
            maxZoom = Math.Clamp(maxZoom, minZoom, 14);
            int z = maxZoom;
            float worldSize = MercatorTileMath.TileSize * (1 << z);

            if (pts.Count == 0)
                return (z, new RectangleF(0, 0, Math.Min(512f, worldSize), Math.Min(512f, worldSize)));

            float minX = float.MaxValue, maxX = float.MinValue, minY = float.MaxValue, maxY = float.MinValue;
            foreach (var (lat, lonM) in pts)
            {
                var px = MercatorTileMath.LatLonToPixel(lat, lonM, z);
                minX = Math.Min(minX, px.X);
                maxX = Math.Max(maxX, px.X);
                minY = Math.Min(minY, px.Y);
                maxY = Math.Max(maxY, px.Y);
            }

            float bw = Math.Max(maxX - minX, 8f);
            float bh = Math.Max(maxY - minY, 8f);
            float mx = bw * 0.04f;
            float my = bh * 0.04f;
            float left = minX - mx;
            float top = minY - my;
            float width = bw + 2f * mx;
            float height = bh + 2f * my;

            left = Math.Clamp(left, 0f, Math.Max(0f, worldSize - width));
            top = Math.Clamp(top, 0f, Math.Max(0f, worldSize - height));
            width = Math.Min(width, worldSize - left);
            height = Math.Min(height, worldSize - top);
            width = Math.Max(width, 16f);
            height = Math.Max(height, 16f);

            return (z, new RectangleF(left, top, width, height));
        }

        private static List<(double lat, double lonM)> CollectPoints(
            Dictionary<string, Dictionary<string, List<List<double>>>> boundaries)
        {
            var list = new List<(double, double)>();
            foreach (var region in boundaries.Values)
            {
                foreach (var polygon in region.Values)
                {
                    if (polygon == null) continue;
                    foreach (var p in polygon)
                    {
                        if (p == null || p.Count < 2) continue;
                        double lat = p[0];
                        double lonM = MercatorTileMath.ToMercatorLongitude(p[1]);
                        list.Add((lat, lonM));
                    }
                }
            }

            return list;
        }
    }
}

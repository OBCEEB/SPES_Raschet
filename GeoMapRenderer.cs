using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using SPES_Raschet.Services;

namespace SPES_Raschet
{
    public class GeoMapRenderer : IDisposable
    {
        // =========================================================================
        // КОНФИГУРАЦИЯ
        // =========================================================================

        public const int MAP_ROTATION_ANGLE = 0;
        public const bool MAP_FLIP_HORIZONTAL = false;
        public const bool MAP_FLIP_VERTICAL = false;

        // Коэффициент 0.6 (или 0.58) дает хорошие пропорции для РФ в этой проекции
        public const double SCALE_FACTOR_X = 0.6;
        public const double SCALE_FACTOR_Y = 1.0;

        private readonly Pen regionPen = new Pen(Color.FromArgb(126, 133, 143), 1.25f);
        private readonly SolidBrush defaultBrush = new SolidBrush(Color.FromArgb(222, 226, 231));
        private readonly SolidBrush hoverBrush = new SolidBrush(Color.FromArgb(109, 186, 234));
        private readonly SolidBrush selectedBrush = new SolidBrush(Color.FromArgb(117, 186, 155));
        private readonly SolidBrush defaultBrushOverTiles = new SolidBrush(Color.FromArgb(195, 222, 226, 231));
        private readonly SolidBrush hoverBrushOverTiles = new SolidBrush(Color.FromArgb(175, 109, 186, 234));
        private readonly SolidBrush selectedBrushOverTiles = new SolidBrush(Color.FromArgb(185, 117, 186, 155));

        // Параметры последней проекции
        private double lastScaleX = 1.0, lastScaleY = 1.0, lastDx = 0.0, lastDy = 0.0;
        private double lastMinLon = 0.0, lastMaxLat = 0.0;
        private double userZoom = 1.0;
        private double userPanX = 0.0;
        private double userPanY = 0.0;

        // Фиксированный Mercator-вид: прямоугольник в мировых пикселях вписывается в окно (как старая карта по РФ).
        private bool _mercatorTileMode;
        private int _mercZoom;
        private RectangleF _mercWorldBounds;
        private Size _mercClientSize;

        public bool IsMercatorTileMode => _mercatorTileMode;

        public int MercatorZoomLevel => _mercZoom;

        public RectangleF MercatorWorldBounds => _mercWorldBounds;

        public void SetMercatorTileView(Size clientSize, int zoom, RectangleF worldBoundsMercatorPixels)
        {
            _mercatorTileMode = true;
            _mercClientSize = clientSize;
            _mercZoom = zoom;
            _mercWorldBounds = worldBoundsMercatorPixels;
            userZoom = 1.0;
            userPanX = 0.0;
            userPanY = 0.0;
        }

        public void ClearMercatorTileView()
        {
            _mercatorTileMode = false;
        }

        /// <summary>
        /// Нормализует долготу, чтобы Чукотка (-170) стала продолжением России (190).
        /// </summary>
        private double NormalizeLon(double lon)
        {
            return lon < 0 ? lon + 360 : lon;
        }

        public void DrawAllRegions(
            Graphics graphics,
            Size targetSize,
            Dictionary<string, Dictionary<string, List<List<double>>>> allBoundaries,
            string? hoverRegionName = null,
            string? selectedRegionName = null)
        {
            if (allBoundaries == null || !allBoundaries.Any()) return;

            if (_mercatorTileMode)
            {
                _mercClientSize = targetSize;
                DrawAllRegionsMercator(graphics, targetSize, allBoundaries, hoverRegionName, selectedRegionName);
                return;
            }

            // 1. Определяем границы (BBox)
            (double minLon, double maxLon, double minLat, double maxLat) = GetBoundingBox(allBoundaries);

            // 2. Расчет масштаба
            // Передаем диапазоны координат и размеры экрана
            var (finalScaleX, finalScaleY, dx, dy) = CalculateProjectionParams(
                maxLon - minLon, maxLat - minLat, targetSize.Width, targetSize.Height);

            // User transform (zoom + pan) applied on top of fit-to-screen projection.
            finalScaleX *= userZoom;
            finalScaleY *= userZoom;
            dx = targetSize.Width / 2.0 - (targetSize.Width / 2.0 - dx) * userZoom + userPanX;
            dy = targetSize.Height / 2.0 - (targetSize.Height / 2.0 - dy) * userZoom + userPanY;

            // Сохраняем для кликов
            lastScaleX = finalScaleX;
            lastScaleY = finalScaleY;
            lastDx = dx;
            lastDy = dy;
            lastMinLon = minLon;
            lastMaxLat = maxLat;

            GraphicsState state = graphics.Save();
            // Включаем сглаживание для красивых линий
            graphics.SmoothingMode = SmoothingMode.AntiAlias;

            foreach (var regionPair in allBoundaries)
            {
                string regionName = regionPair.Key;
                var polygons = regionPair.Value;

                // Перебираем ВСЕ части региона
                foreach (var polyPair in polygons)
                {
                    var geoCoords = polyPair.Value;
                    if (geoCoords == null || geoCoords.Count < 2) continue;

                    // Проецируем точки на экран
                    List<PointF> screenPoints = ProjectRegion(
                        geoCoords, finalScaleX, finalScaleY, dx, dy, minLon, maxLat);

                    if (screenPoints.Count > 1)
                    {
                        SolidBrush currentBrush = defaultBrush;
                        if (regionName == selectedRegionName) currentBrush = selectedBrush;
                        if (regionName == hoverRegionName) currentBrush = hoverBrush;
                        graphics.FillPolygon(currentBrush, screenPoints.ToArray());
                        graphics.DrawPolygon(regionPen, screenPoints.ToArray());
                    }
                }
            }

            graphics.Restore(state);
        }

        private void DrawAllRegionsMercator(
            Graphics graphics,
            Size targetSize,
            Dictionary<string, Dictionary<string, List<List<double>>>> allBoundaries,
            string? hoverRegionName,
            string? selectedRegionName)
        {
            RussiaOverviewMapTransform.Compute(targetSize, _mercWorldBounds, out float s, out float offX, out float offY);

            lastScaleX = 1;
            lastScaleY = 1;
            lastDx = 0;
            lastDy = 0;
            lastMinLon = 0;
            lastMaxLat = 0;

            GraphicsState state = graphics.Save();
            graphics.SmoothingMode = SmoothingMode.AntiAlias;

            foreach (var regionPair in allBoundaries)
            {
                string regionName = regionPair.Key;
                foreach (var polyPair in regionPair.Value)
                {
                    var geoCoords = polyPair.Value;
                    if (geoCoords == null || geoCoords.Count < 2) continue;

                    var screenPoints = ProjectRegionMercator(geoCoords, _mercWorldBounds, s, offX, offY, _mercZoom);
                    if (screenPoints.Count > 1)
                    {
                        SolidBrush brush = defaultBrushOverTiles;
                        if (regionName == selectedRegionName) brush = selectedBrushOverTiles;
                        if (regionName == hoverRegionName) brush = hoverBrushOverTiles;
                        graphics.FillPolygon(brush, screenPoints.ToArray());
                        graphics.DrawPolygon(regionPen, screenPoints.ToArray());
                    }
                }
            }

            graphics.Restore(state);
        }

        private static List<PointF> ProjectRegionMercator(
            List<List<double>> geoCoords,
            RectangleF worldBounds,
            float scale,
            float offX,
            float offY,
            int zoom)
        {
            var screenPoints = new List<PointF>();
            foreach (var p in geoCoords)
            {
                if (p.Count < 2) continue;
                double lat = p[0];
                double lonM = MercatorTileMath.ToMercatorLongitude(p[1]);
                var wp = MercatorTileMath.LatLonToPixel(lat, lonM, zoom);
                RussiaOverviewMapTransform.WorldToScreen(
                    wp.X, wp.Y, worldBounds, scale, offX, offY, out float sx, out float sy);
                screenPoints.Add(new PointF(sx, sy));
            }

            return screenPoints;
        }

        // -------------------------------------------------------------------------
        // Расчет масштаба "zoom to fit" для полного отображения карты.
        // -------------------------------------------------------------------------
        private (double finalScaleX, double finalScaleY, double dx, double dy) CalculateProjectionParams(
            double lonRange, double latRange, int screenWidth, int screenHeight)
        {
            // 1. Вычисляем "виртуальную" ширину и высоту карты в условных единицах,
            // уже с учетом того, что мы хотим сжать ширину в 0.6 раз.
            double virtualMapWidth = lonRange * SCALE_FACTOR_X;
            double virtualMapHeight = latRange * SCALE_FACTOR_Y;

            if (virtualMapWidth <= 0 || virtualMapHeight <= 0) return (1, 1, 0, 0);

            // 2. Считаем коэффициент зума, который нужен, чтобы вписать 
            // эти виртуальные размеры в реальный экран.
            double zoomX = screenWidth / virtualMapWidth;
            double zoomY = screenHeight / virtualMapHeight;

            // 3. Выбираем минимальный зум, чтобы карта влезла целиком 
            // (по самой "тесной" стороне).
            double zoom = Math.Min(zoomX, zoomY);

            // 4. Немного уменьшаем (отступ 2% от краев), чтобы не прилипало к рамке
            zoom *= 0.98;

            // 5. Итоговые коэффициенты для перевода Градус -> Пиксель
            double finalScaleX = zoom * SCALE_FACTOR_X;
            double finalScaleY = zoom * SCALE_FACTOR_Y;

            // 6. Центрируем карту на экране
            double plotWidth = lonRange * finalScaleX;
            double plotHeight = latRange * finalScaleY;

            double dx = (screenWidth - plotWidth) / 2.0;
            double dy = (screenHeight - plotHeight) / 2.0;

            return (finalScaleX, finalScaleY, dx, dy);
        }

        // -------------------------------------------------------------------------
        // Вспомогательные методы проекции, поиска региона и преобразования координат.
        // -------------------------------------------------------------------------

        private (double minLon, double maxLon, double minLat, double maxLat) GetBoundingBox(
            Dictionary<string, Dictionary<string, List<List<double>>>> allBoundaries)
        {
            double minLon = double.MaxValue;
            double maxLon = double.MinValue;
            double minLat = double.MaxValue;
            double maxLat = double.MinValue;

            foreach (var region in allBoundaries.Values)
            {
                foreach (var polygon in region.Values)
                {
                    foreach (var p in polygon)
                    {
                        if (p.Count >= 2)
                        {
                            // p[0] = Lat, p[1] = Lon (в ваших данных)
                            double lat = p[0];
                            double lon = NormalizeLon(p[1]); // Важно: нормализуем долготу

                            minLon = Math.Min(minLon, lon);
                            maxLon = Math.Max(maxLon, lon);
                            minLat = Math.Min(minLat, lat);
                            maxLat = Math.Max(maxLat, lat);
                        }
                    }
                }
            }

            if (minLon == double.MaxValue) return (0, 0, 0, 0);
            return (minLon, maxLon, minLat, maxLat);
        }

        private List<PointF> ProjectRegion(
            List<List<double>> geoCoords,
            double finalScaleX,
            double finalScaleY,
            double dx,
            double dy,
            double minLon,
            double maxLat)
        {
            var screenPoints = new List<PointF>();

            foreach (var p in geoCoords)
            {
                double lat = p[0];
                double lon = NormalizeLon(p[1]); // Важно: нормализуем долготу

                float screenX = (float)(dx + (lon - minLon) * finalScaleX);
                float screenY = (float)(dy + (maxLat - lat) * finalScaleY);

                screenPoints.Add(new PointF(screenX, screenY));
            }
            return screenPoints;
        }

        public bool IsPointInPolygon(List<double> point, List<List<double>> polygon)
        {
            if (polygon.Count < 3 || point.Count < 2) return false;

            double x = point[0]; // Lon
            double y = point[1]; // Lat
            int intersections = 0;

            for (int i = 0; i < polygon.Count; i++)
            {
                var p1 = polygon[i];
                var p2 = polygon[(i + 1) % polygon.Count];

                double y1 = p1[0];
                double x1 = NormalizeLon(p1[1]);

                double y2 = p2[0];
                double x2 = NormalizeLon(p2[1]);

                if (((y1 <= y && y < y2) || (y2 <= y && y < y1)) &&
                    (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1))
                {
                    intersections++;
                }
            }

            return (intersections % 2) != 0;
        }

        public List<double>? PixelToGeo(Point screenPoint)
        {
            if (_mercatorTileMode)
            {
                RussiaOverviewMapTransform.Compute(_mercClientSize, _mercWorldBounds, out float s, out float ox, out float oy);
                RussiaOverviewMapTransform.ScreenToWorld(
                    screenPoint.X, screenPoint.Y, _mercWorldBounds, s, ox, oy, out float worldX, out float worldY);
                var (mercLat, mercLon) = MercatorTileMath.PixelToLatLon(new PointF((float)worldX, (float)worldY), _mercZoom);
                double normLon = mercLon < 0 ? mercLon + 360.0 : mercLon;
                return new List<double> { normLon, mercLat };
            }

            if (lastScaleX <= 0 || lastScaleY <= 0) return null;

            double lon = (screenPoint.X - lastDx) / lastScaleX + lastMinLon;
            double lat = lastMaxLat - (screenPoint.Y - lastDy) / lastScaleY;

            return new List<double> { lon, lat };
        }

        public void Zoom(double delta)
        {
            if (_mercatorTileMode)
                return;
            userZoom *= delta;
            if (userZoom < 0.7) userZoom = 0.7;
            if (userZoom > 4.0) userZoom = 4.0;
        }

        public void Pan(int deltaX, int deltaY)
        {
            if (_mercatorTileMode)
                return;
            userPanX += deltaX;
            userPanY += deltaY;
        }

        public void ResetView()
        {
            if (_mercatorTileMode)
                return;
            userZoom = 1.0;
            userPanX = 0.0;
            userPanY = 0.0;
        }

        public string? GetRegionNameFromScreenPoint(
            Point screenPoint,
            Dictionary<string, Dictionary<string, List<List<double>>>> allBoundaries)
        {
            List<double>? geoPoint = PixelToGeo(screenPoint);

            if (geoPoint == null || allBoundaries == null) return null;

            foreach (var regionPair in allBoundaries)
            {
                foreach (var polyPair in regionPair.Value)
                {
                    if (polyPair.Value != null && polyPair.Value.Count > 2)
                    {
                        if (IsPointInPolygon(geoPoint, polyPair.Value))
                        {
                            return regionPair.Key;
                        }
                    }
                }
            }
            return null;
        }

        private void ApplyTransformations(Graphics graphics, int screenWidth, int screenHeight)
        {
            // Совместимость со старым интерфейсом: преобразования не используются,
            // координаты проецируются напрямую в ProjectRegion.
        }

        public void Dispose()
        {
            regionPen.Dispose();
            defaultBrush.Dispose();
            hoverBrush.Dispose();
            selectedBrush.Dispose();
            defaultBrushOverTiles.Dispose();
            hoverBrushOverTiles.Dispose();
            selectedBrushOverTiles.Dispose();
        }
    }
}
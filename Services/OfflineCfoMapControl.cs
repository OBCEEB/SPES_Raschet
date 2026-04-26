using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Windows.Forms;

namespace SPES_Raschet.Services
{
    public sealed class OfflineCfoMapControl : Control
    {
        private const int TileSize = 256;
        private const int MinSupportedZoom = 6;
        private const int MaxSupportedZoomHardLimit = 14;
        private const int DefaultZoom = 7;
        private const double DefaultCenterLat = 55.0;
        private const double DefaultCenterLon = 38.5;
        private const int MaxTileCacheEntries = 384;

        private readonly Font _infoFont = new Font("Segoe UI", 9f);
        private MbTilesTileReader? _reader;
        private PointF _centerPixels = new PointF(0f, 0f);
        private int _zoom = DefaultZoom;
        private bool _isDragging;
        private Point _lastMouse;
        private bool _dragMoved;
        private string _statusText = "Офлайн-карта ЦФО не загружена.";
        private Dictionary<string, Dictionary<string, List<List<double>>>>? _cfoBoundaries;
        private int _maxAvailableZoom = 9;
        private bool _boundariesAreLatLon = true;

        /// <summary>
        /// Кэш растров тайлов: без него каждый кадр панорамы заново декодирует PNG/JPEG из потока — отсюда рывки.
        /// </summary>
        private readonly Dictionary<(int z, int tx, int ty), Bitmap> _tileCache = new();
        private readonly LinkedList<(int z, int tx, int ty)> _tileCacheOrder = new();
        private readonly Dictionary<(int z, int tx, int ty), LinkedListNode<(int z, int tx, int ty)>> _tileCacheNodes = new();

        public bool IsReady => _reader != null;
        public event Action<double, double>? MapClicked;

        public void SetCfoBoundaries(Dictionary<string, Dictionary<string, List<List<double>>>>? boundaries)
        {
            _cfoBoundaries = boundaries;
            _boundariesAreLatLon = InferLatLonOrder(boundaries);
            Invalidate();
        }

        public OfflineCfoMapControl()
        {
            SetStyle(
                ControlStyles.AllPaintingInWmPaint
                | ControlStyles.UserPaint
                | ControlStyles.OptimizedDoubleBuffer
                | ControlStyles.ResizeRedraw,
                true);
            DoubleBuffered = true;
            BackColor = Color.FromArgb(238, 243, 248);
            Cursor = Cursors.Hand;
            _centerPixels = LatLonToPixel(DefaultCenterLat, DefaultCenterLon, _zoom);
        }

        public bool TryLoadMapPackage()
        {
            try
            {
                var check = OfflineCfoMapPackageService.Validate();
                if (!check.IsReady)
                {
                    _statusText = "Пакет офлайн-карты ЦФО не найден.";
                    _reader?.Dispose();
                    _reader = null;
                    ClearTileCache();
                    Invalidate();
                    return false;
                }

                var mbTilesPath = Path.Combine(check.PackageRootPath, OfflineCfoMapPackageService.TilesFile);
                _reader?.Dispose();
                _reader = new MbTilesTileReader(mbTilesPath);
                ClearTileCache();
                _maxAvailableZoom = Math.Clamp(_reader.MaxZoom, MinSupportedZoom, MaxSupportedZoomHardLimit);
                _zoom = DefaultZoom;
                if (_zoom > _maxAvailableZoom) _zoom = _maxAvailableZoom;
                _centerPixels = LatLonToPixel(DefaultCenterLat, DefaultCenterLon, _zoom);
                _statusText = "Офлайн-карта ЦФО готова.";
                Invalidate();
                return true;
            }
            catch (Exception ex)
            {
                _statusText = $"Ошибка загрузки карты: {ex.Message}";
                _reader?.Dispose();
                _reader = null;
                ClearTileCache();
                Invalidate();
                return false;
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            e.Graphics.Clear(BackColor);

            if (_reader == null)
            {
                DrawStatus(e.Graphics, _statusText);
                return;
            }

            DrawTiles(e.Graphics);
            // Полигоны границ и Region.Exclude очень тяжёлые — во время перетаскивания только тайлы.
            if (!_isDragging)
                DrawCfoOverlay(e.Graphics);
            DrawStatus(e.Graphics, $"ЦФО офлайн • zoom {_zoom}");
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button != MouseButtons.Left)
                return;

            _isDragging = true;
            _dragMoved = false;
            _lastMouse = e.Location;
            Cursor = Cursors.SizeAll;
            Capture = true;
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            base.OnMouseUp(e);
            if (e.Button != MouseButtons.Left)
                return;

            _isDragging = false;
            Cursor = Cursors.Hand;
            Capture = false;
            Invalidate();
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            if (!_isDragging)
                return;

            var dx = e.X - _lastMouse.X;
            var dy = e.Y - _lastMouse.Y;
            if (Math.Abs(dx) + Math.Abs(dy) > 1)
                _dragMoved = true;
            _centerPixels = new PointF(_centerPixels.X - dx, _centerPixels.Y - dy);
            _lastMouse = e.Location;
            Invalidate();
        }

        protected override void OnMouseClick(MouseEventArgs e)
        {
            base.OnMouseClick(e);
            if (e.Button != MouseButtons.Left || _dragMoved || _reader == null)
                return;

            var latLon = ScreenToLatLon(e.Location);
            if (latLon == null)
                return;

            MapClicked?.Invoke(latLon.Value.lat, latLon.Value.lon);
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            base.OnMouseWheel(e);
            if (_reader == null)
                return;

            int nextZoom = _zoom + (e.Delta > 0 ? 1 : -1);
            nextZoom = Math.Clamp(nextZoom, MinSupportedZoom, _maxAvailableZoom);
            if (nextZoom == _zoom)
                return;

            var centerGeo = PixelToLatLon(_centerPixels, _zoom);
            _zoom = nextZoom;
            _centerPixels = LatLonToPixel(centerGeo.lat, centerGeo.lon, _zoom);
            _centerPixels = ClampCenter(_centerPixels, _zoom);
            ClearTileCache();
            Invalidate();
        }

        private void ClearTileCache()
        {
            foreach (var bmp in _tileCache.Values)
                bmp.Dispose();
            _tileCache.Clear();
            _tileCacheOrder.Clear();
            _tileCacheNodes.Clear();
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

            if (_reader == null)
                return null;

            var bytes = _reader.GetTileBytes(z, tx, ty);
            if (bytes == null || bytes.Length == 0)
                return null;

            Bitmap decoded;
            using (var ms = new MemoryStream(bytes))
            using (var src = Image.FromStream(ms))
            {
                decoded = new Bitmap(TileSize, TileSize, PixelFormat.Format32bppPArgb);
                using (var g = Graphics.FromImage(decoded))
                {
                    g.DrawImage(src, 0, 0, TileSize, TileSize);
                }
            }

            while (_tileCache.Count >= MaxTileCacheEntries)
                EvictOldestCacheEntry();

            _tileCache[key] = decoded;
            _tileCacheNodes[key] = _tileCacheOrder.AddLast(key);
            return decoded;
        }

        private void DrawTiles(Graphics g)
        {
            if (_reader == null)
                return;

            var maxPixels = TileSize * (1 << _zoom);
            _centerPixels = ClampCenter(_centerPixels, _zoom);

            float left = _centerPixels.X - Width / 2f;
            float top = _centerPixels.Y - Height / 2f;

            int startTileX = (int)Math.Floor(left / TileSize);
            int endTileX = (int)Math.Floor((left + Width) / TileSize);
            int startTileY = (int)Math.Floor(top / TileSize);
            int endTileY = (int)Math.Floor((top + Height) / TileSize);

            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;

            for (int ty = startTileY; ty <= endTileY; ty++)
            {
                for (int tx = startTileX; tx <= endTileX; tx++)
                {
                    if (tx < 0 || ty < 0)
                        continue;

                    if (tx * TileSize >= maxPixels || ty * TileSize >= maxPixels)
                        continue;

                    var bmp = GetCachedTileBitmap(_zoom, tx, ty);
                    if (bmp == null)
                        continue;

                    float screenX = tx * TileSize - left;
                    float screenY = ty * TileSize - top;
                    g.DrawImage(bmp, screenX, screenY, TileSize, TileSize);
                }
            }
        }

        private static PointF ClampCenter(PointF center, int zoom)
        {
            float max = TileSize * (1 << zoom);
            float x = Math.Clamp(center.X, 0, max);
            float y = Math.Clamp(center.Y, 0, max);
            return new PointF(x, y);
        }

        private void DrawStatus(Graphics g, string text)
        {
            var rect = new Rectangle(8, 8, Math.Min(380, Width - 16), 24);
            using var bg = new SolidBrush(Color.FromArgb(190, 255, 255, 255));
            using var fg = new SolidBrush(Color.FromArgb(35, 50, 70));
            g.FillRectangle(bg, rect);
            g.DrawString(text, _infoFont, fg, rect.Location);
        }

        private void DrawCfoOverlay(Graphics g)
        {
            if (_cfoBoundaries == null || _cfoBoundaries.Count == 0)
                return;

            float left = _centerPixels.X - Width / 2f;
            float top = _centerPixels.Y - Height / 2f;

            using var cfoPath = new GraphicsPath();
            foreach (var region in _cfoBoundaries.Values)
            {
                foreach (var polygon in region.Values)
                {
                    if (polygon == null || polygon.Count < 3)
                        continue;

                    var points = polygon
                        .Where(p => p.Count >= 2)
                        .Select(p =>
                        {
                            double lat = _boundariesAreLatLon ? p[0] : p[1];
                            double lon = _boundariesAreLatLon ? p[1] : p[0];
                            var px = LatLonToPixel(lat, lon, _zoom);
                            return new PointF(px.X - left, px.Y - top);
                        })
                        .ToArray();

                    if (points.Length >= 3)
                        cfoPath.AddPolygon(points);
                }
            }

            if (cfoPath.PointCount == 0)
                return;

            using var outsideRegion = new Region(new RectangleF(0, 0, Width, Height));
            outsideRegion.Exclude(cfoPath);
            using var outsideBrush = new SolidBrush(Color.FromArgb(95, 70, 85, 105));
            g.FillRegion(outsideBrush, outsideRegion);

            using var borderPen = new Pen(Color.FromArgb(32, 88, 146), 1.5f);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.DrawPath(borderPen, cfoPath);
        }

        private (double lat, double lon)? ScreenToLatLon(Point point)
        {
            if (_zoom < 0)
                return null;

            float left = _centerPixels.X - Width / 2f;
            float top = _centerPixels.Y - Height / 2f;
            double worldX = left + point.X;
            double worldY = top + point.Y;
            return PixelToLatLon(new PointF((float)worldX, (float)worldY), _zoom);
        }

        private static PointF LatLonToPixel(double lat, double lon, int zoom)
        {
            double n = Math.Pow(2.0, zoom);
            double x = (lon + 180.0) / 360.0 * TileSize * n;
            double latRad = lat * Math.PI / 180.0;
            double y = (1.0 - Math.Asinh(Math.Tan(latRad)) / Math.PI) / 2.0 * TileSize * n;
            return new PointF((float)x, (float)y);
        }

        private static (double lat, double lon) PixelToLatLon(PointF pixel, int zoom)
        {
            double n = Math.Pow(2.0, zoom);
            double lon = pixel.X / (TileSize * n) * 360.0 - 180.0;
            double y = pixel.Y / (TileSize * n);
            double mercY = Math.PI * (1.0 - 2.0 * y);
            double lat = Math.Atan(Math.Sinh(mercY)) * 180.0 / Math.PI;
            return (lat, lon);
        }

        private static bool InferLatLonOrder(Dictionary<string, Dictionary<string, List<List<double>>>>? boundaries)
        {
            if (boundaries == null || boundaries.Count == 0)
                return true;

            const double minLat = 49.5;
            const double maxLat = 60.5;
            const double minLon = 28.0;
            const double maxLon = 44.5;

            int latLonHits = 0;
            int lonLatHits = 0;
            int sampled = 0;

            foreach (var region in boundaries.Values)
            {
                foreach (var polygon in region.Values)
                {
                    foreach (var p in polygon)
                    {
                        if (p.Count < 2)
                            continue;

                        sampled++;
                        double a = p[0];
                        double b = p[1];

                        if (a >= minLat && a <= maxLat && b >= minLon && b <= maxLon)
                            latLonHits++;
                        if (b >= minLat && b <= maxLat && a >= minLon && a <= maxLon)
                            lonLatHits++;

                        if (sampled > 2000)
                            return latLonHits >= lonLatHits;
                    }
                }
            }

            return latLonHits >= lonLatHits;
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                ClearTileCache();
                _reader?.Dispose();
                _infoFont.Dispose();
            }

            base.Dispose(disposing);
        }
    }
}

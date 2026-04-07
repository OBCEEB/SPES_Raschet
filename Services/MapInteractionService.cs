using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;

namespace SPES_Raschet.Services
{
    public sealed class MapInteractionService
    {
        private bool _isPanning;
        private Point _panStartPoint;

        public bool IsPanning => _isPanning;

        public void BeginPan(MouseButtons button, Point location)
        {
            if (button != MouseButtons.Middle) return;
            _isPanning = true;
            _panStartPoint = location;
        }

        public void EndPan(MouseButtons button)
        {
            if (button != MouseButtons.Middle) return;
            _isPanning = false;
        }

        public Point ConsumePanDelta(Point currentLocation)
        {
            var dx = currentLocation.X - _panStartPoint.X;
            var dy = currentLocation.Y - _panStartPoint.Y;
            _panStartPoint = currentLocation;
            return new Point(dx, dy);
        }

        public string? FindRegionAtPoint(
            GeoMapRenderer renderer,
            Point screenPoint,
            Dictionary<string, Dictionary<string, List<List<double>>>>? allRegionBoundaries)
        {
            if (allRegionBoundaries == null) return null;
            return renderer.GetRegionNameFromScreenPoint(screenPoint, allRegionBoundaries);
        }

        public string? FindHoverRegion(
            GeoMapRenderer renderer,
            Point screenPoint,
            Size mapSize,
            Dictionary<string, Dictionary<string, List<List<double>>>>? allRegionBoundaries)
        {
            if (allRegionBoundaries == null) return null;

            var geoPoint = renderer.PixelToGeo(screenPoint);
            if (geoPoint == null) return null;

            foreach (var regionEntry in allRegionBoundaries)
            {
                foreach (var polygonEntry in regionEntry.Value)
                {
                    if (polygonEntry.Value != null && polygonEntry.Value.Count > 1)
                    {
                        if (renderer.IsPointInPolygon(geoPoint, polygonEntry.Value))
                            return regionEntry.Key;
                    }
                }
            }

            return null;
        }
    }
}

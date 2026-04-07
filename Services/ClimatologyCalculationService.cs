using System;
using System.Collections.Generic;
using System.Data;
using System.Linq;

namespace SPES_Raschet.Services
{
    public static class ClimatologyCalculationService
    {
        public static DataTable CalculateHourlyIrradiance(double targetLat)
        {
            DataTable dt = new DataTable();
            dt.Columns.Add("Час", typeof(int));

            var firstEntry = DataStore.IrradianceList.FirstOrDefault();
            if (firstEntry == null) return dt;

            var directions = firstEntry.Values.Keys.OrderBy(k => k).ToList();
            foreach (var dir in directions) dt.Columns.Add(dir, typeof(double));

            int minHour = DataStore.IrradianceList.Min(d => d.StartHour);
            int maxHour = DataStore.IrradianceList.Max(d => d.StartHour);

            for (int hour = minHour; hour <= maxHour; hour++)
            {
                DataRow row = dt.NewRow();
                row["Час"] = hour;
                bool hasData = false;

                foreach (var dir in directions)
                {
                    var points = new Dictionary<double, double>();
                    var rawData = DataStore.IrradianceList.Where(d => d.StartHour == hour);
                    foreach (var item in rawData)
                    {
                        if (item.Values.TryGetValue(dir, out double val) && val >= 0)
                        {
                            if (!points.ContainsKey(item.Latitude)) points.Add(item.Latitude, val);
                        }
                    }

                    if (points.Count >= 2)
                    {
                        double val = Math.Max(0, MathTools.Interpolate(targetLat, points));
                        row[dir] = Math.Round(val, 2);
                        if (val > 0.1) hasData = true;
                    }
                    else row[dir] = 0;
                }

                if (hasData) dt.Rows.Add(row);
            }

            return dt;
        }

        public static DataTable CalculateSunPosition(double targetLat)
        {
            DataTable dt = new DataTable();
            dt.Columns.Add("Час", typeof(int));
            dt.Columns.Add("Высота (h), °", typeof(double));
            dt.Columns.Add("Азимут (Ac), °", typeof(double));

            if (DataStore.SunPositionList == null || !DataStore.SunPositionList.Any()) return dt;
            var hours = DataStore.SunPositionList.Select(x => x.StartHour).Distinct().OrderBy(h => h).ToList();

            foreach (int hour in hours)
            {
                var altPoints = new Dictionary<double, double>();
                var azPoints = new Dictionary<double, double>();
                var hourData = DataStore.SunPositionList.Where(x => x.StartHour == hour);

                foreach (var item in hourData)
                {
                    if (!altPoints.ContainsKey(item.Longitude)) altPoints.Add(item.Longitude, item.Altitude);
                    if (!azPoints.ContainsKey(item.Longitude)) azPoints.Add(item.Longitude, item.Azimuth);
                }

                if (altPoints.Count >= 2)
                {
                    double alt = MathTools.Interpolate(targetLat, altPoints);
                    double az = MathTools.Interpolate(targetLat, azPoints);
                    DataRow row = dt.NewRow();
                    row["Час"] = hour;
                    row["Высота (h), °"] = Math.Round(alt, 2);
                    row["Азимут (Ac), °"] = Math.Round(az, 2);
                    dt.Rows.Add(row);
                }
            }

            return dt;
        }
    }
}

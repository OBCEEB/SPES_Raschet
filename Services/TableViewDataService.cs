using System.Data;
using System.Linq;

namespace SPES_Raschet.Services
{
    public static class TableViewDataService
    {
        public static DataTable FlattenIrradianceData()
        {
            DataTable dt = new DataTable("IrradianceData");
            if (DataStore.IrradianceList == null || !DataStore.IrradianceList.Any()) return dt;

            var allKeys = DataStore.IrradianceList
                .SelectMany(d => d.Values.Keys)
                .Distinct()
                .OrderBy(key => key)
                .ToList();

            dt.Columns.Add("Широта, °", typeof(double));
            dt.Columns.Add("Час", typeof(int));
            foreach (string key in allKeys) dt.Columns.Add(key, typeof(double));

            foreach (var item in DataStore.IrradianceList)
            {
                DataRow row = dt.NewRow();
                row["Широта, °"] = item.Latitude;
                row["Час"] = item.StartHour;
                foreach (string key in allKeys)
                    row[key] = item.Values.TryGetValue(key, out double value) ? value : (object)DBNull.Value;
                dt.Rows.Add(row);
            }

            return dt;
        }

        public static DataTable FlattenSunPositionData()
        {
            DataTable dt = new DataTable("SunPositionData");
            dt.Columns.Add("Широта, °", typeof(double));
            dt.Columns.Add("Час", typeof(int));
            dt.Columns.Add("Высота (h), °", typeof(double));
            dt.Columns.Add("Азимут (Ac), °", typeof(double));

            if (DataStore.SunPositionList != null)
            {
                foreach (var item in DataStore.SunPositionList)
                    dt.Rows.Add(item.Longitude, item.StartHour, item.Altitude, item.Azimuth);
            }

            return dt;
        }

        public static DataTable FlattenDailyTotalData()
        {
            DataTable dt = new DataTable("DailyTotalData");
            dt.Columns.Add("Широта, °", typeof(double));
            dt.Columns.Add("Суточный итог, МДж/м²", typeof(double));

            if (DataStore.DailyTotalList != null)
            {
                foreach (var item in DataStore.DailyTotalList)
                    dt.Rows.Add(item.Latitude, item.DailyTotalHorizontalIrradiance);
            }

            return dt;
        }
    }
}

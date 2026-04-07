using System;
using System.Collections.Generic;
using System.IO;

namespace SPES_Raschet.Diagnostics
{
    public sealed class DiagnosticsReport
    {
        public List<string> MissingFiles { get; } = new List<string>();
        public List<string> FoundFiles { get; } = new List<string>();
        public bool HasIssues => MissingFiles.Count > 0;
    }

    public static class StartupDiagnosticsService
    {
        private static readonly string[] RequiredFiles =
        {
            "settlements.csv",
            "regions_bounds.json",
            "DailyTotalData.csv",
            "IrradianceData.csv",
            "SunPosition_Altitude.csv",
            "SunPosition_Azimuth.csv"
        };

        public static DiagnosticsReport Run()
        {
            var report = new DiagnosticsReport();
            string baseDir = AppContext.BaseDirectory;

            foreach (var file in RequiredFiles)
            {
                string path = Path.Combine(baseDir, file);
                if (File.Exists(path))
                    report.FoundFiles.Add(file);
                else
                    report.MissingFiles.Add(file);
            }

            return report;
        }
    }
}

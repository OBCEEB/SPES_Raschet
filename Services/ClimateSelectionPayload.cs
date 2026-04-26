using System;

namespace SPES_Raschet.Services
{
    public sealed class ClimateSelectionPayload
    {
        public ClimateMode Mode { get; set; }
        public string Region { get; set; } = string.Empty;
        public string Settlement { get; set; } = string.Empty;
        public double Latitude { get; set; }
        public double Longitude { get; set; }
        public int TimeZoneOffset { get; set; }
        public DateTime CapturedAtUtc { get; set; } = DateTime.UtcNow;
    }
}

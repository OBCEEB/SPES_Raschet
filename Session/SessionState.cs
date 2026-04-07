namespace SPES_Raschet.Session
{
    public sealed class SessionState
    {
        public string SettlementName { get; set; } = string.Empty;
        public string Region { get; set; } = string.Empty;
        public double Latitude { get; set; }
        public double Longitude { get; set; }
        public int TimeZoneOffset { get; set; }
        public int NavTabIndex { get; set; }
        public int SelectedTableIndex { get; set; }
        public string FilterText { get; set; } = string.Empty;
    }
}

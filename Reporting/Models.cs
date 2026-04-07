using System.Collections.Generic;
using System.Data;

namespace SPES_Raschet.Reporting
{
    public enum ReportPageOrientation
    {
        Portrait,
        Landscape
    }

    public sealed class ReportRequest
    {
        public bool IncludeSummary { get; set; } = true;
        public bool IncludeIrradianceTable { get; set; } = true;
        public bool IncludeSunPositionTable { get; set; } = true;
        public bool IncludeOverviewCharts { get; set; } = true;
        public bool IncludeDirectionalCharts { get; set; } = true;
        public bool ShowExactPointLabelsOnCharts { get; set; } = true;
        public ReportPageOrientation Orientation { get; set; } = ReportPageOrientation.Landscape;
    }

    public interface IModuleReportProvider
    {
        ReportDocument BuildReport(ReportRequest request);
    }

    public sealed class ReportDocument
    {
        public string Title { get; set; } = string.Empty;
        public string Subtitle { get; set; } = string.Empty;
        public List<ReportSection> Sections { get; } = new List<ReportSection>();
    }

    public abstract class ReportSection
    {
        public string Title { get; set; } = string.Empty;
    }

    public sealed class TextSection : ReportSection
    {
        public string Text { get; set; } = string.Empty;
    }

    public sealed class TableSection : ReportSection
    {
        public DataTable Table { get; set; } = new DataTable();
    }

    public sealed class ImageSection : ReportSection
    {
        public byte[] ImagePng { get; set; } = new byte[0];
    }
}

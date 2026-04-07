using System;
using System.Data;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms.DataVisualization.Charting;

namespace SPES_Raschet.Reporting
{
    public sealed class ClimatologyReportProvider : IModuleReportProvider
    {
        private readonly SettlementData _settlement;
        private readonly DataTable _irradianceTable;
        private readonly DataTable _sunPositionTable;
        private readonly byte[] _overviewIrradianceChartPng;
        private readonly byte[] _overviewSunChartPng;

        public ClimatologyReportProvider(
            SettlementData settlement,
            DataTable irradianceTable,
            DataTable sunPositionTable,
            byte[] overviewIrradianceChartPng,
            byte[] overviewSunChartPng)
        {
            _settlement = settlement;
            _irradianceTable = irradianceTable;
            _sunPositionTable = sunPositionTable;
            _overviewIrradianceChartPng = overviewIrradianceChartPng;
            _overviewSunChartPng = overviewSunChartPng;
        }

        public ReportDocument BuildReport(ReportRequest request)
        {
            var report = new ReportDocument
            {
                Title = $"СПЭС-Климатология • {_settlement.CityOrSettlement}",
                Subtitle = $"Координаты: {_settlement.Latitude:F2} с.ш., {_settlement.Longitude:F2} в.д."
            };

            if (request.IncludeSummary)
            {
                report.Sections.Add(new TextSection
                {
                    Title = "Сводка",
                    Text = $"Регион: {_settlement.Region}\nНаселенный пункт: {_settlement.CityOrSettlement}\nЧасовой пояс: UTC{(_settlement.TimeZoneOffset >= 0 ? "+" : "")}{_settlement.TimeZoneOffset}"
                });
            }

            if (request.IncludeIrradianceTable)
            {
                report.Sections.Add(new TableSection
                {
                    Title = "Таблица 1. Почасовая радиация",
                    Table = _irradianceTable.Copy()
                });
            }

            if (request.IncludeSunPositionTable)
            {
                report.Sections.Add(new TableSection
                {
                    Title = "Таблица 2. Положение Солнца",
                    Table = _sunPositionTable.Copy()
                });
            }

            if (request.IncludeOverviewCharts)
            {
                report.Sections.Add(new ImageSection
                {
                    Title = "График инсоляции (сводный)",
                    ImagePng = _overviewIrradianceChartPng
                });
                report.Sections.Add(new ImageSection
                {
                    Title = "График положения Солнца (сводный)",
                    ImagePng = _overviewSunChartPng
                });
            }

            if (request.IncludeDirectionalCharts)
            {
                foreach (var section in BuildDirectionalChartSections(_irradianceTable, request.ShowExactPointLabelsOnCharts))
                    report.Sections.Add(section);
            }

            return report;
        }

        private static ImageSection[] BuildDirectionalChartSections(DataTable irradiance, bool showExactLabels)
        {
            if (irradiance.Columns.Count <= 1 || irradiance.Rows.Count == 0)
                return Array.Empty<ImageSection>();

            var sections = irradiance.Columns
                .Cast<DataColumn>()
                .Skip(1)
                .Select(column => new ImageSection
                {
                    Title = $"График по направлению: {column.ColumnName}",
                    ImagePng = RenderSingleDirectionChart(irradiance, column.ColumnName, showExactLabels)
                })
                .ToArray();

            return sections;
        }

        private static byte[] RenderSingleDirectionChart(DataTable source, string directionColumn, bool showExactLabels)
        {
            using var chart = new Chart
            {
                Width = 1200,
                Height = 420,
                BackColor = Color.White
            };

            var area = new ChartArea("Main");
            area.BackColor = Color.White;
            area.AxisX.Title = "Час суток";
            area.AxisY.Title = "Вт/м²";
            area.AxisX.Interval = 1;
            area.AxisX.MajorGrid.LineColor = Color.FromArgb(236, 240, 244);
            area.AxisY.MajorGrid.LineColor = Color.FromArgb(236, 240, 244);
            chart.ChartAreas.Add(area);

            chart.Titles.Add(new Title($"Инсоляция: {directionColumn}") { Font = new Font("Segoe UI", 12, FontStyle.Bold) });

            var series = new Series(directionColumn)
            {
                ChartType = SeriesChartType.Spline,
                BorderWidth = 3,
                Color = Color.FromArgb(35, 140, 93),
                IsValueShownAsLabel = showExactLabels,
                LabelFormat = "0.##",
                Font = new Font("Segoe UI", 8f, FontStyle.Regular),
                LabelForeColor = Color.FromArgb(32, 41, 52)
            };

            foreach (DataRow row in source.Rows)
            {
                if (!int.TryParse(row["Час"]?.ToString(), out int hour))
                    continue;

                if (!double.TryParse(row[directionColumn]?.ToString(), out double value))
                    value = 0;

                series.Points.AddXY(hour, value);
            }

            chart.Series.Add(series);

            using var stream = new MemoryStream();
            chart.SaveImage(stream, ChartImageFormat.Png);
            return stream.ToArray();
        }
    }
}

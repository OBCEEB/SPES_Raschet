using System.Data;
using System.IO;
using QuestPDF.Fluent;
using QuestPDF.Helpers;
using QuestPDF.Infrastructure;

namespace SPES_Raschet.Reporting
{
    public sealed class PdfReportExporter
    {
        public PdfReportExporter()
        {
            QuestPDF.Settings.License = LicenseType.Community;
        }

        public byte[] GenerateBytes(ReportDocument report, ReportPageOrientation orientation)
        {
            return Document
                .Create(container =>
                {
                    container.Page(page =>
                    {
                        page.Size(orientation == ReportPageOrientation.Landscape
                            ? PageSizes.A4.Landscape()
                            : PageSizes.A4);
                        page.Margin(20);
                        page.DefaultTextStyle(x => x.FontSize(10));

                        page.Header().Column(col =>
                        {
                            col.Item().Text(report.Title).SemiBold().FontSize(18);
                            if (!string.IsNullOrWhiteSpace(report.Subtitle))
                                col.Item().Text(report.Subtitle).FontSize(11).FontColor(Colors.Grey.Darken1);
                        });

                        page.Content().PaddingVertical(8).Column(col =>
                        {
                            foreach (var section in report.Sections)
                            {
                                switch (section)
                                {
                                    case TextSection text:
                                        col.Item().PaddingBottom(8).Column(s =>
                                        {
                                            s.Item().Text(section.Title).SemiBold().FontSize(13);
                                            s.Item().Text(text.Text);
                                        });
                                        break;
                                    case TableSection table:
                                        col.Item().PaddingBottom(8).Column(s =>
                                        {
                                            s.Item().Text(section.Title).SemiBold().FontSize(13);
                                            s.Item().Element(c => RenderTable(c, table.Table));
                                        });
                                        break;
                                    case ImageSection image:
                                        col.Item().PaddingBottom(8).PreventPageBreak().Column(s =>
                                        {
                                            s.Item().Text(section.Title).SemiBold().FontSize(13);
                                            s.Item().Image(image.ImagePng).FitWidth();
                                        });
                                        break;
                                }
                            }
                        });

                        page.Footer()
                            .AlignCenter()
                            .Text(x =>
                            {
                                x.Span("СПЭС • ");
                                x.CurrentPageNumber();
                                x.Span(" / ");
                                x.TotalPages();
                            });
                    });
                })
                .GeneratePdf();
        }

        public void Export(ReportDocument report, ReportPageOrientation orientation, string targetPath)
        {
            var bytes = GenerateBytes(report, orientation);
            File.WriteAllBytes(targetPath, bytes);
        }

        private static void RenderTable(IContainer container, DataTable table)
        {
            container.Table(t =>
            {
                int colCount = table.Columns.Count;
                t.ColumnsDefinition(c =>
                {
                    for (int i = 0; i < colCount; i++)
                        c.RelativeColumn();
                });

                t.Header(header =>
                {
                    foreach (DataColumn column in table.Columns)
                    {
                        header.Cell()
                            .Background(Colors.Green.Lighten3)
                            .Border(1)
                            .Padding(4)
                            .Text(column.ColumnName)
                            .SemiBold()
                            .FontSize(9);
                    }
                });

                foreach (DataRow row in table.Rows)
                {
                    foreach (DataColumn column in table.Columns)
                    {
                        var value = row[column] == DBNull.Value ? string.Empty : row[column]?.ToString() ?? string.Empty;
                        t.Cell().Border(1).Padding(3).Text(value).FontSize(8);
                    }
                }
            });
        }
    }
}

using System.Drawing;
using System.IO;
using System.Windows.Forms;
using Microsoft.Web.WebView2.WinForms;

namespace SPES_Raschet.Reporting
{
    public class ReportExportOptionsForm : Form
    {
        private readonly CheckBox chkSummary;
        private readonly CheckBox chkIrradianceTable;
        private readonly CheckBox chkSunTable;
        private readonly CheckBox chkOverviewCharts;
        private readonly CheckBox chkDirectionalCharts;
        private readonly CheckBox chkExactLabels;
        private readonly RadioButton rbLandscape;
        private readonly RadioButton rbPortrait;
        private readonly WebView2 previewBrowser;
        private readonly System.Windows.Forms.Timer previewTimer;
        private readonly Func<ReportRequest, byte[]>? _previewBuilder;
        private readonly SplitContainer rootSplit;
        private string? _previewFilePath;

        public ReportRequest Request { get; private set; } = new ReportRequest();

        public ReportExportOptionsForm(Func<ReportRequest, byte[]>? previewBuilder = null)
        {
            _previewBuilder = previewBuilder;
            Text = "Параметры экспорта в PDF";
            StartPosition = FormStartPosition.CenterParent;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ClientSize = new Size(1240, 700);
            BackColor = Color.White;

            rootSplit = new SplitContainer
            {
                Dock = DockStyle.Fill,
                SplitterDistance = 250,
                IsSplitterFixed = false,
                BorderStyle = BorderStyle.None,
                FixedPanel = FixedPanel.Panel1
            };
            rootSplit.Panel1MinSize = 260;
            Controls.Add(rootSplit);

            rootSplit.SplitterMoved += (_, _) =>
            {
                if (rootSplit.SplitterDistance < rootSplit.Panel1MinSize)
                    rootSplit.SplitterDistance = rootSplit.Panel1MinSize;
            };

            var panel = new Panel { Dock = DockStyle.Fill, Padding = new Padding(18, 14, 18, 14) };
            rootSplit.Panel1.Controls.Add(panel);
            var title = new Label
            {
                Dock = DockStyle.Top,
                Height = 32,
                Text = "Выберите состав отчета",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                ForeColor = AppTheme.TextColor
            };
            panel.Controls.Add(title);

            var flow = new FlowLayoutPanel
            {
                Dock = DockStyle.Top,
                AutoSize = true,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                Padding = new Padding(0, 8, 0, 8)
            };
            panel.Controls.Add(flow);

            chkSummary = CreateCheckBox("Сводная информация по населенному пункту", true);
            chkIrradianceTable = CreateCheckBox("Таблица почасовой радиации", true);
            chkSunTable = CreateCheckBox("Таблица положения Солнца", true);
            chkOverviewCharts = CreateCheckBox("Сводные графики", true);
            chkDirectionalCharts = CreateCheckBox("Отдельные графики по направлениям", true);
            chkExactLabels = CreateCheckBox("Точные подписи данных на графиках", true);
            rbLandscape = new RadioButton
            {
                Text = "Альбомная ориентация (рекомендуется)",
                Checked = true,
                AutoSize = true,
                Font = new Font("Segoe UI", 9.5f, FontStyle.Regular),
                ForeColor = AppTheme.TextColor,
                Margin = new Padding(0, 10, 0, 4)
            };
            rbPortrait = new RadioButton
            {
                Text = "Книжная ориентация",
                AutoSize = true,
                Font = new Font("Segoe UI", 9.5f, FontStyle.Regular),
                ForeColor = AppTheme.TextColor,
                Margin = new Padding(0, 4, 0, 8)
            };

            flow.Controls.Add(chkSummary);
            flow.Controls.Add(chkIrradianceTable);
            flow.Controls.Add(chkSunTable);
            flow.Controls.Add(chkOverviewCharts);
            flow.Controls.Add(chkDirectionalCharts);
            flow.Controls.Add(chkExactLabels);
            flow.Controls.Add(rbLandscape);
            flow.Controls.Add(rbPortrait);

            var btnExport = new Button
            {
                Text = "Экспорт",
                Width = 110,
                Height = 32,
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            btnExport.FlatAppearance.BorderSize = 0;
            btnExport.Click += (_, _) =>
            {
                Request = new ReportRequest
                {
                    IncludeSummary = chkSummary.Checked,
                    IncludeIrradianceTable = chkIrradianceTable.Checked,
                    IncludeSunPositionTable = chkSunTable.Checked,
                    IncludeOverviewCharts = chkOverviewCharts.Checked,
                    IncludeDirectionalCharts = chkDirectionalCharts.Checked,
                    ShowExactPointLabelsOnCharts = chkExactLabels.Checked,
                    Orientation = rbPortrait.Checked ? ReportPageOrientation.Portrait : ReportPageOrientation.Landscape
                };
                DialogResult = DialogResult.OK;
                Close();
            };

            var btnCancel = new Button
            {
                Text = "Отмена",
                Width = 110,
                Height = 32,
                FlatStyle = FlatStyle.Flat
            };
            btnCancel.Click += (_, _) =>
            {
                DialogResult = DialogResult.Cancel;
                Close();
            };

            var previewButtons = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                FlowDirection = FlowDirection.RightToLeft,
                Height = 44,
                Padding = new Padding(8, 4, 8, 4)
            };

            var previewPanel = new Panel { Dock = DockStyle.Fill, BackColor = Color.White };
            rootSplit.Panel2.Controls.Add(previewPanel);

            var previewTitle = new Label
            {
                Dock = DockStyle.Top,
                Height = 36,
                Text = "Предпросмотр отчета",
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                ForeColor = AppTheme.TextColor,
                Padding = new Padding(10, 8, 0, 0)
            };
            previewPanel.Controls.Add(previewTitle);

            previewBrowser = new WebView2
            {
                Dock = DockStyle.Fill
            };
            previewPanel.Controls.Add(previewBrowser);
            previewPanel.Controls.Add(previewButtons);
            previewBrowser.BringToFront();
            previewButtons.BringToFront();

            previewButtons.Controls.Add(btnExport);
            previewButtons.Controls.Add(btnCancel);

            previewTimer = new System.Windows.Forms.Timer { Interval = 500 };
            previewTimer.Tick += (_, _) =>
            {
                previewTimer.Stop();
                RefreshPreview();
            };

            HookPreviewEvents();
            Shown += async (_, _) =>
            {
                ApplyDefaultPreviewLayout();
                try
                {
                    await previewBrowser.EnsureCoreWebView2Async();
                    RefreshPreview();
                }
                catch
                {
                    previewTitle.Text = "Предпросмотр недоступен (WebView2 Runtime не найден)";
                }
            };
            Resize += (_, _) => ApplyDefaultPreviewLayout();
            FormClosed += (_, _) =>
            {
                try
                {
                    if (!string.IsNullOrWhiteSpace(_previewFilePath) && File.Exists(_previewFilePath))
                        File.Delete(_previewFilePath);
                }
                catch { }
            };
        }

        private static CheckBox CreateCheckBox(string text, bool isChecked)
        {
            return new CheckBox
            {
                Text = text,
                Checked = isChecked,
                AutoSize = true,
                Margin = new Padding(0, 4, 0, 4),
                Font = new Font("Segoe UI", 9.5f, FontStyle.Regular),
                ForeColor = AppTheme.TextColor
            };
        }

        private void HookPreviewEvents()
        {
            chkSummary.CheckedChanged += (_, _) => SchedulePreview();
            chkIrradianceTable.CheckedChanged += (_, _) => SchedulePreview();
            chkSunTable.CheckedChanged += (_, _) => SchedulePreview();
            chkOverviewCharts.CheckedChanged += (_, _) => SchedulePreview();
            chkDirectionalCharts.CheckedChanged += (_, _) => SchedulePreview();
            chkExactLabels.CheckedChanged += (_, _) => SchedulePreview();
            rbLandscape.CheckedChanged += (_, _) => SchedulePreview();
            rbPortrait.CheckedChanged += (_, _) => SchedulePreview();
        }

        private void SchedulePreview()
        {
            if (_previewBuilder == null) return;
            previewTimer.Stop();
            previewTimer.Start();
        }

        private void RefreshPreview()
        {
            if (_previewBuilder == null || previewBrowser.CoreWebView2 == null)
                return;

            var request = new ReportRequest
            {
                IncludeSummary = chkSummary.Checked,
                IncludeIrradianceTable = chkIrradianceTable.Checked,
                IncludeSunPositionTable = chkSunTable.Checked,
                IncludeOverviewCharts = chkOverviewCharts.Checked,
                IncludeDirectionalCharts = chkDirectionalCharts.Checked,
                ShowExactPointLabelsOnCharts = chkExactLabels.Checked,
                Orientation = rbPortrait.Checked ? ReportPageOrientation.Portrait : ReportPageOrientation.Landscape
            };

            var bytes = _previewBuilder(request);
            _previewFilePath = Path.Combine(Path.GetTempPath(), $"spes_preview_{System.Guid.NewGuid():N}.pdf");
            File.WriteAllBytes(_previewFilePath, bytes);
            previewBrowser.CoreWebView2.Navigate(_previewFilePath);
        }

        private void ApplyDefaultPreviewLayout()
        {
            int targetLeftWidth = (int)(ClientSize.Width * 0.22);
            if (targetLeftWidth < rootSplit.Panel1MinSize)
                targetLeftWidth = rootSplit.Panel1MinSize;

            if (targetLeftWidth > ClientSize.Width - 200)
                targetLeftWidth = ClientSize.Width - 200;

            if (targetLeftWidth > rootSplit.Panel1MinSize)
                rootSplit.SplitterDistance = targetLeftWidth;
        }
    }
}

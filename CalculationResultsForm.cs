using System;
using System.Collections.Generic;
using System.Data;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Windows.Forms;
using System.Windows.Forms.DataVisualization.Charting;
using SPES_Raschet.Reporting;
using SPES_Raschet.Services;

namespace SPES_Raschet
{
    public class CalculationResultsForm : Form
    {
        private readonly SettlementData _settlement;

        // --- UI Элементы ---
        private TabControl mainTabControl = null!;
        private DataGridView gridIrradiance = null!;
        private DataGridView gridSunPosition = null!;
        private Chart chartIrradiance = null!;
        private Chart chartSunPosition = null!;
        private Label titleLabel = null!;
        private Label subtitleLabel = null!;
        private Button btnExportPdf = null!;

        // --- Элементы управления Графиками ---
        private PictureBox compassBox = null!;
        private CheckBox chkShowMarkers = null!;
        private Dictionary<string, bool> directionsState;
        private readonly string[] _directionsOrder = { "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ", "С", "СВ" };
        private const int CENTER_RADIUS = 15;

        // --- Переменные для анимации графика ---
        private DataPoint? _lastHighlightedPoint = null;
        private readonly ToolTip _chartToolTip = new ToolTip();
        private const int DefaultMarkerSize = 0; // По умолчанию точки скрыты
        private const int VisibleMarkerSize = 7; // Размер если включен чекбокс
        private const int HoverMarkerSize = 12;  // Размер при наведении
        private static readonly Color[] IrradianceSeriesPalette =
        {
            Color.FromArgb(0, 114, 178),   // Blue
            Color.FromArgb(213, 94, 0),    // Vermillion
            Color.FromArgb(0, 158, 115),   // Bluish green
            Color.FromArgb(204, 121, 167), // Reddish purple
            Color.FromArgb(86, 180, 233),  // Sky blue
            Color.FromArgb(230, 159, 0),   // Orange
            Color.FromArgb(153, 153, 153), // Gray
            Color.FromArgb(52, 73, 94),    // Dark slate
            Color.FromArgb(46, 134, 193),
            Color.FromArgb(39, 174, 96),
            Color.FromArgb(241, 196, 15),
            Color.FromArgb(192, 57, 43),
            Color.FromArgb(22, 160, 133),
            Color.FromArgb(142, 68, 173),
            Color.FromArgb(127, 140, 141),
            Color.FromArgb(44, 62, 80)
        };
        private DataTable _irradianceResult = new DataTable();
        private DataTable _sunPositionResult = new DataTable();

        public CalculationResultsForm(SettlementData data)
        {
            _settlement = data;

            directionsState = new Dictionary<string, bool>();
            foreach (var dir in _directionsOrder) directionsState[dir] = true;

            InitializeUI();
            PerformCalculations();
        }

        private void InitializeUI()
        {
            this.Text = $"Результаты расчета: {_settlement.CityOrSettlement}";
            this.Size = new Size(1300, 850);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = AppTheme.BackgroundColor;
            this.Font = new Font("Segoe UI", 9);

            // 1. Верхняя панель
            Panel headerPanel = new Panel
            {
                Dock = DockStyle.Top,
                Height = 80,
                BackColor = Color.White,
                Padding = new Padding(24, 10, 24, 10)
            };

            titleLabel = new Label
            {
                Text = $"{_settlement.CityOrSettlement} ({_settlement.Region})",
                Font = new Font("Segoe UI", 16, FontStyle.Bold),
                ForeColor = AppTheme.TextColor,
                AutoSize = true,
                Dock = DockStyle.Top
            };

            subtitleLabel = new Label
            {
                Text = "Идет расчет...",
                Font = new Font("Segoe UI", 11, FontStyle.Regular),
                ForeColor = AppTheme.MutedTextColor,
                AutoSize = true,
                Dock = DockStyle.Top,
                Padding = new Padding(0, 5, 0, 0)
            };

            headerPanel.Controls.Add(subtitleLabel);
            headerPanel.Controls.Add(titleLabel);

            btnExportPdf = new Button
            {
                Text = "Экспорт PDF",
                Width = 140,
                Height = 34,
                Anchor = AnchorStyles.Top | AnchorStyles.Right,
                FlatStyle = FlatStyle.Flat,
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White,
                Location = new Point(headerPanel.Width - 170, 22)
            };
            btnExportPdf.FlatAppearance.BorderSize = 0;
            btnExportPdf.FlatAppearance.MouseOverBackColor = AppTheme.DarkPrimary;
            btnExportPdf.FlatAppearance.MouseDownBackColor = AppTheme.DarkPrimary;
            btnExportPdf.Click += BtnExportPdf_Click;
            headerPanel.Resize += (_, _) => btnExportPdf.Location = new Point(headerPanel.Width - 170, 22);
            headerPanel.Controls.Add(btnExportPdf);
            this.Controls.Add(headerPanel);

            // 2. Вкладки
            mainTabControl = new TabControl
            {
                Dock = DockStyle.Fill,
                Font = new Font("Segoe UI", 10),
                Padding = new Point(15, 5)
            };
            this.Controls.Add(mainTabControl);
            mainTabControl.BringToFront();

            // === ВКЛАДКА 1: ТАБЛИЦЫ ===
            TabPage tabTables = new TabPage("Табличные данные");
            tabTables.BackColor = Color.White;

            SplitContainer splitTables = new SplitContainer
            {
                Dock = DockStyle.Fill,
                Orientation = Orientation.Horizontal,
                SplitterDistance = this.Height / 2,
                SplitterWidth = 8,
                BackColor = AppTheme.BackgroundColor
            };

            gridIrradiance = CreateStyledGrid();
            gridSunPosition = CreateStyledGrid();

            splitTables.Panel1.Controls.Add(AddLabelToGrid(gridIrradiance, "Таблица 1: Почасовая радиация (Вт/м²)"));
            splitTables.Panel2.Controls.Add(AddLabelToGrid(gridSunPosition, "Таблица 2: Положение Солнца"));

            tabTables.Controls.Add(splitTables);
            mainTabControl.TabPages.Add(tabTables);

            // === ВКЛАДКА 2: ГРАФИКИ ===
            TabPage tabCharts = new TabPage("Графики");
            tabCharts.BackColor = Color.White;

            TableLayoutPanel tlpCharts = new TableLayoutPanel();
            tlpCharts.Dock = DockStyle.Fill;
            tlpCharts.ColumnCount = 2;
            tlpCharts.RowCount = 2;
            tlpCharts.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            tlpCharts.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 250F));
            tlpCharts.RowStyles.Add(new RowStyle(SizeType.Percent, 50F));
            tlpCharts.RowStyles.Add(new RowStyle(SizeType.Percent, 50F));

            chartIrradiance = CreateChart("График инсоляции (Вт/м²)");
            chartIrradiance.MouseMove += Chart_MouseMove;
            tlpCharts.Controls.Add(chartIrradiance, 0, 0);

            chartSunPosition = CreateChart("Положение Солнца");
            chartSunPosition.MouseMove += Chart_MouseMove;
            tlpCharts.Controls.Add(chartSunPosition, 0, 1);

            // Панель управления
            GroupBox controlGroup = new GroupBox
            {
                Text = "Фильтр направлений",
                Dock = DockStyle.Fill,
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                ForeColor = AppTheme.TextColor,
                BackColor = Color.White
            };

            compassBox = new PictureBox
            {
                Size = new Size(180, 180),
                Location = new Point(35, 30),
                Cursor = Cursors.Hand
            };
            compassBox.Paint += CompassBox_Paint;
            compassBox.MouseClick += CompassBox_MouseClick;

            Label lblHint = new Label
            {
                Text = "Клик по сектору: вкл/выкл\nКлик в центр: выбрать все",
                AutoSize = true,
                Location = new Point(35, 220),
                Font = new Font("Segoe UI", 8, FontStyle.Regular),
                ForeColor = AppTheme.MutedTextColor
            };

            Panel separator = new Panel
            {
                Size = new Size(200, 1),
                Location = new Point(25, 265),
                BackColor = AppTheme.BorderColor
            };

            chkShowMarkers = new CheckBox
            {
                Text = "Узловые точки и\nподсветка значений",
                AutoSize = true,
                Location = new Point(35, 280),
                Font = new Font("Segoe UI", 10, FontStyle.Regular),
                Cursor = Cursors.Hand
            };
            chkShowMarkers.CheckedChanged += (s, e) => ToggleMarkers(chkShowMarkers.Checked);

            controlGroup.Controls.Add(compassBox);
            controlGroup.Controls.Add(lblHint);
            controlGroup.Controls.Add(separator);
            controlGroup.Controls.Add(chkShowMarkers);

            tlpCharts.Controls.Add(controlGroup, 1, 0);
            tlpCharts.SetRowSpan(controlGroup, 2);

            tabCharts.Controls.Add(tlpCharts);
            mainTabControl.TabPages.Add(tabCharts);
        }

        private Control AddLabelToGrid(DataGridView grid, string title)
        {
            Panel p = new Panel { Dock = DockStyle.Fill, Padding = new Padding(0) };
            Label l = new Label
            {
                Text = title,
                Dock = DockStyle.Top,
                Height = 34,
                TextAlign = ContentAlignment.MiddleLeft,
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                Padding = new Padding(10, 0, 0, 0),
                ForeColor = AppTheme.TextColor,
                BackColor = Color.White
            };
            p.Controls.Add(grid);
            p.Controls.Add(l);
            return p;
        }

        // --- ЛОГИКА ГРАФИКОВ И АНИМАЦИИ ---

        private void Chart_MouseMove(object? sender, MouseEventArgs e)
        {
            if (!chkShowMarkers.Checked) return;

            if (sender is not Chart chart) return;

            // Поиск ближайшей точки и серии в радиусе курсора.
            var result = FindNearestPoint(chart, e.Location, 30);
            DataPoint? nearestPoint = result.Point;
            Series? nearestSeries = result.Series;

            if (nearestPoint != _lastHighlightedPoint)
            {
                // Сброс старой точки
                if (_lastHighlightedPoint != null)
                {
                    _lastHighlightedPoint.MarkerSize = VisibleMarkerSize;
                    _lastHighlightedPoint.MarkerColor = Color.Empty;
                }

                // Активация новой точки
                if (nearestPoint != null && nearestSeries != null)
                {
                    nearestPoint.MarkerSize = HoverMarkerSize;

                    // Тултип показывает час, серию и значение точки.
                    string tooltipText = $"Час: {nearestPoint.XValue}\n{nearestSeries.Name}: {nearestPoint.YValues[0]:F2}";
                    _chartToolTip.Show(tooltipText, chart, e.X + 10, e.Y - 20);
                }
                else
                {
                    _chartToolTip.Hide(chart);
                }

                _lastHighlightedPoint = nearestPoint;
            }
        }

        /// <summary>
        /// Находит ближайшую точку и возвращает её вместе с родительской серией.
        /// </summary>
        private (Series? Series, DataPoint? Point) FindNearestPoint(Chart chart, Point mouseLocation, int searchRadius)
        {
            DataPoint? nearestPoint = null;
            Series? nearestSeries = null;
            double minDistance = double.MaxValue;

            foreach (var series in chart.Series)
            {
                if (!series.Enabled) continue;

                ChartArea area = chart.ChartAreas[series.ChartArea];
                Axis axisX = area.AxisX;
                Axis axisY = series.YAxisType == AxisType.Primary ? area.AxisY : area.AxisY2;

                try
                {
                    foreach (var point in series.Points)
                    {
                        double xPix = axisX.ValueToPixelPosition(point.XValue);
                        double yPix = axisY.ValueToPixelPosition(point.YValues[0]);

                        double dist = Math.Sqrt(Math.Pow(xPix - mouseLocation.X, 2) + Math.Pow(yPix - mouseLocation.Y, 2));

                        if (dist < minDistance && dist <= searchRadius)
                        {
                            minDistance = dist;
                            nearestPoint = point;
                            nearestSeries = series; // Запоминаем серию
                        }
                    }
                }
                catch
                {
                    // Игнорируем ошибки при зуме/скролле
                }
            }
            return (nearestSeries, nearestPoint);
        }

        private void ToggleMarkers(bool show)
        {
            _lastHighlightedPoint = null;
            _chartToolTip.Hide(chartIrradiance);
            _chartToolTip.Hide(chartSunPosition);

            int size = show ? VisibleMarkerSize : DefaultMarkerSize;
            MarkerStyle style = show ? MarkerStyle.Circle : MarkerStyle.None;

            foreach (var series in chartIrradiance.Series)
            {
                series.MarkerStyle = style;
                series.MarkerSize = size;
                series.MarkerBorderColor = Color.White;
                series.MarkerBorderWidth = show ? 1 : 0;
            }
            foreach (var series in chartSunPosition.Series)
            {
                series.MarkerStyle = style;
                series.MarkerSize = size;
                series.MarkerBorderColor = Color.White;
                series.MarkerBorderWidth = show ? 1 : 0;
            }
        }


        // --- ЛОГИКА РОЗЫ ВЕТРОВ ---

        private void CompassBox_Paint(object? sender, PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            int w = compassBox.Width;
            int h = compassBox.Height;
            int cx = w / 2;
            int cy = h / 2;
            int r = Math.Min(w, h) / 2 - 5;

            float startAngle = -22.5f;
            float sweepAngle = 45f;

            using (Pen borderPen = new Pen(Color.White, 2))
            using (Font textFont = new Font("Segoe UI", 8, FontStyle.Bold))
            {
                for (int i = 0; i < 8; i++)
                {
                    string dirName = _directionsOrder[i];
                    bool isActive = directionsState[dirName];
                    Brush fillBrush = isActive
                        ? new SolidBrush(Color.FromArgb(230, 159, 0))
                        : new SolidBrush(Color.FromArgb(225, 230, 234));

                    e.Graphics.FillPie(fillBrush, cx - r, cy - r, 2 * r, 2 * r, startAngle, sweepAngle);
                    e.Graphics.DrawPie(borderPen, cx - r, cy - r, 2 * r, 2 * r, startAngle, sweepAngle);
                    if (fillBrush is IDisposable disposableBrush) disposableBrush.Dispose();

                    double midAngleRad = (startAngle + sweepAngle / 2) * Math.PI / 180.0;
                    int textR = r - 25;
                    float tx = cx + (float)(textR * Math.Cos(midAngleRad));
                    float ty = cy + (float)(textR * Math.Sin(midAngleRad));
                    SizeF textSize = e.Graphics.MeasureString(dirName, textFont);
                    e.Graphics.DrawString(dirName, textFont, Brushes.Black, tx - textSize.Width / 2, ty - textSize.Height / 2);

                    startAngle += sweepAngle;
                }
            }

            bool allOn = directionsState.Values.All(x => x);
            bool allOff = directionsState.Values.All(x => !x);
            Brush centerBrush = allOn
                ? new SolidBrush(AppTheme.SuccessBackColor)
                : (allOff ? new SolidBrush(AppTheme.ErrorBackColor) : new SolidBrush(Color.White));

            e.Graphics.FillEllipse(centerBrush, cx - CENTER_RADIUS, cy - CENTER_RADIUS, 2 * CENTER_RADIUS, 2 * CENTER_RADIUS);
            e.Graphics.DrawEllipse(new Pen(AppTheme.BorderColor), cx - CENTER_RADIUS, cy - CENTER_RADIUS, 2 * CENTER_RADIUS, 2 * CENTER_RADIUS);
            if (centerBrush is IDisposable disposableCenterBrush) disposableCenterBrush.Dispose();
        }

        private void CompassBox_MouseClick(object? sender, MouseEventArgs e)
        {
            int cx = compassBox.Width / 2;
            int cy = compassBox.Height / 2;
            double dx = e.X - cx;
            double dy = e.Y - cy;

            // Клик в центр
            if (dx * dx + dy * dy <= CENTER_RADIUS * CENTER_RADIUS)
            {
                bool allAreOn = directionsState.Values.All(x => x);
                bool newState = !allAreOn;

                foreach (var key in directionsState.Keys.ToList()) directionsState[key] = newState;

                compassBox.Invalidate();
                UpdateChartSeriesVisibility();
                return;
            }

            // Клик в сектор
            double angleRad = Math.Atan2(dy, dx);
            double angleDeg = angleRad * 180.0 / Math.PI;
            if (angleDeg < 0) angleDeg += 360;

            double shiftedAngle = angleDeg + 22.5;
            if (shiftedAngle >= 360) shiftedAngle -= 360;

            int index = (int)(shiftedAngle / 45.0);

            if (index >= 0 && index < 8)
            {
                string clickedDir = _directionsOrder[index];
                directionsState[clickedDir] = !directionsState[clickedDir];
                compassBox.Invalidate();
                UpdateChartSeriesVisibility();
            }
        }

        private void UpdateChartSeriesVisibility()
        {
            foreach (var series in chartIrradiance.Series)
            {
                string dirPrefix = series.Name.Split(' ')[0];
                if (directionsState.ContainsKey(dirPrefix))
                {
                    series.Enabled = directionsState[dirPrefix];
                }
            }
            chartIrradiance.ChartAreas[0].RecalculateAxesScale();
        }

        // --- РАСЧЕТЫ ---

        private void PerformCalculations()
        {
            double lat = _settlement.Latitude;

            double dailyTotal = MathTools.Interpolate(lat,
                DataStore.DailyTotalList.ToDictionary(d => d.Latitude, d => d.DailyTotalHorizontalIrradiance));

            subtitleLabel.Text = $"Координаты: {lat:F2} с.ш., {_settlement.Longitude:F2} в.д. | " +
                                 $"Интерполированный суточный приход радиации: {dailyTotal:F2} МДж/м²";

            DataTable dtIrradiance = ClimatologyCalculationService.CalculateHourlyIrradiance(lat);
            _irradianceResult = dtIrradiance.Copy();
            gridIrradiance.DataSource = dtIrradiance;

            DataTable dtSunPosition = ClimatologyCalculationService.CalculateSunPosition(lat);
            _sunPositionResult = dtSunPosition.Copy();
            gridSunPosition.DataSource = dtSunPosition;

            FillIrradianceChart(dtIrradiance);
            FillSunPositionChart(dtSunPosition);

            ToggleMarkers(chkShowMarkers.Checked);
            UpdateChartSeriesVisibility();
        }

        // --- СТАНДАРТНЫЕ МЕТОДЫ ---

        private DataGridView CreateStyledGrid()
        {
            var grid = new DataGridView
            {
                Dock = DockStyle.Fill,
                BackgroundColor = Color.White,
                ReadOnly = true,
                AllowUserToAddRows = false,
                AllowUserToResizeRows = false,
                AllowUserToOrderColumns = false,
                RowHeadersVisible = false,
                AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
                BorderStyle = BorderStyle.None,
                ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.EnableResizing
            };
            grid.ColumnHeadersHeight = 46;
            grid.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 9, FontStyle.Bold);
            grid.ColumnHeadersDefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;
            grid.ColumnHeadersDefaultCellStyle.BackColor = AppTheme.PrimaryColor;
            grid.ColumnHeadersDefaultCellStyle.ForeColor = Color.White;
            grid.EnableHeadersVisualStyles = false;
            grid.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;
            grid.DefaultCellStyle.Font = new Font("Segoe UI", 9);
            grid.DefaultCellStyle.SelectionBackColor = AppTheme.NavActiveBackColor;
            grid.DefaultCellStyle.SelectionForeColor = AppTheme.TextColor;
            grid.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(249, 250, 251);
            grid.GridColor = AppTheme.BorderColor;
            grid.RowTemplate.Height = 30;
            return grid;
        }

        private Chart CreateChart(string titleText)
        {
            Chart chart = new Chart { Dock = DockStyle.Fill };
            ChartArea area = new ChartArea("MainArea");
            area.AxisX.Title = "Час суток";
            area.AxisX.Interval = 1;
            area.BackColor = Color.White;
            area.AxisX.MajorGrid.LineColor = Color.FromArgb(236, 240, 244);
            area.AxisY.MajorGrid.LineColor = Color.FromArgb(236, 240, 244);
            area.AxisX.LineColor = AppTheme.BorderColor;
            area.AxisY.LineColor = AppTheme.BorderColor;
            area.AxisX.LabelStyle.ForeColor = AppTheme.TextColor;
            area.AxisY.LabelStyle.ForeColor = AppTheme.TextColor;
            area.AxisX.TitleForeColor = AppTheme.TextColor;
            area.AxisY.TitleForeColor = AppTheme.TextColor;
            area.AxisX.IsStartedFromZero = false;
            chart.ChartAreas.Add(area);
            Legend legend = new Legend("MainLegend");
            legend.Docking = Docking.Bottom;
            legend.Alignment = StringAlignment.Center;
            legend.Font = new Font("Segoe UI", 8.5f, FontStyle.Regular);
            legend.BackColor = Color.White;
            legend.ForeColor = AppTheme.TextColor;
            chart.Legends.Add(legend);
            Title title = new Title(titleText);
            title.Font = new Font("Segoe UI", 12, FontStyle.Bold);
            title.ForeColor = AppTheme.TextColor;
            chart.Titles.Add(title);
            return chart;
        }

        private void FillIrradianceChart(DataTable dt)
        {
            chartIrradiance.Series.Clear();
            if (dt.Rows.Count == 0) return;

            for (int i = 1; i < dt.Columns.Count; i++)
            {
                string seriesName = dt.Columns[i].ColumnName;
                Series series = new Series(seriesName);
                series.ChartType = SeriesChartType.Spline;
                series.BorderWidth = 2;
                series.Color = IrradianceSeriesPalette[(i - 1) % IrradianceSeriesPalette.Length];
                series.Legend = "MainLegend";
                series.MarkerStyle = MarkerStyle.None;
                foreach (DataRow row in dt.Rows)
                {
                    int hour = Convert.ToInt32(row["Час"]);
                    double val = Convert.ToDouble(row[i]);
                    series.Points.AddXY(hour, val);
                }
                chartIrradiance.Series.Add(series);
            }
        }

        private void FillSunPositionChart(DataTable dt)
        {
            chartSunPosition.Series.Clear();
            if (dt.Rows.Count == 0) return;
            Series serAlt = new Series("Высота (h)") { ChartType = SeriesChartType.Spline, BorderWidth = 3, Color = Color.FromArgb(230, 81, 0), YAxisType = AxisType.Primary };
            Series serAz = new Series("Азимут (Ac)") { ChartType = SeriesChartType.Line, BorderWidth = 3, Color = Color.FromArgb(33, 111, 181), YAxisType = AxisType.Secondary };
            foreach (DataRow row in dt.Rows)
            {
                int hour = Convert.ToInt32(row["Час"]);
                serAlt.Points.AddXY(hour, Convert.ToDouble(row["Высота (h), °"]));
                serAz.Points.AddXY(hour, Convert.ToDouble(row["Азимут (Ac), °"]));
            }
            chartSunPosition.ChartAreas[0].AxisY.Title = "Высота (°)";
            chartSunPosition.ChartAreas[0].AxisY2.Enabled = AxisEnabled.True;
            chartSunPosition.ChartAreas[0].AxisY2.Title = "Азимут (°)";
            chartSunPosition.ChartAreas[0].AxisY2.LabelStyle.ForeColor = AppTheme.TextColor;
            chartSunPosition.ChartAreas[0].AxisY2.TitleForeColor = AppTheme.TextColor;
            chartSunPosition.ChartAreas[0].AxisY2.LineColor = AppTheme.BorderColor;
            chartSunPosition.ChartAreas[0].AxisY2.MajorGrid.Enabled = false;
            StripLine horizon = new StripLine { IntervalOffset = 0, StripWidth = 0.08, BackColor = Color.FromArgb(110, 110, 110) };
            chartSunPosition.ChartAreas[0].AxisY.StripLines.Add(horizon);
            chartSunPosition.Series.Add(serAlt);
            chartSunPosition.Series.Add(serAz);
        }

        private void BtnExportPdf_Click(object? sender, EventArgs e)
        {
            if (_irradianceResult.Rows.Count == 0 && _sunPositionResult.Rows.Count == 0)
            {
                UiMessageService.Info(
                    "Экспорт PDF",
                    "Нет данных для формирования отчета.\n\nСначала выполните расчет, затем повторите экспорт.",
                    this);
                return;
            }

            var exporter = new PdfReportExporter();

            using var optionsForm = new ReportExportOptionsForm(request =>
            {
                var irrChart = ExportChartToPng(chartIrradiance, request.ShowExactPointLabelsOnCharts);
                var sunChart = ExportChartToPng(chartSunPosition, request.ShowExactPointLabelsOnCharts);
                var previewProvider = new ClimatologyReportProvider(
                    _settlement,
                    _irradianceResult,
                    _sunPositionResult,
                    irrChart,
                    sunChart);
                var previewReport = previewProvider.BuildReport(request);
                return exporter.GenerateBytes(previewReport, request.Orientation);
            });
            if (optionsForm.ShowDialog(this) != DialogResult.OK)
                return;

            using var saveDialog = new SaveFileDialog
            {
                Filter = "PDF files (*.pdf)|*.pdf",
                FileName = $"SPES_Climatology_{_settlement.CityOrSettlement}_{DateTime.Now:yyyyMMdd_HHmm}.pdf",
                Title = "Сохранить отчет PDF"
            };

            if (saveDialog.ShowDialog(this) != DialogResult.OK)
                return;

            try
            {
                var reportProvider = new ClimatologyReportProvider(
                    _settlement,
                    _irradianceResult,
                    _sunPositionResult,
                    ExportChartToPng(chartIrradiance, optionsForm.Request.ShowExactPointLabelsOnCharts),
                    ExportChartToPng(chartSunPosition, optionsForm.Request.ShowExactPointLabelsOnCharts));
                var report = reportProvider.BuildReport(optionsForm.Request);
                exporter.Export(report, optionsForm.Request.Orientation, saveDialog.FileName);

                UiMessageService.Info(
                    "Экспорт PDF",
                    $"Отчет успешно сохранен.\n\nПуть к файлу:\n{saveDialog.FileName}",
                    this);
            }
            catch (Exception ex)
            {
                UiMessageService.Error(
                    "Экспорт PDF",
                    $"Не удалось сохранить PDF-отчет.\n\n{ex.Message}\n\nПопробуйте выбрать другую папку или имя файла.",
                    this);
            }
        }

        private static byte[] ExportChartToPng(Chart chart, bool showExactLabels)
        {
            using var clonedChart = new Chart
            {
                Width = chart.Width > 0 ? chart.Width : 1200,
                Height = chart.Height > 0 ? chart.Height : 420,
                BackColor = chart.BackColor
            };

            foreach (ChartArea area in chart.ChartAreas)
            {
                var newArea = new ChartArea(area.Name)
                {
                    BackColor = area.BackColor
                };
                newArea.AxisX.Title = area.AxisX.Title;
                newArea.AxisY.Title = area.AxisY.Title;
                newArea.AxisY2.Title = area.AxisY2.Title;
                newArea.AxisX.Interval = area.AxisX.Interval;
                newArea.AxisX.MajorGrid.LineColor = area.AxisX.MajorGrid.LineColor;
                newArea.AxisY.MajorGrid.LineColor = area.AxisY.MajorGrid.LineColor;
                newArea.AxisX.LineColor = area.AxisX.LineColor;
                newArea.AxisY.LineColor = area.AxisY.LineColor;
                newArea.AxisY2.LineColor = area.AxisY2.LineColor;
                newArea.AxisY2.Enabled = area.AxisY2.Enabled;
                clonedChart.ChartAreas.Add(newArea);
            }

            foreach (var legend in chart.Legends.Cast<Legend>())
            {
                var newLegend = new Legend(legend.Name)
                {
                    Docking = legend.Docking,
                    Alignment = legend.Alignment,
                    Font = legend.Font,
                    BackColor = legend.BackColor,
                    ForeColor = legend.ForeColor
                };
                clonedChart.Legends.Add(newLegend);
            }

            foreach (Title title in chart.Titles)
            {
                clonedChart.Titles.Add(new Title(title.Text)
                {
                    Font = title.Font,
                    ForeColor = title.ForeColor
                });
            }

            foreach (Series series in chart.Series)
            {
                var newSeries = new Series(series.Name)
                {
                    ChartType = series.ChartType,
                    BorderWidth = series.BorderWidth,
                    Color = series.Color,
                    ChartArea = series.ChartArea,
                    Legend = series.Legend,
                    YAxisType = series.YAxisType,
                    IsValueShownAsLabel = showExactLabels,
                    LabelFormat = "0.##",
                    Font = new Font("Segoe UI", 8f, FontStyle.Regular),
                    LabelForeColor = AppTheme.TextColor,
                    MarkerStyle = series.MarkerStyle,
                    MarkerSize = series.MarkerSize
                };

                foreach (var point in series.Points)
                {
                    var p = new DataPoint(point.XValue, point.YValues[0]);
                    newSeries.Points.Add(p);
                }

                clonedChart.Series.Add(newSeries);
            }

            using var stream = new System.IO.MemoryStream();
            clonedChart.SaveImage(stream, ChartImageFormat.Png);
            return stream.ToArray();
        }
    }
}
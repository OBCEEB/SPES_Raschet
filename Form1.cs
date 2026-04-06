using System;
using System.Collections.Generic;
using System.Data;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Windows.Forms;
using System.Diagnostics;

namespace SPES_Raschet
{
    public partial class Form1 : Form
    {
        // --- Данные ---
        private DataTable? currentDataTable;
        private GeoMapRenderer mapRenderer;
        private Dictionary<string, Dictionary<string, List<List<double>>>>? allRegionBoundaries;
        private string? hoverRegionName = null;
        private string? selectedRegion = null;
        private SettlementData? currentSettlement = null;

        // --- UI Элементы ---
        private ToolTip mapToolTip = new ToolTip();
        private string? lastTooltipRegion = null;

        // Кнопка запуска расчета на вкладке карты.
        private Button btnCalculate = null!;

        // Элементы меню
        private Panel panelMenu = null!;
        private Panel panelLogo = null!;
        private Button btnNavMap = null!;
        private Button btnNavData = null!;
        private Button btnNavHelp = null!;
        private Panel navIndicator = null!; // Полоска активной вкладки

        public Form1()
        {
            InitializeComponent();
            ApplyModernDesign();

            // Настройка логики
            mapToolTip.AutoPopDelay = 5000;
            mapToolTip.InitialDelay = 100;
            mapToolTip.ReshowDelay = 100;
            mapToolTip.ShowAlways = true;

            mapRenderer = new GeoMapRenderer();

            // Подписки
            this.mapPictureBox.Paint += mapPictureBox_Paint;
            this.FormClosing += (s, e) => mapRenderer?.Dispose();
            this.mapPictureBox.MouseMove += mapPictureBox_MouseMove;
            this.mapPictureBox.MouseClick += mapPictureBox_MouseClick;

            // Подписки таблицы
            this.dataGridViewData.CellFormatting += DataGridViewData_CellFormatting;

            InitializeProgramAndLoadData();
        }

        private void ApplyModernDesign()
        {
            this.BackColor = AppTheme.BackgroundColor;
            this.Font = AppTheme.MainFont;

            // 1. Настройка TabControl (Скрываем стандартные заголовки)
            tabControl1.Appearance = TabAppearance.FlatButtons;
            tabControl1.ItemSize = new Size(0, 1);
            tabControl1.SizeMode = TabSizeMode.Fixed;
            tabControl1.Dock = DockStyle.Fill;

            // Убираем рамки у вкладок
            foreach (TabPage tab in tabControl1.TabPages)
            {
                tab.BackColor = AppTheme.BackgroundColor;
                tab.BorderStyle = BorderStyle.None;
                tab.Padding = new Padding(20); // Отступ контента
            }

            // 2. Создаем Боковое Меню
            panelMenu = new Panel
            {
                Dock = DockStyle.Left,
                Width = 220,
                BackColor = Color.White,
                Padding = new Padding(0, 0, 0, 0)
            };
            // Тень или разделитель справа
            Panel border = new Panel { Dock = DockStyle.Right, Width = 1, BackColor = Color.LightGray };
            panelMenu.Controls.Add(border);

            // Логотип/Заголовок
            panelLogo = new Panel { Dock = DockStyle.Top, Height = 80 };
            Label lblTitle = new Label
            {
                Text = "СПЭС\nРасчет",
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Segoe UI", 16, FontStyle.Bold),
                ForeColor = AppTheme.PrimaryColor
            };
            panelLogo.Controls.Add(lblTitle);
            panelMenu.Controls.Add(panelLogo);

            // Индикатор активной вкладки
            navIndicator = new Panel { Width = 5, BackColor = AppTheme.PrimaryColor, Visible = false };
            panelMenu.Controls.Add(navIndicator);

            // Кнопки навигации
            btnNavHelp = CreateNavButton("Инструкция", 2);
            btnNavData = CreateNavButton("Справочник", 1);
            btnNavMap = CreateNavButton("Карта и Расчет", 0);

            panelMenu.Controls.Add(btnNavHelp);
            panelMenu.Controls.Add(btnNavData);
            panelMenu.Controls.Add(btnNavMap); // Добавляем в обратном порядке из-за Dock=Top

            this.Controls.Add(panelMenu); // Добавляем меню на форму

            // 3. Стилизация Таблицы справочника
            AppTheme.StyleDataGridView(dataGridViewData);

            // 4. Кнопка "Рассчитать" (Плавающая внизу карты)
            btnCalculate = new Button
            {
                Text = "ПОКАЗАТЬ РЕЗУЛЬТАТЫ РАСЧЕТА ➤",
                Size = new Size(350, 50),
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                Cursor = Cursors.Hand,
                Visible = false // Скрыта пока не выбран город
            };
            btnCalculate.FlatAppearance.BorderSize = 0;
            btnCalculate.Click += CalcButton_Click;

            // Размещаем кнопку на вкладке карты
            // Чтобы она была внизу по центру, используем Panel-контейнер или Anchor
            // Проще всего положить её в Panel поверх карты, но PictureBox перекроет.
            // Добавим её в Controls tabPageCalculator и сделаем BringToFront
            tabPageCalculator.Controls.Add(btnCalculate);
            btnCalculate.BringToFront();
            // Позиционирование в Resize
            tabPageCalculator.Resize += (s, e) =>
            {
                btnCalculate.Location = new Point(
                    (tabPageCalculator.Width - btnCalculate.Width) / 2,
                    tabPageCalculator.Height - btnCalculate.Height - 20);
            };

            // 5. Инициализация вкладки Инструкции
            InitializeHelpTab();

            // Активируем первую вкладку
            SwitchTab(0, btnNavMap);
        }

        private Button CreateNavButton(string text, int tabIndex)
        {
            Button btn = new Button();
            btn.Text = text;
            btn.Dock = DockStyle.Top;
            btn.Height = 55;
            AppTheme.StyleNavButton(btn);
            btn.Click += (s, e) => SwitchTab(tabIndex, btn);
            return btn;
        }

        private void SwitchTab(int index, Button senderBtn)
        {
            // Сброс стилей всех кнопок
            foreach (Control c in panelMenu.Controls)
                if (c is Button b)
                {
                    b.ForeColor = Color.Gray;
                    b.BackColor = Color.Transparent;
                }

            // Активация текущей
            AppTheme.SetActiveNavButton(senderBtn, navIndicator);
            tabControl1.SelectedIndex = index;
        }

        private void InitializeHelpTab()
        {
            TabPage helpTab = new TabPage("Инструкция");
            helpTab.BackColor = AppTheme.BackgroundColor;

            // Карточка для текста (белая панель с тенью/рамкой)
            Panel card = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(30),
                BackColor = Color.White
            };

            RichTextBox rtb = new RichTextBox
            {
                Dock = DockStyle.Fill,
                BorderStyle = BorderStyle.None,
                ReadOnly = true,
                BackColor = Color.White,
                Font = new Font("Segoe UI", 11),
                ForeColor = AppTheme.TextColor
            };

            // Форматированный текст
            rtb.Text = "";
            rtb.SelectionFont = new Font("Segoe UI", 18, FontStyle.Bold);
            rtb.SelectionColor = AppTheme.PrimaryColor;
            rtb.AppendText("Руководство пользователя\n\n");

            rtb.SelectionFont = new Font("Segoe UI", 12, FontStyle.Bold);
            rtb.AppendText("1. Работа с Картой\n");
            rtb.SelectionFont = new Font("Segoe UI", 11);
            rtb.AppendText("• Выберите регион на карте кликом мыши.\n" +
                           "• В появившемся окне выберите населенный пункт.\n" +
                           "• Снизу появится зеленая кнопка. Нажмите её для расчета.\n\n");

            rtb.SelectionFont = new Font("Segoe UI", 12, FontStyle.Bold);
            rtb.AppendText("2. Справочник\n");
            rtb.SelectionFont = new Font("Segoe UI", 11);
            rtb.AppendText("• Просматривайте исходные данные таблиц.\n" +
                           "• Используйте фильтр по Широте для поиска.\n");

            card.Controls.Add(rtb);
            helpTab.Controls.Add(card);
            tabControl1.TabPages.Add(helpTab);
        }

        // Инициализация данных и состояния основного экрана.

        private void InitializeProgramAndLoadData()
        {
            LoadGeoData();
            LoadIrradianceAndSunData();
            LoadAllMapData();
        }

        private void LoadAllMapData()
        {
            allRegionBoundaries = GeoProcessor.GetAllBoundaries();
            mapPictureBox.Invalidate();
        }

        private void LoadGeoData()
        {
            GeoDataHandler.LoadAllGeoData();
            if (GeoDataHandler.SettlementList.Any())
            {
                statusLabel.Text = "Данные геопозиции загружены.";
            }
            else
            {
                statusLabel.Text = "Не удалось загрузить геоданные.";
                statusLabel.BackColor = Color.FromArgb(255, 235, 235);
            }
        }

        private void LoadIrradianceAndSunData()
        {
            var loadResult = DataImporter.LoadAllData();
            if (!loadResult.Success)
            {
                MessageBox.Show(loadResult.Message, "Ошибка загрузки данных", MessageBoxButtons.OK, MessageBoxIcon.Error);
                statusLabel.Text = "Ошибка загрузки расчетных данных.";
                statusLabel.BackColor = Color.FromArgb(255, 235, 235);
                return;
            }

            PopulateTableSelectionComboBox();
        }

        private void PopulateTableSelectionComboBox()
        {
            comboSelectTable.Items.Clear();
            comboSelectTable.Items.Add("Почасовая радиация (Таблица 1)");
            comboSelectTable.Items.Add("Положение Солнца (Таблица 2)");
            comboSelectTable.Items.Add("Суточные итоги (Таблица 3)");
            if (comboSelectTable.Items.Count > 0) comboSelectTable.SelectedIndex = 0;
        }

        // ... (Код таблиц DataTables - без изменений) ...
        private DataTable FlattenIrradianceDataToDataTable()
        {
            DataTable dt = new DataTable("IrradianceData");
            if (DataStore.IrradianceList == null || !DataStore.IrradianceList.Any()) return dt;
            var allKeys = DataStore.IrradianceList.SelectMany(d => d.Values.Keys).Distinct().OrderBy(key => key).ToList();
            dt.Columns.Add("Широта, °", typeof(double));
            dt.Columns.Add("Час", typeof(int));
            foreach (string key in allKeys) dt.Columns.Add(key, typeof(double));
            foreach (var item in DataStore.IrradianceList)
            {
                DataRow row = dt.NewRow();
                row["Широта, °"] = item.Latitude;
                row["Час"] = item.StartHour;
                foreach (string key in allKeys) row[key] = item.Values.TryGetValue(key, out double value) ? value : (object)DBNull.Value;
                dt.Rows.Add(row);
            }
            return dt;
        }

        private DataTable FlattenSunPositionToDataTable()
        {
            DataTable dt = new DataTable("SunPositionData");
            dt.Columns.Add("Широта, °", typeof(double));
            dt.Columns.Add("Час", typeof(int));
            dt.Columns.Add("Высота (h), °", typeof(double));
            dt.Columns.Add("Азимут (Ac), °", typeof(double));
            if (DataStore.SunPositionList != null)
                foreach (var item in DataStore.SunPositionList)
                    dt.Rows.Add(item.Longitude, item.StartHour, item.Altitude, item.Azimuth);
            return dt;
        }

        private DataTable FlattenDailyTotalToDataTable()
        {
            DataTable dt = new DataTable("DailyTotalData");
            dt.Columns.Add("Широта, °", typeof(double));
            dt.Columns.Add("Суточный итог, МДж/м²", typeof(double));
            if (DataStore.DailyTotalList != null)
                foreach (var item in DataStore.DailyTotalList)
                    dt.Rows.Add(item.Latitude, item.DailyTotalHorizontalIrradiance);
            return dt;
        }

        // ... (Логика UI Таблицы) ...

        private void comboSelectTable_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (comboSelectTable.SelectedItem == null) return;
            string? selectedTable = comboSelectTable.SelectedItem as string;
            dataGridViewData.DataSource = null;
            BindingSource bs = new BindingSource();
            try
            {
                switch (selectedTable)
                {
                    case "Почасовая радиация (Таблица 1)": currentDataTable = FlattenIrradianceDataToDataTable(); break;
                    case "Положение Солнца (Таблица 2)": currentDataTable = FlattenSunPositionToDataTable(); break;
                    case "Суточные итоги (Таблица 3)": currentDataTable = FlattenDailyTotalToDataTable(); break;
                }
                if (currentDataTable != null)
                {
                    bs.DataSource = currentDataTable;
                    dataGridViewData.DataSource = bs;
                    filterTextBox_TextChanged(this, EventArgs.Empty);
                }
            }
            catch { }
        }

        private void filterTextBox_TextChanged(object sender, EventArgs e)
        {
            if (dataGridViewData.DataSource is BindingSource bs)
            {
                string filterText = filterTextBox.Text.Trim().Replace("'", "''");
                label1.Text = "Фильтр (Широта):";
                if (string.IsNullOrWhiteSpace(filterText)) bs.Filter = null;
                else try { bs.Filter = $"Convert([Широта, °], 'System.String') LIKE '%{filterText}%'"; } catch { }
            }
        }

        private void DataGridViewData_CellFormatting(object? sender, DataGridViewCellFormattingEventArgs e)
        {
            if (comboSelectTable.SelectedIndex == 2 || e.RowIndex < 0) return;
            if (e.ColumnIndex > 1) return;

            bool isRowActive = dataGridViewData.CurrentCell != null && dataGridViewData.CurrentCell.RowIndex == e.RowIndex;
            if (isRowActive)
            {
                e.CellStyle.BackColor = Color.FromArgb(200, 230, 255);
                e.CellStyle.SelectionBackColor = Color.FromArgb(200, 230, 255);
                e.CellStyle.SelectionForeColor = Color.Black;
            }
            else
            {
                e.CellStyle.BackColor = (e.RowIndex % 2 != 0) ? Color.FromArgb(245, 245, 245) : Color.White;
            }
        }

        // ... (Логика Карты - без изменений) ...

        private void mapPictureBox_Paint(object? sender, PaintEventArgs e)
        {
            if (allRegionBoundaries != null)
                mapRenderer.DrawAllRegions(e.Graphics, mapPictureBox.Size, allRegionBoundaries, hoverRegionName);
        }

        private void mapPictureBox_MouseMove(object? sender, MouseEventArgs e)
        {
            if (allRegionBoundaries == null) return;
            Point unrotatedPoint = UntransformPoint(e.Location, mapPictureBox.Size);
            List<double>? geoPoint = mapRenderer.PixelToGeo(unrotatedPoint);
            if (geoPoint == null) return;

            string? newHoverRegion = null;
            foreach (var regionEntry in allRegionBoundaries)
            {
                foreach (var polygonEntry in regionEntry.Value)
                {
                    if (polygonEntry.Value != null && polygonEntry.Value.Count > 1)
                        if (mapRenderer.IsPointInPolygon(geoPoint, polygonEntry.Value))
                        {
                            newHoverRegion = regionEntry.Key;
                            break;
                        }
                }
                if (newHoverRegion != null) break;
            }

            if (newHoverRegion != hoverRegionName)
            {
                hoverRegionName = newHoverRegion;
                mapPictureBox.Invalidate();
            }
            if (newHoverRegion != lastTooltipRegion)
            {
                lastTooltipRegion = newHoverRegion;
                if (newHoverRegion != null) mapToolTip.Show(newHoverRegion, mapPictureBox, e.X + 15, e.Y + 10);
                else mapToolTip.Hide(mapPictureBox);
            }
        }

        private void mapPictureBox_MouseClick(object? sender, MouseEventArgs e)
        {
            Point untransformedPoint = UntransformPoint(e.Location, mapPictureBox.Size);
            string? clickedRegion = mapRenderer.GetRegionNameFromScreenPoint(untransformedPoint, allRegionBoundaries!);
            if (clickedRegion != null)
            {
                if (selectedRegion != clickedRegion)
                {
                    selectedRegion = clickedRegion;
                    mapPictureBox.Invalidate();
                }
                ShowSettlementsForRegion(clickedRegion);
            }
        }

        private Point UntransformPoint(Point originalPoint, Size controlSize)
        {
            Matrix transformMatrix = new Matrix();
            transformMatrix.Translate(controlSize.Width / 2f, controlSize.Height / 2f);
            transformMatrix.Rotate(GeoMapRenderer.MAP_ROTATION_ANGLE);
            float flipX = GeoMapRenderer.MAP_FLIP_HORIZONTAL ? -1f : 1f;
            float flipY = GeoMapRenderer.MAP_FLIP_VERTICAL ? -1f : 1f;
            transformMatrix.Scale(flipX, flipY);
            transformMatrix.Translate(-controlSize.Width / 2f, -controlSize.Height / 2f);
            transformMatrix.Invert();
            Point[] points = new Point[] { originalPoint };
            transformMatrix.TransformPoints(points);
            return points[0];
        }

        // ... (Логика Выбора и Кнопки) ...

        private void ShowSettlementsForRegion(string regionName)
        {
            var settlements = GeoProcessor.GetSettlementsByRegion(regionName);
            if (settlements.Any())
            {
                mapToolTip.Hide(mapPictureBox);
                using (var listForm = new SettlementListForm(regionName, settlements))
                {
                    if (listForm.ShowDialog() == DialogResult.OK && listForm.SelectedSettlement != null)
                    {
                        currentSettlement = listForm.SelectedSettlement;
                        UpdateStatusWithSelection();
                    }
                }
            }
            else MessageBox.Show($"Нет данных для: {regionName}", "Инфо", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void UpdateStatusWithSelection()
        {
            if (currentSettlement != null)
            {
                btnCalculate.Visible = true;
                statusLabel.Text = $"ВЫБРАН: {currentSettlement.CityOrSettlement} ({currentSettlement.Region})";
                statusLabel.BackColor = Color.FromArgb(220, 255, 220); // Нежно-зеленый
            }
        }

        private void CalcButton_Click(object? sender, EventArgs e)
        {
            if (currentSettlement != null)
            {
                var resultsForm = new CalculationResultsForm(currentSettlement);
                resultsForm.Show();
            }
        }
    }
}
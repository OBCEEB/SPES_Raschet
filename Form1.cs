using System;
using System.Collections.Generic;
using System.Data;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Windows.Forms;
using System.Diagnostics;
using SPES_Raschet.Services;

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
        private Panel restorePanel = null!;
        private readonly MapInteractionService mapInteraction = new MapInteractionService();
        private readonly SessionCoordinator sessionCoordinator = new SessionCoordinator();
        private Panel mapToolsPanel = null!;
        private Label mapHintLabel = null!;

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
            this.mapPictureBox.MouseDown += mapPictureBox_MouseDown;
            this.mapPictureBox.MouseUp += mapPictureBox_MouseUp;
            this.mapPictureBox.MouseWheel += mapPictureBox_MouseWheel;
            this.mapPictureBox.MouseEnter += (_, _) => mapPictureBox.Focus();
            this.mapPictureBox.DoubleClick += (_, _) =>
            {
                mapRenderer.ResetView();
                mapPictureBox.Invalidate();
            };

            // Подписки таблицы
            this.dataGridViewData.CellFormatting += DataGridViewData_CellFormatting;
            this.FormClosing += (_, _) => SaveCurrentSessionState();
            this.Shown += (_, _) => ShowRestorePromptIfNeeded();

            InitializeProgramAndLoadData();
        }

        private void ApplyModernDesign()
        {
            this.BackColor = AppTheme.BackgroundColor;
            this.Font = AppTheme.MainFont;
            statusStrip1.BackColor = Color.White;
            statusStrip1.SizingGrip = false;
            statusLabel.ForeColor = AppTheme.TextColor;
            statusLabel.Margin = new Padding(8, 3, 0, 2);

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
                Padding = new Padding(0)
            };
            Panel border = new Panel { Dock = DockStyle.Right, Width = 1, BackColor = AppTheme.BorderColor };
            panelMenu.Controls.Add(border);

            panelLogo = new Panel { Dock = DockStyle.Bottom, Height = 120 };
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
            panelMenu.Controls.Add(btnNavMap);
            this.Controls.Add(panelMenu);

            // 3. Стилизация Таблицы справочника
            AppTheme.StyleDataGridView(dataGridViewData);
            dataGridViewData.RowTemplate.Height = 32;
            dataGridViewData.ColumnHeadersHeight = 42;
            dataGridViewData.GridColor = AppTheme.BorderColor;
            dataGridViewData.DefaultCellStyle.Padding = new Padding(2);

            grpControls.BackColor = Color.White;
            grpControls.ForeColor = AppTheme.TextColor;
            grpControls.Padding = new Padding(10, 8, 10, 8);
            tlpControls.Padding = new Padding(0, 2, 0, 0);
            lblSelectTable.ForeColor = AppTheme.TextColor;
            label1.ForeColor = AppTheme.TextColor;

            comboSelectTable.FlatStyle = FlatStyle.Flat;
            comboSelectTable.BackColor = Color.White;
            comboSelectTable.ForeColor = AppTheme.TextColor;

            filterTextBox.BorderStyle = BorderStyle.FixedSingle;
            filterTextBox.BackColor = Color.White;
            filterTextBox.ForeColor = AppTheme.TextColor;

            btnCalculate = new Button
            {
                Text = "ПОКАЗАТЬ РЕЗУЛЬТАТЫ РАСЧЕТА ➤",
                Size = new Size(360, 54),
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                Cursor = Cursors.Hand,
                Visible = false
            };
            btnCalculate.FlatAppearance.BorderSize = 0;
            btnCalculate.FlatAppearance.MouseOverBackColor = AppTheme.DarkPrimary;
            btnCalculate.FlatAppearance.MouseDownBackColor = AppTheme.DarkPrimary;
            btnCalculate.Click += CalcButton_Click;

            tabPageCalculator.Controls.Add(btnCalculate);
            btnCalculate.BringToFront();
            tabPageCalculator.Resize += (s, e) =>
            {
                btnCalculate.Location = new Point(
                    (tabPageCalculator.Width - btnCalculate.Width) / 2,
                    tabPageCalculator.Height - btnCalculate.Height - 28);
            };
            mapPictureBox.Cursor = Cursors.Hand;
            mapPictureBox.TabStop = true;
            InitializeMapToolsOverlay();

            InitializeHelpTab();

            SwitchTab(0, btnNavMap);
            SetStatusNeutral("Данные геопозиции загружены.");

            restorePanel = new Panel
            {
                Dock = DockStyle.Top,
                Height = 42,
                Visible = false,
                BackColor = Color.FromArgb(255, 248, 221),
                Padding = new Padding(10, 8, 10, 6)
            };

            var restoreLabel = new Label
            {
                AutoSize = true,
                Text = "Найдена предыдущая сессия. Восстановить?",
                ForeColor = AppTheme.TextColor,
                Dock = DockStyle.Left
            };
            var btnRestore = new Button
            {
                Text = "Восстановить",
                Width = 110,
                Height = 26,
                FlatStyle = FlatStyle.Flat,
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White,
                Dock = DockStyle.Right
            };
            btnRestore.FlatAppearance.BorderSize = 0;
            btnRestore.Click += (_, _) => RestorePreviousSession();

            var btnDismiss = new Button
            {
                Text = "Игнорировать",
                Width = 110,
                Height = 26,
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.White,
                ForeColor = AppTheme.TextColor,
                Dock = DockStyle.Right
            };
            btnDismiss.Click += (_, _) =>
            {
                restorePanel.Visible = false;
                PositionMapToolsOverlay();
            };

            restorePanel.Controls.Add(btnRestore);
            restorePanel.Controls.Add(btnDismiss);
            restorePanel.Controls.Add(restoreLabel);
            tabPageCalculator.Controls.Add(restorePanel);
            restorePanel.BringToFront();
        }

        private void InitializeMapToolsOverlay()
        {
            mapToolsPanel = new Panel
            {
                Size = new Size(220, 112),
                BackColor = Color.FromArgb(245, 250, 255),
                BorderStyle = BorderStyle.FixedSingle
            };

            var btnZoomIn = new Button
            {
                Text = "+",
                Width = 42,
                Height = 30,
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.White,
                ForeColor = AppTheme.TextColor,
                Location = new Point(10, 8)
            };
            btnZoomIn.FlatAppearance.BorderColor = AppTheme.BorderColor;
            btnZoomIn.Click += (_, _) =>
            {
                mapRenderer.Zoom(1.12);
                mapPictureBox.Invalidate();
            };

            var btnZoomOut = new Button
            {
                Text = "-",
                Width = 42,
                Height = 30,
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.White,
                ForeColor = AppTheme.TextColor,
                Location = new Point(58, 8)
            };
            btnZoomOut.FlatAppearance.BorderColor = AppTheme.BorderColor;
            btnZoomOut.Click += (_, _) =>
            {
                mapRenderer.Zoom(0.90);
                mapPictureBox.Invalidate();
            };

            var btnResetView = new Button
            {
                Text = "Сброс",
                Width = 106,
                Height = 30,
                FlatStyle = FlatStyle.Flat,
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White,
                Location = new Point(106, 8)
            };
            btnResetView.FlatAppearance.BorderSize = 0;
            btnResetView.Click += (_, _) =>
            {
                mapRenderer.ResetView();
                mapPictureBox.Invalidate();
            };

            mapHintLabel = new Label
            {
                AutoSize = false,
                Width = 198,
                Height = 62,
                Location = new Point(10, 42),
                Text = "Колесо: масштаб\nСредняя кнопка: перетаскивание\nДвойной клик: сброс",
                ForeColor = AppTheme.MutedTextColor,
                Font = new Font("Segoe UI", 8.5f),
                TextAlign = ContentAlignment.TopLeft
            };

            mapToolsPanel.Controls.Add(btnZoomIn);
            mapToolsPanel.Controls.Add(btnZoomOut);
            mapToolsPanel.Controls.Add(btnResetView);
            mapToolsPanel.Controls.Add(mapHintLabel);
            mapPictureBox.Controls.Add(mapToolsPanel);
            mapToolsPanel.BringToFront();

            PositionMapToolsOverlay();
            mapPictureBox.Resize += (_, _) => PositionMapToolsOverlay();
        }

        private void PositionMapToolsOverlay()
        {
            if (mapToolsPanel == null) return;
            int topOffset = restorePanel != null && restorePanel.Visible ? 58 : 16;

            mapToolsPanel.Location = new Point(
                Math.Max(8, mapPictureBox.Width - mapToolsPanel.Width - 16),
                topOffset);
        }

        private Button CreateNavButton(string text, int tabIndex)
        {
            Button btn = new Button();
            btn.Text = text;
            btn.Dock = DockStyle.Top;
            btn.Height = 55;
            AppTheme.StyleNavButton(btn);
            btn.MouseEnter += (_, _) =>
            {
                if (tabControl1.SelectedIndex != tabIndex) btn.BackColor = AppTheme.NavHoverBackColor;
            };
            btn.MouseLeave += (_, _) =>
            {
                if (tabControl1.SelectedIndex != tabIndex) btn.BackColor = Color.Transparent;
            };
            btn.Click += (s, e) => SwitchTab(tabIndex, btn);
            return btn;
        }

        private void SwitchTab(int index, Button senderBtn)
        {
            // Сброс стилей всех кнопок
            foreach (Control c in panelMenu.Controls)
                if (c is Button b)
                {
                    b.ForeColor = AppTheme.MutedTextColor;
                    b.BackColor = Color.Transparent;
                }

            // Активация текущей
            AppTheme.SetActiveNavButton(senderBtn, navIndicator);
            tabControl1.SelectedIndex = index;
            SaveCurrentSessionState();
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
                SetStatusNeutral("Данные геопозиции загружены.");
            }
            else
            {
                SetStatusError("Не удалось загрузить геоданные.");
            }
        }

        private void LoadIrradianceAndSunData()
        {
            var loadResult = DataImporter.LoadAllData();
            if (!loadResult.Success)
            {
                UiMessageService.Error(
                    "Ошибка загрузки данных",
                    $"Не удалось загрузить расчетные таблицы.\n\n{loadResult.Message}\n\nПроверьте файлы данных и повторите запуск.",
                    this);
                SetStatusError("Ошибка загрузки расчетных данных.");
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
                    case "Почасовая радиация (Таблица 1)": currentDataTable = TableViewDataService.FlattenIrradianceData(); break;
                    case "Положение Солнца (Таблица 2)": currentDataTable = TableViewDataService.FlattenSunPositionData(); break;
                    case "Суточные итоги (Таблица 3)": currentDataTable = TableViewDataService.FlattenDailyTotalData(); break;
                }
                if (currentDataTable != null)
                {
                    bs.DataSource = currentDataTable;
                    dataGridViewData.DataSource = bs;
                    filterTextBox_TextChanged(this, EventArgs.Empty);
                    SaveCurrentSessionState();
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
                SaveCurrentSessionState();
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
                mapRenderer.DrawAllRegions(e.Graphics, mapPictureBox.Size, allRegionBoundaries, hoverRegionName, selectedRegion);
        }

        private void mapPictureBox_MouseMove(object? sender, MouseEventArgs e)
        {
            if (mapInteraction.IsPanning)
            {
                var delta = mapInteraction.ConsumePanDelta(e.Location);
                mapRenderer.Pan(delta.X, delta.Y);
                mapPictureBox.Invalidate();
                return;
            }

            if (allRegionBoundaries == null) return;
            Point unrotatedPoint = UntransformPoint(e.Location, mapPictureBox.Size);
            string? newHoverRegion = mapInteraction.FindHoverRegion(
                mapRenderer,
                unrotatedPoint,
                mapPictureBox.Size,
                allRegionBoundaries);

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
            if (mapInteraction.IsPanning || e.Button != MouseButtons.Left) return;

            Point untransformedPoint = UntransformPoint(e.Location, mapPictureBox.Size);
            string? clickedRegion = mapInteraction.FindRegionAtPoint(mapRenderer, untransformedPoint, allRegionBoundaries);
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

        private void mapPictureBox_MouseDown(object? sender, MouseEventArgs e)
        {
            mapInteraction.BeginPan(e.Button, e.Location);
            if (!mapInteraction.IsPanning) return;
            mapPictureBox.Cursor = Cursors.SizeAll;
            mapToolTip.Hide(mapPictureBox);
        }

        private void mapPictureBox_MouseUp(object? sender, MouseEventArgs e)
        {
            mapInteraction.EndPan(e.Button);
            mapPictureBox.Cursor = Cursors.Hand;
        }

        private void mapPictureBox_MouseWheel(object? sender, MouseEventArgs e)
        {
            mapRenderer.Zoom(e.Delta > 0 ? 1.12 : 0.90);
            mapPictureBox.Invalidate();
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
            else UiMessageService.Info(
                "Данные не найдены",
                $"Для региона \"{regionName}\" сейчас нет доступных населенных пунктов.",
                this);
        }

        private void UpdateStatusWithSelection()
        {
            if (currentSettlement != null)
            {
                btnCalculate.Visible = true;
                SetStatusSuccess($"Выбран: {currentSettlement.CityOrSettlement} ({currentSettlement.Region})");
                SaveCurrentSessionState();
            }
        }

        private void SetStatusNeutral(string message)
        {
            statusStrip1.BackColor = Color.White;
            statusLabel.Text = message;
            statusLabel.ForeColor = AppTheme.TextColor;
        }

        private void SetStatusSuccess(string message)
        {
            statusStrip1.BackColor = AppTheme.SuccessBackColor;
            statusLabel.Text = message;
            statusLabel.ForeColor = AppTheme.DarkPrimary;
        }

        private void SetStatusError(string message)
        {
            statusStrip1.BackColor = AppTheme.ErrorBackColor;
            statusLabel.Text = message;
            statusLabel.ForeColor = Color.FromArgb(139, 0, 0);
        }

        private void ShowRestorePromptIfNeeded()
        {
            if (!sessionCoordinator.HasPendingState) return;
            restorePanel.Visible = true;
            if (IsHandleCreated) BeginInvoke((Action)PositionMapToolsOverlay);
            else PositionMapToolsOverlay();
        }

        private void RestorePreviousSession()
        {
            var state = sessionCoordinator.ConsumePendingState();
            if (state == null)
            {
                restorePanel.Visible = false;
                BeginInvoke((Action)PositionMapToolsOverlay);
                return;
            }

            restorePanel.Visible = false;
            BeginInvoke((Action)PositionMapToolsOverlay);

            var settlement = sessionCoordinator.ResolveSettlement(state);

            if (settlement != null)
            {
                currentSettlement = settlement;
                selectedRegion = state.Region;
                UpdateStatusWithSelection();
            }

            if (state.NavTabIndex >= 0 && state.NavTabIndex < tabControl1.TabPages.Count)
                tabControl1.SelectedIndex = state.NavTabIndex;

            if (state.SelectedTableIndex >= 0 && state.SelectedTableIndex < comboSelectTable.Items.Count)
                comboSelectTable.SelectedIndex = state.SelectedTableIndex;

            filterTextBox.Text = state.FilterText ?? string.Empty;
        }

        private void SaveCurrentSessionState()
        {
            sessionCoordinator.Save(
                currentSettlement,
                tabControl1.SelectedIndex,
                comboSelectTable.SelectedIndex,
                filterTextBox.Text);
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
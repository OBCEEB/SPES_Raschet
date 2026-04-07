using System;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using SPES_Raschet.Diagnostics;
using SPES_Raschet.Session;

namespace SPES_Raschet
{
    public class ShellForm : Form
    {
        private Panel modulesCard = null!;
        private Panel diagnosticsCard = null!;
        private Panel helpCard = null!;
        private Button btnClimate = null!;
        private Button btnSolarCollector = null!;
        private Button btnDiagnostics = null!;
        private RichTextBox helpText = null!;
        private ComboBox themeSelector = null!;
        private Label lblTheme = null!;

        public ShellForm()
        {
            Text = "СПЭС • Мастер-приложение";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(1080, 700);
            BackColor = AppTheme.BackgroundColor;
            Font = AppTheme.MainFont;

            var root = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 2,
                RowCount = 1
            };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 55));
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 45));
            root.Padding = new Padding(10);
            Controls.Add(root);

            modulesCard = CreateCard("Модули СПЭС");
            root.Controls.Add(modulesCard, 0, 0);

            var modulesFlow = new FlowLayoutPanel
            {
                Dock = DockStyle.Top,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AutoSize = true,
                Margin = new Padding(0, 10, 0, 0)
            };
            modulesCard.Controls.Add(modulesFlow);
            modulesFlow.BringToFront();

            btnClimate = CreateActionButton("СПЭС-Климатология");
            btnClimate.Click += (_, _) =>
            {
                using var module = new Form1();
                module.ShowDialog(this);
            };
            modulesFlow.Controls.Add(btnClimate);

            btnSolarCollector = CreateActionButton("СПЭС-Расчет коллектора (скоро)");
            btnSolarCollector.Enabled = false;
            modulesFlow.Controls.Add(btnSolarCollector);

            var rightCol = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 2
            };
            rightCol.RowStyles.Add(new RowStyle(SizeType.Percent, 38));
            rightCol.RowStyles.Add(new RowStyle(SizeType.Percent, 62));
            root.Controls.Add(rightCol, 1, 0);

            diagnosticsCard = CreateCard("Средства диагностики");
            rightCol.Controls.Add(diagnosticsCard, 0, 0);

            var diagnosticsFlow = new FlowLayoutPanel
            {
                Dock = DockStyle.Top,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AutoSize = true,
                Margin = new Padding(0, 10, 0, 0)
            };
            diagnosticsCard.Controls.Add(diagnosticsFlow);
            diagnosticsFlow.BringToFront();

            lblTheme = new Label
            {
                Text = "Цветовая схема",
                AutoSize = true,
                ForeColor = AppTheme.TextColor,
                Margin = new Padding(0, 0, 0, 4)
            };
            diagnosticsFlow.Controls.Add(lblTheme);

            themeSelector = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Width = 210,
                Font = new Font("Segoe UI", 10f),
                Margin = new Padding(0, 0, 0, 8)
            };
            themeSelector.Items.AddRange(new object[]
            {
                "Синий",
                "Зеленый",
                "Красный",
                "Оранжевый"
            });
            themeSelector.DropDownWidth = 210;
            themeSelector.SelectedIndex = ThemeToIndex(AppTheme.CurrentTheme);
            themeSelector.SelectedIndexChanged += (_, _) => ApplySelectedTheme();
            diagnosticsFlow.Controls.Add(themeSelector);

            btnDiagnostics = CreateActionButton("Проверить файлы данных");
            btnDiagnostics.Click += (_, _) => ShowDiagnostics();
            diagnosticsFlow.Controls.Add(btnDiagnostics);

            helpCard = CreateCard("Справка");
            rightCol.Controls.Add(helpCard, 0, 1);

            helpText = new RichTextBox
            {
                Dock = DockStyle.Fill,
                ReadOnly = true,
                BorderStyle = BorderStyle.None,
                BackColor = AppTheme.PanelColor,
                Font = new Font("Segoe UI", 10.5f, FontStyle.Regular),
                ForeColor = AppTheme.TextColor,
                Text =
                    "СПЭС — набор прикладных модулей для расчета и анализа данных.\n\n" +
                    "1) СПЭС-Климатология\n" +
                    "   Выбор населенного пункта по карте и получение климатических данных.\n\n" +
                    "2) СПЭС-Расчет коллектора (планируется)\n" +
                    "   Расчет параметров солнечного коллектора на основе климатических данных.\n\n" +
                    "Рекомендации:\n" +
                    "• Перед началом работы выполняйте диагностику файлов данных.\n" +
                    "• Для формирования отчетов используйте экспорт PDF внутри модуля.\n" +
                    "• При наличии сохраненной сессии модуль предложит восстановление."
            };
            helpCard.Controls.Add(helpText);

            ApplyThemeToShell();
        }

        private static Panel CreateCard(string title)
        {
            var card = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = AppTheme.PanelColor,
                Padding = new Padding(14)
            };

            var lbl = new Label
            {
                Dock = DockStyle.Top,
                Height = 34,
                Text = title,
                Font = new Font("Segoe UI", 12f, FontStyle.Bold),
                ForeColor = AppTheme.TextColor
            };
            card.Controls.Add(lbl);
            lbl.BringToFront();

            return card;
        }

        private static Button CreateActionButton(string text)
        {
            return new Button
            {
                Text = text,
                Height = 46,
                Width = 500,
                FlatStyle = FlatStyle.Flat,
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 10.5f, FontStyle.Bold),
                Cursor = Cursors.Hand,
                Margin = new Padding(0, 8, 0, 8)
            };
        }

        private void ShowDiagnostics()
        {
            var report = StartupDiagnosticsService.Run();
            if (!report.HasIssues)
            {
                MessageBox.Show(
                    $"Диагностика завершена успешно.\n\nНайдено файлов: {report.FoundFiles.Count}",
                    "СПЭС • Диагностика",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            MessageBox.Show(
                "Обнаружены проблемы с файлами данных:\n\n" +
                string.Join("\n", report.MissingFiles.Select(x => "• " + x)),
                "СПЭС • Диагностика",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }

        private void ApplySelectedTheme()
        {
            var selectedTheme = IndexToTheme(themeSelector.SelectedIndex);
            AppTheme.SetTheme(selectedTheme);
            ThemeSettingsService.Save(selectedTheme);
            ApplyThemeToShell();
        }

        private void ApplyThemeToShell()
        {
            BackColor = AppTheme.BackgroundColor;

            modulesCard.BackColor = AppTheme.PanelColor;
            diagnosticsCard.BackColor = AppTheme.PanelColor;
            helpCard.BackColor = AppTheme.PanelColor;
            helpText.BackColor = AppTheme.PanelColor;
            helpText.ForeColor = AppTheme.TextColor;
            lblTheme.ForeColor = AppTheme.TextColor;

            StyleButton(btnClimate);
            StyleButton(btnSolarCollector);
            StyleButton(btnDiagnostics);
        }

        private static void StyleButton(Button btn)
        {
            btn.BackColor = AppTheme.PrimaryColor;
            btn.ForeColor = Color.White;
            btn.FlatAppearance.BorderSize = 0;
            btn.FlatAppearance.MouseOverBackColor = AppTheme.DarkPrimary;
            btn.FlatAppearance.MouseDownBackColor = AppTheme.DarkPrimary;
        }

        private static int ThemeToIndex(ThemeVariant theme)
        {
            return theme switch
            {
                ThemeVariant.Green => 1,
                ThemeVariant.Red => 2,
                ThemeVariant.Orange => 3,
                _ => 0
            };
        }

        private static ThemeVariant IndexToTheme(int index)
        {
            return index switch
            {
                1 => ThemeVariant.Green,
                2 => ThemeVariant.Red,
                3 => ThemeVariant.Orange,
                _ => ThemeVariant.BlueAtlantika440
            };
        }
    }
}

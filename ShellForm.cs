using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using SPES_Raschet.Modules;
using SPES_Raschet.Services;
using SPES_Raschet.Session;

namespace SPES_Raschet
{
    public class ShellForm : Form
    {
        private Panel modulesCard = null!;
        private Panel diagnosticsCard = null!;
        private Panel helpCard = null!;
        private Button btnDiagnostics = null!;
        private RichTextBox helpText = null!;
        private ComboBox themeSelector = null!;
        private Label lblTheme = null!;
        private FlowLayoutPanel modulesFlow = null!;
        private IReadOnlyList<IModuleDescriptor> modules = null!;
        private readonly List<Button> moduleButtons = new List<Button>();

        public ShellForm()
        {
            Text = "СПЭС • Мастер-приложение";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(1080, 700);
            BackColor = AppTheme.BackgroundColor;
            Font = AppTheme.MainFont;
            modules = ModuleRegistry.GetModules();

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

            modulesFlow = new FlowLayoutPanel
            {
                Dock = DockStyle.Top,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AutoSize = true,
                Margin = new Padding(0, 10, 0, 0)
            };
            modulesCard.Controls.Add(modulesFlow);
            modulesFlow.BringToFront();
            BuildModuleButtons();

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
                Text = BuildHelpText()
            };
            helpCard.Controls.Add(helpText);

            ApplyThemeToShell();
        }

        private void BuildModuleButtons()
        {
            modulesFlow.Controls.Clear();
            moduleButtons.Clear();

            foreach (var module in modules)
            {
                var button = CreateActionButton(module.DisplayName);
                button.Enabled = module.IsAvailable;
                button.Click += (_, _) => LaunchModule(module);
                modulesFlow.Controls.Add(button);
                moduleButtons.Add(button);
            }
        }

        private void LaunchModule(IModuleDescriptor module)
        {
            if (module is not IModuleLauncher launcher)
            {
                UiMessageService.Warning(
                    "Модули",
                    $"Раздел \"{module.DisplayName}\" сейчас временно недоступен.",
                    this);
                return;
            }

            launcher.Launch(this);
        }

        private string BuildHelpText()
        {
            var sb = new StringBuilder();
            sb.AppendLine("СПЭС помогает получать и анализировать данные для выбранного населенного пункта.");
            sb.AppendLine();
            sb.AppendLine("Как начать работу:");
            sb.AppendLine("1) При необходимости нажмите \"Проверить файлы данных\".");
            sb.AppendLine("2) Выберите нужный модуль слева.");
            sb.AppendLine("3) Выполните расчет и сформируйте PDF-отчет внутри модуля.");
            sb.AppendLine();
            sb.AppendLine("Доступные разделы:");
            for (int i = 0; i < modules.Count; i++)
            {
                var module = modules[i];
                sb.AppendLine($"{i + 1}) {module.DisplayName}{(module.IsAvailable ? string.Empty : " (планируется)")}");
                sb.AppendLine($"   {module.Description}");
                sb.AppendLine();
            }

            sb.AppendLine("Полезно знать:");
            sb.AppendLine("• Тема интерфейса меняется в блоке \"Цветовая схема\".");
            sb.AppendLine("• Если ранее работа уже велась, модуль может предложить восстановить сессию.");
            sb.AppendLine("• При проблемах сначала проверьте наличие файлов данных.");

            return sb.ToString().TrimEnd();
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
            var issues = modules
                .Where(module => module.IsAvailable)
                .SelectMany(module =>
                {
                    if (module is not IModuleDiagnostics diagnostics)
                    {
                        return new[]
                        {
                            $"{module.DisplayName}: проверка файлов сейчас недоступна"
                        };
                    }

                    return diagnostics.ValidateEnvironment()
                        .Select(issue => $"{module.DisplayName}: {issue}");
                })
                .ToList();

            if (issues.Count == 0)
            {
                UiMessageService.Info(
                    "Диагностика",
                    "Все в порядке: обязательные файлы данных найдены.\n\nМожно переходить к расчетам.",
                    this);
                return;
            }

            UiMessageService.Warning(
                "Диагностика",
                "Не удалось найти часть файлов данных.\n\n" +
                "Что сделать:\n" +
                "1) Проверьте, что файлы данных находятся рядом с приложением.\n" +
                "2) Если файлы были перемещены, верните их в папку программы.\n\n" +
                "Список отсутствующих файлов:\n" +
                string.Join("\n", issues.Select(x => "• " + x)),
                this);
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

            foreach (var moduleButton in moduleButtons)
            {
                StyleButton(moduleButton);
            }
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

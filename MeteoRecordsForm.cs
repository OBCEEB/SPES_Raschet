using System;
using System.Data;
using System.Drawing;
using System.Windows.Forms;
using SPES_Raschet.Services;
using SPES_Raschet.Services.Meteo;

namespace SPES_Raschet
{
    public sealed class MeteoRecordsForm : Form
    {
        private readonly long _stationId;
        private readonly long _datasetId;
        private readonly string _stationTitle;
        private DataTable? _currentTable;
        private int _pageSize = 5000;
        private int _offset;
        private int _totalRows;

        private ComboBox _yearCombo = null!;
        private DataGridView _grid = null!;
        private Label _summaryLabel = null!;
        private Button _btnPrev = null!;
        private Button _btnNext = null!;

        public MeteoRecordsForm(long stationId, long datasetId, string stationTitle)
        {
            _stationId = stationId;
            _datasetId = datasetId;
            _stationTitle = stationTitle;

            Text = "СПЭС • Актуальная климатология";
            StartPosition = FormStartPosition.CenterParent;
            MinimumSize = new Size(900, 580);
            Size = new Size(1120, 700);
            BackColor = AppTheme.BackgroundColor;
            Font = AppTheme.MainFont;

            BuildUi();
            Shown += (_, _) => LoadData();
        }

        private void BuildUi()
        {
            var root = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                RowCount = 3,
                ColumnCount = 1,
                BackColor = AppTheme.BackgroundColor
            };
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 72));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
            Controls.Add(root);

            var topPanel = new Panel { Dock = DockStyle.Fill, BackColor = Color.White, Padding = new Padding(10, 8, 10, 8) };
            root.Controls.Add(topPanel, 0, 0);

            var title = new Label
            {
                AutoSize = true,
                Text = $"{_stationTitle}: радиация и НГО",
                Font = new Font("Segoe UI", 12f, FontStyle.Bold),
                ForeColor = AppTheme.TextColor,
                Location = new Point(8, 8)
            };
            topPanel.Controls.Add(title);

            var yearLbl = new Label
            {
                AutoSize = true,
                Text = "Год:",
                ForeColor = AppTheme.TextColor,
                Location = new Point(10, 42)
            };
            topPanel.Controls.Add(yearLbl);

            _yearCombo = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Width = 110,
                Location = new Point(52, 38)
            };
            _yearCombo.Items.Add("Все");
            for (int y = 2021; y <= 2025; y++) _yearCombo.Items.Add(y.ToString());
            _yearCombo.SelectedIndex = 0;
            _yearCombo.SelectedIndexChanged += (_, _) =>
            {
                _offset = 0;
                LoadData();
            };
            topPanel.Controls.Add(_yearCombo);

            var loadBtn = new Button
            {
                Text = "Показать",
                Width = 110,
                Height = 28,
                Location = new Point(172, 37),
                FlatStyle = FlatStyle.Flat,
                BackColor = AppTheme.PrimaryColor,
                ForeColor = Color.White
            };
            loadBtn.FlatAppearance.BorderSize = 0;
            loadBtn.Click += (_, _) => LoadData();
            topPanel.Controls.Add(loadBtn);

            _btnPrev = new Button
            {
                Text = "◀",
                Width = 34,
                Height = 28,
                Location = new Point(292, 37),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.White,
                ForeColor = AppTheme.TextColor
            };
            _btnPrev.Click += (_, _) =>
            {
                _offset = Math.Max(0, _offset - _pageSize);
                LoadData();
            };
            topPanel.Controls.Add(_btnPrev);

            _btnNext = new Button
            {
                Text = "▶",
                Width = 34,
                Height = 28,
                Location = new Point(330, 37),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.White,
                ForeColor = AppTheme.TextColor
            };
            _btnNext.Click += (_, _) =>
            {
                if (_offset + _pageSize < _totalRows)
                {
                    _offset += _pageSize;
                    LoadData();
                }
            };
            topPanel.Controls.Add(_btnNext);

            _grid = new DataGridView
            {
                Dock = DockStyle.Fill,
                ReadOnly = true,
                AllowUserToAddRows = false,
                AllowUserToDeleteRows = false,
                AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill
            };
            AppTheme.StyleDataGridView(_grid);
            root.Controls.Add(_grid, 0, 1);

            _summaryLabel = new Label
            {
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleLeft,
                ForeColor = AppTheme.MutedTextColor,
                Padding = new Padding(10, 0, 10, 0)
            };
            root.Controls.Add(_summaryLabel, 0, 2);
        }

        private void LoadData()
        {
            int? year = null;
            if (_yearCombo.SelectedItem is string s && int.TryParse(s, out var y))
                year = y;

            Cursor = Cursors.WaitCursor;
            try
            {
                _totalRows = MeteoQueryService.GetRadiationAndNgoCount(_stationId, _datasetId, year);
                if (_offset >= _totalRows)
                    _offset = 0;

                _currentTable?.Dispose();
                _grid.DataSource = null;

                _currentTable = MeteoQueryService.GetRadiationAndNgoTablePage(
                    _stationId, _datasetId, year, _offset, _pageSize);
                _grid.DataSource = _currentTable;

                var first = _totalRows == 0 ? 0 : _offset + 1;
                var last = Math.Min(_offset + _pageSize, _totalRows);
                _summaryLabel.Text =
                    $"Записей: {_totalRows:N0} • Показано: {first:N0}-{last:N0}" +
                    (year.HasValue ? $" • Год: {year}" : " • Год: все") +
                    $" • Страница: {_pageSize:N0}";

                _btnPrev.Enabled = _offset > 0;
                _btnNext.Enabled = _offset + _pageSize < _totalRows;
            }
            finally
            {
                Cursor = Cursors.Default;
            }
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            _grid.DataSource = null;
            _currentTable?.Dispose();
            _currentTable = null;
            base.OnFormClosed(e);
        }
    }
}


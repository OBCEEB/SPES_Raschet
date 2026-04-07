using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;

namespace SPES_Raschet
{
    public class SettlementListForm : Form
    {
        private readonly DataGridView dataGridView;
        private readonly Label captionLabel;
        public SettlementData? SelectedSettlement { get; private set; }

        public SettlementListForm(string regionName, List<SettlementData> settlements)
        {
            // Базовые настройки формы выбора населенного пункта.
            this.Text = regionName;
            this.StartPosition = FormStartPosition.CenterParent;
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.MinimizeBox = false;

            // Закрытие допускается только после выбора элемента.
            this.ControlBox = false;
            this.BackColor = AppTheme.BackgroundColor;

            captionLabel = new Label
            {
                Dock = DockStyle.Top,
                Height = 44,
                Text = "Выберите населенный пункт (двойной клик или одиночный клик по строке)",
                TextAlign = ContentAlignment.MiddleLeft,
                Padding = new Padding(14, 0, 0, 0),
                Font = new Font("Segoe UI", 9, FontStyle.Regular),
                ForeColor = AppTheme.MutedTextColor,
                BackColor = Color.White
            };

            dataGridView = new DataGridView
            {
                Dock = DockStyle.Fill,
                AutoGenerateColumns = false,
                ReadOnly = true,
                AllowUserToAddRows = false,
                AllowUserToDeleteRows = false,
                AllowUserToResizeRows = false,
                AllowUserToResizeColumns = false,
                AllowUserToOrderColumns = false,
                RowHeadersVisible = false,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect,
                MultiSelect = false,
                BackgroundColor = Color.White,
                BorderStyle = BorderStyle.None,
                CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal,
                ColumnHeadersBorderStyle = DataGridViewHeaderBorderStyle.Single,
                EnableHeadersVisualStyles = false
            };

            dataGridView.ColumnHeadersHeight = 36;
            dataGridView.ColumnHeadersDefaultCellStyle.BackColor = AppTheme.PrimaryColor;
            dataGridView.ColumnHeadersDefaultCellStyle.ForeColor = Color.White;
            dataGridView.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 9, FontStyle.Bold);
            dataGridView.DefaultCellStyle.Font = new Font("Segoe UI", 9);
            dataGridView.DefaultCellStyle.SelectionBackColor = AppTheme.NavActiveBackColor;
            dataGridView.DefaultCellStyle.SelectionForeColor = AppTheme.TextColor;
            dataGridView.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;
            dataGridView.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(249, 250, 251);
            dataGridView.GridColor = AppTheme.BorderColor;
            dataGridView.RowTemplate.Height = 30;

            // Выбор выполняется по клику на строку.
            dataGridView.CellClick += DataGridView_CellClick;

            this.Controls.Add(dataGridView);
            this.Controls.Add(captionLabel);

            // Сначала показываем районные центры, затем сортируем по названию.
            var sortedSettlements = settlements
                .OrderByDescending(s => s.CenterFlag)
                .ThenBy(s => s.CityOrSettlement)
                .ToList();

            ConfigureGridAndBind(sortedSettlements);
            AdjustWindowSize();
        }

        // Защищаем форму от преждевременного закрытия без выбора.
        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing && SelectedSettlement == null)
            {
                e.Cancel = true;
                MessageBox.Show("Пожалуйста, выберите населенный пункт для продолжения.", "Выбор обязателен", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }

            base.OnFormClosing(e);
        }

        private void ConfigureGridAndBind(List<SettlementData> data)
        {
            dataGridView.AutoGenerateColumns = true;
            dataGridView.DataSource = data;

            // Скрываем служебные поля модели.
            string[] columnsToHide = { "Region", "District", "CenterFlag" };
            foreach (string colName in columnsToHide)
            {
                if (dataGridView.Columns.Contains(colName))
                {
                    dataGridView.Columns[colName].Visible = false;
                }
            }

            // Настраиваем пользовательские заголовки и ширины колонок.
            if (dataGridView.Columns.Contains("CityOrSettlement"))
            {
                dataGridView.Columns["CityOrSettlement"].HeaderText = "Населенный пункт";
                dataGridView.Columns["CityOrSettlement"].AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill;
            }

            if (dataGridView.Columns.Contains("Latitude"))
            {
                dataGridView.Columns["Latitude"].HeaderText = "Широта";
                dataGridView.Columns["Latitude"].Width = 70;
                dataGridView.Columns["Latitude"].DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;
            }

            if (dataGridView.Columns.Contains("Longitude"))
            {
                dataGridView.Columns["Longitude"].HeaderText = "Долгота";
                dataGridView.Columns["Longitude"].Width = 70;
                dataGridView.Columns["Longitude"].DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;
            }

            if (dataGridView.Columns.Contains("TimeZoneOffset"))
            {
                dataGridView.Columns["TimeZoneOffset"].HeaderText = "UTC";
                dataGridView.Columns["TimeZoneOffset"].Width = 50;
                dataGridView.Columns["TimeZoneOffset"].DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;
            }
        }

        private void AdjustWindowSize()
        {
            int totalRowHeight = dataGridView.ColumnHeadersHeight;
            foreach (DataGridViewRow row in dataGridView.Rows)
            {
                totalRowHeight += row.Height;
            }

            int height = Math.Min(totalRowHeight + 40, 600);
            int widthPadding = (totalRowHeight > 600) ? 20 : 0;

            this.ClientSize = new Size(540 + widthPadding, height + captionLabel.Height);
        }

        private void DataGridView_CellClick(object? sender, DataGridViewCellEventArgs e)
        {
            if (e.RowIndex >= 0)
            {
                var selectedItem = dataGridView.Rows[e.RowIndex].DataBoundItem as SettlementData;
                if (selectedItem != null)
                {
                    SelectedSettlement = selectedItem;
                    this.DialogResult = DialogResult.OK;
                    this.Close();
                }
            }
        }
    }
}
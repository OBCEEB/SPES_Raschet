using System.Drawing;
using System.Windows.Forms;
using System.Windows.Forms.DataVisualization.Charting;

namespace SPES_Raschet
{
    public static class AppTheme
    {
        // Палитра
        public static Color PrimaryColor = Color.SeaGreen; // Приятный зеленый
        public static Color DarkPrimary = Color.DarkGreen;
        public static Color AccentColor = Color.Orange;
        public static Color BackgroundColor = Color.FromArgb(245, 247, 249); // Очень светло-серый
        public static Color PanelColor = Color.White;
        public static Color TextColor = Color.FromArgb(50, 50, 50);
        public static Font MainFont = new Font("Segoe UI", 10F, FontStyle.Regular);
        public static Font HeaderFont = new Font("Segoe UI", 12F, FontStyle.Bold);

        // Метод для стилизации Таблиц
        public static void StyleDataGridView(DataGridView grid)
        {
            grid.BackgroundColor = PanelColor;
            grid.BorderStyle = BorderStyle.None;
            grid.CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal;
            grid.ColumnHeadersBorderStyle = DataGridViewHeaderBorderStyle.None;

            // Заголовки
            grid.EnableHeadersVisualStyles = false;
            grid.ColumnHeadersHeight = 40;
            grid.ColumnHeadersDefaultCellStyle.BackColor = PrimaryColor;
            grid.ColumnHeadersDefaultCellStyle.ForeColor = Color.White;
            grid.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 10F, FontStyle.Bold);
            grid.ColumnHeadersDefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;

            // Строки
            grid.DefaultCellStyle.Font = MainFont;
            grid.DefaultCellStyle.ForeColor = TextColor;
            grid.DefaultCellStyle.SelectionBackColor = Color.FromArgb(220, 240, 230); // Бледно-зеленый
            grid.DefaultCellStyle.SelectionForeColor = Color.Black;
            grid.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;

            // Зебра
            grid.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(250, 250, 250);

            grid.RowHeadersVisible = false;
            grid.AllowUserToResizeRows = false;
        }

        // Метод для стилизации плоских кнопок меню
        public static void StyleNavButton(Button btn)
        {
            btn.FlatStyle = FlatStyle.Flat;
            btn.FlatAppearance.BorderSize = 0;
            btn.BackColor = Color.Transparent;
            btn.ForeColor = Color.Gray;
            btn.Font = new Font("Segoe UI", 11F, FontStyle.Bold);
            btn.Cursor = Cursors.Hand;
            btn.TextAlign = ContentAlignment.MiddleLeft;
            btn.Padding = new Padding(10, 0, 0, 0);
        }

        // Метод для активации кнопки меню (подсветка)
        public static void SetActiveNavButton(Button btn, Panel indicator)
        {
            btn.ForeColor = PrimaryColor;
            btn.BackColor = Color.FromArgb(235, 250, 240);
            // Двигаем полоску-индикатор
            indicator.Height = btn.Height;
            indicator.Top = btn.Top;
            indicator.Left = 0; // Если меню слева
            indicator.Visible = true;
        }
    }
}
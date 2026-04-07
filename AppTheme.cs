using System.Drawing;
using System.Windows.Forms;
using System.Windows.Forms.DataVisualization.Charting;

namespace SPES_Raschet
{
    public static class AppTheme
    {
        // Палитра
        public static Color PrimaryColor = Color.FromArgb(35, 140, 93);
        public static Color DarkPrimary = Color.FromArgb(24, 107, 70);
        public static Color AccentColor = Color.FromArgb(245, 158, 11);
        public static Color BackgroundColor = Color.FromArgb(246, 248, 250);
        public static Color PanelColor = Color.White;
        public static Color TextColor = Color.FromArgb(32, 41, 52);
        public static Color MutedTextColor = Color.FromArgb(105, 117, 132);
        public static Color BorderColor = Color.FromArgb(223, 230, 237);
        public static Color NavHoverBackColor = Color.FromArgb(240, 247, 244);
        public static Color NavActiveBackColor = Color.FromArgb(230, 245, 238);
        public static Color SuccessBackColor = Color.FromArgb(226, 244, 235);
        public static Color ErrorBackColor = Color.FromArgb(255, 235, 235);
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
            grid.DefaultCellStyle.SelectionBackColor = NavActiveBackColor;
            grid.DefaultCellStyle.SelectionForeColor = Color.Black;
            grid.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;

            // Зебра
            grid.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(250, 251, 252);

            grid.RowHeadersVisible = false;
            grid.AllowUserToResizeRows = false;
        }

        // Метод для стилизации плоских кнопок меню
        public static void StyleNavButton(Button btn)
        {
            btn.FlatStyle = FlatStyle.Flat;
            btn.FlatAppearance.BorderSize = 0;
            btn.BackColor = Color.Transparent;
            btn.ForeColor = MutedTextColor;
            btn.Font = new Font("Segoe UI", 11F, FontStyle.Bold);
            btn.Cursor = Cursors.Hand;
            btn.TextAlign = ContentAlignment.MiddleLeft;
            btn.Padding = new Padding(16, 0, 0, 0);
        }

        // Метод для активации кнопки меню (подсветка)
        public static void SetActiveNavButton(Button btn, Panel indicator)
        {
            btn.ForeColor = PrimaryColor;
            btn.BackColor = NavActiveBackColor;
            // Двигаем полоску-индикатор
            indicator.Height = btn.Height;
            indicator.Top = btn.Top;
            indicator.Left = 0; // Если меню слева
            indicator.Visible = true;
        }
    }
}
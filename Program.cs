using System;
using System.Text;
using System.Windows.Forms;

namespace SPES_Raschet
{
    static class Program
    {
        /// <summary>
        /// ??????? ????? ????? ??? ??????????.
        /// </summary>
        [STAThread]
        static void Main()
        {
            // ????? ??? ?????? legacy CSV ? Windows-1251.
            Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);

            Application.SetHighDpiMode(HighDpiMode.SystemAware);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new Form1());
        }
    }
}
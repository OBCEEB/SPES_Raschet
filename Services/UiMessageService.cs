using System.Windows.Forms;

namespace SPES_Raschet.Services
{
    public static class UiMessageService
    {
        public static void Info(string context, string message, IWin32Window? owner = null)
        {
            Show(context, message, MessageBoxIcon.Information, owner);
        }

        public static void Warning(string context, string message, IWin32Window? owner = null)
        {
            Show(context, message, MessageBoxIcon.Warning, owner);
        }

        public static void Error(string context, string message, IWin32Window? owner = null)
        {
            Show(context, message, MessageBoxIcon.Error, owner);
        }

        private static void Show(string context, string message, MessageBoxIcon icon, IWin32Window? owner)
        {
            var title = $"СПЭС • {context}";
            if (owner == null)
            {
                MessageBox.Show(message, title, MessageBoxButtons.OK, icon);
                return;
            }

            MessageBox.Show(owner, message, title, MessageBoxButtons.OK, icon);
        }
    }
}

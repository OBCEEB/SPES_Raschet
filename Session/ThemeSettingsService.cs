using System;
using System.IO;

namespace SPES_Raschet.Session
{
    public static class ThemeSettingsService
    {
        private static readonly string SettingsDir =
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SPES");

        private static readonly string ThemeFile = Path.Combine(SettingsDir, "theme.txt");

        public static ThemeVariant LoadOrDefault()
        {
            try
            {
                if (!File.Exists(ThemeFile))
                    return ThemeVariant.BlueAtlantika440;

                var raw = File.ReadAllText(ThemeFile).Trim();
                if (Enum.TryParse<ThemeVariant>(raw, true, out var theme))
                    return theme;
            }
            catch
            {
            }

            return ThemeVariant.BlueAtlantika440;
        }

        public static void Save(ThemeVariant theme)
        {
            try
            {
                Directory.CreateDirectory(SettingsDir);
                File.WriteAllText(ThemeFile, theme.ToString());
            }
            catch
            {
            }
        }
    }
}

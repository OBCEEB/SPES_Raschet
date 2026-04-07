using System;
using System.IO;
using System.Text.Json;

namespace SPES_Raschet.Session
{
    public static class SessionStateService
    {
        private static readonly string SessionDir =
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SPES");

        private static readonly string SessionFile = Path.Combine(SessionDir, "climatology.session.json");

        public static void Save(SessionState state)
        {
            try
            {
                Directory.CreateDirectory(SessionDir);
                var json = JsonSerializer.Serialize(state, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(SessionFile, json);
            }
            catch
            {
                // Non-critical: session persistence should not break workflow.
            }
        }

        public static SessionState? TryLoad()
        {
            try
            {
                if (!File.Exists(SessionFile)) return null;
                var json = File.ReadAllText(SessionFile);
                return JsonSerializer.Deserialize<SessionState>(json);
            }
            catch
            {
                return null;
            }
        }
    }
}

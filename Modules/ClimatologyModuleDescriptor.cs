using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;
using SPES_Raschet.Diagnostics;

namespace SPES_Raschet.Modules
{
    public sealed class ClimatologyModuleDescriptor : IModuleDescriptor, IModuleLauncher, IModuleDiagnostics
    {
        public string Id => "climatology";
        public string DisplayName => "СПЭС-Климатология";
        public string Description => "Выбор населенного пункта и расчет климатических параметров.";
        public bool IsAvailable => true;

        public void Launch(IWin32Window owner)
        {
            using var moduleForm = new Form1();
            moduleForm.ShowDialog(owner);
        }

        public IReadOnlyList<string> ValidateEnvironment()
        {
            var report = StartupDiagnosticsService.Run();
            return report.MissingFiles.Select(x => $"Не найден файл данных: {x}").ToList();
        }
    }
}

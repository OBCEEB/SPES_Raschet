using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;
using SPES_Raschet.Diagnostics;
using SPES_Raschet.Services;

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
            var issues = report.MissingFiles.Select(x => $"Не найден файл данных: {x}").ToList();

            var cfoMissing = CfoClimateDataService.GetMissingFiles();
            foreach (var file in cfoMissing)
            {
                issues.Add($"Для режима новых данных ЦФО не найден файл: {file}");
            }

            var cfoMapPackage = OfflineCfoMapPackageService.Validate();
            foreach (var file in cfoMapPackage.MissingFiles)
            {
                issues.Add($"Для офлайн-карты ЦФО не найден файл: {file}");
            }

            return issues;
        }
    }
}

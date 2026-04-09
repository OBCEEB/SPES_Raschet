using System.Collections.Generic;
using System.Windows.Forms;
using SPES_Raschet.Services;

namespace SPES_Raschet.Modules
{
    public sealed class SolarCollectorModuleDescriptor : IModuleDescriptor, IModuleLauncher, IModuleDiagnostics
    {
        public string Id => "solar-collector";
        public string DisplayName => "СПЭС-Расчет коллектора";
        public string Description => "Модуль расчета солнечного коллектора (в разработке).";
        public bool IsAvailable => false;

        public void Launch(IWin32Window owner)
        {
            UiMessageService.Info(
                "Модули",
                "Модуль находится в разработке и пока недоступен.",
                owner);
        }

        public IReadOnlyList<string> ValidateEnvironment()
        {
            return new List<string>();
        }
    }
}

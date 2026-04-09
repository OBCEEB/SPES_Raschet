using System.Collections.Generic;

namespace SPES_Raschet.Modules
{
    public static class ModuleRegistry
    {
        public static IReadOnlyList<IModuleDescriptor> GetModules()
        {
            return new IModuleDescriptor[]
            {
                new ClimatologyModuleDescriptor(),
                new SolarCollectorModuleDescriptor()
            };
        }
    }
}

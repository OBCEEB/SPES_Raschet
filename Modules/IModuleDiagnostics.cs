using System.Collections.Generic;

namespace SPES_Raschet.Modules
{
    public interface IModuleDiagnostics
    {
        IReadOnlyList<string> ValidateEnvironment();
    }
}

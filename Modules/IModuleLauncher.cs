using System.Windows.Forms;

namespace SPES_Raschet.Modules
{
    public interface IModuleLauncher
    {
        void Launch(IWin32Window owner);
    }
}

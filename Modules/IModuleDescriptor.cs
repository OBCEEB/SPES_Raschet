namespace SPES_Raschet.Modules
{
    public interface IModuleDescriptor
    {
        string Id { get; }
        string DisplayName { get; }
        string Description { get; }
        bool IsAvailable { get; }
    }
}

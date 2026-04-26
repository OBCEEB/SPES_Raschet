namespace SPES_Raschet.Services
{
    public static class ClimateSelectionBridge
    {
        public static ClimateSelectionPayload? LastSelection { get; private set; }

        public static void Publish(ClimateSelectionPayload payload)
        {
            LastSelection = payload;
        }
    }
}

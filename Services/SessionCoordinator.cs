using System;
using System.Linq;
using SPES_Raschet.Session;

namespace SPES_Raschet.Services
{
    public sealed class SessionCoordinator
    {
        public SessionState? PendingState { get; private set; }

        public SessionCoordinator()
        {
            PendingState = SessionStateService.TryLoad();
        }

        public bool HasPendingState =>
            PendingState != null && !string.IsNullOrWhiteSpace(PendingState.SettlementName);

        public SessionState? ConsumePendingState()
        {
            var state = PendingState;
            PendingState = null;
            return state;
        }

        public SettlementData? ResolveSettlement(SessionState state)
        {
            return GeoDataHandler.SettlementList.FirstOrDefault(x =>
                x.CityOrSettlement == state.SettlementName &&
                Math.Abs(x.Latitude - state.Latitude) < 0.0001 &&
                Math.Abs(x.Longitude - state.Longitude) < 0.0001);
        }

        public void Save(
            SettlementData? currentSettlement,
            int navTabIndex,
            int selectedTableIndex,
            string filterText)
        {
            if (currentSettlement == null) return;

            var state = new SessionState
            {
                SettlementName = currentSettlement.CityOrSettlement,
                Region = currentSettlement.Region,
                Latitude = currentSettlement.Latitude,
                Longitude = currentSettlement.Longitude,
                TimeZoneOffset = currentSettlement.TimeZoneOffset,
                NavTabIndex = navTabIndex,
                SelectedTableIndex = selectedTableIndex,
                FilterText = filterText
            };

            SessionStateService.Save(state);
        }
    }
}

using System;

namespace SPES_Raschet.Services.Meteo
{
    public sealed class MeteoStationInfo
    {
        public long Id { get; init; }
        public string Code { get; init; } = string.Empty;
        public string DisplayName { get; init; } = string.Empty;
        public string? RegionSubject { get; init; }
        public string TimezoneIana { get; init; } = "Europe/Moscow";
    }

    public sealed class MeteoDatasetInfo
    {
        public long Id { get; init; }
        public long StationId { get; init; }
        public string Code { get; init; } = string.Empty;
        public string DisplayName { get; init; } = string.Empty;
        public string? ParameterKind { get; init; }
    }

    public sealed class MeteoObservationRow
    {
        public DateTime TimestampLocal { get; init; }
        public double? Qmjm2 { get; init; }
        public double? TdegC { get; init; }
        public double? Qmj { get; init; }
        public double? NgoMeters { get; init; }
        public double? SsdSeconds { get; init; }
    }

    /// <summary>Суточные агрегаты по одному набору (для контроля пропусков и суточной выработки).</summary>
    public sealed class MeteoDailyAggregate
    {
        public DateOnly Date { get; init; }
        public int RowCount { get; init; }
        public int Qmjm2NonNullCount { get; init; }
        public double? SumQmj { get; init; }
        public double? SumSsdSeconds { get; init; }
        public double? AvgTdegC { get; init; }
    }

    /// <summary>Месячные агрегаты для усреднения за период (коллекторы, климат).</summary>
    public sealed class MeteoMonthlyAggregate
    {
        public int Year { get; init; }
        public int Month { get; init; }
        public int RowCount { get; init; }
        public int Qmjm2NonNullCount { get; init; }
        public double? AvgQmjm2 { get; init; }
        public double? SumQmj { get; init; }
        public double? SumSsdSeconds { get; init; }
        public double? AvgTdegC { get; init; }
    }

    /// <summary>Покрытие данных по месяцам: отдельно радиация, НГО и их пересечение.</summary>
    public sealed class MeteoMonthlyCoverage
    {
        public int Year { get; init; }
        public int Month { get; init; }
        public int TotalRows { get; init; }
        public int RadiationRows { get; init; }
        public int NgoRows { get; init; }
        public int RadiationAndNgoRows { get; init; }
    }

    public sealed class MeteoDatabaseSummary
    {
        public string DatabasePath { get; init; } = string.Empty;
        public bool Exists { get; init; }
        public long StationCount { get; init; }
        public long DatasetCount { get; init; }
        public long ObservationCount { get; init; }
    }
}

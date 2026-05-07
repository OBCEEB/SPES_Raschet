using System;

namespace SPES_Raschet.Services.Meteo
{
    public sealed class MeteoImportResult
    {
        public bool Success { get; init; }
        public string Message { get; init; } = string.Empty;
        public int FilesProcessed { get; init; }
        public int RowsInserted { get; init; }
        public TimeSpan Elapsed { get; init; }
    }
}

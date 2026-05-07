using System.Security.Cryptography;
using System.Text;

namespace SPES_Raschet.Services.Meteo
{
    /// <summary>Стабильные коды станций и наборов (как при импорте CSV).</summary>
    public static class MeteoIdentifiers
    {
        public static string StationCode(string regionDisplayName)
            => StableCode("region:" + regionDisplayName, "st_");

        public static string DatasetCode(long stationId, string parameterDisplayName)
            => StableCode("dataset:" + stationId + ":" + parameterDisplayName, "ds_");

        public static string StableCode(string label, string prefix)
        {
            var hash = SHA256.HashData(Encoding.UTF8.GetBytes(label));
            var hex = Convert.ToHexString(hash.AsSpan(0, 8));
            return prefix + hex.ToLowerInvariant();
        }
    }
}

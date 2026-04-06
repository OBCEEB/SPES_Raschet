using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions; // Нужно для Regex

namespace SPES_Raschet
{
    public static class GeoProcessor
    {
        // Слова, которые мы будем удалять при сравнении
        private static readonly string[] StopWords = new[]
        {
            "область", "край", "республика", "автономный", "округ", "ао", "г.", "респ", "обл"
        };

        /// <summary>
        /// Очищает название от типов регионов и спецсимволов для сравнения.
        /// Пример: "Алтайский край" -> "алтайский"
        /// Пример: "Респ|Алтай" -> "алтай"
        /// </summary>
        private static string NormalizeName(string input)
        {
            if (string.IsNullOrEmpty(input)) return "";

            // 1. Переводим в нижний регистр
            string clean = input.ToLower();

            // 2. Заменяем разделитель из GeoDataHandler (|) на пробел
            clean = clean.Replace("|", " ");

            // 3. Удаляем знаки препинания (скобки, тире, точки)
            clean = Regex.Replace(clean, @"[()./\-]", " ");

            // 4. Удаляем стоп-слова
            foreach (var word in StopWords)
            {
                // Заменяем слово целиком (с пробелами вокруг), чтобы не удалить часть другого слова
                clean = clean.Replace(" " + word + " ", " ");
                clean = clean.Replace("^" + word + " ", " "); // Если в начале
                clean = clean.Replace(" " + word + "$", " "); // Если в конце

                // Просто удаляем, если осталось
                clean = clean.Replace(word, "");
            }

            // 5. Убираем лишние пробелы
            return Regex.Replace(clean, @"\s+", "").Trim();
        }

        public static List<SettlementData> GetSettlementsByRegion(string mapRegionName)
        {
            if (GeoDataHandler.SettlementList == null) return new List<SettlementData>();

            // Нормализуем имя региона с карты (из JSON)
            // Пример: "Алтайский край" -> "алтайский"
            string mapNameClean = NormalizeName(mapRegionName);

            var result = new List<SettlementData>();

            foreach (var settlement in GeoDataHandler.SettlementList)
            {
                // Нормализуем имя региона из CSV
                // В GeoDataHandler мы сохранили его как "Тип|Имя" (например "край|Алтайский")
                // Normalize превратит это в "алтайский"
                string csvNameClean = NormalizeName(settlement.Region);

                // Сравниваем очищенные имена
                // Используем Contains, чтобы "Саха" нашлась в "Саха Якутия"
                if (mapNameClean.Contains(csvNameClean) || csvNameClean.Contains(mapNameClean))
                {
                    result.Add(settlement);
                }
            }

            return result;
        }

        public static Dictionary<string, Dictionary<string, List<List<double>>>>? GetAllBoundaries()
        {
            return GeoDataHandler.RegionBoundaries;
        }
    }
}
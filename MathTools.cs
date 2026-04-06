using System;
using System.Collections.Generic;
using System.Linq;

namespace SPES_Raschet
{
    public static class MathTools
    {
        /// <summary>
        /// Линейная интерполяция по двум ближайшим точкам.
        /// Это самый надежный метод для данных инсоляции, чтобы избежать выбросов.
        /// </summary>
        public static double Interpolate(double targetX, Dictionary<double, double> points)
        {
            var sortedLats = points.Keys.OrderBy(k => k).ToList();

            if (sortedLats.Count == 0) return 0;
            if (sortedLats.Count == 1) return points[sortedLats[0]];

            // 1. Если точка совпадает с табличной
            if (points.ContainsKey(targetX)) return points[targetX];

            // 2. Ищем соседей (X1 < targetX < X2)
            double x1 = -1, x2 = -1;

            // Находим ближайшую точку слева
            for (int i = 0; i < sortedLats.Count; i++)
            {
                if (sortedLats[i] < targetX)
                {
                    x1 = sortedLats[i];
                }
                else
                {
                    // Как только нашли точку больше или равную, это наша X2
                    x2 = sortedLats[i];
                    break;
                }
            }

            // 3. Обработка краев (экстраполяция или возврат крайнего)
            // Если мы левее всех (x1 не найден)
            if (x1 == -1) return points[sortedLats.First()];
            // Если мы правее всех (x2 не найден)
            if (x2 == -1) return points[sortedLats.Last()];

            // 4. Линейная интерполяция: Y = Y1 + (X - X1) * (Y2 - Y1) / (X2 - X1)
            double y1 = points[x1];
            double y2 = points[x2];

            double result = y1 + (targetX - x1) * (y2 - y1) / (x2 - x1);

            return Math.Max(0, result); // Радиация не может быть отрицательной
        }

        // Оставляем метод Лагранжа для истории или переименовываем, если нужно строго его использовать
        // Но он дает выбросы на резких скачках данных.
    }
}
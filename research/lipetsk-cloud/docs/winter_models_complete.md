# Руководство по улучшению зимней модели Kt для Cursor-агентов

**Дата:** 2026-10-17  
**Проект:** Актуализация солнечной радиации для коллекторов, Липецк  
**Контекст:** Логарифмическая модель индекса ясности систематически недооценивает зимнюю радиацию, что приводит к обнулению расчётной полезной теплоты коллектора в месяцы XI–I. Данный документ содержит 7 альтернативных подходов для устранения этой проблемы.

---

## Оглавление

1. Проблема и её причины
2. Критическая радиация Gcrit
3. Мультиколлинеарность log(Kref) и месяцев
4. Семь вариантов улучшения модели
5. Сравнительная таблица
6. План тестирования
7. Интеграция в существующий pipeline
8. Требования к отчёту в статью

---

## Проблема и её причины

### Наблюдаемые симптомы

Из таблицы §14.2 отчёта `otchet-raschety.md`:

| Месяц | Qobs (кВт·ч/м²·мес) | Qadj (кВт·ч/м²·мес) | Qadj/Qobs |
|---|---:|---:|---:|
| XI (ноябрь) | 34 | 0 | 0.01 |
| XII (декабрь) | 24 | 1 | 0.02 |
| I (январь) | 56 | 11 | 0.20 |

Модель предсказывает зимнюю полезную теплоту в 5–100 раз меньше фактической. Фактически коллектор зимой работал, а модель говорит, что он почти не работает.

### Причина: предсказанная радиация ниже Gcrit

1. Логарифмическая модель Kt обучена на композите 2023–2025 годов
2. При применении к out-of-sample году она предсказывает зимний Kt слишком низким
3. Низкий Kt → низкая почасовая радиация G
4. G < Gcrit почти весь световой день
5. Код обнуляет Q → суммарный Qadj за месяц ≈ 0

Но фактически зимой были часы с кратковременными прояснениями (G > 210 Вт/м²), и коллектор работал.

### Возможные причины недооценки

1. Мало зимних данных в обучении — если в train больше летних дней, модель переоптимизирована на лето
2. Логарифм не подходит для низких Kt — при Kt → 0 логарифм → −∞, модель может давать пессимистичные предсказания
3. Высокая зимняя изменчивость — облачность меняется резче, модель без AR(1) или случайных эффектов суток не улавливает кратковременные прояснения

---

## Критическая радиация Gcrit

### Определение

Критическая радиация — минимальная облучённость в плоскости коллектора, при которой КПД равен нулю. Ниже этого порога коллектор охлаждается: тепловые потери больше прихода солнечной энергии.

### Формула КПД коллектора (ISO 9806)

η = η₀K_τα - (a₁(Tm - Ta))/G - (a₂(Tm - Ta)²)/G

где:
- G — облучённость в плоскости коллектора, Вт/м²
- Tm — средняя температура теплоносителя, °C
- Ta — температура наружного воздуха, °C
- η₀ — оптический КПД (доля поглощённой радиации при ΔT = 0)
- a₁ — линейный коэффициент потерь, Вт/(м²·K)
- a₂ — квадратичный коэффициент потерь, Вт/(м²·K²)

### Расчёт Gcrit

Критическая радиация определяется из условия η = 0:

G_crit = (a₁ΔT + a₂ΔT²) / (η₀K_τα)

Для типичного остеклённого коллектора при ΔT = 40 K:

G_crit = (3.5 × 40 + 0.015 × 40²) / (0.78 × 1) = (140 + 24) / 0.78 ≈ 210 Вт/м²

### Пример зависимости η от G

| G, Вт/м² | η |
|---:|---:|
| 1000 | 0.78 − 0.14 − 0.024 = 0.62 |
| 500 | 0.78 − 0.28 − 0.048 = 0.45 |
| 210 | 0.78 − 0.67 − 0.11 = 0.00 |
| 100 | 0.78 − 1.4 − 0.24 = −0.86 (охлаждение) |

### Почему это важно зимой

Зимой: солнечная радиация ниже, много облачных часов, температура воздуха низкая → большой ΔT. Из-за этого большая часть дня G < Gcrit, и коллектор не работает. Летом G > Gcrit почти весь день, поэтому ошибка модели Kt на 10–20% меньше влияет на Qadj. Зимой даже небольшая ошибка в Kt может сдвинуть G ниже Gcrit и обнулить всю выработку.

---

## Мультиколлинеарность log(Kref) и месяцев

### Наблюдение

В логарифмической модели коэффициент β₁ при log(Kref) скачет по годам:

| Обучение | β₁ (log Kref) |
|---|---:|
| 2023+2024 → test 2025 | 0.26 |
| 2023+2025 → test 2024 | 3.24 |
| 2024+2025 → test 2023 | 1.85 |

Такой разброс — не физический эффект, а математический артефакт.

### Причина: мультиколлинеарность

Мультиколлинеарность означает, что две переменные сильно коррелируют друг с другом — несут примерно одну информацию. В модели есть log(Kref) и αₘ (коэффициенты месяцев). Kref рассчитывается как K_ref = G_cs,Hottel / H₀. Обе величины зависят только от широты, дня года и солнечной геометрии. То есть Kref не содержит информации о фактической погоде — это чисто геометрическая величина, сильно коррелирующая с номером месяца.

### Что происходит в регрессии

Модель пытается объяснить наблюдаемый Kt через месячные константы и log(Kref), но поскольку log(Kref) в январе всегда примерно одинаков, регрессия не может разделить, какая часть объяснения приходится на константу месяца, а какая — на β₁ × log(Kref). Существует бесконечно много комбинаций (α, β₁), которые дают одинаковое предсказание.

### Что значит «не интерпретируется как упругость»

В экономике упругость — это процентное изменение Y при процентном изменении X. Если бы log-линейная модель была стабильной, β₁ можно было бы интерпретировать так: «При увеличении Kref на 1%, Kt увеличивается на β₁ процентов». Но когда β₁ скачет от 0.26 до 3.24 в зависимости от года обучения, такая интерпретация бессмысленна — физически ничего не изменилось, а коэффициент прыгает в 12 раз.

### Как это исправить

Вариант 1: Убрать либо log(Kref), либо месяцы из модели.

Вариант 2: Заменить фиксированные коэффициенты месяцев на циклический сплайн дня года — тогда сезонность будет гладкой функцией, а не 12 независимыми константами.

Вариант 3: Принять, что log(Kref) и месяцы несут одну и ту же информацию (сезонность), и не интерпретировать β₁, а просто использовать модель для предсказания.

---

## Семь вариантов улучшения модели

Все варианты совместимы с year-wise валидацией и существующей инфраструктурой.

---

## Вариант 1. Двухкомпонентная модель (hurdle)

### Идея

Разделить задачу на два этапа:

Этап 1: Предсказать вероятность того, что коллектор вообще работает (G > Gcrit).

Этап 2: Если работает — предсказать, насколько интенсивно (Kt или Qadj).

### Математическая формулировка

Модель 1 (бинарная):
P(G > G_crit) = logit⁻¹(αₘ + βₛs + β_h log(H_cloud+10) + β_z cosθ_z)

Модель 2 (условная на положительном):
log(Kt) | G > G_crit = αₘ + β₁ log(K_ref) + β₂ sinα_n + β₃s + β₄ log(H+10)

### Код (Python)

```python
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import statsmodels.api as sm

def fit_hurdle_model(df_train, df_test, gcrit=210.0):
    """
    Двухкомпонентная модель Kt (hurdle).

    Ожидаемые колонки:
      month, Kt, Kref, sin_alpha_n, s, log_Hcloud, cos_theta_z, G_obs
    """
    df_train = df_train.copy()
    df_test = df_test.copy()

    # Шаг 1: вероятность "коллектор работает"
    df_train['works'] = (df_train['G_obs'] > gcrit).astype(int)
    df_test['works'] = (df_test['G_obs'] > gcrit).astype(int)

    Xb_vars = ['s', 'log_Hcloud', 'cos_theta_z']
    Xtr_b = pd.get_dummies(df_train[['month'] + Xb_vars], columns=['month'], drop_first=True)
    Xte_b = pd.get_dummies(df_test[['month'] + Xb_vars], columns=['month'], drop_first=True)
    Xte_b = Xte_b.reindex(columns=Xtr_b.columns, fill_value=0)

    logit_bin = LogisticRegression(max_iter=2000, random_state=42)
    logit_bin.fit(Xtr_b, df_train['works'])
    p_work = logit_bin.predict_proba(Xte_b)[:, 1]

    # Шаг 2: условная модель на "рабочих" днях
    df_pos = df_train[df_train['works'] == 1].copy()
    Xc_vars = ['Kref', 'sin_alpha_n', 's', 'log_Hcloud']
    Xtr_c = pd.get_dummies(df_pos[['month'] + Xc_vars], columns=['month'], drop_first=True)
    Xte_c = pd.get_dummies(df_test[['month'] + Xc_vars], columns=['month'], drop_first=True)
    Xte_c = Xte_c.reindex(columns=Xtr_c.columns, fill_value=0)

    ols_c = sm.OLS(df_pos['Kt'], sm.add_constant(Xtr_c)).fit()
    kt_pos = ols_c.predict(sm.add_constant(Xte_c)).clip(0, 1)

    # Шаг 3: комбинация
    Kt_pred = (p_work * kt_pos).clip(0, 1)
    return Kt_pred, {'p_work': p_work, 'kt_conditional': kt_pos,
                     'logit_binary': logit_bin, 'ols_conditional': ols_c}
```

### Преимущества

- Явно моделирует «будет ли коллектор работать вообще»
- Зимой большая часть неопределённости именно в этом бинарном вопросе
- На положительных значениях условная модель более стабильна

### Недостатки

- Две модели — сложнее отлаживать
- Нужно достаточно зимних «рабочих» дней для обучения второй модели

---

## Вариант 2. Модель с усечением (tobit)

### Идея

Вместо логарифма использовать усечённую регрессию, которая естественным образом моделирует нижнюю границу (Kt ≥ Kmin).

### Математическая формулировка

Латентная переменная:

K* = Xβ + ε,  ε ~ N(0, σ²)

Наблюдаемая:

Kt = max(Kmin, K*)

### Код (Python)

```python
import statsmodels.api as sm

def fit_tobit_model(df_train, df_test, lower_bound=0.05):
    """
    Tobit-модель для Kt с нижним усечением.
    statsmodels снимает усечение только сверху (cens_ul);
    нижнее усечение нужно задавать самостоятельно.
    """
    X_vars = ['Kref', 'sin_alpha_n', 's', 'log_Hcloud']
    Xtr = pd.get_dummies(df_train[['month'] + X_vars], columns=['month'], drop_first=True)
    Xte = pd.get_dummies(df_test[['month'] + X_vars], columns=['month'], drop_first=True)
    Xte = Xte.reindex(columns=Xtr.columns, fill_value=0)

    res = sm.Tobit(df_train['Kt'], sm.add_constant(Xtr),
                   cens_ll=lower_bound, cens_ul=1.0).fit(disp=False)

    Kt_pred = np.clip(res.predict(sm.add_constant(Xte)), lower_bound, 1.0)
    return Kt_pred, {'model': res}
```

### Преимущества

- Естественная обработка нижней границы
- Одна модель вместо двух

### Недостатки

- Требует нормальности остатков
- Ограниченная поддержка нижнего усечения в statsmodels

---

## Вариант 3. Квантильная регрессия

### Идея

Минимизировать абсолютную ошибку (медианная регрессия) вместо квадратичной — робастнее к зимним экстремумам.

### Код (Python)

```python
import statsmodels.formula.api as smf

def fit_quantile_model(df_train, df_test, quantile=0.5):
    formula = 'Kt ~ C(month) + Kref + sin_alpha_n + s + log_Hcloud'
    res = smf.quantreg(formula, df_train).fit(q=quantile)
    Kt_pred = np.clip(res.predict(df_test), 0, 1)
    return Kt_pred, {'model': res}
```

### Построение интервалов

Обучите квантили 0.1 / 0.5 / 0.9 — получите 80% предсказательный интервал.

### Преимущества

- Робастность к выбросам
- Прямой путь к предсказательным интервалам
- Работает без логарифма

### Недостатки

- Медиана ≠ среднее, для RMSE нужна корректировка
- Требует clip для положительности

---

## Вариант 4. Бета-регрессия

### Идея

Kt ∈ (0,1) естественно следует бета-распределению.

### Формулировка

Kt ~ Beta(μ, φ),   logit(μ) = Xβ

### Код (R, пакет betareg)

```r
library(betareg)
train_df$Kt <- pmin(pmax(train_df$Kt, 1e-6), 1 - 1e-6)
m <- betareg(Kt ~ factor(month) + Kref + sin_alpha_n + s + log_Hcloud, data = train_df)
pred <- predict(m, newdata = test_df)
```

### Преимущества

- Автоматически держит предсказания в (0,1)
- Можно моделировать гетероскедастичность

### Недостатки

- Нужен R (или rpy2)
- Не принимает точные 0 и 1 без трансформации

---

## Вариант 5. Иерархическая модель с AR(1)

### Идея

Добавить случайный эффект года, случайный эффект суток и временную автокорреляцию остатков.

### Формулировка (суточный уровень)

log(Kt_d) = α_m + β₁log(Kref_d) + β₂ sinα_n + β₃ s_d + β₄ log(H_d+10) + u_y + u_d + ε_d

u_y ~ N(0, σ²_y),  u_d ~ N(0, σ²_d)

### Код (statsmodels MixedLM)

```python
import statsmodels.formula.api as smf

def fit_mixed_year_effect(df_train, df_test):
    formula = 'Kt ~ C(month) + Kref + sin_alpha_n + s + log_Hcloud'
    m = smf.mixedlm(formula, df_train, groups=df_train['year']).fit()
    Kt_pred = np.clip(m.predict(df_test), 0, 1)
    return Kt_pred, {'model': m}
```

### Код (PyMC, полная иерархия)

```python
import pymc as pm

def fit_hierarchical_pymc(df_train, n_draws=2000):
    idx_y = df_train['year'].astype('category').cat.codes.values
    idx_d = df_train['day_id'].astype('category').cat.codes.values

    X = df_train[['Kref', 'sin_alpha_n', 's', 'log_Hcloud']].values
    X = np.column_stack([np.ones(len(X)), X])

    with pm.Model() as model:
        sigma_y = pm.HalfNormal('sigma_year', 0.1)
        sigma_d = pm.HalfNormal('sigma_day', 0.2)
        u_y = pm.Normal('u_year', 0, sigma_y, shape=idx_y.max() + 1)
        u_d = pm.Normal('u_day', 0, sigma_d, shape=idx_d.max() + 1)
        beta = pm.Normal('beta', 0, 1, shape=X.shape[1])
        sigma = pm.HalfNormal('sigma', 0.1)

        mu = pm.math.dot(X, beta) + u_y[idx_y] + u_d[idx_d]
        pm.Normal('y', mu, sigma, observed=df_train['Kt'].values)
        idata = pm.sample(n_draws, tune=1000, return_inferencedata=True)

    return model, idata
```

### Преимущества

- Учитывает иерархию год → сутки → часы
- Даёт калиброванные интервалы неопределённости
- Корректно выражает межгодовую неопределённость

### Недостатки

- Сложная и медленная реализация
- Нужна аккуратная сборка индексов

---

## Вариант 6. Сезонный ансамбль

### Идея

Обучить отдельные модели для зимнего и летнего режима и смешивать их по месяцу.

### Формулировка

Kt_hat = w_m · Kt_hat_winter + (1 - w_m) · Kt_hat_summer

w_m: 1.0 для XII–II, 0.7 для XI и III, 0.3 для X и IV, 0.0 для V–IX

### Код (Python)

```python
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

def fit_seasonal_ensemble(df_train, df_test):
    winter_months = [11, 12, 1, 2, 3]
    features = ['Kref', 'sin_alpha_n', 's', 'log_Hcloud']

    df_w = df_train[df_train['month'].isin(winter_months)]
    df_s = df_train[df_train['month'].isin([5, 6, 7, 8, 9])]

    sc_w, sc_s = StandardScaler(), StandardScaler()
    Xw = sc_w.fit_transform(df_w[features]); Xs = sc_s.fit_transform(df_s[features])
    mw = Ridge(alpha=1.0).fit(Xw, df_w['Kt'])
    ms = Ridge(alpha=1.0).fit(Xs, df_s['Kt'])

    Xt = df_test[features]
    kw = np.clip(mw.predict(sc_w.transform(Xt)), 0, 1)
    ks = np.clip(ms.predict(sc_s.transform(Xt)), 0, 1)

    w = df_test['month'].map({12: 1.0, 1: 1.0, 2: 1.0,
                              11: 0.7, 3: 0.7,
                              10: 0.3, 4: 0.3,
                              5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0, 9: 0.0}).fillna(0.5)

    return (w * kw + (1 - w) * ks).clip(0, 1), {'winter': mw, 'summer': ms, 'weights': w}
```

### Преимущества

- Простая и прозрачная
- Каждая модель оптимизирована под свой режим

### Недостатки

- Веса задаются вручную
- Резкие переходы на границе сезонных групп

---

## Вариант 7. XGBoost с зимним взвешиванием

### Идея

Нелинейная модель со штрафом за недооценку зимних значений.

### Формулировка

L = Σ_i w_i (y_i - ŷ_i)²,  w_i = 3 для зимних месяцев, 1 для остальных

### Код (Python)

```python
import xgboost as xgb

def fit_xgboost_weighted(df_train, df_test, early_stopping_rounds=20):
    features = ['month', 'Kref', 'sin_alpha_n', 's', 'log_Hcloud', 'cos_theta_z']
    Xtr, ytr = df_train[features], df_train['Kt']
    Xte, yte = df_test[features], df_test['Kt']

    winter = df_train['month'].isin([11, 12, 1, 2, 3])
    w = np.where(winter, 3.0, 1.0)

    dtrain = xgb.DMatrix(Xtr, label=ytr, weight=w)
    dvalid = xgb.DMatrix(Xte, label=yte)

    params = {'objective': 'reg:squarederror', 'max_depth': 6, 'eta': 0.1,
              'subsample': 0.8, 'colsample_bytree': 0.8, 'eval_metric': 'rmse'}

    model = xgb.train(params, dtrain, num_boost_round=500,
                      evals=[(dvalid, 'holdout')],
                      early_stopping_rounds=early_stopping_rounds,
                      verbose_eval=False)

    Kt_pred = np.clip(model.predict(dvalid), 0, 1)
    return Kt_pred, {'model': model}
```

### Важное предостережение

Ранняя остановка по тестовому году — это подбор гиперпараметров на тесте. Для честной валидации нужен отдельный год валидации либо вложенный цикл: обучение на 2 годах, ранняя остановка на 3-м, финальная оценка на оставшемся.

### Преимущества

- Улавливает нелинейные взаимодействия
- Целенаправленно борется с зимней недооценкой

### Недостатки

- Чёрный ящик
- Требует аккуратной схемы валидации

---

## Сравнительная tabla

| Вариант | Сложность | Интерпретируемость | Зима | Доп. зависимости |
|---|---|---|---|---|
| 1. Hurdle | ★★★ | ★★★ | ★★★★ | sklearn, statsmodels |
| 2. Tobit | ★★★ | ★★ | ★★★ | statsmodels |
| 3. Квантильная | ★★ | ★★★ | ★★★ | statsmodels |
| 4. Бета-регрессия | ★★★★ | ★★ | ★★★★ | R betareg / rpy2 |
| 5. Иерархическая | ★★★★★ | ★★ | ★★★★★ | PyMC |
| 6. Сезонный ансамбль | ★★ | ★★★★ | ★★★★ | sklearn |
| 7. XGBoost | ★★ | ★ | ★★★★ | xgboost |

---

## План тестирования

### Этап 1. Базовая линия

Зафиксировать текущую логарифмическую модель как baseline: `log(Kt) = α_m + β₁log(Kref) + β₂sinα_n + β₃s + β₄log(H+10)` с year-wise split и bias-correction exp(resid/2).

### Этап 2. Простые кандидаты

Варианты 3 и 6. Цель — проверить гипотезу «смена функциональной формы и сезонная стратификация решают проблему».

### Этап 3. Структурные кандидаты

Варианты 1 и 4. Если hurdle покажет пользу, стоит остановиться на нём — он интерпретируем и физически осмыслен.

### Этап 4. Продвинутые кандидаты

Вариант 7 (с корректной схемой валидации) и вариант 5 (если нужны интервалы неопределённости для статьи).

### Метрики

Обязательно раздельно по сезонам:

- зима: месяцы XI, XII, I, II, III
- лето: месяцы V, VI, VII, VIII, IX
- межсезонье: IV, X

Для каждой группы: RMSE Kt, MAE, R², а также RMSE и MAE для Q (полезной теплоты) и для суточной энергии E (МДж/м²·сут). Сравнение только по общему RMSE скрывает проблему — именно зимняя группа даёт сбой.

---

## Интеграция в существующий pipeline

### Единый интерфейс модели

```python
from abc import ABC, abstractmethod
import pandas as pd

class KtModel(ABC):
    name: str = 'base'

    @abstractmethod
    def fit(self, df_train: pd.DataFrame) -> 'KtModel':
        ...

    @abstractmethod
    def predict(self, df_test: pd.DataFrame) -> pd.Series:
        ...

    def get_params(self) -> dict:
        return {}
```

Обёртка для вариантов из документа:

```python
class SklearnWrapper(KtModel):
    def __init__(self, fn, name):
        self.fn = fn; self.name = name; self.inner = None

    def fit(self, df_train):
        # отдельная реализация fit для каждой модели
        raise NotImplementedError
```

Практичнее сделать обёртку вида:

```python
class ModelAdapter(KtModel):
    """Адаптирует функции вида fit_*(df_train, df_test) -> (pred, info)."""
    def __init__(self, fn, name):
        self.fn = fn
        self.name = name

    def fit_predict(self, df_train, df_test):
        pred, info = self.fn(df_train, df_test)
        self._info = info
        return pd.Series(pred, index=df_test.index)
```

### Скрипт сравнения

```python
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

MODELS = {
    'quantile': lambda a, b: fit_quantile_model(a, b, 0.5),
    'ensemble': fit_seasonal_ensemble,
    'hurdle': lambda a, b: fit_hurdle_model(a, b, gcrit=210.0),
}

WINTER = [11, 12, 1, 2, 3]
SUMMER = [5, 6, 7, 8, 9]
SHOULDER = [4, 10]

def evaluate(df_test, y_pred, name):
    y = df_test['Kt'].values
    y_pred = np.asarray(y_pred)
    row = {'model': name, 'n': len(y)}
    for label, months in [('all', None), ('winter', WINTER),
                          ('summer', SUMMER), ('shoulder', SHOULDER)]:
        m = np.ones(len(y), bool) if months is None else df_test['month'].isin(months).values
        row[f'rmse_{label}'] = float(np.sqrt(mean_squared_error(y[m], y_pred[m])))
        row[f'mae_{label}'] = float(mean_absolute_error(y[m], y_pred[m]))
        row[f'r2_{label}'] = float(r2_score(y[m], y_pred[m])) if m.sum() > 2 else np.nan
    return row

def main(df):
    rows = []
    for test_year in sorted(df['year'].unique()):
        train_years = [y for y in df['year'].unique() if y != test_year]
        df_train = df[df['year'].isin(train_years)]
        df_test = df[df['year'] == test_year]
        for name, fn in MODELS.items():
            pred, _ = fn(df_train, df_test)
            r = evaluate(df_test, pred, name)
            r['test_year'] = test_year
            rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv('results/winter_models_comparison.csv', index=False)
    print(out.to_string(index=False))
```

### Оценка влияния на полезную теплоту

```python
def collector_Q(G, delta_T=40.0, eta0=0.78, a1=3.5, a2=0.015, b0=0.10):
    """G — облучённость в плоскости коллектора, Вт/м²."""
    Kta = 1.0  # упрощённо; при необходимости считать по углу падения
    G_crit = (a1 * delta_T + a2 * delta_T**2) / (eta0 * Kta)
    eta = np.where(G > G_crit,
                   eta0 - (a1 * delta_T) / G - (a2 * delta_T**2) / G,
                   0.0)
    return np.maximum(0.0, G * eta), G_crit
```

Модель качества считается только после того, как Kt скорректирован и перенесён в плоскость коллектора через Liu–Jordan. Метрики для Q: месячные суммы, доля часов с G ≤ G_crit, Qobs/Qadj.

---

## Требования к отчёту в статью

### Описание проблемы

> Начальная логарифмическая модель индекса ясности при временно независимой проверке систематически занижала зимние значения. Поскольку расчёт полезной теплоты коллектора обнуляется при облучённости ниже критической G_crit ≈ 210 Вт/м² (ΔT = 40 K), это приводило к практически нулевой оценке выработки в месяцы XI–I, тогда как измеренная выработка составляла 24–56 кВт·ч/м² в месяц.

### Описание проверки

> Для устранения смещения рассмотрены две группы моделей: (а) смена функциональной формы — квантильная регрессия и сезонный ансамбль; (б) явное разделение режимов — двухкомпонентная (hurdle) и бета-регрессия. Оценка выполнена по схеме leave-one-year-out с раздельным учётом сезонных групп.

### Требования к честности изложения

- Указывать, что XGBoost с ранней остановкой требует отдельного года валидации, иначе это подбор на тесте.
- Не называть hurdle «точной моделью коллектора» — это модель индекса ясности.
- Если используется ансамбль с вручную заданными весами, это нужно указать как допущение.
- Не переносить результаты на другие регионы: калибровка выполнена на одной станции.
- Отдельно указать, что SSD измеряется тем же логгером, что и радиация, поэтому это не независимый признак, а вспомогательный.

---

## Чек-лист для агента

1. Зафиксировать baseline: текущая логарифмическая модель с теми же коэффициентами и той же схемой валидации.
2. Убедиться, что во всех экспериментах используется один и тот же набор дней (complete_day).
3. Не менять предобработку между экспериментами; изменение QC — отдельная ветка.
4. Для каждой модели сохранить: имя, параметры, RMSE по сезонам, R², долю обнулённых Q зимой.
5. Ранняя остановка в XGBoost — только на валидационном году.
6. Все графики: единый стиль, подписи осей с единицами, легенда.
7. Итог: таблица сравнения + график «зимние суточные Q: observed vs baseline vs лучшая модель».
8. Обновить `docs/decisions_log.md` записью о выбранной модели и причине.
9. Не менять формулировки в статье до подтверждения результатов.
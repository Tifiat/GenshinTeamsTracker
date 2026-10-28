# Полезные алгоритмические принципы после общей математики

Точечный review exact R5 source map48f643c2…; диагностическая база сохраняет
эти алгоритмы. Это не предложение сделать поиски трёх режимов одинаковыми.
Статусы ниже относятся к доказанному месту применения, не к общей готовности.

| Принцип | Selected / AllSets: место и доказанный эффект | Theory сейчас | Применимость и риск |
| --- | --- | --- | --- |
| Staged ordinary verification |**Implemented AllSets R2:** finalists/r2_staged_finalists.go:47–53,145–240; all_sets.go:422–431.9n500→9n100+1n500; verification47,465→20,938 с, −26,527 с в одной Chasca pair. Selected сохраняет fixed n500(main.go:367–386).|**Absent staged policy:** theoryverify/archive.go:17–40,198–214 fixed n500, lifetime7/reserve2; реально2n500/~14 с.|Реальное различие, но не объясняет313 с replay. Four-SE screening эвристический; близкие альтернативы n100 хуже измерены. Не автоматическая рекомендация переноса.|
| Ограничить повторные simulator checks по exact identity |**Implemented:** R2 сохраняет77 intermediate calls (24 adaptive+53 response n1),2 captures и run-local reuse. Дальнейшее точное preparation/binding reuse в BASELINE_AND_NEXT:35–49 — **proposed-only**, не достигнутый эффект.|**Implemented/inherited:** conditional support-response,52 saved response results; identity dedup и lifetime archive budget, source/program reuse. theoryverify/responses.go:620–681, archive.go:151–185,216–324.|Нельзя представлять отсутствие intermediate checks/reuse как преимущество старого режима. Не удалять probes по одному проигравшему случаю; сначала стоимость, dependence/identity и качество.|
| Семейства и ранняя дедупликация |**Implemented:** AllSets result_archive.go:25–66,87–141 группирует package identities и exact assignments.|**Implemented differently:** theorysearch/search.go:154–176,316–351 pools response families, tuple aliases; verification/build.go:38–45,148–170 хранит полную frame/package/witness identity.|Разные уровни identity нужны разным пространствам. Numeric/response alias не разрешает повторное использование uncertain bound mechanics. Сам принцип в Theory не отсутствует.|
| Screening, starts, refinement |**Implemented AllSets neutral route:** legal seed+screen по feasible package, queue/deeper refine и bounded finalist stabilization; neutral_coordinator.go:704–767,939–1135,1194–1294.|**Implemented:** deterministic tuple starts, до2 distinct families, короткий family screen, light/deep refinement/catalog passes; theorysearch/search.go:230–379,390–528.|Не доказано, что меньше starts/одноимённые budgets дадут ту же ценность в виртуальном45-roll domain. Нужна lineage, а не автоматический перенос owned-item search.|
| Остановка при достаточном результате и verified incumbent |**Implemented:** AllSets Finish завершает существующего complete energy-feasible кандидата; без него no verified result(all_sets.go:297–321,422–431).|**Implemented:** First/Finish(session.go:172–183), response-reserved lane, identity dedup/lifetime budget и удержание completed ordinary incumbent(archive.go:335–350,356–433,436–498).|Не отсутствующая оптимизация. Это sufficient-result, не optimality. Текущий долгий First не исправляется повторным добавлением уже существующего Finish.|
| Явное обращение с неопределённостью |**Implemented:** AllSets finalist quotas могут сохранять uncertain package groups и учитывать omitted groups; coordinator.go:622–719, result_archive.go:10–19,87–141. R1 no-recapture/frozen path является отдельной политикой.|**Inherited annotations**, но **absent dedicated uncertainty finalist slot**: aliases сохраняют uncertainty(result.go:22–41); archive выбор по rank/response reserve. R1 opt-in также admitted incomplete guides через shared constructor.|Сначала разнести unobserved fact, unsupported operation/binding, frozen schedule и uncertain response. Не объявлять все uncertain groups одинаковыми и не доказывать quality удалением unknown.|
| Learned residual из simulator changes |Для R2 **proposed-only/deferred**, BASELINE_AND_NEXT:87–107: total DPS не идентифицирует frozen contribution.|R1 frozen anchor/reference — сохранённый guide, **не implemented general residual learner**.|Нельзя приписывать переносом существующий measured gain. Нужны отдельные наблюдения/идентифицируемость; текущий GO разрешает сбор данных, не обучение/новую модель.|

R3–R5 инженерные изменения структур/буферов здесь намеренно не пересказываются.
Их общие measured AllSets итоги не доказывают эффект нового Theory-алгоритма.
R1/R2/R3 сохранили ordinary verification, реальные входы и наблюдаемые ограничения;
изолированный результат одной команды не даёт no-loss гарантии других команд.

Источники: MAIN docs/optimizer-evidence/2026-10-27-staged-finalists/
RESULT_RU.md и BASELINE_AND_NEXT.md; engineering-efficiency/RESULT_RU.md,
R4_RESULT_RU.md, R5_RESULT_RU.md; текущие control-v2/r5-v1/bookkeeping receipts.
Line refs — восстановленный native image, не dirty HEAD.

После сбора event-level данных ROOT показывает человеку интерпретацию и
конкретные предлагаемые эксперименты. Эта таблица сама не является GO ни для
staged policy, ни для frozenOFF, reuse, learning, нового поиска или установки.

После collect: конкретно установлены initialization-order boundary, joint-wide
reference freeze при Clam2 и повтор неподдержанного CurrentHPRatio при concrete
queries. См. RESULT_RU.md. Это данные к строкам uncertainty/reuse; новых
simulator budget/staged-quality измерений не было, статусы таблицы не меняются.

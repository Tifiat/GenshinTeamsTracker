# Theory Chasca: исторические 105 с, control-v2 и timed R5

28 октября 2026. Завершённые наблюдения: исторический OFF105,344 с,
worker2 control-v2 и worker3 r5-v1. Новый r5-bookkeeping-v1 сюда пока не включён:
его единственный прогон отдельно поручён Luna решением ROOT. Для этого отчёта
не запускались движок, численные тесты, приложение или новые сборки.

**Доказанный результат:** старый native415d с общей текущей обвязкой остаётся
быстрым —114,734 с. Timed R5 требует462,079 с, причём396,607 с занимает First;
внутри подготовки правил измерено372,930 с inclusive replay. Исторические105 с
не восстановлены как точная среда Python/env. R1 frozen policy действительно
доходит до Theory и меняет допустимость неполных моделей. Какую часть времени
занимает выбрасываемая диагностика R1, пока не измерено.

## 1. Что сравниваем

| Наблюдение | Исторический OFF,25 октября | worker2 control-v2 | worker3 r5-v1 |
| --- | --- | --- | --- |
| Native |415d995c…;403 файла,a5262483…|Тот же сохранённый415d|R5 base444,48f643c2… + coarse timing;449 файлов,b0b5d32d…; бинарник506cd4b7…|
| Python/harness |Рецепт известен; полный снимок и ambient env неизвестны|Общие pinned394/111 файла,e3d71c21…/218d189c…|Те же pinned394/111 файла|
| Обвязка |Исторический corpus→button gate→реальная Qt-кнопка|Изолированная копия, общий t1_control,c9e893a3…|Тот же t1_control без изменения байтов + тонкий timing wrapper|
| Producer |f1e076b7…, mechanic-compiler25Oct|Тот же артефакт|Тот же артефакт|
| R1 frozen |В415d этой реализации нет|Нет; experiment flags очищены|GTT_R1_SINGLE_NEUTRAL=1 включает shared frozen policy|
| Прочие flags |Старый рецепт не задаёт R3/R4; полный parent env неизвестен|R1/R3/R4/C4/whole flags очищены|Точные9 флагов T1v2, проверены на validate и optimize|

Полные identities и восстановление403/403 исходников находятся в
[историческом паспорте](../../../../GenshinTeamsTracker/docs/optimizer-evidence/2026-10-27-engineering-efficiency/t1-run-v2/RECOVERED_FAST_THEORY.md).
Это восстановление native, а не полного исторического Python/dependency/env.
Современный control — новая контрольная точка, а не переименование старого
прогона. Между историей и control +9,390 с; одного запуска недостаточно, чтобы
приписать эту разницу Python, расположению файлов или случайной нагрузке.

В r5-v1 применены R3_PARALLEL_CAPTURE/TYPED_CANONICAL/ADJOINT_REUSE/
PROGRAM_IDENTITY/OPERATION_SWITCH и R4_FAST_COUNTERS/OWNED_DIGEST/TYPED_PANEL
(все с префиксом GTT_, значение1), плюс R1_SINGLE_NEUTRAL=1. Здесь не пересказываются
оптимизации структур данных прежнего этапа: flags фиксируют конфигурацию,
но сами по себе не объясняют измеренные372 с.

Обе новые копии используют один read-only MAIN Python3.11.5/PySide6.11.0,
Qt offscreen, наблюдаемый CPU budget16. В фактических numerical launches
GOMAXPROCS/GOMEMLIMIT/GOGC/GODEBUG не заданы; GOFLAGS также отсутствует в ambient.
Build-only ограничения2 потока/2GiB не переносились в численную команду.
Producer перескопирован с проверкой доверия и новой привязкой к пути копии;
разные binding/request hashes нельзя выдавать за разные gameplay-входы или
за побайтово одинаковый request. Hash joins проверены внутри каждого прогона.

## 2. Что осталось одинаковым

Chasca/Furina/Bennett/Ororon, исходные профили, config и rotation; snapshot
604 артефакта /597 eligible /39 equipped. Это источник входов, а не перебор
600 принадлежащих игроку предметов: Theory передаёт0 wire artifacts и строит
виртуальные легальные наборы для4 wearers, по45 roll units, четвертная сетка,
обычный полный none/2p/4p/2+2 domain. Seed panel742031889/742031890.

Normal infinite-energy Theory; result options{}; настоящий cache OFF. Отключены
дисковые mechanic caches, но in-process reuse сохраняется. Lifetime максимум7
обычных кандидатов, включая2 response-reserved; ordinary finalists n500,
unseeded. Общий support producer сохраняет лимит66 n1 calls/180 с; это лимит,
а не фактически потраченное время. В Theory не введён AllSets n100 staged policy.

Product timeout0. Положительный harness sentinel1 нормализуется до0; внешний
watchdog1200 с не является сроком получения результата. Современная проверка
смотрит окончательный session request после нормализации; прежняя ранняя проверка
могла остановить wrapper ещё до native. Защитный Qt callback и обработка case=None
меняют надёжность экспорта/ошибок, а не бюджет поиска.

Контроль использует существующий button harness. Изолированные appdata/temp,
копия snapshot/runtime и минимальный shim только для ENGINE_ID позволяют
перенести pinned приложение без импорта постороннего исторического build-графа;
реальные trust/path/hash проверки сохранены. В r5-v1 добавлены только coarse
scopes, чтение существующих Stats и экспорт фаз до удаления scratch.

## 3. Порядок от кнопки до Finish

1. AppShell-кнопка готовит/валидирует Theory request и formula inputs.
2. Native загружает source catalog/request, запускает progress clock;
   далее neutral context, двухseed capture, модель, config/world и отдельный
   response-world fork. Catalog/request preamble предшествует coarse clock.
3. Original ResolveMechanics/binding, затем First: starts, один catalog pass,
   refinement, absorb и checkpoint fork. Deep не продолжается.
4. OfferSearch, затем OfferResponseProposals с support stat-response probes.
   Они выполняются до ordinary verification; это отдельная работа.
5. Archive.Verify публикует ещё НЕ проверенный finalist event перед запуском
   ordinary batch. Поэтому429 с у R5 — накопленное время до batch, а не
   отдельная компиляция, чистый поиск или длительность n500-симуляций.
6. После ordinary-verified first_light GUI получает допустимый snapshot;
   harness нажимает обычную Finish. В обоих новых прогонах на этой границе
   уже2 проверенных кандидата, publication_version4, snapshot_version1.
   Затем finished_early и joined worker. Это первый usable результат,
   не exhaustive convergence и не тест по истечении короткого таймера.

## 4. Измеренные результаты и работа

| Метрика | История | control-v2 | r5-v1 |
| --- | ---: | ---: | ---: |
| Кнопка→terminal,с |105,344|114,734|462,079|
| Первый verified GUI snapshot от кнопки,с |97,532|103,891|459,594|
| Adapter prepare / formula inputs,с |4,531 /5,860|5,797 /7,391|5,109 /6,375|
| Adapter optimizer process,с |94,156|100,484|449,906|
| Первый unverified finalist, UI offset,с |70,344|72,172|429,407|
| Verified searching, тот же UI clock,с |81,844|84,954|442,532|
| Leading formula |197302,481673|197302,481673|196428,786211|
| Ordinary DPS / SE,n500 |199053,697 /141,941|199023,030 /153,865|198293,889 /150,230|

UI offsets начинаются от первого progress event и не равны button time или
длительности фазы. R5 медленнее control на347,345 с; почти вся разница видна
уже до finalist batch. Formula control точно совпала с историей, R5 — с
неинструментированным T1 (461,797 с). Разница ordinary DPS сама по себе не
доказывает качество алгоритма: unseeded измерения и достигнутые кандидаты различны.

В обоих новых прогонах ровно2 capture requests,52 stat-response result files,
2 ordinary n500 results. Исторический экспорт не содержит полного счётчика probes;
его нельзя задним числом объявлять измеренным. Одинаковые современные counts
исключают объяснение только увеличением числа симуляций, но не доказывают
одинаковую длительность каждой симуляции.

| First-pass work | control-v2 | r5-v1 |
| --- | ---: | ---: |
| Found families / tuples / unavailable |447 /10534 /476|452 /11010 /0|
| Catalog passes / sweeps / deep bundles |1 /8 /0|1 /8 /0|
| Formula / gradient evaluations |90220 /21402|111890 /21460|
| Allocation attempts |1341|1356|
| Independent / transferred starts |658 /683|666 /690|
| Publication refinements / pair candidates |2 /528|2 /528|

В истории эти подробные work counters не сохранены; значения control нельзя
подменять историческими. Сумма found+unavailable11010 совпадает, но полного
старого/нового tuple-key join нет: идентичность каждой строки не доказана.

## 5. Фазы r5-v1 и правила сложения

| Coarse scope | Старт от native clock,с | Wall,с |
| --- | ---: | ---: |
| context_setup |0,000000|0,683312|
| capture |0,683312|8,354755|
| model |9,038068|0,100326|
| config_world |9,138394|0,064542|
| response_world_fork |9,202935|0 в разрешении часов|
| initial_resolve_binding |9,211493|0,773798|
| First |9,985292|396,606654|
| ↳ checkpoint_fork, внутри First |406,493934|0,069976|
| OfferSearch |406,591945|11,706204|
| OfferResponse |418,298149|10,225756|
| ↳ support_probes, внутри OfferResponse |418,512547|9,930071|
| Verify |428,523905|13,999735|

Вложенные строки повторно не складываются. Collector elapsed444,547637 с
не равен462,079 с кнопки: clocks имеют разные начала/концы; gaps, preamble,
Finish/finalization не распределены выдуманными фазами. Для control и истории
такого native breakdown нет; это не парное вычитание replay time.

Main model после original resolve + First: RuleSeconds374,185143;
внутри него Preparation.ReplaySeconds372,929676; BindSeconds11,231044,
ViewSeconds0,963583. Начальные counters были0. Эти Stats вложены в содержащую
работу и не прибавляются к First. Response fork имеет свой ReplaySeconds0,155932;
это не ещё одна копия372 с. Schema/dropped0/все12 spans проверены квитанцией.

## 6. R1 frozen: доказанная цепочка и предел вывода

Shared NeutralModel constructor видит GTT_R1_SINGLE_NEUTRAL=1 и включает
EnableR1FrozenResiduals также для Theory. R1 задумывался для AllSets, но флаг
не разделял эти входы. Неполные symbolic effects теперь могут получить concrete
EvaluatePackages replay; r1FreezeConcrete сохраняет observed anchor либо
неизвестный source slot как reference guide, uncertainty и r1Frozen, очищая
boundaries. Модель может продолжить binding/family/allocation вместо unavailable.
Это доказанное изменение политики; Theory не имеет собственного recapture fallback.

Complete frozen output при этом исключён из композиционного reuse через
`complete && !r1Frozen && tracked footprint`. Cache hit компонента может означать
попадание в непригодный для композиции компонент, за которым следует full joint
replay. Сам joint replay интерпретирует сохранённые rules в памяти; это не новая
gcsim capture. Не доказано, что все3102 full fallbacks имеют только frozen-причину:
другие guards остаются. ForkTheory сохраняет component/group caches; measured
checkpoint copy0,070 с не объясняет372 с. Model dispatch hits11010 из22020 requests
показывают reuse второго обращения к tuple, program hits10557/misses453 также
не позволяют объявлять весь reuse потерянным.

Preparation:3516 Replays,3111 JointReplays,3102 FullFallbacks.
ReplaySeconds увеличивается только в compilePackagesJoint и включает вложенный
concrete replay; прямой EvaluatePackages не имеет второго независимого joint timer.
R1FallbackReplays3140 — другой счётчик вызовов после начальной проверки dimensions.
AnchorPorts26076661 + ReferencePorts4677622 =30754283 повторных port events;
из них30754155 записей пропущено,128 сохранено. Это не число tuple или симуляций.

В старой функции R1FrozenPort и ruleChoicesKey строятся до проверки лимита128.
**Гипотеза:** значимая доля372,930 с — это работа над выбрасываемыми diagnostic
records/ключами. Подготовленный bookkeeping-вариант меняет только её; parity
и lazy-key тесты прошли. До результата Luna нельзя объявлять ни выигрыш,
ни численную эквивалентность нового прогона. FrozenOFF не реализован.
Подробная [привязка к исходникам](r5-bookkeeping-v1/DIAGNOSIS.md) отделена
от measured result и не подменяет фазовый замер.

## 7. Сохранность и закрытие этого отчёта

Квитанции обоих завершённых прогонов: success, worker_thread_joined,
job_removed, main_protected_after_match, package_retained=true. В control сейчас
0 job-*; raw scratch r5-v1 удалён по его квитанции. Scratch нового
Luna-прогона не трогали и не объявляем остатком старого теста.

При подготовке отчёта read-only проверены4 защищённых MAIN файла (active engine,
artifact DB, profile registry, optimizer binary): hashes совпадают с обеими
сохранёнными квитанциями. Consumer и все pinned nonbinary файлы worker2 baseline
совпадают; сохранённый worker3 timed baseline.exe соответствует506cd4b7…,
его pinned nonbinary файлы также совпадают. Временное переключение canonical
worker3 binary принадлежит новому Luna-прогону; в него не вмешивались.
Completed JSON evidence control-v2/r5-v1 совпадает с HEAD по содержимому,
tracked diff этих evidence отсутствует. Различия LF/CRLF не считаются изменением
JSON; новый bookkeeping registry не входит в этот baseline-check.

Для этого этапа меняется только COMPARISON_RU.md. Нет установки, правки алгоритма,
переноса в MAIN/worker2 или удаления retained apps. ROOT отдельно обновит current
handoffs/shared queue и добавит новый численный итог после Luna.

Основные доказательства: [control-v2 RESULT](../../../../worker2%20GTT/docs/optimizer-evidence/2026-10-28-theory-control/control-v2/RESULT.md),
[r5-v1 RESULT](r5-v1/RESULT.md), [phases.json](r5-v1/phases.json),
[off.json](r5-v1/off.json), [observations](r5-v1/observations.json),
[source/delta identities](r5-v1/source.json),
[T1 historical forensics](../../../../GenshinTeamsTracker/docs/optimizer-evidence/2026-10-27-engineering-efficiency/t1-run-v2/FORENSIC_429.md).

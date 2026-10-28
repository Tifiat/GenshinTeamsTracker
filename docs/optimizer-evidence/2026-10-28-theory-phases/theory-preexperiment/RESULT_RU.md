# Подготовительная диагностика завершена — отчёт и STOP

28 октября2026. Luna выполнила один collect: **2 captures,15 cases×2 passes,
0 search/ordinary calls**. MAIN только свёл сохранённые события и проверил
custody. [Машинная сводка](summary.json), полный events.json и исходный
source/delta сохраняют проверяемые данные; новых запусков/исправлений нет.

## World/order1 и Clam2

| Seed | World present/Complete | States | Первый Order | States с Facts/Custom | State при order1 |
| --- | --- | ---: | ---: | ---: | --- |
|742031889|true/true|547|3|547/547|index−1, нет Facts/Custom|
|742031890|true/true|526|3|526/526|index−1, нет Facts/Custom|

Custom не потерян exporter-ом в этой pair: поле есть во всех captured states.
Consumer worldAt(...,1) не находит предшествующий state и оставляет h.facts=nil.
Это отличается от отсутствия Fields[Custom] в существующих Facts. Безопасность
использования более позднего state3 как раннего состояния здесь не проверялась.

Изолированный Clam2 Bennett в symbolic и concrete обоих seeds падает в Init:
`neutral resource facts are unobserved: Custom`, unobserved_runtime_fact,
rule_resources.go:23, frame0/order0, caller_owner2. owner_known=false: owner0
в этом cause нельзя считать владельцем. Producer Init безусловно обращается
к OHCActiveChar и для2p; heal/bubble subscription4p к этому failure не относится.
Event/query stage не исполняется. Нулевые init/replay wall у быстрых вызовов
могут быть разрешением часов, а не отсутствием работы.

Init abort оставляет весь member Value vector unknown (4942/4911 ports).
Concrete повторяет ту же раннюю ошибку, а не получает authoritative ответ.
Это counts портов, не4942 уникальных mechanics.

## Локальная ошибка затрагивает весь joint package

Derived контроль сохранил Chasca4Obsidian, Furina4Tenacity, Ororon4Scroll;
заменён только Bennett4Noblesse старым Night2+Clam2. Retained-leader case сам
по себе Frozen=false, все member query values known. Derived case — complete
только после R1, Frozen=true: **0 anchors,9853 reference ports**.

| Query owner | Reference seed889 | seed890 |
| --- | ---: | ---: |
|Chasca(index0)|2102|2090|
|Furina(index1)|1391|1386|
|Bennett(index2)|185|185|
|Ororon(index3)|1264|1250|
|Всего|4942|4911|

Reference coverage затронула все6 присутствующих query kinds: stat, attack,
heal_bonus, flat_event, reaction, resistance. Ошибка Init не ограничилась185
ports Bennett. Derived binding program совпал с empty-package program45277b74…,
а не leader3df815bd…. Это поведение uncertain guide, **не физический DPS** и
не доказательство истинной нулевой полезности трёх исправных сетов. Source slots
сохранены как reference; независимые set effects не доказаны нулевыми.

## Berserker4: другая стадия и локальная coverage

Первый проход; время — сумма двух seeds. Во всех строках Init завершается,
unknown_operation CurrentHPRatio возникает в Amount при attack queries.
Bound owner_known=true; неизвестные ports у других owners равны0.

| Wearer | Symbolic,с | Concrete,с | Unknown seed889/890 | Первый frame |
| --- | ---: | ---: | ---: | ---: |
|Bennett|0,012490|0,010643|54/54|285|
|Chasca|0,057099|0,031228|807/808|79|
|Furina|0,028425|0,021779|545/544|19|
|Ororon|0,027556|0,023407|516/510|91|

Concrete имеет те же неизвестные attack ports, что symbolic: API не поддержан
в обоих режимах. Это повтор event/query работы, а не повтор parsing failure.
Остальные known ports сохраняются; reference freeze локален отсутствующим
attack slots, в отличие от Clam Init abort. Production частота не измерена.

## Совпадающие результаты и второй проход

30 rows:15 distinct choice keys,9 diagnostic output digests,7 local binding
program IDs. Для всех15 cases pass1/pass2 совпали digest и program. Digest
включает diagnostics/provenance и не является arithmetic-family ID. Все8 Clam
cases связались с neutral program; один имеет другой diagnostic digest/owner
origin. Это наблюдение об alias, не автоматическое разрешение reuse.

Во втором проходе empty/leader/исправный изолированный2p component не делали
joint replay; leader:4 joint calls→0. Каждый из8 Clam и4 Berserker cases снова
выполнил1 joint,2 symbolic member replay,2 concrete member replay,1 freeze.
Всего20 component rejection rows: tracked=true, Group=false; соответствующие
outputs complete+frozen, следовательно в этих наблюдениях мешает frozen guard,
а не отсутствие footprint. Binding cache может вернуть известную программу
после повторной подготовки — два уровня reuse нельзя смешивать.

| Подвыборка | Preparation pass1,с | pass2,с |
| --- | ---: | ---: |
|6 recovered old tuples|0,342527|0,154782|
|4 Berserker cases|0,275679|0,239087|
|Derived leader-three+old pair|0,025471|0,027682|

Direct CompilePackagesSparse обходит NeutralModel dispatch. Pass2 — **не частота
повторов production**, не15 новых найденных Theory tuples и не прогноз
экономии на11010 tuples/452 families или всех313,493 с.

## Вложенные таймеры

| Граница,30 cases | Сумма,с | Область |
| --- | ---: | --- |
|Case preparation|1,330387|Joint и часть collector work внутри|
|Joint|1,311829|Внутри preparation|
|Symbolic member replay|0,541715|Внутри joint|
|Outer r1Freeze|0,504088|Внутри joint, включает concrete|
|↳ Concrete member replay|0,204837|Внутри outer freeze|
|↳ Direct r1FreezeConcrete|0,110650|После concrete, внутри outer freeze|
|↳ Freeze observer aggregation|0,178634|Внутри outer freeze|
|Binding|0,047553|Отдельно после preparation, без search view/evaluation|

Replay Init0,114478 с и event/query0,595134 с вложены в symbolic+concrete0,746552 с;
разница включает setup/world/order/glue и разрешение часов. Direct
r1FreezeConcrete включает constants/vector, uncertainty/records/counters и
coverage observer; это не pure bookkeeping. Остаток outer freeze после
concrete/observer0,120617 с также не чистая диагностика. ObserverSeconds0,918057
смешивает агрегацию внутри preparation и output digest снаружи: его нельзя
целиком прибавить/вычесть из1,330387. Collect/capture/model total wall не сохранён
как benchmark boundary; сумма строк не время кнопки. Доли313 с не установлены.

## Overflow и полнота

Dropped0: все30 case,128 replay,38 joint,26 freeze,20 rejection rows сохранены.
Group_overflow337372 **целиком** равен UnknownPorts минус сумму retained
unknown-detail counts. Проверка даёт0 omitted mechanic-cause observations.

Cap8 касается detail keys owner/kind/stat/mode/reason на replay. Каждое событие
за пределом8 снова увеличивает overflow, даже для повторно пропущенного ключа.
337372 — omitted detail observations, не уникальные группы/ошибки, не потеря
capture/случаев. Полные Coverage Known/Unknown counts проверены против Ports;
first causes сохранены. У Init abort per-query Boundary может быть пустым:
общий replay Boundary содержит Custom failure, а Values остались default unknown.
Полный список omitted detail keys восстановить нельзя.

## Custody и границы вывода

Проверены6 runner/input/binary pins, source delta,15×2 IDs, request SHA (тот же
ddb0bf6e… из R5), source SHA, все baseline pins/control bytes и4 MAIN protected
hashes. Managed jobs0; job_removed/baseline_unchanged/main_protected_after_match
true.8 private gzip archives:2081216 compressed /54506643 raw bytes; stored/raw
hashes совпали. Они остаются под прежними owner/expiry/release для этого data
этапа; raw managed scratch удалён. В Git нет captures, DB или бинарников.
Failed preparation logs сохранены. Handoff checker по worker3 scope — PASS.

Неизвестны полный old476→new join, production частоты/стоимость типов failure
в313 с, влияние на starts/incumbent и смену rolls, ordinary quality/физическая
чувствительность.41 annotations лидера — общий model context, не число новых
failure events. Данные уточняют frozen/reuse/uncertainty границы, но не тестируют
staged finalists и не разрешают менять inherited/absent/proposed-only статусы.
Решения и предлагаемые эксперименты — ROOT после обсуждения с человеком.
**STOP: никаких исправлений поведения, captures/полных прогонов/установки.**

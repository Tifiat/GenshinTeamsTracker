# Какие данные есть до выбора следующего эксперимента

28 октября 2026. Только сохранённые данные, точечный review pinned source и
подготовка instrumentation. Численная диагностика этим этапом не запускалась.
ROOT сначала рассматривает будущие данные с человеком; новой политики,
алгоритма, полного comparison run или установки без последующего GO нет.

## Что восстановлено предметно

В историческом OFF и control-v2 одинаковые reason groups:

| Источник observation | Причина | Количество observations | Что это доказывает |
| --- | --- | ---: | --- |
| berserker | unknown_operation, CurrentHPRatio |1016|Достигнута неподдержанная runtime host operation; не ошибка статического parsing cache|
| oceanhuedclam | unobserved_runtime_fact, rule_resources.go:23 |8|Сработала ветка отсутствия всего facts, а не отсутствующего Custom внутри существующих facts|

Это1024 diagnostic observations, не1024 уникальных механики/tuple, не время
и не полная частота причин476 unavailable. Bound-boundary exporter имеет
source_available=false. В новом frozen-прогоне reason groups пусты: это
не доказательство исчезновения исходных причин или полноценной поддержки.

В off-details/native-causes.json исторического прогона сохранился4096-символьный
фрагмент native output. Из него JSON decoder восстановил **6 полных rows**
с tuple_key/packages/reasons. Все6 имеют причину
`neutral resource facts are unobserved: Custom`. Например:
`nightoftheskysunveiling:2+oceanhuedclam:2|none|none|none`.
Часть строк — compound packages с остальными тремя wearers; это материал
для узкого replay, но не репрезентативная выборка всей области поиска.
Полные476 keys/reasons, текущие11010 tuple-resolution rows и их join не сохранены.
Нельзя приписывать все476 одному найденному сету или восстанавливать пропущенные
строки по совпавшей сумме10534+476=11010. Исходный fragment hash и6 rows —
в [saved_inventory.json](saved_inventory.json).

У лидеров control и нового R5 одинаковые4 set packages и41 uncertainty codes;
список41 совпадает точно, отдельных r1_* нет. Формулы и rolls отличаются.
Эти41 annotations описывают также унаследованные ограничения captured arithmetic;
они не являются41 новыми R1 failure events. Отсутствие r1_* у двух финальных
aliases не доказывает отсутствия frozen guides внутри всего поиска. Lineage
начала каждого start, смены incumbent и вклада конкретных uncertain tuples
в их выбор не сохранён; причинную связь со сменой rolls заявить нельзя.

## Pinned source: два разных механизма

Consumer review относится к восстановленному R5+bookkeeping map8848afb8…,
а не к dirty native. Producer sources читаются из собственной pinned копии
worker3. source_proof.json проверяет байты выбранных runtime files против
set-sources.json items/rule_repository и SHA, связанных с f1e producer/catalog.

**Clam2: initialization facts.** В producer
internal/artifacts/oceanhuedclam/oceanhuedclam.go:Init безусловно записывает
`s.core.Flags.Custom["OHCActiveChar"]=-1`. Это выполняется и для2p.
Heal listener/bubble path находится отдельно под count>=4. Следовательно,
ошибка сохранённого clam2 не обосновывает гипотезу о новых heal/bubble events,
новой трассе или конкретном персонаже.

Consumer rule_resources.go:21–29 различает facts==nil (строка23, «facts are
unobserved») и отсутствующий Fields[name] (строка27, «fact is absent»).
resourceField:49–58 при core.Flags.Custom отмечает core_flags read/write и
сначала запрашивает fact("Custom"). Это host seam для observed state,
не unsupported parsing и не новая игровая механика.

rule_replay.go до NewSet/Init вызывает worldAt(neutral.World,1).
worldAt:393–404 сбрасывает h.facts=nil и выбирает последний state с Order<=1;
если такого state нет, возвращается с nil. При найденном state :430–433
передаёт state.Facts, включая nil; cache-hit branches также восстанавливают
facts. Producer pkg/core/gtt_neutral_resources.go **экспортирует Custom**;
pkg/gtttrace/neutral_world.go хранит Facts при CaptureNeutralWorldAt(order).
Из сохранённого reason нельзя заключить, что exporter вообще потерял поле.
Нужно различить отсутствие state на initialization order1 и nil Facts в выбранном
state. Текущая matching capture pair удалена; это конкретный недостающий факт.

**Berserker4: deferred query operation.** В producer >=4 регистрирует AttackMod,
Amount которого обращается к char.CurrentHPRatio(). >=2 stat mod этого вызова
не содержит. Consumer char host-call switch не реализует CurrentHPRatio;
в материализованном mechanic_operations нет descriptor этой операции, и
resolveBoundSourceMethod не объявляет её accepted host seam. Поэтому callback
при query может завершиться unknown operation. Это отличается от failure в
Init и требует source/event/owner привязки. Добавлять guessed HP ratio или
новую реализацию в этом этапе не разрешено.

## Что значит «дорогой повтор» — и чего пока не знаем

По r5-bookkeeping-v1 остаётся313,493 с inclusive joint replay,3140 R1 concrete
fallback calls и3102 composition full fallbacks; эти единицы различны.
Около30,75 млн anchor/reference port events многократно посещают одни и те же
ports; это не количество уникальных source rules. Стоимость по отдельным
set/rule/operation/init/event/freeze не была экспортирована. Компонент может
попасть в cache и оставаться unusable; frozen output намеренно не composable.
Но все3102 нельзя без событий приписать именно frozen rejection.

Узкий replay должен проверить: повторяется ли дешёвый initialization failure,
дорог ли последующий concrete/event replay, и превращается ли **весь joint
package** в frozen guide при локальном Clam Init failure. Для этого подготовлен
derived case: package владельца первого old row заменён его же Clam2+pair,
остальные3 packages retained leader сохранены. Known/unknown coverage при
symbolic/concrete replay и frozen anchor/reference observations группируются
по seed/owner/query kind. Это не sensitivity/quality тест.

Условная цепочка уже видна в source: initialization error возвращает весь
RuleReplay member до query loop, оставляя Values unknown; compilePackagesJoint
при replay.Boundary пропускает весь member, а не только ports одного сета.
Если concrete replay того же joint также падает в Init, r1FreezeConcrete может
сохранить reference slots всех недостающих ports, включая других wearers.
Это source-backed условие, не измеренная частота production и не оценка DPS.
Derived контроль проверит, выполняется ли именно это условие на текущем panel.

## Что недоступно без новых входов

Сохранённая architecture-inputs-v1 pair от15 октября имеет другой producer
manifest/config и **не содержит mechanic-invocation extension**. Она пригодна
для прежних codec-cost проверок, но не заменяет текущий f1e neutral tape.
Нельзя replay-измерением на ней объяснять313 с нынешнего прогона.

Минимальная необходимость — **2 neutral captures** текущих seeds на том же
реальном сохранённом prepared input, в одном owned job. После них — только
<=16 явно заданных preparation cases,2 passes, без поиска, ordinary finalists
и stat-response probes. Captures сжимаются в private owned variant с hashes,
owner/expiry/release, чтобы несколько измерений этого этапа могли использовать
один panel; raw job очищается. Ни capture, ни collect не запускались MAIN.
Готовая команда/границы — в README.md; запуск выполняет только Luna после review ROOT.

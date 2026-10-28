# R3: офлайн-допуск исходников и runner

Все измерения ниже выполнены без engine, полного поиска и установки. Полного
результата R3 по времени кнопки/DPS пока нет. ROOT выбрал пять модулей: parallel2
capture, typed JSON canonical, adjoint scratch, reverse program identity и
operation switch. Формула, порядок FP, поиск, 77 промежуточных проверок, 3×3,
семена и R2 n100/n500/four-SE не менялись.

## Восстановление и исходники

`r3_recovery.py` + [дельта](r2-source-delta-v1.patch) +
[манифест](r2-source-delta-v1.json) восстанавливают R2 из Git
`6f1cab8389bc63e53297a91a7b14b743009ebd96`: 411 файлов, карта
`5091c1ca4365c894b93db7685dc3e0d6905bdb226c1772b8cd06ab1fd0c64d14`.
211 файлов дельты включают 153 отсутствовавших в baseline; размер 1 839 394 байта,
SHA256 `c1d8b94eefa97258f0e01c81bf13b12557fff1a672e3cb84f44521ce7e7a2c34`.
Восстановление независимо подтверждено ROOT. Старые 682 helper-зависимости не
требуются. Генерируемый zip остаётся локальным ускорителем, не Git-зависимостью.
Это самостоятельное восстановление нативного модуля; Python button/material
и producer сохраняют прежние отдельные привязки.

R3 overlay: 428 файлов, 26 отличающихся от R2, карта
`3401a0e41238cc6fb85b9f74121f89e2c7cd062c6aebb2a717fc1969a9db9672`.
Поимённая карта, пять флагов, hashes runner/recovery/source и команды закреплены
в [квитанции предлагаемой конфигурации](proposed-source-v1.json).

## Проверки и измерения

- [Focused a1](focused-v1-a1.json) остановился до Go: несовпадение LF/CRLF в
  exact replacement. Исправлен только поиск точного варианта перевода строк.
  [Focused a2](focused-v1-a2.json): 17 проверок PASS. Они включают schema mirror,
  differential acceptance/errors, canonical bytes/SHA, null/missing/unknown,
  строки/числа/pointers, FP gradient и владение returned gradient/scratch,
  ограничение двух capture, cancel/join/identity, eviction и foreign pointers.
- [Первые saved-data измерения](saved-cost-v1-a1.json) сохранены полностью.
  На seed889 готовый путь регрессировал 3586→3921 мс, на seed890 улучшился
  2872→2418 мс. CPU profile и lifetime этой серии не позволяют надёжно отделить
  причины. Этот результат не переписан и не принят по среднему.
- По отдельному решению ROOT выполнен один
  [уточняющий ABBA](saved-ready-abba-v2-a1.json), по четыре arm на каждое семя,
  profiling OFF. Готовый путь: среднее 2910→2209 мс для seed889 и 2935→2140 мс
  для seed890; каждый typed arm быстрее обоих control своего семени. Средний
  process CPU: 3219→2422 и 3242→2328 мс. Выделение памяти ~759→574 и ~755→572 МБ;
  GC: control 14–17, typed 12–13. Ready graph/actor score совпадает побитово во
  всех восьми arm. Ready retained ~65/64 МБ сопоставим; это Go heap, не peak/RSS.
  Системная внешняя загрузка не измерялась; конкретная причина первой регрессии
  не доказана. ROOT принял typed модуль, дальнейших codec-рядов нет.
- Timed ready включает read, настоящий DecodeSeedMember/validation, sidecar
  decode/binding, product member digest и CompileSeedMember. Дополнительный
  fixture sidecar hash вынесен из wall/CPU/alloc. Экспорт engine и gameplay не
  измерялись этим replay. Байты JSON/wire не менялись. Старые real payload
  Часки имеют другой source/context и не содержат mechanic_invocations: их
  время не выдаётся за стоимость нынешнего f1e/R3. Canonical codec retained
  из первой серии удерживает первый member ради parity и не доказывает равный
  lifetime; для этого используется исправленный ready benchmark.
- [Whitelist gate](validator-v1-a1.json): 1944 differential случая для обоих
  положений переключателя с точными ошибками PASS. Один проход по уже
  декодированным узлам каждого реального seed: 268→180 и 235→164 мс,
  ~56→15,6 и ~55,8→15,5 МБ выделений. Один constant node: frozen/disabled 12,
  switch 9 allocations. Сохранены все девять операций и порядок отказов.
- Adjoint: 32 вызова на сохранённой специализации Bennett (261/263 узла),
  87 072→13 344 байта выделений, на 32 allocations меньше; дополнительный
  owner buffer 2088/2104 байта. Wall 0/менее миллисекунды ниже разрешения
  таймера: процента ускорения нет. Это не граф R2 целиком. Return gradient
  остаётся отдельным, копии/ForkTheory не разделяют adjoints.
- Reverse index сохраняет только уже удержанные программы, их прежние
  exact keys, лимиты и eviction. Нет новой symbolic-group/persistent cache;
  отдельного обещания выигрыша времени для reverse lookup нет.
- `-race` недоступен: фиксированный Windows Go1.26.4, CGO=0, gcc отсутствует.
  Ничего не устанавливалось. ROOT принял это ограничение вместе с bounded
  concurrency/cancellation проверками и статической проверкой ownership.

CPU/alloc profiles первой серии указывают на generic SHA и IRNode.validate.
Хеши и crypto/toolchain не менялись. Включён только принятый operation switch;
прочие идеи остаются за пределами R3. Inclusive phase times не складываются.

## Runner и следующий gate

Три новые Python проверки runner PASS: production worker и оба native launcher
получают ровно пять флагов; сохраняются R2 inventory/options/seeds/cache OFF;
повторный OFF запрещён. Используются прежние R1 managed owner и R2 staged
export/formatter, finite ownership/watchdog, raw custody и protected-state checks.
R3 дополнительно требует одну parallel2 batch/два compact child/одну neutral model.

Подготовка, только после сохранения/проверки source+runner ROOT:

```powershell
.venv/Scripts/python.exe -B -m tools.experiments.gcsim.mvp_polish.r3_button --action prepare --output "C:/Users/user/Desktop/GenshinTeamsTracker/docs/optimizer-evidence/2026-10-27-engineering-efficiency/run-v1"
```

Она строит один consumer, копирует неизменённый f1e в owned store, проверяет
Go target и свежий настоящий 604/597/39 inventory относительно R2; engine calls=0.
Далее ROOT сверяет source/consumer/producer/flags/input/protected hashes и
допускает **один OFF существующему тестировщику**. MAIN OFF не выдаёт.

```powershell
.venv/Scripts/python.exe -B -m tools.experiments.gcsim.mvp_polish.r3_button --action off --output "C:/Users/user/Desktop/GenshinTeamsTracker/docs/optimizer-evidence/2026-10-27-engineering-efficiency/run-v1"
.venv/Scripts/python.exe -B -m tools.experiments.gcsim.mvp_polish.r3_button --action release --output "C:/Users/user/Desktop/GenshinTeamsTracker/docs/optimizer-evidence/2026-10-27-engineering-efficiency/run-v1"
```

После единственного результата: экспорт минимальных evidence, сравнение с R2,
release исходного owner, cleanup/protected/process checks, локальный commit и
STOP. Нет ON/warm/install/других команд/новых оптимизаций.

## R4 —28October: три принятых модуля и rejected frontier

Новый ограниченный этап от R3 source0596011/result0eb1aad. Математика, поиск,
77 промежуточных проверок,3×3, seeds, staged n100/n500/four-SE не менялись.
Повторная semantic validation сохранена: публичные member slices изменяемы,
простой безопасной immutable ownership границы нет. ROOT принял это исключение.

Приняты raw SHA reuse внутри owned runCompact; точная typed panel canonical
без generic DOM; фиксированные atomic counters. External byte-taking sidecar
entry всегда вычисляет свой SHA. Raw и canonical SHA не смешиваются. Invalid
Go UTF-8 panel уходит в старую generic-нормализацию; nil/empty/optional pointers,
MaxUint64 и отказы проверены. Счётчики сохраняют точные totals и лимит256имён,
включая насыщение/zero/wrap; старый disabled mutex fastpath тоже устранён.

[r4-focused-v1-a1](r4-focused-v1-a1.json):15 top checks PASS плюс invalid-input
subcases. [Saved costs](r4-saved-v1-a1.json) — один ограниченный проход без engine:
panel1355.530→323.675мс,467378040→99648480allocatedbytes,5655081→68allocations,
18 206 094 canonical bytes/hash одинаковые. Raw per-member2→1hash:196.875→98.357
и194.766→101.158мс;256→128allocatedbytes. Enabled375606Countcalls:15.199→5.619мс,
208bytes/1allocation в обоих вариантах; totals366624eval/8982gradient точные.
Disabled:8.130→1.620мс; это local call-cost, не обещание процента всей кнопки.
Контрольный canonical output удерживался для byte parity: времена не доказывают
равный GC lifetime; сравнение allocations и identity остаётся прямым.

Dirty frontier — полезный отрицательный результат. На исторических graphs2671/2638
source nodes,469/460ports,64вектора unchanged/disjoint/dense сократил Visited
170944→31399 и168832→30876 при тех же Rebuilt/Reused/output graphs/битовых scores.
Время17.289→17.054 и16.553→18.519мс,alloc+~112KB,index~80KB. Последний вариант
не ускорился. Контрольные64outputs удерживались ради parity при candidate pass,
так что GC lifetime тоже неодинаков. ROOT исключил модуль: нет сохранённого
репрезентативного R3neutral graph/векторов. Новых captures/синтетик/серий нет.
Историческое damage_nodes=0 — ошибка diagnostic чтения lazy-parent: правильные
значения2671/2638 следуют из control Visited/64. Старый JSON сохранён как есть.
Кандидат/тесты воспроизводимы через region_candidate=True только при новом допуске;
в production images отсутствуют. region_binding.go/theory_fork.go exact R3.

[Combined a1](r4-combined-v1-a1.json) прошёл все feature/verification packages;
единственный FAIL — product fixture искалась вне owned root из-за мелкого layout.
Исправлены только layout native/gcsim_optimizer и две публичные fixture внутри
job. [Cmd a2](r4-combined-cmd-v1-a2.json) PASS, native map идентичен a1; повторён
только этот пакет.3 runnerchecks PASS (worker, оба native env, inventory/oneOFF).
Saved-input tests в combined пропущены намеренно, их отдельная серия пройдена.
Race detector отсутствует при фиксированном WindowsCGO0/no-gcc; ROOT принял
bounded concurrency/lifecycle evidence без установки нового toolchain.

Готовая конфигурация:438файлов,map0f504808a6fd57fd3fae55403d15853bc6adaeb891583c32fabdc813535c9e83.
[Readiness/точные команды](r4-ready-v1.json) фиксируют source/harness,8flags
(5R3+3R4), исключение frontier, gate и policy. Пока0engine/0search/0consumerbuild,
ничего не установлено. Source milestone, затем разрешённая подготовка одного
managed owner; OFF выдаёт ROOT после проверки consumer/input/protected pins.


## R5 - bounded closure (28 October, before the admitted full run)

All six findings have a disposition. No gameplay, FP order, search/coverage,
77 intermediate checks or n100/n500 policy changed; no engine/search calls here.

1. **Fixed:** one read-only SQLite transaction freezes inventory and equipment;
   validation/hash runs once over owned rows. The independently supplied inventory
   API retains its old cross-transaction recheck. WAL mutation/virtual mapping/
   legality tests pass. First full config report becomes the existing common
   slot/mapping payload; final full report remains. Keeping common slot preparation
   preserves virtual overrides and identity/rotation validation without rewriting
   the character/config builder. Two full assemblies become one; no isolated
   real-config timing is claimed.
2. **Fixed/retained:** derive the requested binary SHA in the store-tree pass;
   stream that binary on one reused buffer, keep ordinary small-file reads.
   Tree and binary digest scopes remain distinct. Existing verified Go repository
   supplies later source text and go.mod; catalog and mutable cross-stage integrity
   checks remain. Full-tree extra SHA maps/caches or RAM mirrors were not added.
3. **Fixed/retained:** one uncertain-view scratch copy replaces two. Independent
   values/previous/error/adjoint storage and the zero-input preflight remain.
   Context.Replace/New remains: it validates/freezes complete caller inputs before
   the exact dispatch key exists. No new context cache or unchecked identity path.
4. **Fixed:** finite/Float64bits-change scanning fused on the reuse path; every
   input is checked before early reuse. Signed zero and R4 early-error scratch
   behavior remain; arithmetic errors still invalidate partially computed state.
5. **Fixed:** stderr retains eight 2048-character tails plus Finish-marker flags
   from the original last eight lines. Full owned file/progress/cancel lifecycle
   remains. Go binary SHA uses streaming for every required existing check.
6. **Fixed:** prospectively frozen 394-file product Python image, Git+readable delta,
   applies eight owned overlays without editing/staging dirty live product files.
   Private/generated directories are pruned before descent. Ordinary data/resource
   paths keep existing checks; they are not an executable-code sandbox. The 111
   non-R5 imported harness files have a separate Git+delta reconstruction; owned
   R5 helpers belong to the source milestone. Finite lazy harness route and actual
   sitecustomize/AppShell-definition startup are checked offline. Python/Qt/SQLite
   runtime identities and source pins are checked before/after numerical work.
   Historical R4 product Python identity is unknown and is not reconstructed here.

### Local costs and limits

- Saved full inventory604, input32e4a835: two transactions/hashes to one,
  instrumented1646.611 to1137.850ms. Four service-only virtual baselines; this is
  not a full config/button timing. Source envelope10058.542 to9878.905ms with
  tracing/read counters; identical envelope,117 fewer opens. These include probe
  overhead and use the prospective pre-R5 Python baseline.
- All-file streaming was rejected: instrumented6.785 to10.451s (v1), improved
  reused-buffer all-file variant6.759 to6.965s (v2). Keep both historical receipts
  and maps. Final binary-only hybrid, without profiler/read interception and with
  reversed order:4.361 versus4.437s, CPU4.344 versus4.359s; exact distinct digests.
  The76ms difference is not claimed as a stable gain. One55,406,080-byte duplicate
  binary read and its whole-file buffer are removed.
-64 uncertain scratch constructors on each saved fixture allocate1,392,640 to
 696,320bytes,512 to256allocations. Timer was below resolution; this proves
 allocation reduction only, not the cost of the retained zero preflight.
- Initial2048-call Evaluate samples were too short/mixed. One ROOT-admitted
 clarification used1,048,576calls per arm with equal bit checks and reversed
 fixture order:455.126 to439.621ms;460.278 to436.494ms. Bit/error parity passed;
 ROOT accepted the local3.4-5.2percent result, not a full-search speed claim.
- One existing55,406,080-byte producer SHA: Go allocations55,412,408 to34,064bytes;
 wall678.566 to647.781ms, local process CPU687.5 to656.25ms. One warm-order pair;
 every required check remains. Do not attribute the whole final outer-minus-inner
 timer to hashing. No full-run CPU/allocation/RSS claim.

### Checks and custody

Combined native gate:19 top-level PASS across the selected existing/new checks;
managed neutral fixture SKIP disclosed, allsets compiled with no matching test.
Actual artifact/gradient/mask/scratch/context/binary-mutation/finalist grouping
checks passed. Python10 focused checks plus targeted source/adapter/hybrid
checks passed. Runner source/bootstrap/late-import/mutation/one-OFF checks pass;
exact current receipts and commands are indexed by r5-ready-v1.json.
Initial native field/method-name compile failure and Python fixture writer-close/
bootstrap-order failures remain as separate receipts. No product defect is hidden
by those harness corrections. All local managed jobs were removed, protected
state stayed exact. Full Chasca OFF still requires final ROOT admission; no
installation, ON/warm, other team or repeat follows automatically.

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

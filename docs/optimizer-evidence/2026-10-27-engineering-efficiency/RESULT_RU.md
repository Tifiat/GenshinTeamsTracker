# R3: один полный прогон Часки — 27 октября 2026

Полный путь AppShell → worker → native → проверка финалистов → группированный результат завершился за **90,500 с** против **101,250 с** у R2: на **10,750 с / 10,62%** быстрее. Победила та же физическая сборка из 20 артефактов: **158226,929 DPS ±108,027 SE, n500**. У R2: 158310,460 ±101,969 SE, n500. Наблюдаемая разница −83,530 DPS / −0,0528%; формульная оценка победителя в обоих случаях 156969,251659.

Это один замер одной команды. Одинаковые семена и конфигурация при обычном многопоточном движке не доказывают тождественные или независимые RNG-выборки между запусками. Поэтому разница DPS не является доказательством изменения качества формулы, а выигрыш времени не является универсальной гарантией. Другие команды и HP/лечение Тигнари этим экспериментом не принимались.

## Что именно измерено

Один корректный полный Chasca All Sets OFF по [контракту](CONTRACT.md), с допуском ROOT в [ROOT_ADMISSION](run-v1/ROOT_ADMISSION.json), выполнен существующим тестировщиком. После паузы из-за квоты MAIN продолжил только экспорт и закрытие. Повторной успешной серии, ON/warm, установки и прогонов других команд нет.

Включены ровно пять инженерных изменений: два независимых seed capture одновременно; типизированная канонизация IRSeedMember JSON; внутренний owner-local adjoint buffer; прямой индекс уже сохранённой программы; switch вместо выделяемой для каждого IR-узла таблицы девяти операций. Wire/exporter и producer не менялись. Сохраняются FP-порядок, выражения, охват, бюджеты, 77 промежуточных проверок и n100/n500/four-SE.

Полный настоящий инвентарь: **604 артефакта, 597 пригодных, 39 сетов**, те же профиль, оружия/уровни/созвездия, ротация и target. Семена 742031889/742031890, обычная панель 3×3, cache OFF с прежним reuse внутри запуска. Inventory SHA, material/config/target и проверки профиля сохранены в [атрибуции](run-v1/off-attribution-v1.json). `registry_imported=false` сохранено как фактически наблюдённое поле.

## Сохранение результата и охвата

Все девять упорядоченных исходных финалистов совпали с R2 по assignment, formula DPS, source и config SHA. Полные gear, mains и substats каждой из девяти сборок тоже совпали. Все семантические строки search_work совпали после исключения wall timers и provenance context SHA. Победитель имеет assignment SHA `ebb3316762058f4fe1aac2e6efa976a5de6ac990bebda926b58a27182e6b6c66`, config SHA `19a7bc8cb20070ca2346101f6fec325fbeb15779eacf3cdf8f28e8dc721e3f4e`.

| Финалист | Formula DPS | R2 DPS ± SE | R3 DPS ± SE | Итерации R3 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 156969.252 | 158310.460 ±101.969 | 158226.929 ±108.027 | 500 |
| 2 | 148644.309 | 149998.135 ±312.375 | 149940.351 ±356.918 | 100 |
| 3 | 145247.145 | 147037.437 ±233.153 | 146542.445 ±255.877 | 100 |
| 4 | 154637.811 | 155788.705 ±198.646 | 155931.628 ±233.386 | 100 |
| 5 | 154633.286 | 155764.020 ±206.954 | 155808.572 ±227.240 | 100 |
| 6 | 154617.048 | 156351.719 ±224.285 | 156215.953 ±229.486 | 100 |
| 7 | 153368.878 | 155051.871 ±210.974 | 154636.503 ±217.944 | 100 |
| 8 | 153364.353 | 154503.632 ±225.141 | 154532.232 ±239.968 | 100 |
| 9 | 153348.116 | 154686.860 ±217.486 | 154847.356 ±197.043 | 100 |

Все девять получили pilot n100; только лидер получил новый полный n500. Итого 10 финальных вызовов / 1400 итераций, как у R2. Pilot-статистика лидера заменена n500, без склеивания выборок и без фиктивного n600. Глобальный `iterations=0` означает `per_candidate`; реальные n/SE сохранены у каждой строки. Сохранены 17 promotion/reconsideration решений. Four-SE — эвристика, не строгая граница риска.

Опубликованы восемь из девяти проверенных сборок по прежнему правилу группировки одиночных замен. Строка 3 — комбинированная замена двух вещей; она проверена, но не показана среди distance-one альтернатив. Это прежнее поведение R2, не потеря проверки.

Счётчики R2 и R3 совпадают: **87 ordinary = 24 adaptive n1 + 53 stat-response n1 + 9 pilot n100 + 1 подтверждение n500**; ещё два compact child, одна neutral model, ноль дополнительных context capture/C4 projections. Все 87 ordinary и оба compact завершились успешно. `artifact.evaluate_calls=366624`, `artifact.gradient_calls=8982`.

Два цикла сохранили 128 sampled refinements, по 32 на каждого актёра; CandidateSearchCalls 1639/2760 и reuse 61/439. `Processed=0` относится к Exhaustive-отчётам, а не отсутствию локального поиска. Есть семь завершающих стабилизационных отчётов. 24 adaptive samples и 131 event полностью сохранены в [off-details](run-v1/off-details.json).

## Время и его границы

| Граница | R2, с | R3, с |
| --- | ---: | ---: |
| Кнопка → терминальный результат | 101.250000 | 90.500000 |
| Native total | 85.563405 | 75.174306 |
| Search inclusive | 49.959410 | 42.453736 |
| Начальный capture + model, внутри search | 16.052439 | 9.819931 |
| Search за вычетом capture + model | 33.906971 | 32.633805 |
| Source preparation, вложенная фаза | 2.226465 | 2.205300 |
| Final staged outer | 23.729383 | 21.358005 |
| Сумма FullBuild inner двух стадий | 20.938042 | 18.690717 |
| Stat-response lane | 9.800477 | 9.271663 |
| Adaptive lane wall | 2.893463 | 2.936138 |

Сокращение search на 7,506 с включает **6,233 с** экономии внутри начального capture + model. Оставшийся search изменился 33,907→32,634 с, то есть примерно на 1,273 с. Нельзя называть все 7,506 с ускорением поиска после готовой формулы.

Новая граница parallel capture batch — **7,267883 с wall**. Сумма двух process timers — **9,023777 с**, двух decode timers — **3,755229 с**; они пересекаются между семенами и не складываются с wall batch. У R2 захваты шли последовательно: process sum 8,596347 с, decode sum 5,009778 с. ProcessMS включает запуск/симуляцию/exporter/завершение child; DecodeMS включает чтение JSON, strict canonical/semantic validation и sidecar binding. Отдельного production-timer только для exporter/encode нет.

Final staged outer изменился 23,729→21,358 с; FullBuild inner 20,938→18,691 с. Pilot n100 inner: 15,459→14,285 с, подтверждение n500 inner: 5,479→4,406 с. Разница outer−inner 2,791→2,667 с включает подготовку/binding/квитанции. Policy/число вызовов и движок не менялись: вклад финальных стадий в общий выигрыш — наблюдение между запусками, не отдельно доказанный эффект правок R3.

Финальные волны прежние: pilot 4×4 / 4×4 / 1×16, подтверждение 1×16. Rule 11,591→11,039 с и bind 3,867→3,667 с — другие вложенные виды search, их нельзя добавлять к outer time.

Непересекающиеся фазы клика R3: 5,204 с подготовка входов + 5,750 с formula inputs + 0,140 с preflight + 78,735 с optimizer process + 0,671 с вне adapter = **90,500 с**. Worker render 0,454 с входит в измеренный путь; fixture build 5,875 с и подготовительная сборка consumer не входят в button time.

## Владение трассами и предел сравнения

Проверены оба исходных R3 capture-request: config SHA совпадает с sidecar context/input-config SHA, семена точные, iterations=workers=1, energy override и effect inputs явные, raw member hash совпадает с sidecar. Наличие mechanic_invocations подтверждено. Nodes/channels: 89010/372 и 88553/366. Компактная квитанция seed/config/source/member/topology находится в attribution.

Provider context SHA включает EngineBinding и поэтому меняется при переносе owned engine. Подготовленный product config, target, расписание семян и выбранные final config SHA совпадают с R2. Сырые member hashes различаются; исходные R2 payload уже были штатно удалены, поэтому pairwise semantic equality этих двух captures доказать нельзя. Причину различия raw member bytes не выдаём за установленную только по relocation. Есть точное совпадение формульных результатов/поисковых строк и офлайн-паритета на сохранённых real inputs; это отдельный уровень свидетельств.

## Офлайн-свидетельства и память

[Офлайн-квитанция](OFFLINE_RU.md) сохраняет и первую аномальную серию, и единственный разрешённый уточняющий ABBA. Первая регрессия seed889 не воспроизвелась без profiling при ABBA; её точная причина не доказана. Уточняющий ready-path на исторических real IR: среднее 2910→2209 и 2935→2140 мс, allocations около 759→574 и 755→572 МБ; ready retained heap около 65/64 МБ сопоставим. Byte identity/валидация и побитовая оценка графа совпали.

Исторический sidecar не имел mechanic_invocations и имел иной source/context. Поэтому эти allocation/CPU цифры не выдаются за full R3 memory profile. В полном R3 CPU/heap/RSS/alloc instrumentation не включалась, counter-поля AllocBytes/CPUNS=0 означают отсутствие замера. Peak памяти и отдельный выигрыш каждого из пяти модулей не измерены.

Adjoint локально сократил 32 allocations и 87072→13344 байт за 32 вызова при owner buffer 2088/2104 байта; wall ниже разрешения таймера, процента ускорения нет. Operation switch: 1944 error-parity случая PASS, один проход по реальным nodes 268→180 и 235→164 мс, примерно на 40 МБ меньше allocations/pass. Reverse index сохраняет прежние ключи/лимиты/eviction; новых group/persistent caches нет.

Focused a1 остановился до Go из-за LF/CRLF seam, a2 прошёл 17 проверок. Runner прошёл 3 проверки, включая действительные worker/launcher flags и запрет второго OFF. `-race` недоступен без отсутствующего C-компилятора при фиксированном Windows Go; ограничение принято ROOT, C-компилятор/обновление toolchain не устанавливались. Дополнительные проверки после полного прогона не запускались.

## Победившая сборка

Порядок слотов во всех assignment: flower, plume, sands, goblet, circlet. Все вещи уровня 20, редкость 5. Mains/substats ниже — точные сохранённые ключи и числа; процентные значения хранятся долями.

| Актёр | Четырёхчастный бонус | ID пяти вещей |
| --- | --- | --- |
| bennett | noblesseoblige×4 | 36, 1413, 1426, 140, 203 |
| chasca | obsidiancodex×4 | 1571, 81, 92, 88, 1615 |
| furina | tenacityofthemillelith×4 | 1395, 1598, 1466, 1563, 1614 |
| ororon | scrolloftheheroofcindercity×4 | 1616, 91, 241, 1586, 119 |

| Актёр / слот / ID | Сет вещи | Main | Substats |
| --- | --- | --- | --- |
| bennett / flower / 36 | noblesseoblige | hp=4780 | crit_damage=0.07; crit_rate=0.101; em=82; hp_percent=0.047 |
| bennett / plume / 1413 | noblesseoblige | atk=311 | atk_percent=0.14; crit_damage=0.179; crit_rate=0.078; hp_percent=0.047 |
| bennett / sands / 1426 | noblesseoblige | em=187 | crit_damage=0.202; crit_rate=0.074; def=37; hp=239 |
| bennett / goblet / 140 | gildeddreams | pyro_damage_bonus=0.466 | crit_damage=0.132; crit_rate=0.078; em=63; hp_percent=0.058 |
| bennett / circlet / 203 | noblesseoblige | crit_damage=0.622 | atk=19; atk_percent=0.047; crit_rate=0.128; em=63 |
| chasca / flower / 1571 | obsidiancodex | hp=4780 | atk_percent=0.111; crit_damage=0.288; crit_rate=0.027; em=23 |
| chasca / plume / 81 | obsidiancodex | atk=311 | atk_percent=0.053; crit_damage=0.148; crit_rate=0.136; em=37 |
| chasca / sands / 92 | deepwoodmemories | atk_percent=0.466 | crit_damage=0.311; crit_rate=0.062; def=42; energy_recharge=0.052 |
| chasca / goblet / 88 | obsidiancodex | atk_percent=0.466 | atk=35; crit_damage=0.288; crit_rate=0.039; def=19 |
| chasca / circlet / 1615 | obsidiancodex | crit_damage=0.622 | atk=19; atk_percent=0.105; crit_rate=0.097; def=56 |
| furina / flower / 1395 | tenacityofthemillelith | hp=4780 | atk_percent=0.053; crit_damage=0.272; def=44; hp_percent=0.099 |
| furina / plume / 1598 | tenacityofthemillelith | atk=311 | atk_percent=0.111; crit_damage=0.288; em=19; hp_percent=0.105 |
| furina / sands / 1466 | wandererstroupe | hp_percent=0.466 | crit_damage=0.187; crit_rate=0.128; em=21; energy_recharge=0.052 |
| furina / goblet / 1563 | tenacityofthemillelith | hp_percent=0.466 | crit_damage=0.21; crit_rate=0.066; em=56; hp=269 |
| furina / circlet / 1614 | tenacityofthemillelith | crit_damage=0.622 | atk=45; atk_percent=0.082; crit_rate=0.031; energy_recharge=0.117 |
| ororon / flower / 1616 | scrolloftheheroofcindercity | hp=4780 | atk=14; atk_percent=0.117; crit_damage=0.21; crit_rate=0.066 |
| ororon / plume / 91 | scrolloftheheroofcindercity | atk=311 | atk_percent=0.146; crit_damage=0.124; crit_rate=0.109; energy_recharge=0.052 |
| ororon / sands / 241 | scrolloftheheroofcindercity | atk_percent=0.466 | crit_damage=0.218; crit_rate=0.074; def_percent=0.124; hp=209 |
| ororon / goblet / 1586 | aubadeofmorningstarandmoon | electro_damage_bonus=0.466 | atk=14; crit_damage=0.35; crit_rate=0.031; def_percent=0.051 |
| ororon / circlet / 119 | scrolloftheheroofcindercity | crit_rate=0.311 | crit_damage=0.264; em=21; hp=538; hp_percent=0.058 |

## Источник, custody и остановка

Сохранённый исходный milestone **`05960111603914b08b945553ee5f0df220597161`**; карта R3 428 файлов **`3401a0e41238cc6fb85b9f74121f89e2c7cd062c6aebb2a717fc1969a9db9672`**. Consumer **`e286d59d46a932cc52c34f14659e34c99790b70fe2f890e62ec1ad0c7e59f448`**, producer **`f1e076b7fa9d292d0bab83aed9d3db0ec917437b288dcc6798cd69f4718f9b93`**. Windows/amd64/v1, Go1.26.4, CGO=0, без Go experiments; версии Python/Go зафиксированы в prepared-review.

Выполнена одна подготовительная consumer build за 12,281 с, producer rebuild=0. Native R2 восстанавливается из pinned `6f1cab8` и текстовой дельты; exact411-map проверен MAIN и ROOT, zip необязателен. Python/material и producer сохраняют отдельные существующие зависимости. Исторические owner.source_commit=e6d076c/source_closure=accepted403 — поля старого wrapper, не идентичность R3; это явно квалифицировано ROOT_ADMISSION и prepared-review.

Экспорт: [off](run-v1/off.json), [подробные измерения](run-v1/off-details.json), [компактная атрибуция](run-v1/off-attribution-v1.json), [наблюдения пяти флагов](run-v1/off-r3-observations.json). Attribution содержит SHA owner до release; финальный owner SHA и проверка удаления/процессов/сохранности принадлежат [closeout](run-v1/closeout.json). Сырые captures, snapshot DB и временные бинарники не сохраняются вне исходного job.

Состояние release и окончательной сохранности устанавливается closeout.json после штатного освобождения исходного owner `job-uvyvjrw5`; отчёт сам по себе не заменяет эту квитанцию. Ничего не установлено; обычный installed consumer/engine не менялись. После cleanup и локальной фиксации результата — **STOP**, без автоматически выбранного следующего эксперимента.

Осталось по текущему списку
1. [x] Зафиксировать текущий статус в TODO/handoff

	~~Мы начали docs update, но его ещё надо спокойно довести: отметить закрытыми right-panel smoothness, character add/select, Artifact Browser target filters; оставить актуальные следующие задачи.~~
	
	~~Это docs-only, можно сделать маленьким safe-diff.~~

2. [x] Cleanup временных right-panel правок

	- ~~После того как всё стало плавно, надо проверить и, возможно, убрать временные костыли/лишнее:~~
	
	- ~~setUpdatesEnabled(False) вокруг RightPanelPrototypeWidget.set_model, если он уже не нужен.~~
	- ~~Жёсткие fixed-height фиксы для team rows / teams container, если skeleton/single-refresh уже решают проблему.~~
	- ~~Лишние perf/debug logs, если они слишком шумят.~~
	- ~~Старые debug-файлы типа debug_right_panel_bounce.log, если они остались untracked.~~
	
	- ~~Это лучше делать independent safe-diff chain: один cleanup → smoke → следующий.~~

3. [x] Artifact Browser first init / loade
	- Текущий холодный init был примерно:
	
	- artifact_browser_init total ~350ms
	- store ~110ms
	- targets ~46ms
	- ui ~170ms
	
	- Плюс при первом открытии Artifacts было изменение размера AppShell 1408x820 → 1408x850, потому что Artifact Browser поднимает minimum size.
	
	- Что осталось решить:
	
	- loader/progress screen при первом открытии/старте;
	- staged init: сначала shell/loader, потом store/targets/UI/presets;
	- позже persistent cache, чтобы второй запуск был дешевле;
	- отдельно убрать geometry twitch от current_min_hint=732x808, если он визуально мешает.
	
	- Это уже лучше для Codex или atomic series, не мелкими случайными диффами.

4. [x] Bulk persistent equipment prewarm / negative cache

	Сейчас UX уже нормальный, но архитектурно можно улучшить:
	
	после загрузки аккаунта одним проходом узнать, у кого есть current weapon/artifacts;
	записать negative cache для персонажей без экипировки;
	для персонажей с экипировкой прогреть lightweight hydration data;
	не делать мелкие DB-запросы при первом выборе каждого персонажа.

5. [x] Drag/drop между 8 слотами

	Модель уже позволяет: TeamBuilderState.swap_slots(...) умеет менять слоты между командами.
	
	Нужно сделать UI:
	
	drag ghost карточки;
	drop на другой слот;
	swap full slot payload, а не только портрет;
	вместе должны ехать character, weapon, details, artifact/build mini icons, warnings;
	selection follows dragged card;
	pending hydration cancel/stale guard;
	резонансы/командные бонусы не копируются, а пересчитываются из нового состава команды.
	
	Это хорошая отдельная Codex-задача. По сложности средняя, но много edge cases.

- [x] Прокрутка фильтров
- [ ] глобальный размер окна
- [ ] оверлей иконок




6. [ ] Artifact Browser first-launch persistent cache / “запечь”

	Это продолжение пункта 3, но отдельным слоем:
	
	кэш store/model данных по DB mtime/schema/import version/content language;
	кэш target previews/icons уже частично есть;
	кэш preset bonus pixmaps уже есть;
	цель: первый запуск под loader, последующие — сильно быстрее.
7. [ ] Дальнейшая интеграция Artifact Browser C2

	Сейчас C1 embedded browser + operation target/current equipment scaffold есть. Осталось по продуктовой логике:
	
	artifact click в equip mode уже должен/будет писать через equipment service, если ещё не финализировано;
	preset apply как явное действие Надеть пресет;
	current equipment zone как отдельная строка над пресетами;
	repeated preset click deselect;
	conflict confirmation с side icons;
	incomplete preset behavior уже зафиксирован: missing slots очищаются.
	
	Часть уже сделана, но C2 как цель ещё не закрыта полностью.

8. Большая будущая архитектура Run Workspace

	Это уже не текущий perf-блок, но остаётся в плане:
	
	заменить legacy right panel на полноценный Run Workspace;
	Abyss / DPS Dummy modes;
	shared TeamCard / RunCard;
	immutable snapshots для истории;
	позже GCSIM/DPS Dummy integration.
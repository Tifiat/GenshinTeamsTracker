# GenshinTeamsTracker — снимок исходников Theory

Это отдельный очищенный снимок исходного дерева локального коммита
`98f1069f7736420b2b66ef932f5f4d0b3c83a726` (`codex/optimizer-theory`). Он
сохраняет исходный код приложения, конфигурацию и тестовый код именно той
версии. Это не интеграция в `master` и не полная копия истории ветки.

Исходная версия включает экспериментальную реализацию оптимизатора Theory.
Её наличие в исходниках само по себе не подтверждает полноту поиска,
продуктовую готовность или приёмку пользовательского интерфейса.

Для запуска используется Python 3.11 и зависимости из `requirements.txt`:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Нативный оптимизатор находится в `native/gcsim_optimizer/`, интеграция — в
`run_workspace/gcsim/`. Исходные тесты сохранены, но пользовательские/сырые
fixtures не включены, поэтому полный набор тестов этим снимком не обещается.

Состав и исключения описаны в
[`docs/publication/optimizer-theory-source-snapshot-2026-10-28.md`](docs/publication/optimizer-theory-source-snapshot-2026-10-28.md).
"""Render reviewed CURRENT Theory choices; never substitute archived choices.

Owner: docs/optimizer-evidence/2026-10-03-theory-current-matrix/README.md.
Inputs are minimal receipts. The reader report is replaced as reviews finish;
receipts remain immutable. Retain until the Theory regressions absorb them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.mode_matrix import run_product_matrix as matrix
OWNER = ROOT / "docs/optimizer-evidence/2026-10-03-theory-current-matrix"
OUTPUTS = Path(r"C:\Users\user\Documents\Codex\2026-10-03\theory-genshinteamstracker-c-users-user-desktop\outputs")
TEAMS = (
    ("gaming_melt", "Таяние — КаМин"),
    ("lunar_crystallize", "Лунная кристаллизация — Навия"),
    ("lunar_charged", "Лунный заряд — Флинс"),
    ("lunar_bloom", "Лунная бутонизация"),
    ("bountiful_core", "Бутонизация — Нилу"),
    ("chiori_lunar_crystallize", "Лунная кристаллизация — Тиори"),
    ("spread", "Разрастание — Тигнари"),
    ("aggravate", "Обострение — Кэ Цин"),
    ("vaporize", "Пар"),
    ("burgeon", "Цветение"),
    ("burning", "Горение — Кинич"),
    ("physical", "Физический урон — Фремине"),
    ("overload", "Перегрузка"),
    ("taser", "Заряжен"),
)
CHARACTERS = {
    "gaming": "КаМин", "citlali": "Ситлали", "diona": "Диона", "bennett": "Беннет",
    "navia": "Навия", "xilonen": "Шилонен", "ineffa": "Инеффа", "columbina": "Коломбина",
    "flins": "Флинс", "jahoda": "Ягода", "kukishinobu": "Куки Синобу", "lauma": "Лаума",
    "nahida": "Нахида", "nilou": "Нилу", "kaveh": "Кавех", "xingqiu": "Син Цю",
    "furina": "Фурина", "chiori": "Тиори", "fischl": "Фишль", "tighnari": "Тигнари",
    "keqing": "Кэ Цин", "lanyan": "Лань Янь", "xiangling": "Сян Лин", "freminet": "Фремине",
    "thoma": "Тома", "kinich": "Кинич", "emilie": "Эмилия", "dehya": "Дэхья", "mika": "Мика",
    "chevreuse": "Шеврёз", "sucrose": "Сахароза", "beidou": "Бэй Доу",
}
STATS = {
    "atk": "АТК", "hp": "HP", "def": "Защита", "atk_percent": "АТК%", "hp_percent": "HP%",
    "def_percent": "Защита%", "crit_rate": "Крит. шанс", "crit_damage": "Крит. урон",
    "em": "МС", "er": "ВЭ", "energy_recharge": "ВЭ", "healing_bonus": "Лечение",
    "pyro_damage_bonus": "Пиро", "cryo_damage_bonus": "Крио", "hydro_damage_bonus": "Гидро",
    "electro_damage_bonus": "Электро", "anemo_damage_bonus": "Анемо", "geo_damage_bonus": "Гео",
    "dendro_damage_bonus": "Дендро", "physical_damage_bonus": "Физ. урон",
}
WARNINGS = {
    "theory_guidance_not_owned_artifacts": "виртуальные артефакты, не личный инвентарь",
    "bounded_set_shortlist_not_global_optimum": "ограниченная очередь, глобальный оптимум не доказан",
    "theory_context_budget_exhausted_partial_result": "частичный результат: достигнут предел времени/сценариев",
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names() -> dict[str, str]:
    uri = (ROOT / "data/artifacts.db").resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute("""SELECT s.fallback_name, n.name FROM artifact_sets AS s
            JOIN artifact_set_names AS n ON n.set_uid=s.set_uid WHERE n.lang='ru-ru'""").fetchall()
    return {re.sub(r"[^a-z0-9]", "", english.lower()): russian for english, russian in rows if english}


def package(row: dict, catalogue: dict) -> str:
    sets = row.get("sets")
    if not sets:
        return "Без выделенного бонуса сета"
    return " + ".join(f'{item["count"]}× «{catalogue.get(item["set_uid"], item["set_uid"])}»' for item in sets)


def receipt(team: str) -> Path:
    if team == "lunar_charged":
        return ROOT / "tests/fixtures/gcsim_optimizer_go_v1/theory_lunar_audit_20261003_v1.json"
    return OWNER / f"{team}_theory.json"


def reviewed(path: Path, team: str) -> dict:
    data = read(path)
    if data["input"]["team"] != team or data["input"]["run_id"] != team + "_theory":
        raise ValueError(f"Wrong current receipt: {path.name}")
    cleanup = data["cleanup"]
    verified = cleanup.get("verified_by_harness") or cleanup.get("verified_after_outer_runner")
    if not verified or not cleanup.get("job_absent_after_cleanup"):
        raise ValueError(f"Cleanup not reviewed: {path.name}")
    if data["binding"]["engine_artifact_sha256"] != "7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c":
        raise ValueError("Report engine binding changed")
    if not data["execution"]["success"] or not data["product"]["candidates"]:
        raise ValueError(f"Failed current search: {path.name}")
    return data


def replay_comparison(data: dict, team: str) -> tuple[list[str], dict | None]:
    relative = "lunar_charged_rank1_response.json" if team == "lunar_charged" else f"matrix/{team}_rank1_response.json"
    fresh = OWNER / f"{team}_rank1_response.json"
    path = fresh if fresh.is_file() else ROOT / "docs/optimizer-evidence/2026-10-03-theory-verification" / relative
    if not path.is_file():
        return ["GCSIM для этого свежего распределения ещё не сопоставлен."], None
    replay = read(path)
    if replay.get("status") != "verification_completed":
        return ["Проверка GCSIM не завершена успешно; её результат не используется."], None
    current = data["product"]["candidates"][0]
    point = replay["input"]["candidate"]
    job_relative = replay["cleanup"].get("managed_job_relative", "")
    if not job_relative.startswith(".codex_tmp/managed-optimizer/job-"):
        raise ValueError("Replay cleanup path outside managed scope")
    job = (ROOT / job_relative).resolve()
    if job.parent != (ROOT / ".codex_tmp/managed-optimizer").resolve():
        raise ValueError("Replay cleanup path outside managed root")
    replay_job_absent_now = not job.exists()
    checks = {
        "packages": current["packages"] == point["packages"],
        "allocations": current["allocations"] == point["allocations"],
        "team": replay["input"]["team"] == team,
        "manifest": replay["input"]["manifest_sha256"] == data["input"]["manifest_sha256"],
        "rotation": replay["input"]["rotation_sha256"] == data["input"]["rotation_sha256"],
        "energy": replay["input"]["energy"] == "infinite",
        "engine_id": replay["binding"]["engine_id"] == data["binding"]["engine_id"],
        "engine_artifact": replay["binding"]["artifact_sha256"] == data["binding"]["engine_artifact_sha256"],
        "patch": replay["binding"]["patch_manifest_sha256"] == data["binding"]["request_engine"]["patch_manifest_sha256"],
        "source": replay["binding"]["source_manifest_sha256"] == data["binding"]["request_engine"]["source_manifest_sha256"],
        "shared_input_sources": all(value == replay["source_sha256"][key] for key, value in data["source_sha256"].items() if key in replay["source_sha256"]),
        "config_text_hash": hashlib.sha256(replay["input"]["config_text"].encode("utf-8")).hexdigest() == replay["input"]["config_sha256"],
        "replay_cleanup": bool(replay["cleanup"].get("verified_after_outer_runner") or replay["cleanup"].get("verified_by_harness")) and replay_job_absent_now,
    }
    if not all(checks.values()):
        return ["Предыдущая проверка GCSIM не подтверждает именно этот свежий результат: " + ", ".join(key for key, ok in checks.items() if not ok)], None
    fixed = replay["comparison"]["fresh_two_seed_expected_dps"]
    ordinary = replay["ordinary"]
    delta = 100 * (fixed / current["formula_dps"] - 1)
    panel_gap = 100 * (ordinary["dps"] / fixed - 1)
    lines = [
        "Проверка GCSIM выполнена для полностью совпадающего распределения на нынешнем движке.",
        f'  Фиксированные 2 сценария: {fixed:,.2f} DPS; отличие от нынешнего прогноза Theory {delta:+.3f}%.',
        f'  Обычный GCSIM, {ordinary["iterations"]} итераций: {ordinary["dps"]:,.2f} DPS, ошибка среднего {ordinary["standard_error"]:,.2f}; отличие от фиксированных сценариев {panel_gap:+.3f}%.',
        "  Совпадение в одной точке не доказывает правильный выбор лучшего сета и распределения.",
        "Источник проверки: " + path.relative_to(ROOT).as_posix(),
        "SHA256 проверки: " + digest(path),
    ]
    witness = {
        "scope": "exact current-selected vector replay reuse; not selection or changed-vector response acceptance",
        "current_search_sha256": digest(receipt(team)),
        "replay_sha256": digest(path),
        "replay_path": path.relative_to(ROOT).as_posix(),
        "checks": checks,
        "replay_job_absent_at_report": replay_job_absent_now,
        "current_formula_dps": current["formula_dps"],
        "fixed_panel_dps": fixed,
        "fixed_panel_vs_formula_percent": delta,
        "ordinary_dps": ordinary["dps"],
        "ordinary_iterations": ordinary["iterations"],
        "ordinary_vs_panel_percent": panel_gap,
    }
    return lines, witness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", nargs="+", choices=[team for team, _ in TEAMS], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    if target.parent != OUTPUTS.resolve() or target.suffix != ".txt":
        raise ValueError("Reader report must be a text deliverable in this task's outputs")
    selected = set(args.reviewed)
    catalogue = names()
    witnesses = {}
    manifest_path = ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
    profile_rows = {row["team"]: row["virtual_profiles"] for row in matrix._expanded_manifest_entries(read(manifest_path)) if row["mode"] == "theory"}
    lines = [
        "ВЫБОР СЕТОВ НЫНЕШНИМ THEORY — СЕРИЯ НАЧАТА 03.10.2026",
        f"Свежие поиски: {len(selected)} из 14 команд. Остальные помечены как ожидающие.",
        "Режим реализован, но качество отбора и расчёта ещё не принято. Алгоритм не менялся.",
        "Это результат текущего поиска, а не повторный показ старых сборок.",
        "Профили/оружие/созвездия/ротации взяты из существующей тестовой матрицы; энергия бесконечная.",
        "Это виртуальные профили матрицы, а не оптимизация личного инвентаря пользователя.",
        "Без выделенного бонуса: алгоритм не выделил сет, это не доказательство отсутствия полезного сета.",
        "Подстаты ниже указаны в единицах максимального прока. 45 на персонажа; четверти допустимы.",
        "Распределение непрерывное и не гарантирует сборку пяти реально выпавших артефактов.",
        "Цветок всегда HP, перо всегда АТК. Основные статы: часы / кубок / корона.",
        "DPS — прогноз Theory на фиксированных сценариях, не подтверждённый средний обычного GCSIM.",
        "",
    ]
    lines.append("БЫСТРЫЙ СПИСОК ВЫБРАННЫХ СЕТОВ")
    for team, label in TEAMS:
        if team not in selected:
            lines.append(label + ": свежий выбор ожидается.")
            continue
        data = reviewed(receipt(team), team)
        rank_one = data["product"]["candidates"][0]
        by_wearer = {row["wearer_key"]: row for row in rank_one["packages"]}
        sets = "; ".join(CHARACTERS.get(profile["character_key"], profile["character_key"]) + " — " + package(by_wearer[profile["character_key"]], catalogue) for profile in data["input"]["profiles"])
        coverage = data["product"]["coverage"]
        marker = " [частично]" if "theory_context_budget_exhausted_partial_result" in data["product"]["warnings"] else ""
        lines.append(f'{label} ({coverage["contexts_evaluated"]}/{coverage["contexts_limit"]}){marker}: {sets}.')
    lines.extend(["", "ПОДРОБНОСТИ И ПРОВЕРКИ GCSIM", ""])
    for index, (team, label) in enumerate(TEAMS, 1):
        lines.append(f"{index}. {label} ({team})")
        if team not in selected:
            lines.extend(["Свежий выбор ещё не получен.", ""])
            continue
        path = receipt(team)
        data = reviewed(path, team)
        profiles = profile_rows[team]
        profiles_sha = hashlib.sha256(json.dumps(profiles, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        if data["input"]["profiles_sha256"] != profiles_sha or data["input"]["manifest_sha256"] != digest(manifest_path):
            raise ValueError("Report profiles differ from current search")
        result = data["product"]
        rank1 = result["candidates"][0]
        cover = result["coverage"]
        partial = "ЧАСТИЧНЫЙ" if "theory_context_budget_exhausted_partial_result" in result["warnings"] else "Поиск завершён в своих пределах"
        lines.append(f'{partial}; проверено {cover["contexts_evaluated"]}/{cover["contexts_limit"]} сценариев, прогноз {rank1["formula_dps"]:,.2f} DPS.')
        lines.append(f'Сетов в каталоге {cover["catalog_sets"]}; пакетов {cover["packages_considered"]}; в очереди {cover["packages_shortlisted"]}; вне очереди {cover["unqueued_packages"]}.')
        packages = {row["wearer_key"]: row for row in rank1["packages"]}
        allocations = {row["wearer_key"]: row for row in rank1["allocations"]}
        for profile in profiles:
            key = profile["character_key"]
            alloc = allocations[key]
            talents = "/".join(str(value) for value in profile["talents"])
            lines.append(f'  {CHARACTERS.get(key, key)} [{key}], C{profile["constellation"]}, таланты {talents}, оружие {profile["weapon_key"]} R{profile["refinement"]}: {package(packages[key], catalogue)}')
            mains = alloc["main_stats"]
            lines.append("    Осн. статы: " + " / ".join(STATS.get(mains[slot], mains[slot]) for slot in ("sands", "goblet", "circlet")))
            lines.append("    Проки: " + "; ".join(f'{STATS.get(row["stat_key"], row["stat_key"])} {row["roll_units"]:g}' for row in alloc["substats"]))
            lines.append(f'    Потрачено {alloc["spent_roll_units"]:g}; осталось {alloc["unspent_roll_units"]:g}.')
        lines.append("Другие возвращённые варианты (их порядок по прогнозу Theory):" if len(result["candidates"]) > 1 else "Других вариантов в результате нет.")
        for alternative in result["candidates"][1:5]:
            desc = "; ".join(f'{CHARACTERS.get(row["wearer_key"], row["wearer_key"])}: {package(row, catalogue)}' for row in alternative["packages"])
            lines.append(f'  №{alternative["rank"]}, {alternative["formula_dps"]:,.2f} DPS — {desc}')
        lines.append("Предупреждения: " + "; ".join(WARNINGS.get(code, code) for code in result["warnings"]))
        lines.append(f'Неописанных зависимостей в прогнозе: {len(rank1["opaque_reasons"])}. Ограниченная очередь не гарантирует глобальный оптимум.')
        replay_lines, witness = replay_comparison(data, team)
        lines.extend(replay_lines)
        if witness is not None:
            witnesses[team] = witness
        if team == "gaming_melt":
            trace_path = OWNER / "gaming_melt_full_trace.json"
            if trace_path.is_file():
                trace = read(trace_path)
                if trace.get("status") == "trace_completed" and trace["binding"]["current_theory_sha256"] == digest(path):
                    for summary in trace["traces"]:
                        plunges = summary["gaming_tag3_plunge"]
                        lines.append(f'  Сценарий {summary["seed"]}: КаМин — {plunges["total"]["count"]} падений, из них {plunges["melted"]["count"]} с Таянием.')
                    lines.append("  Все атаки КаМина: по 15 Таяний в фиксированных сценариях против среднего 9,824 в обычных 500 итерациях.")
                    lines.append("  Счётчики сопоставлены по коду симулятора; обычное число Таяний именно на падениях здесь не измерено.")
                    lines.append("  Более частое Таяние — зацепка для разницы DPS; точная доля разрыва и ошибка прогноза требуют отдельной проверки.")
                    lines.append("Источник событий: " + trace_path.relative_to(ROOT).as_posix())
        if team == "lunar_bloom" and witness is not None:
            old_path = ROOT / "docs/optimizer-evidence/2026-10-03-theory-verification/matrix/lunar_bloom_rank1_response.json"
            old, fresh = read(old_path), read(OWNER / "lunar_bloom_rank1_response.json")
            trimmed = "\n".join(line for line in fresh["input"]["config_text"].split("\n") if line not in {
                'kukishinobu add set="silkenmoonsserenade" count=4;',
                'lauma add set="silkenmoonsserenade" count=4;',
            })
            if (
                trimmed == old["input"]["config_text"]
                and fresh["binding"] == old["binding"]
                and fresh["input"]["seeds"] == old["input"]["seeds"]
                and [(row["seed"], row["expected_dps"], row["duration_ms"]) for row in fresh["captures"]]
                == [(row["seed"], row["expected_dps"], row["duration_ms"]) for row in old["captures"]]
            ):
                lines.append("  Контроль: добавление Серенады на Куки и Лауму не изменило DPS ни в одном из двух сценариев.")
                lines.append("  Все остальные строки конфигурации совпадают. Полезность двух дополнительных сетов на этих сценариях не подтверждена.")
        if team == "bountiful_core" and witness is not None:
            counter_path = OWNER / "bountiful_core_nilou_hp_counter_response.json"
            if counter_path.is_file():
                counter = read(counter_path)
                variant = counter["input"]["candidate"]
                expected_nilou = {"wearer_key": "nilou", "sets": [
                    {"count": 2, "set_uid": "tenacityofthemillelith"},
                    {"count": 2, "set_uid": "vourukashasglow"},
                ]}
                if (
                    counter.get("status") == "verification_completed"
                    and variant["allocations"] == rank1["allocations"]
                    and [row for row in variant["packages"] if row["wearer_key"] != "nilou"] == [row for row in rank1["packages"] if row["wearer_key"] != "nilou"]
                    and [row for row in variant["packages"] if row["wearer_key"] == "nilou"] == [expected_nilou]
                    and counter["binding"]["artifact_sha256"] == data["binding"]["engine_artifact_sha256"]
                    and counter["input"]["manifest_sha256"] == data["input"]["manifest_sha256"]
                    and counter["input"]["rotation_sha256"] == data["input"]["rotation_sha256"]
                ):
                    fixed = counter["comparison"]["fresh_two_seed_expected_dps"]
                    gain = 100 * (fixed / witness["fixed_panel_dps"] - 1)
                    lines.append("  КОНТРПРИМЕР: только Нилу заменена на 2× Стойкость Миллелита + 2× Сияние Вурукаши; все проки прежние.")
                    lines.append(f'  Два фиксированных сценария: {fixed:,.2f} DPS, прибавка {gain:+.3f}% к выбранной Theory сборке.')
                    lines.append(f'  Обычный GCSIM, 128 итераций: {counter["ordinary"]["dps"]:,.2f} DPS против {witness["ordinary_dps"]:,.2f}.')
                    lines.append("  Это улучшение в проверенных условиях, не доказательство глобально лучшей сборки. Прогноз Theory для контроля не считался.")
                    lines.append("Источник контроля: " + counter_path.relative_to(ROOT).as_posix())
        lines.append("Источник: " + path.relative_to(ROOT).as_posix())
        lines.append("SHA256 отчёта поиска: " + digest(path))
        lines.extend(["", ""])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    journal = {
        "owner": OWNER.relative_to(ROOT).as_posix() + "/README.md",
        "lifecycle": "reviewed report projection; retain until Theory regression absorption, consolidate/prune duplicates",
        "current_teams": sorted(selected),
        "witnesses": witnesses,
    }
    (OWNER / "reviewed_replay_bindings.json").write_text(json.dumps(journal, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(target), "current_teams": len(selected), "bytes": target.stat().st_size}, ensure_ascii=True))


if __name__ == "__main__":
    main()

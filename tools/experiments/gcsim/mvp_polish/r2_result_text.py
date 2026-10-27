"""Additive experiment-only text used by the unchanged AppShell result path."""
from run_workspace.gcsim.optimizer_go_result_text import format_gcsim_optimizer_go_selected_result as original_text


def format_staged_result(payload):
    text = original_text(payload)
    result = payload.get('result') or {}
    if payload.get('status') != 'success' or not result.get('measured'):
        return text
    rows = result.get('candidates') or []
    if result['measured'].get('iterations') != 500:
        raise ValueError('R2 output winner is not independently confirmed at n500')
    details = '; '.join(f"#{row['rank']}: n{row['measured']['iterations']}, SE {row['measured']['standard_error']}" for row in rows)
    return text + '\nЛидер подтверждён при n500; альтернативы сохраняют свои n100 или n500.\n' + details

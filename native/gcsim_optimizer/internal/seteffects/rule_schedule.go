package seteffects

// Schedule inputs are not damage ports. internal/frames reads AtkSpd while
// computing action frames, so an activated speed vector cannot disappear just
// because no damage expression requested that component. This is a conservative
// route boundary, not a simulation of new action timing or a set-name exception.
import "go/ast"

func (h *ruleReplayHost) checkScheduleStat(m replayMod) {
	if m.kind != "stat" {
		return
	}
	index, known := h.statIndices["atkspd%"]
	if !known {
		return // Synthetic source controls may intentionally omit this vocabulary.
	}
	if m.affected != nil {
		affected := ruleInteger(m.affected)
		if affected == index {
			ruleFail("schedule_change: activated attack-speed modifier")
		}
		if none, ok := h.statIndices["n/a"]; ok && affected != none {
			return // AffectedStat filtering excludes it from Stat(AtkSpd).
		}
	}
	fn := m.object.fields["Amount"].(*ruleFunction)
	if array := m.vm.amountScratch(fn); array != nil && index < len(array.values) {
		value, err := ruleTry(func() any { return ruleNumber(array.values[index]) })
		if err != nil || value != float64(0) {
			ruleFail("schedule_change: activated vector contains attack speed")
		}
	}
	ast.Inspect(fn.body, func(node ast.Node) bool {
		assignment, ok := node.(*ast.AssignStmt)
		if !ok {
			return true
		}
		for _, lhs := range assignment.Lhs {
			cell, ok := lhs.(*ast.IndexExpr)
			if !ok {
				continue
			}
			// Only lexical names/selectors: no speculative API/stat getter calls.
			if ruleStoragePath(cell.Index) == "" {
				continue
			}
			value, err := ruleTry(func() any { return ruleInteger(m.vm.eval(cell.Index, fn.env)) })
			if err == nil && value == index {
				ruleFail("schedule_change: amount writes attack speed")
			}
		}
		return true
	})
}

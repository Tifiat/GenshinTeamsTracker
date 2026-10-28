package seteffects

// A single immutable engine query asks for several stats from the same Amount
// vector. Reuse that already-validated pure source evaluation; never replay an
// AST per item or merge equal values from different query points.
type ruleAmountKey struct {
	object                *ruleObject
	order, generation     uint64
	frame, active, target int
	mode                  string
}
type ruleAmountValue struct {
	value any
	err   error
}

func (h *ruleReplayHost) amount(m replayMod, q RuleQuery, args []any) (any, error) {
	key := ruleAmountKey{m.object, h.order, h.lifecycle, h.frame, h.active, q.Target, q.Mode}
	if h.order != 0 {
		if h.amountOrder != h.order {
			h.amountCache = map[ruleAmountKey]ruleAmountValue{}
			h.amountOrder = h.order
		}
		if cached, ok := h.amountCache[key]; ok {
			return cached.value, cached.err
		}
	}
	value, err := ruleTry(func() any { return m.vm.invokeAmount(m.object.fields["Amount"].(*ruleFunction), args) })
	if h.order != 0 {
		h.amountCache[key] = ruleAmountValue{value, err}
	}
	return value, err
}

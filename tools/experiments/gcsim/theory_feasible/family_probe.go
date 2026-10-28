package setcontext

// Copied only into managed scratch. A key is meaningful within this one model,
// after source activation/interaction validation, for the frozen DPS objective.
// It is not a proof that schedules or the actual sets are interchangeable.
import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

// Retain the owned capture before NewNeutralModel transfers it. Each invocation
// constructs an independent binding/program/cache universe from identical input.
// No search state, previous optimization, or context cache is shared.
func ResearchNeutralFactory(h *Handle, sources *seteffects.SourceCatalog) func() (*NeutralModel, error) {
	saved := *h.compiled
	return func() (*NeutralModel, error) {
		c := saved
		copyHandle := *h
		copyHandle.compiled = &c
		return NewNeutralModel(&copyHandle, sources)
	}
}

func (m *NeutralModel) ResearchFamily(target *Context) (*Handle, string, []string, error) {
	h, codes, err := m.Resolve(target)
	if h == nil || err != nil {
		return h, "", codes, err
	}
	if d, ok := m.targetPrograms[target.key]; ok {
		return h, fmt.Sprintf("program:%x", d.key), codes, nil
	}
	return h, "context:" + target.key, codes, nil
}

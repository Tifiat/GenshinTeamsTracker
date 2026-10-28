package allsets

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

// CanonicalReference removes equipped artifact/set influence before capturing
// the schedule as well as before searching. Raw request identity remains the
// outer receipt's identity; the independent capture has its own config hash.
func CanonicalReference(req contracts.OptimizerRequest, index *domain.Index, base *setcontext.Context, binding setcontext.Binding) (contracts.OptimizerRequest, *domain.Index, *setcontext.Context, error) {
	canonical, packs, err := index.CanonicalAllSetsAnchor()
	if err != nil {
		return req, nil, nil, err
	}
	changes := map[string][]setcontext.Set{}
	copyReq := req
	copyReq.Wearers = append([]contracts.Wearer(nil), req.Wearers...)
	for actor, w := range copyReq.Wearers {
		changes[w.WearerKey] = nil
		for _, s := range packs[actor].Sets {
			changes[w.WearerKey] = append(changes[w.WearerKey], setcontext.Set{UID: s.SetUID, Count: s.Count})
		}
		copyReq.Wearers[actor].SelectedSetUID = ""
		copyReq.Wearers[actor].SelectedSets = packs[actor].Sets
	}
	replaced, err := base.Replace(changes)
	if err != nil {
		return req, nil, nil, err
	}
	copyReq.Context.PreparedConfig.Text = replaced.Config()
	rendered, err := finalists.RenderConfig(copyReq, canonical, canonical.Incumbent, 1, 1)
	if err != nil {
		return req, nil, nil, err
	}
	copyReq.Context.PreparedConfig = contracts.SourceText{Text: rendered.Text, SHA256: rendered.SHA256}
	canonicalBase, err := setcontext.New(binding, rendered.Text)
	return copyReq, canonical, canonicalBase, err
}

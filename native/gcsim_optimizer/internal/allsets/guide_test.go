package allsets

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestGuideKeepsUnknownMechanicsAndRejectsStaleContext(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	b, e := os.ReadFile(filepath.Join(root, "request_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	req, e := contracts.DecodeRequest(b)
	if e != nil {
		t.Fatal(e)
	}
	b, e = os.ReadFile(filepath.Join(root, "compact_ir_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	compact, e := contracts.DecodeCompactIR(b)
	if e != nil {
		t.Fatal(e)
	}
	text := ""
	owners := []string{}
	for _, w := range req.Wearers {
		owners = append(owners, w.WearerKey)
		text += w.WearerKey + " char lvl=90/90;\n"
		sets := w.SelectedSets
		if len(sets) == 0 {
			sets = []contracts.SetRequirement{{SetUID: w.SelectedSetUID, Count: 4}}
		}
		for _, s := range sets {
			text += w.WearerKey + " add set=\"" + s.SetUID + "\" count=" + strconv.Itoa(s.Count) + ";\n"
		}
	}
	seeds := []uint64{}
	for _, m := range compact.Members {
		seeds = append(seeds, m.Seed)
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: strings.Repeat("c", 64), ReferenceStatsSHA256: strings.Repeat("d", 64), Seeds: seeds}
	c, e := setcontext.New(binding, text)
	if e != nil {
		t.Fatal(e)
	}
	provider := func(_ context.Context, target *setcontext.Context) (setcontext.Capture, error) {
		out := setcontext.Capture{ContextSHA256: target.Key(), ConfigSHA256: target.ConfigSHA256(), EngineBindingSHA256: req.Engine.BindingSHA256, Members: compact.Members}
		for _, m := range out.Members {
			out.Effects = append(out.Effects, contracts.EffectInputsOutput{SchemaVersion: 1, Capability: contracts.EffectInputsCapability,
				ContextSHA256: target.ConfigSHA256(), InputConfigSHA256: target.ConfigSHA256(), SourceManifestBodySHA256: req.Engine.SourceManifestSHA256, Seed: strconv.FormatUint(m.Seed, 10), CharacterKeys: owners,
				EffectInputs: []contracts.EffectInput{}, ResistanceInputs: []contracts.ResistanceInput{}})
		}
		return out, nil
	}
	s, _ := setcontext.NewSession(provider, len(seeds)*2)
	h, e := s.Resolve(context.Background(), c, nil, nil)
	if e != nil {
		t.Fatal(e)
	}
	panel, e := h.SearchPanel()
	if e != nil {
		t.Fatal(e)
	}
	index, e := domain.Build(req, panel.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	source := &seteffects.SourceCatalog{EngineSHA256: req.Engine.ArtifactSHA256, SourceManifestSHA256: req.Engine.SourceManifestSHA256, CatalogSHA256: binding.CatalogSHA256,
		Sets: []seteffects.DiscoveredSet{{Key: "future", FourPieceModeled: true, Unresolved: "new source syntax", Recipes: []seteffects.Recipe{{Effect: seteffects.Effect{Kind: "new_attack"}}}}}}
	g, e := BuildGuide(context.Background(), index, h, source)
	if e != nil {
		t.Fatal(e)
	}
	for _, w := range index.Wearers {
		hint := g.hints[HintKey{Wearer: w.WearerKey, Set: "future", Pieces: 4}]
		if !hint.Unresolved || !hint.NewOutput {
			t.Fatal("unknown/new-output discovery lane lost", hint)
		}
	}
	// Source-derived shared-key opportunities, synthetic here. A transfer must
	// release the donor's physical pieces instead of ruling the receiver out.
	caps := []domain.SetCapability{}
	for _, owner := range index.Wearers {
		for _, set := range owner.SelectedSets {
			caps = append(caps, domain.SetCapability{UID: set.SetUID, TwoPiece: true, FourPiece: true})
		}
	}
	sharedSet := index.Wearers[0].SelectedSets[0].SetUID
	for _, w := range index.Wearers {
		g.hints[HintKey{Wearer: w.WearerKey, Set: sharedSet, Pieces: 4}] = Hint{Shared: true, SharedGroups: map[string]float64{"synthetic_shared": 50}}
	}
	transfers, e := g.ProposeTransfers(context.Background(), index, h, caps, 3)
	if e != nil || len(transfers.Queue) == 0 {
		t.Fatal(transfers, e)
	}
	repeat, e := g.ProposeTransfers(context.Background(), index, h, caps, 3)
	if e != nil || !reflect.DeepEqual(repeat, transfers) {
		t.Fatal("transfer ordering changed", e)
	}
	for _, p := range transfers.Queue {
		if p.Actors[0] != 0 {
			t.Fatal("wrong current source carrier")
		}
		if _, e = index.ForPackages(p.Packages, p.Seed, index.Coordinates); e != nil {
			t.Fatal("illegal joint seed", e)
		}
	}
	noBudget, _ := setcontext.NewSession(provider, 0)
	cfg := search.DefaultConfig()
	cfg.MaxExpandedPerActor = 20
	cfg.MaxCycles = 1
	if _, e = RefineTransfers(context.Background(), index, c, h, noBudget, transfers.Queue[:1], cfg); e == nil {
		t.Fatal("joint capture bypassed shared budget")
	}
	jointSession, _ := setcontext.NewSession(provider, len(seeds))
	joint, e := RefineTransfers(context.Background(), index, c, h, jointSession, transfers.Queue[:1], cfg)
	if e != nil || len(joint) != 1 {
		t.Fatal(joint, e)
	}
	if jointSession.AttemptedCaptureMembers() != len(seeds) {
		t.Fatal("joint proposal was not one complete context")
	}
	next, e := c.Replace(map[string][]setcontext.Set{owners[0]: {{UID: "other", Count: 4}}})
	if e != nil {
		t.Fatal(e)
	}
	other, e := s.Resolve(context.Background(), next, h, nil)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = g.Propose(context.Background(), index, other, nil, 1); e == nil {
		t.Fatal("old guide reused after set replacement")
	}
	wrong := *source
	wrong.SourceManifestSHA256 = strings.Repeat("e", 64)
	if _, e = BuildGuide(context.Background(), index, h, &wrong); e == nil {
		t.Fatal("source mismatch accepted")
	}
	g.anchorSHA = "changed"
	if _, e = g.Propose(context.Background(), index, h, nil, 1); e == nil {
		t.Fatal("old stat-anchor guide accepted")
	}
}

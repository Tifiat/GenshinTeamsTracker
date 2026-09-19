package allsets

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

// Synthetic set semantics deliberately reuse a small neutral graph. These tests
// pin scheduling/identity/budgets, never real set activation or gameplay quality.
func coordinatorFixture(t *testing.T) (*domain.Index, *setcontext.Context, *seteffects.SourceCatalog, setcontext.CaptureProvider, CoordinatorConfig) {
	t.Helper()
	root := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	read := func(name string) []byte {
		b, e := os.ReadFile(filepath.Join(root, name))
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	req, e := contracts.DecodeRequest(read("request_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	for i := range req.Artifacts {
		if req.Artifacts[i].MainStat.Key == "damage_bonus" {
			req.Artifacts[i].MainStat.Key = "pyro_damage_bonus"
		}
	}
	ir, e := contracts.DecodeCompactIR(read("compact_ir_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	originalItems := append([]contracts.Artifact(nil), req.Artifacts...)
	maxID := int64(0)
	for _, a := range originalItems {
		if a.ArtifactID > maxID {
			maxID = a.ArtifactID
		}
	}
	for _, a := range originalItems {
		maxID++
		a.ArtifactID = maxID
		req.Artifacts = append(req.Artifacts, a)
	}
	index, e := domain.Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	text := ""
	actors := []string{}
	sets := map[string]bool{}
	sources := &seteffects.SourceCatalog{EngineSHA256: req.Engine.ArtifactSHA256, SourceManifestSHA256: req.Engine.SourceManifestSHA256, CatalogSHA256: strings.Repeat("c", 64)}
	for _, w := range index.Wearers {
		actors = append(actors, w.WearerKey)
		text += w.WearerKey + " char lvl=90/90;\n"
		for _, s := range w.SelectedSets {
			text += fmt.Sprintf("%s add set=%q count=%d;\n", w.WearerKey, s.SetUID, s.Count)
			if !sets[s.SetUID] {
				sets[s.SetUID] = true
				sources.Sets = append(sources.Sets, seteffects.DiscoveredSet{Key: s.SetUID, FourPieceModeled: true, Unresolved: "synthetic unmodeled effect"})
			}
		}
		text += w.WearerKey + " add stats hp=1;\n"
	}
	text += "# rotation sentinel\noptions iteration=1 workers=1 ignore_burst_energy=true;\nactive " + actors[0] + ";\n"
	seeds := []uint64{}
	for _, m := range ir.Members {
		seeds = append(seeds, m.Seed)
	}
	base, e := setcontext.New(setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: strings.Repeat("d", 64), Seeds: seeds}, text)
	if e != nil {
		t.Fatal(e)
	}
	provider := func(ctx context.Context, target *setcontext.Context) (setcontext.Capture, error) {
		if e := ctx.Err(); e != nil {
			return setcontext.Capture{}, e
		}
		c := setcontext.Capture{ContextSHA256: target.Key(), ConfigSHA256: target.ConfigSHA256(), EngineBindingSHA256: req.Engine.BindingSHA256, Members: ir.Members}
		for _, m := range c.Members {
			c.Effects = append(c.Effects, contracts.EffectInputsOutput{SchemaVersion: 1, Capability: contracts.EffectInputsCapability, ContextSHA256: target.ConfigSHA256(), InputConfigSHA256: target.ConfigSHA256(), SourceManifestBodySHA256: req.Engine.SourceManifestSHA256, Seed: strconv.FormatUint(m.Seed, 10), CharacterKeys: actors, EffectInputs: []contracts.EffectInput{}, ResistanceInputs: []contracts.ResistanceInput{}})
		}
		return c, nil
	}
	cfg := CoordinatorConfig{MaxContexts: 3, MaxGuides: 2, SingleQueue: 8, TransferQueue: 2, FinalistLimit: 5, MaxSearchExpansions: 400, SearchTime: time.Minute, Search: search.DefaultConfig()}
	cfg.Search.MaxCycles = 1
	cfg.Search.MaxExpandedPerActor = 20
	return index, base, sources, provider, cfg
}

func TestCoordinatorGlobalBudgetAndDeterminism(t *testing.T) {
	index, base, sources, provider, cfg := coordinatorFixture(t)
	calls := 0
	counted := func(ctx context.Context, c *setcontext.Context) (setcontext.Capture, error) {
		calls++
		return provider(ctx, c)
	}
	r, e := Run(context.Background(), index, base, sources, counted, cfg)
	if e != nil {
		t.Fatal(e)
	}
	if calls != cfg.MaxContexts || r.CaptureMembers != cfg.MaxContexts*len(base.Seeds()) || r.SearchExpansions > cfg.MaxSearchExpansions || r.StopReason != "context_budget" {
		t.Fatal("global limits", calls, r)
	}
	if r.Leader.Score.DPS < r.Selected.Score.DPS || r.Selected.Score.DPS < r.Initial.Score.DPS {
		t.Fatal("lost baseline")
	}
	have := map[domain.Assignment]bool{}
	for _, c := range r.Finalists {
		if e := c.Index.ValidateAssignment(c.Score.Assignment); e != nil {
			t.Fatal(e)
		}
		if have[c.Score.Assignment] {
			t.Fatal("duplicate finalist")
		}
		have[c.Score.Assignment] = true
		if c.Handle.ContextKey() != c.Context.Key() {
			t.Fatal("stale finalist context")
		}
	}
	if !have[r.Initial.Score.Assignment] || !have[r.Selected.Score.Assignment] {
		t.Fatal("baseline comparison missing")
	}
	second, e := Run(context.Background(), index, base, sources, provider, cfg)
	if e != nil {
		t.Fatal(e)
	}
	a := []search.ScoredAssignment{}
	b := []search.ScoredAssignment{}
	for _, c := range r.Finalists {
		a = append(a, c.Score)
	}
	for _, c := range second.Finalists {
		b = append(b, c.Score)
	}
	if !reflect.DeepEqual(a, b) {
		x, _ := json.Marshal(a)
		y, _ := json.Marshal(b)
		t.Fatal("nondeterministic", string(x), string(y))
	}
}

func TestCoordinatorScoutsAllContextsBeforeBoundedDeepening(t *testing.T) {
	index, base, sources, provider, cfg := coordinatorFixture(t)
	cfg.DeepContextLimit = 2
	cfg.Scout = cfg.Search
	cfg.Scout.MaxExpandedPerActor = 5
	cfg.MaxSearchExpansions = 2000

	r, e := Run(context.Background(), index, base, sources, provider, cfg)
	if e != nil {
		t.Fatal(e)
	}
	scouts, deep := 0, 0
	for _, work := range r.Work {
		if strings.HasPrefix(work.Lane, "scout_") {
			scouts++
		}
		if strings.HasPrefix(work.Lane, "deep_") {
			deep++
		}
	}
	if scouts != cfg.MaxContexts-1 || deep != cfg.DeepContextLimit {
		t.Fatalf("unexpected two-stage work: scouts=%d deep=%d work=%#v", scouts, deep, r.Work)
	}
	if r.Leader.Score.DPS < r.Selected.Score.DPS || r.SearchExpansions > cfg.MaxSearchExpansions {
		t.Fatalf("two-stage search lost its safe baseline or budget: %#v", r)
	}
}

func TestCoordinatorPartialDeadlineDoesNotEraseSelected(t *testing.T) {
	index, base, sources, provider, cfg := coordinatorFixture(t)
	for _, failure := range []error{context.DeadlineExceeded, errors.New("corrupt engine evidence")} {
		calls := 0
		wrapped := func(ctx context.Context, c *setcontext.Context) (setcontext.Capture, error) {
			calls++
			if calls == 2 {
				return setcontext.Capture{}, failure
			}
			return provider(ctx, c)
		}
		r, e := Run(context.Background(), index, base, sources, wrapped, cfg)
		if calls != 2 || len(r.Finalists) == 0 || r.Selected.Context == nil {
			t.Fatal("lost partial result", calls, r.StopReason, e)
		}
		if errors.Is(failure, context.DeadlineExceeded) {
			if e != nil || r.StopReason != "search_deadline" {
				t.Fatal(e, r.StopReason)
			}
		} else if e == nil {
			t.Fatal("provenance failure hidden as success")
		}
	}
	cancelled, cancel := context.WithCancel(context.Background())
	cancel()
	if _, e := Run(cancelled, index, base, sources, provider, cfg); !errors.Is(e, context.Canceled) {
		t.Fatal("cancellation lost", e)
	}
	cfg.MaxSearchExpansions = 1
	calls := 0
	r, e := Run(context.Background(), index, base, sources, func(ctx context.Context, c *setcontext.Context) (setcontext.Capture, error) {
		calls++
		return provider(ctx, c)
	}, cfg)
	if e != nil || calls != 1 || r.StopReason != "search_expansion_budget" || len(r.Finalists) != 1 {
		t.Fatal("expansion budget", calls, e, r.StopReason)
	}
}

func TestProposalSchedulingKeepsBreadthAndUnknowns(t *testing.T) {
	pending := []contextProposal{{lane: "joint", wearer: -1}, {lane: "joint", wearer: -1}}
	for i := 0; i < 4; i++ {
		pending = append(pending, contextProposal{lane: "wearer", wearer: i})
	}
	pending = append(pending, contextProposal{wearer: 0, hint: Hint{Shared: true}}, contextProposal{wearer: 0, hint: Hint{NewOutput: true}}, contextProposal{wearer: 0, hint: Hint{Unresolved: true}})
	cursor, wearer := 0, 0
	order := []int{}
	for {
		n := pickProposal(pending, &cursor, &wearer)
		if n < 0 {
			break
		}
		order = append(order, n)
		pending[n].consumed = true
	}
	if !reflect.DeepEqual(order, []int{0, 2, 3, 1, 4, 5, 6, 7, 8}) {
		t.Fatal(order)
	}
}

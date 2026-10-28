package setcontext

// Opt-in source gate consumes neutral/control captures of one or two saved seeds in
// the managed job. No engine calls here. The distinct neutral route/ownership
// contract is proved before the product coordinator is changed.
import (
	"encoding/json"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

func TestNeutralModelSavedFixtureOwnershipAndResponse(t *testing.T) {
	job := os.Getenv("GTT_NEUTRAL_CAPTURE_DIR")
	if job == "" {
		t.Skip("managed neutral capture gate only")
	}
	if job != os.Getenv("GTT_SCRATCH_DIR") {
		t.Fatal("unowned scratch")
	}
	read := func(path string, target any) {
		t.Helper()
		body, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(body, target); err != nil {
			t.Fatal(err)
		}
	}
	var source seteffects.SourceBundle
	read(os.Getenv("GTT_RULE_SOURCE_BUNDLE"), &source)
	engine := contracts.EngineBinding{ArtifactSHA256: source.EngineSHA256, SourceManifestSHA256: source.SourceManifestSHA256, BindingSHA256: strings.Repeat("a", 64), PatchManifestSHA256: strings.Repeat("b", 64)}
	catalog, err := seteffects.CompileSourceBundle(source, engine, source.CatalogSHA256)
	if err != nil {
		t.Fatal(err)
	}
	suffixes := []string{""}
	if os.Getenv("GTT_NEUTRAL_TWO_SEEDS") == "1" {
		suffixes = append(suffixes, "-second")
	}
	var members, controls []contracts.IRSeedMember
	var effects []contracts.EffectInputsOutput
	for _, suffix := range suffixes {
		var member, control contracts.IRSeedMember
		var effect contracts.EffectInputsOutput
		read(filepath.Join(job, "neutral-member"+suffix+".json"), &member)
		read(filepath.Join(job, "neutral-member"+suffix+".json.effects.json"), &effect)
		read(filepath.Join(job, "control-member"+suffix+".json"), &control)
		members, controls, effects = append(members, member), append(controls, control), append(effects, effect)
	}
	sort.Slice(members, func(i, j int) bool { return members[i].Seed < members[j].Seed })
	sort.Slice(controls, func(i, j int) bool { return controls[i].Seed < controls[j].Seed })
	seeds := make([]uint64, len(members))
	for i := range members {
		seeds[i] = members[i].Seed
	}
	controlPanel, err := evaluator.CompileMembers([]string{"columbina", "flins", "ineffa", "jahoda"}, seeds, controls)
	if err != nil {
		t.Fatal(err)
	}
	want, err := controlPanel.EvaluateDPS(make([]float64, len(controlPanel.Coordinates())))
	if err != nil {
		t.Fatal(err)
	}
	text, err := os.ReadFile(filepath.Join(job, "neutral.txt"))
	if err != nil {
		t.Fatal(err)
	}
	binding := Binding{Engine: engine, CatalogSHA256: source.CatalogSHA256, ReferenceStatsSHA256: contracts.TextSHA256(string(text)), Seeds: seeds}
	neutral, err := New(binding, string(text))
	if err != nil {
		t.Fatal(err)
	}
	capture := Capture{ContextSHA256: neutral.Key(), ConfigSHA256: neutral.configSHA, EngineBindingSHA256: engine.BindingSHA256, Members: members, Effects: effects}
	compiled, err := compileCapture(neutral, capture)
	if err != nil {
		t.Fatal(err)
	}
	handle := &Handle{context: neutral, compiled: compiled, decision: Decision{Route: FreshCapture}}
	model, err := NewNeutralModel(handle, catalog)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = handle.EnergyMembers(); err == nil {
		t.Fatal("transferred raw evidence still borrowable")
	}
	if _, err = NewNeutralModel(handle, catalog); err == nil {
		t.Fatal("evidence transferred twice")
	}
	target, err := neutral.Replace(map[string][]Set{
		"flins": {{UID: "nightoftheskysunveiling", Count: 4}}, "ineffa": {{UID: "silkenmoonsserenade", Count: 4}},
		"columbina": {{UID: "tenacityofthemillelith", Count: 4}}, "jahoda": {{UID: "viridescentvenerer", Count: 4}},
	})
	if err != nil {
		t.Fatal(err)
	}
	for repeat := 0; repeat < 2; repeat++ {
		started := time.Now()
		got, boundaries, err := model.Resolve(target)
		if err != nil || got == nil || len(boundaries) > 0 {
			t.Fatal(boundaries, err)
		}
		t.Logf("neutral Resolve pass=%d seconds=%.6f", repeat, time.Since(started).Seconds())
		score, err := got.EvaluateDPS(nil)
		if err != nil || math.Abs(score-want) > 0.000001 {
			t.Fatal("neutral panel/control response mismatch", seeds, score, want, err)
		}
		t.Logf("neutral response seeds=%v model=%.9f independent_control=%.9f", seeds, score, want)
		if got.Route() != NeutralEffects || got.ContextKey() != target.Key() {
			t.Fatal("neutral model impersonates capture")
		}
		panel, err := got.SearchPanel()
		if err != nil {
			t.Fatal(err)
		}
		p, err := panel.ArtifactProgram(make([]float64, len(panel.Coordinates())), 0)
		if err != nil || !p.HasUnresolvedDependencies() {
			t.Fatal("approximation became a pruning certificate", err)
		}
		if _, err = got.EnergyMembers(); err == nil {
			t.Fatal("neutral energy evidence leaked to changed package")
		}
	}
	if model.Stats().ProgramHits < 1 || model.Stats().ProgramMisses != 1 {
		t.Fatal("identical full-vector program not reused", model.Stats())
	}
	parameterized, err := target.Replace(map[string][]Set{"flins": {{UID: "nightoftheskysunveiling", Count: 4, Parameters: " +params=[test=1]"}}})
	if err != nil {
		t.Fatal(err)
	}
	if h, boundaries, err := model.Resolve(parameterized); err != nil || h != nil || len(boundaries) == 0 {
		t.Fatal("unbound parameters accepted", h, boundaries, err)
	}
}

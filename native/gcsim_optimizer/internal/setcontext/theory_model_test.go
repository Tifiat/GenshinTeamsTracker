package setcontext

// Synthetic cache/route ownership checks; no engine or activation evidence.
import (
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func theoryCacheModel(t *testing.T) (*NeutralModel, *Context, [32]byte) {
	t.Helper()
	base := fixtureContext(t)
	captured, err := compileCapture(base, syntheticCapture(base, "100"))
	if err != nil {
		t.Fatal(err)
	}
	ports := []formula.EffectPort{}
	for member := range base.Seeds() {
		ports = append(ports, formula.EffectPort{Member: member, NodeID: 1, Key: "test", Observed: 100})
	}
	prepared, err := captured.panel.PrepareEffectInputs(ports)
	if err != nil {
		t.Fatal(err)
	}
	model := &NeutralModel{
		origin: base, panel: captured.panel, prepared: prepared, binding: &seteffects.NeutralBinding{},
		owners: map[string]int{}, specializations: formula.NewSpecializationCache(4, 1000),
	}
	for index, actor := range base.actors {
		model.owners[actor] = index
	}
	if _, err := model.bindProgram(map[string]*formula.InputExpression{"test": {Operation: "constant", Value: 0}}); err != nil {
		t.Fatal(err)
	}
	key := model.programOrder[0]
	model.targetPrograms = map[string]contextDispatch{base.key: {key: key, uncertainty: []string{"fixture_uncertainty"}}}
	model.effectDimensions, model.constantDimensions = []int{0}, []int{0}
	return model, base, key
}

func TestNeutralModelTheoryForkOwnsCachesAndRetainsFamilyIdentity(t *testing.T) {
	parent, target, key := theoryCacheModel(t)
	handle, family, codes, err := parent.TheoryFamily(target)
	if err != nil || handle == nil || len(codes) != 0 || !strings.HasPrefix(family, "program:") {
		t.Fatalf("synthetic cached family unavailable: %q %v %v", family, codes, err)
	}
	panel, err := handle.SearchPanel()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := panel.ArtifactProgram([]float64{0}, 0); err != nil {
		t.Fatal(err)
	}
	stats, cacheStats := parent.Stats(), parent.specializations.Stats()
	branch, sibling := parent.ForkTheory(), parent.ForkTheory()
	if branch.prepared == parent.prepared || branch.binding == parent.binding || branch.specializations == parent.specializations || branch.programCache[key] == parent.programCache[key] {
		t.Fatal("fork shared mutable model programs, binding, or cache")
	}
	child, childFamily, childCodes, err := branch.TheoryFamily(target)
	if err != nil || child == nil || childFamily != family || len(childCodes) != 0 {
		t.Fatalf("fork changed retained arithmetic family: %q %v %v", childFamily, childCodes, err)
	}
	childPanel, err := child.SearchPanel()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := childPanel.ArtifactProgram([]float64{0}, 0); err != nil {
		t.Fatal(err)
	}
	if branch.specializations.Stats().Hits != cacheStats.Hits+1 {
		t.Fatal("fork lost the retained specialization source identity")
	}
	if _, err := branch.programCache[key].Evaluate([]float64{9}, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := branch.bindProgram(map[string]*formula.InputExpression{"test": {Operation: "constant", Value: 1}}); err != nil {
		t.Fatal(err)
	}
	dispatch := branch.targetPrograms[target.key]
	dispatch.uncertainty[0] = "changed"
	branch.owners["actor_a"] = 3
	branch.programOrder[0] = [32]byte{9}
	branch.effectKeys[0], branch.constantKeys[0] = "changed", "changed"
	branch.effectDimensions[0], branch.constantDimensions[0] = 9, 9
	delete(branch.programCache, key)
	delete(branch.targetPrograms, target.key)
	if !reflect.DeepEqual(parent.Stats(), stats) || parent.specializations.Stats() != cacheStats || sibling.specializations.Stats() != cacheStats ||
		len(parent.programCache) != 1 || len(sibling.programCache) != 1 || parent.programCache[key] == nil ||
		parent.programOrder[0] != key || sibling.programOrder[0] != key || parent.targetPrograms[target.key].uncertainty[0] != "fixture_uncertainty" ||
		parent.owners["actor_a"] != 0 || parent.effectKeys[0] != "test" || parent.constantKeys[0] != "test" ||
		parent.effectDimensions[0] != 0 || parent.constantDimensions[0] != 0 {
		t.Fatal("child mutation changed parent/sibling cache, FIFO, diagnostics, dimensions, or counters")
	}
	value, err := parent.programCache[key].Evaluate([]float64{0}, nil)
	if err != nil || value != 100 {
		t.Fatalf("child cache scratch changed retained parent arithmetic: %g %v", value, err)
	}
}

func TestTheoryFamilyUnavailablePreservesOrdinaryResolveBoundary(t *testing.T) {
	parent, base, _ := theoryCacheModel(t)
	target := replaced(t, base, []Set{{UID: "unsupported", Count: 4}})
	branch := parent.ForkTheory()
	before := parent.Stats()
	handle, family, codes, err := branch.TheoryFamily(target)
	if err != nil || handle != nil || family != "" || !reflect.DeepEqual(codes, []string{"neutral binding is unavailable"}) {
		t.Fatalf("ordinary unavailable boundary was replaced: handle %v family %q codes %v err %v", handle, family, codes, err)
	}
	if branch.stats.Requests != before.Requests+1 || branch.stats.Unavailable != before.Unavailable+1 || !reflect.DeepEqual(parent.Stats(), before) {
		t.Fatal("unavailable child resolution changed parent counters or was not accounted")
	}
}

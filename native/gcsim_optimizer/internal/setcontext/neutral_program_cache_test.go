package setcontext

import (
	"crypto/sha256"
	"math"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

func TestNeutralSymbolicKeyMatchesIncrementalHashProtocol(t *testing.T) {
	shared := &formula.InputExpression{Operation: "constant", Value: 2}
	effects := map[string]*formula.InputExpression{
		"damage": {Operation: "add", Inputs: []*formula.InputExpression{{Operation: "read", Key: "owner-a.er"}, shared}},
		"latent": shared,
	}
	got, ok := symbolicEffectKey([]string{"latent", "damage"}, effects)
	if !ok {
		t.Fatal("valid graph rejected")
	}
	h := sha256.New()
	writeNeutralCacheString(h, "neutral-symbolic-program-v1")
	writeNeutralCacheUint64(h, 2)
	writeNeutralCacheString(h, "damage")
	node := func(id uint64, operation, key string, value float64, arity uint64) {
		h.Write([]byte{1})
		writeNeutralCacheUint64(h, id)
		writeNeutralCacheString(h, operation)
		writeNeutralCacheString(h, key)
		writeNeutralCacheUint64(h, math.Float64bits(value))
		writeNeutralCacheUint64(h, arity)
	}
	node(0, "add", "", 0, 2)
	node(1, "read", "owner-a.er", 0, 0)
	node(2, "constant", "", 2, 0)
	writeNeutralCacheString(h, "latent")
	h.Write([]byte{2})
	writeNeutralCacheUint64(h, 2)
	var want [32]byte
	copy(want[:], h.Sum(nil))
	if got != want {
		t.Fatal("buffering changed the expression identity protocol")
	}
}

func TestNeutralConstantProgramKeyRequiresFullVectorIdentity(t *testing.T) {
	keys := []string{"owner0/time1", "owner1/time2"}
	vector := map[string]*formula.InputExpression{keys[0]: {Operation: "constant", Value: 0}, keys[1]: {Operation: "constant", Value: 1}}
	key, ok := constantEffectKey(keys, vector)
	if !ok {
		t.Fatal("valid vector rejected")
	}
	for _, value := range []float64{2, math.SmallestNonzeroFloat64, math.Copysign(0, -1)} {
		vector[keys[0]].Value = value
		next, ok := constantEffectKey(keys, vector)
		if !ok || next == key {
			t.Fatal("different effect vectors merged", value)
		}
	}
	vector[keys[0]].Operation = "artifact"
	if _, ok := constantEffectKey(keys, vector); ok {
		t.Fatal("point-dependent expression cached")
	}
	delete(vector, keys[0])
	if _, ok := constantEffectKey(keys, vector); ok {
		t.Fatal("missing input cached")
	}
}

func TestNeutralConstantKeyProjectionRequiresAllInputsConstant(t *testing.T) {
	keys := []string{"damage", "latent"}
	live := keys[:1]
	x := map[string]*formula.InputExpression{"damage": {Operation: "constant", Value: 1}, "latent": {Operation: "constant", Value: 2}}
	key, ok := projectedConstantEffectKey(keys, live, x)
	if !ok {
		t.Fatal("valid projection rejected")
	}
	x["latent"].Value = 3
	if next, ok := projectedConstantEffectKey(keys, live, x); !ok || next != key {
		t.Fatal("unreachable constant changed damage key")
	}
	x["damage"].Value = 2
	if next, ok := projectedConstantEffectKey(keys, live, x); !ok || next == key {
		t.Fatal("damage input ignored")
	}
	for _, invalid := range []*formula.InputExpression{nil, {Operation: "artifact", Key: "a.atk"}, {Operation: "read", Key: "latent_read"}, {Operation: "constant", Value: math.Inf(1)}, {Operation: "constant", Inputs: []*formula.InputExpression{{Operation: "constant"}}}} {
		x["latent"] = invalid
		if _, ok := projectedConstantEffectKey(keys, live, x); ok {
			t.Fatal("invalid/nonconstant latent input admitted")
		}
	}
	delete(x, "latent")
	if _, ok := projectedConstantEffectKey(keys, live, x); ok {
		t.Fatal("missing input admitted")
	}
}

func TestNeutralProgramCacheIsBoundedAndEvictionKeepsLiveViews(t *testing.T) {
	base := fixtureContext(t)
	captured, err := compileCapture(base, syntheticCapture(base, "100"))
	if err != nil {
		t.Fatal(err)
	}
	ports := []formula.EffectPort{}
	for i := range base.Seeds() {
		ports = append(ports, formula.EffectPort{Member: i, NodeID: 1, Key: "test", Observed: 100})
	}
	prepared, err := captured.panel.PrepareEffectInputs(ports)
	if err != nil {
		t.Fatal(err)
	}
	m := &NeutralModel{prepared: prepared}
	effects := map[string]*formula.InputExpression{"test": {Operation: "constant", Value: 0}}
	first, err := m.bindProgram(effects)
	if err != nil {
		t.Fatal(err)
	}
	live := first.WithOwnScratch()
	keyDigest, _ := constantEffectKey(prepared.EffectKeys(), effects)
	key := taggedProgramCacheKey("constant", keyDigest)
	m.retainProgram(key, first)
	if len(m.programOrder) != 1 || m.programNodes != first.NodeCount() {
		t.Fatal("duplicate retention changed FIFO/node accounting", len(m.programOrder), m.programNodes)
	}
	for i := 0; i < neutralProgramEntries+1; i++ {
		effects["test"].Value = float64(i)
		if _, err = m.bindProgram(effects); err != nil {
			t.Fatal(err)
		}
		if len(m.programCache) > neutralProgramEntries || m.programNodes > neutralProgramNodes {
			t.Fatal("unbounded model cache", m.programNodes)
		}
	}
	if m.stats.ProgramHits != 1 || m.programCache[key] != nil {
		t.Fatal("FIFO/equality cache contract", m.stats)
	}
	want, err := first.Evaluate(make([]float64, len(first.Coordinates())), nil)
	if err != nil {
		t.Fatal(err)
	}
	got, err := live.Evaluate(make([]float64, len(live.Coordinates())), nil)
	if err != nil || got != want {
		t.Fatal("eviction altered retained candidate", got, want, err)
	}
}

func TestNeutralSymbolicProgramKeyIncludesAllRootsAndStructure(t *testing.T) {
	keys := []string{"damage", "latent"}
	shared := &formula.InputExpression{Operation: "constant", Value: 2}
	damage := &formula.InputExpression{Operation: "add", Inputs: []*formula.InputExpression{
		{Operation: "artifact", Key: "actor_a.em"}, shared,
	}}
	effects := map[string]*formula.InputExpression{
		"damage": damage,
		"latent": {Operation: "read", Key: "owner/actor_a/hp"},
	}
	key, ok := symbolicEffectKey(keys, effects)
	if !ok {
		t.Fatal("valid symbolic inputs rejected")
	}

	clone := map[string]*formula.InputExpression{
		"damage": {Operation: "add", Inputs: []*formula.InputExpression{
			{Operation: "artifact", Key: "actor_a.em"}, {Operation: "constant", Value: 2},
		}},
		"latent": {Operation: "read", Key: "owner/actor_a/hp"},
	}
	if next, ok := symbolicEffectKey(keys, clone); !ok || next != key {
		t.Fatal("equal expression structures did not share a key")
	}

	mutations := []func(map[string]*formula.InputExpression){
		func(x map[string]*formula.InputExpression) { x["latent"].Key = "owner/actor_b/hp" },
		func(x map[string]*formula.InputExpression) { x["damage"].Inputs[1].Value = 3 },
		func(x map[string]*formula.InputExpression) {
			x["damage"].Inputs[0], x["damage"].Inputs[1] = x["damage"].Inputs[1], x["damage"].Inputs[0]
		},
		func(x map[string]*formula.InputExpression) { x["damage"].Inputs[1].Value = math.Copysign(0, -1) },
	}
	for index, mutate := range mutations {
		candidate := map[string]*formula.InputExpression{
			"damage": {Operation: "add", Inputs: []*formula.InputExpression{
				{Operation: "artifact", Key: "actor_a.em"}, {Operation: "constant", Value: 2},
			}},
			"latent": {Operation: "read", Key: "owner/actor_a/hp"},
		}
		mutate(candidate)
		if next, ok := symbolicEffectKey(keys, candidate); !ok || next == key {
			t.Fatalf("structural mutation %d reused the original key", index)
		}
	}
	if _, ok := symbolicEffectKey(keys, map[string]*formula.InputExpression{"damage": damage}); ok {
		t.Fatal("missing latent expression root was cacheable")
	}
	positiveZero := map[string]*formula.InputExpression{
		"damage": {Operation: "constant", Value: 0},
		"latent": {Operation: "read", Key: "owner/actor_a/hp"},
	}
	negativeZero := map[string]*formula.InputExpression{
		"damage": {Operation: "constant", Value: math.Copysign(0, -1)},
		"latent": {Operation: "read", Key: "owner/actor_a/hp"},
	}
	positiveKey, positiveOK := symbolicEffectKey(keys, positiveZero)
	negativeKey, negativeOK := symbolicEffectKey(keys, negativeZero)
	if !positiveOK || !negativeOK || positiveKey == negativeKey {
		t.Fatal("symbolic key erased the sign of zero")
	}

	dag := map[string]*formula.InputExpression{
		"damage": {Operation: "add", Inputs: []*formula.InputExpression{shared, shared}},
		"latent": {Operation: "read", Key: "owner/actor_a/hp"},
	}
	tree := map[string]*formula.InputExpression{
		"damage": {Operation: "add", Inputs: []*formula.InputExpression{{Operation: "constant", Value: 2}, {Operation: "constant", Value: 2}}},
		"latent": {Operation: "read", Key: "owner/actor_a/hp"},
	}
	dagKey, dagOK := symbolicEffectKey(keys, dag)
	treeKey, treeOK := symbolicEffectKey(keys, tree)
	if !dagOK || !treeOK || dagKey == treeKey {
		t.Fatal("shared and duplicated expression nodes lost their distinct structure")
	}
}

func TestNeutralSymbolicProgramCacheRequiresExactSuccessfulBinding(t *testing.T) {
	base := fixtureContext(t)
	captured, err := compileCapture(base, syntheticCapture(base, "100"))
	if err != nil {
		t.Fatal(err)
	}
	ports := []formula.EffectPort{}
	for i := range base.Seeds() {
		ports = append(ports, formula.EffectPort{Member: i, NodeID: 1, Key: "test", Observed: 100})
	}
	reads := []formula.ReadRoot{
		{Member: 0, NodeID: 2, Key: "owner/actor_a/em", Observed: 0},
		{Member: 0, NodeID: 2, Key: "owner/actor_b/em", Observed: 0},
	}
	prepared, err := captured.panel.PrepareEffectInputsWithReads(ports, reads)
	if err != nil {
		t.Fatal(err)
	}
	m := &NeutralModel{prepared: prepared}
	makeEffects := func(readKey string, constant float64) map[string]*formula.InputExpression {
		return map[string]*formula.InputExpression{
			"test": {Operation: "add", Inputs: []*formula.InputExpression{
				{Operation: "read", Key: readKey}, {Operation: "constant", Value: constant},
			}},
		}
	}
	first, err := m.bindProgram(makeEffects("owner/actor_a/em", 1))
	if err != nil {
		t.Fatal("valid symbolic binding failed:", err)
	}
	same, err := m.bindProgram(makeEffects("owner/actor_a/em", 1))
	if err != nil || same != first || m.stats.ProgramHits != 1 {
		t.Fatal("equal symbolic structure missed cache", m.stats, err)
	}
	changedOwner, err := m.bindProgram(makeEffects("owner/actor_b/em", 1))
	if err != nil || changedOwner == first || m.stats.ProgramMisses != 2 {
		t.Fatal("changed read owner reused cached program", m.stats, err)
	}
	changedChild, err := m.bindProgram(makeEffects("owner/actor_a/em", 2))
	if err != nil || changedChild == first || m.stats.ProgramMisses != 3 {
		t.Fatal("changed constant child reused cached program", m.stats, err)
	}

	beforeEntries, beforeNodes := len(m.programCache), m.programNodes
	if _, err = m.bindProgram(map[string]*formula.InputExpression{}); err == nil {
		t.Fatal("missing effect accepted")
	}
	cycle := &formula.InputExpression{Operation: "add"}
	cycle.Inputs = []*formula.InputExpression{cycle, {Operation: "constant", Value: 1}}
	if _, err = m.bindProgram(map[string]*formula.InputExpression{"test": cycle}); err == nil {
		t.Fatal("cyclic expression accepted")
	}
	if _, err = m.bindProgram(map[string]*formula.InputExpression{"test": {Operation: "constant", Value: math.Inf(1)}}); err == nil {
		t.Fatal("nonfinite expression accepted")
	}
	if len(m.programCache) != beforeEntries || m.programNodes != beforeNodes {
		t.Fatal("failed bindings were retained", len(m.programCache), m.programNodes)
	}
}

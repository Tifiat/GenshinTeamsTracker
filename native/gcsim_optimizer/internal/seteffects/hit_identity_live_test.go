package seteffects

// Managed real-binary gate. This deliberately does not manufacture HitID:
// the producer must supply it before a real OnEnemyHit callback is replayed.
import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func TestLiveSongHitIdentityAndResponse(t *testing.T) {
	dir := os.Getenv("GTT_HIT_IDENTITY_GATE")
	if dir == "" {
		t.Skip("managed installed-lineage binary gate only")
	}
	c := activeRuleCatalog(t)
	read := func(name string, out any) {
		t.Helper()
		data, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(data, out); err != nil {
			t.Fatal(err)
		}
	}
	var neutral, control contracts.IRSeedMember
	var sidecar contracts.EffectInputsOutput
	read("song-neutral.json", &neutral)
	read("song-control.json", &control)
	read("song-neutral.json.effects.json", &sidecar)
	n := sidecar.Neutral
	if n == nil || n.Ledger.Truncated {
		t.Fatal("missing event tape")
	}
	hits := map[uint64]contracts.NeutralHitPoint{}
	for _, h := range n.Hits {
		if h.HitID == 0 || hits[h.HitID].HitID != 0 {
			t.Fatal("zero/duplicate terminal identity", h.HitID)
		}
		hits[h.HitID] = h
	}
	onHit := int(ruleTestConstant(t, c, "pkg/core/event", "OnEnemyHit"))
	seen, targets, frames := map[uint64]bool{}, map[float64]bool{}, map[int]int{}
	for _, e := range n.Ledger.Events {
		if e.Event != onHit {
			continue
		}
		id := uint64(e.Arguments[1].Fields["HitID"].Number)
		h, ok := hits[id]
		if id == 0 || !ok || seen[id] {
			t.Fatal("event identity is missing, duplicated, or unbound", id)
		}
		if h.Point.HitFrame != e.Frame || h.Point.TargetKey != int(e.Arguments[0].Fields["Key"].Number) || h.Actor != int(e.Arguments[1].Fields["Info"].Fields["ActorIndex"].Number) {
			t.Fatal("event linked to a different terminal hit", id)
		}
		seen[id] = true
		targets[e.Arguments[0].Fields["Key"].Number] = true
		frames[e.Frame]++
	}
	if len(seen) != len(hits) || len(targets) < 2 {
		t.Fatal("fixture did not cover all hits/multiple targets", len(seen), len(hits), targets)
	}
	multi := false
	for _, count := range frames {
		multi = multi || count > 1
	}
	if !multi {
		t.Fatal("fixture lacks simultaneous hits")
	}
	owners := append([]string(nil), sidecar.CharacterKeys...)
	sort.Strings(owners)
	panel, err := evaluator.CompileMembers(owners, []uint64{neutral.Seed}, []contracts.IRSeedMember{neutral})
	if err != nil {
		t.Fatal(err)
	}
	b, err := NewNeutralBinding(c, []contracts.EffectInputsOutput{sidecar})
	if err != nil {
		t.Fatal(err)
	}
	program, err := panel.PrepareEffectInputsWithReads(b.Ports(), b.Reads())
	if err != nil {
		t.Fatal(err)
	}
	healer := -1
	for i, key := range sidecar.CharacterKeys {
		if key == "sangonomiyakokomi" {
			healer = i
		}
	}
	if healer < 0 {
		t.Fatal("healer absent")
	}
	base := b.EvaluatePackages(nil)
	song := b.EvaluatePackages([]RuleChoice{{healer, "songofdayspast", 4}})
	if !base.Complete() || !song.Complete() {
		t.Fatal(base.Boundaries, song.Boundaries)
	}
	x := make([]float64, len(panel.Coordinates()))
	a, err := program.Evaluate(x, base.Values)
	if err != nil {
		t.Fatal(err)
	}
	predicted, err := program.Evaluate(x, song.Values)
	if err != nil {
		t.Fatal(err)
	}
	cp, err := evaluator.CompileMembers(owners, []uint64{control.Seed}, []contracts.IRSeedMember{control})
	if err != nil {
		t.Fatal(err)
	}
	measured, err := cp.Evaluate(make([]float64, len(cp.Coordinates())))
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("SONG_RESPONSE_BEFORE_ALIGNMENT_CHECK base=%.9f predicted=%.9f independent=%.9f residual=%.12g", a, predicted, measured.MeanDPS, predicted-measured.MeanDPS)
	if neutral.DurationMS != control.DurationMS || len(neutral.Channels) != len(control.Channels) {
		t.Fatal("controlled schedule changed")
	}
	// The compact topology hash also incorporates provenance/completeness guards.
	// Song's ordinary FlatDmg callback changes that guard; compare actual events
	// and per-hit scheduling facts, not a damage-provenance hash as a schedule.
	var rawA, rawB struct {
		Topology []json.RawMessage            `json:"topology_events"`
		Hits     []map[string]json.RawMessage `json:"hits"`
	}
	read("song-neutral-raw.json", &rawA)
	read("song-control-raw.json", &rawB)
	if !reflect.DeepEqual(rawA.Topology, rawB.Topology) || len(rawA.Hits) != len(rawB.Hits) {
		t.Fatal("raw topology changed")
	}
	for i, a := range rawA.Hits {
		for _, key := range []string{"attack_id", "hit_id", "parent_attack_id", "parent_hit_id", "parent_target_key", "frame", "source_frame", "snapshot_frame", "actor_index", "damage_src", "ability", "attack_tag", "element", "target_key", "target_type", "formula_kind", "reaction_operator_id", "icd_tag", "icd_group", "durability_initial", "durability_post_icd", "damage_group_multiplier", "aura_before", "aura_after_reaction", "aura_after_attachment"} {
			if _, ok := a[key]; !ok || !reflect.DeepEqual(a[key], rawB.Hits[i][key]) {
				t.Fatal("raw hit scheduling facts changed", i, key)
			}
		}
	}
	if predicted <= a || math.Abs(predicted-measured.MeanDPS) > 1e-7 {
		t.Fatalf("neutral %.12f predicted %.12f independent %.12f", a, predicted, measured.MeanDPS)
	}
	t.Logf("REAL_SONG_GATE hits=%d targets=%d same_frame=true base=%.9f predicted=%.9f independent=%.9f residual=%.12g uncertainty=%v", len(hits), len(targets), a, predicted, measured.MeanDPS, predicted-measured.MeanDPS, song.Uncertainty)
}

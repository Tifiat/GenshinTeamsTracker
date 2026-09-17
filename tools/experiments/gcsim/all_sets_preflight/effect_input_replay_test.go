package formula

// Overlay of actual native scorer; no alternate damage arithmetic. Fresh
// engine controls are the oracle. Node offsets are test/guide-only additions,
// not a claim that a real conditional set is active or replaces an old set.
import (
	"encoding/json"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"testing"
	"time"
)

type inputCapture struct {
	Member contracts.IRSeedMember `json:"member"`
	Inputs []struct {
		NodeID                           uint32 `json:"node_id"`
		Kind, Owner, AttackTag, Observed string
	} `json:"inputs"`
	Owners []string `json:"owners"`
	Owner  string   `json:"owner"`
}

func TestEffectInputCapturedResponses(t *testing.T) {
	dir := os.Getenv("GTT_EFFECT_INPUT_OUTPUT")
	rows := []any{}
	for _, name := range []string{"bloom", "cloud"} {
		load := func(mode string) inputCapture {
			b, e := os.ReadFile(filepath.Join(dir, name+"-"+mode+".json"))
			if e != nil {
				t.Fatal(e)
			}
			var c inputCapture
			if e = json.Unmarshal(b, &c); e != nil {
				t.Fatal(e)
			}
			return c
		}
		base, fresh := load("baseline"), load("offset")
		if base.Member.DurationMS != fresh.Member.DurationMS || len(base.Member.Channels) != len(fresh.Member.Channels) {
			t.Fatal("schedule changed", name)
		}
		for i, ch := range base.Member.Channels {
			other := fresh.Member.Channels[i]
			if ch.ActorKey != other.ActorKey || ch.AttackTag != other.AttackTag || ch.DamageType != other.DamageType {
				t.Fatal("channel alignment changed", name)
			}
		}
		coords := []string{}
		seen := map[string]bool{}
		for _, node := range base.Member.Nodes {
			if node.Operation == "artifact_stat" && !seen[node.Coordinate] {
				coords = append(coords, node.Coordinate)
				seen[node.Coordinate] = true
			}
		}
		sort.Strings(coords)
		nodes := []uint32{}
		offsets := map[uint32]float64{}
		for _, input := range base.Inputs {
			if input.Kind != "reaction_bonus" || input.Owner != base.Owner {
				continue
			}
			if _, ok := offsets[input.NodeID]; ok {
				t.Fatal("duplicate read binding")
			}
			nodes = append(nodes, input.NodeID)
			offsets[input.NodeID] = .1
		}
		p, e := CompileInterventions(base.Member, base.Owners, coords, nodes)
		if e != nil {
			t.Fatal(e)
		}
		zero := make([]float64, len(coords))
		_, e = p.Evaluate(zero, nil)
		if e != nil {
			t.Fatal(e)
		}
		for _, input := range base.Inputs {
			value, e := strconv.ParseFloat(input.Observed, 64)
			if e != nil {
				t.Fatal(e)
			}
			if math.Abs(p.values[input.NodeID]-value) > 1e-9*math.Max(1, math.Abs(value)) {
				t.Fatal("input value mismatch")
			}
		}
		started := time.Now()
		var got DenseMemberScore
		for i := 0; i < 100; i++ {
			got, e = p.Evaluate(zero, offsets)
			if e != nil {
				t.Fatal(e)
			}
		}
		probeSeconds := time.Since(started).Seconds() / 100
		want, e := EvaluateSeedMember(fresh.Member, nil)
		if e != nil {
			t.Fatal(e)
		}
		old, e := EvaluateSeedMember(base.Member, nil)
		if e != nil {
			t.Fatal(e)
		}
		relative := math.Abs(got.Damage-want.Damage) / math.Max(1, math.Abs(want.Damage))
		if relative > 1e-9 {
			t.Errorf("%s: response mismatch %g versus %g (%g)", name, got.Damage, want.Damage, relative)
		}
		scale := 1000 / float64(base.Member.DurationMS)
		rows = append(rows, map[string]any{"case": name, "owner": base.Owner, "inputs": len(nodes), "baseline_dps": old.Damage * scale, "predicted_dps": got.Damage * scale, "fresh_dps": want.Damage * scale, "relative_residual": relative, "one_offset_evaluation_seconds": probeSeconds, "new_engine_calls_in_replay": 0})
	}
	raw, e := json.MarshalIndent(rows, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(dir, "response-receipt.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
}

package seteffects

// Managed, read-only parity/profile on the user's saved neutral event panel.
// No simulator calls or persisted output; retire at the Flins acceptance gate.
import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestSavedPreparationParity(t *testing.T) {
	run := os.Getenv("GTT_SAVED_FEATHER_RUN")
	if run == "" {
		t.Skip("explicit saved-user panel only")
	}
	job := os.Getenv("GTT_SCRATCH_DIR")
	if job == "" || filepath.Dir(os.Getenv("GOCACHE")) != job {
		t.Fatal("managed job required")
	}
	c := activeRuleCatalog(t)
	paths, err := filepath.Glob(filepath.Join(run, "verification", "contexts", "context-*", "seed-*", "member.json.effects.json"))
	if err != nil {
		t.Fatal(err)
	}
	var sidecars []contracts.EffectInputsOutput
	for _, path := range paths {
		data, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		var s contracts.EffectInputsOutput
		if e = json.Unmarshal(data, &s); e != nil {
			t.Fatal(e)
		}
		if s.Neutral != nil && s.Neutral.Context.NoSets {
			sidecars = append(sidecars, s)
		}
	}
	if len(sidecars) != 2 {
		t.Fatal("expected the two saved neutral members", len(sidecars))
	}
	b, err := NewNeutralBinding(c, sidecars)
	if err != nil {
		t.Fatal(err)
	}
	owner := func(key string) int {
		for i, ch := range sidecars[0].Neutral.Context.Characters {
			if ch.Key == key {
				return i
			}
		}
		t.Fatal("missing owner", key)
		return -1
	}
	f, i, co, j := owner("flins"), owner("ineffa"), owner("columbina"), owner("jahoda")
	var cases [][]RuleChoice
	for _, key := range []string{"nightoftheskysunveiling", "obsidiancodex", "gladiatorsfinale", "shimenawasreminiscence", "aubadeofmorningstarandmoon", "silkenmoonsserenade"} {
		for _, pieces := range []int{2, 4} {
			cases = append(cases, []RuleChoice{{co, "noblesseoblige", 4}, {i, "noblesseoblige", 4}, {j, "viridescentvenerer", 4}, {f, key, pieces}})
		}
	}
	cases = append(cases, []RuleChoice{{co, "silkenmoonsserenade", 4}, {i, "aubadeofmorningstarandmoon", 4}, {j, "viridescentvenerer", 4}, {f, "nightoftheskysunveiling", 4}})
	// Include both a shared-key group and a stat-dependent full-replay fallback.
	cases = append(cases, []RuleChoice{{co, "noblesseoblige", 4}, {i, "noblesseoblige", 4}, {j, "viridescentvenerer", 4}, {f, "emblemofseveredfate", 4}})
	var fast, full float64
	for repeat := 0; repeat < 2; repeat++ {
		for _, choices := range cases {
			start := time.Now()
			got := b.CompilePackages(choices)
			fast += time.Since(start).Seconds()
			start = time.Now()
			want := b.compilePackagesJoint(choices)
			full += time.Since(start).Seconds()
			if !got.Complete() || !want.Complete() || !reflect.DeepEqual(got.Uncertainty, want.Uncertainty) || len(got.Effects) != len(want.Effects) {
				t.Fatalf("choices=%v boundaries=%v/%v uncertainty=%v/%v", choices, got.Boundaries, want.Boundaries, got.Uncertainty, want.Uncertainty)
			}
			for key, a := range got.Effects {
				bb := want.Effects[key]
				if a.Operation == "constant" && bb.Operation == "constant" {
					if math.Abs(a.Value-bb.Value) > 1e-12 {
						t.Fatal("constant parity", key, a.Value, bb.Value)
					}
				} else if !reflect.DeepEqual(a, bb) {
					t.Fatal("expression parity", key)
				}
			}
		}
	}
	fmt.Printf("SAVED_PREPARATION cases=%d fast_seconds=%.6f full_replay_seconds=%.6f stats=%+v\n", 2*len(cases), fast, full, b.PreparationStats())
	if b.stats.GroupHits == 0 {
		t.Fatal("saved conflict group never reused")
	}
}

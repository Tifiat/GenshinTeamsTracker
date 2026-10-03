package evaluator_test

// Explicit opt-in compiler gate using the retained small Flins witness and the
// CURRENT active engine through the production All Sets capture provider. It is
// not an optimizer/ordinary-DPS acceptance test or a set-lifecycle proof. Only
// managed scratch contains generated captures; no saved receipt is overwritten.
import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

func TestParametricActiveEngineWitness(t *testing.T) {
	if os.Getenv("GTT_PARAMETRIC_LIVE") != "1" {
		t.Skip("explicit managed active-engine gate only")
	}
	scratch := os.Getenv("GTT_SCRATCH_DIR")
	if scratch == "" || filepath.Dir(os.Getenv("GOCACHE")) != scratch {
		t.Fatal("managed scratch is required")
	}
	root := filepath.Join("..", "..", "..", "..")
	var receipt struct {
		Engine     contracts.EngineBinding `json:"engine"`
		Seeds      []uint64                `json:"seeds"`
		CatalogSHA string                  `json:"catalog_sha256"`
		Inputs     []struct {
			Name   string `json:"name"`
			Config string `json:"config"`
		} `json:"inputs"`
	}
	read := func(path string, target any) {
		t.Helper()
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(data, target); err != nil {
			t.Fatal(err)
		}
	}
	read(filepath.Join(root, "tests", "fixtures", "gcsim_optimizer_go_v1", "inventory_bound_poc_lineage5_v1.json"), &receipt)
	var active struct {
		ID string `json:"active_engine_id"`
	}
	read(filepath.Join(root, "data", "gcsim", "engines", "active_engine.json"), &active)
	expected, err := filepath.Abs(filepath.Join(root, "data", "gcsim", "engines", "engines", active.ID, "build", "gtt-gcsim.exe"))
	if err != nil {
		t.Fatal(err)
	}
	actual, err := filepath.Abs(receipt.Engine.BinaryPath)
	if err != nil || filepath.Clean(expected) != filepath.Clean(actual) {
		t.Fatal("saved witness is not the active button engine", actual, expected, err)
	}
	if len(receipt.Inputs) == 0 || len(receipt.Seeds) != 2 {
		t.Fatal("invalid retained witness")
	}
	config := receipt.Inputs[0].Config
	binding := setcontext.Binding{Engine: receipt.Engine, CatalogSHA256: receipt.CatalogSHA, ReferenceStatsSHA256: contracts.TextSHA256(config), Seeds: receipt.Seeds}
	c, err := setcontext.New(binding, config)
	if err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, scratch)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := provider.Close(); err != nil {
			t.Error(err)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	started := time.Now()
	capture, err := provider.Capture(ctx, c)
	if err != nil {
		t.Fatal(err)
	}
	captureMS := float64(time.Since(started)) / float64(time.Millisecond)
	actors := append([]string(nil), capture.Effects[0].CharacterKeys...)
	sort.Strings(actors)
	panel, err := evaluator.CompileMembers(actors, receipt.Seeds, capture.Members)
	if err != nil {
		t.Fatal(err)
	}
	coords := panel.Coordinates()
	members := []*formula.CompiledMember{}
	oracles := []*formula.InterventionProgram{}
	ports := []formula.EffectPort{}
	portNodes := [][]uint32{}
	originalNodes := 0
	for mi, m := range capture.Members {
		compiled, err := formula.CompileSeedMember(m, actors, coords)
		if err != nil {
			t.Fatal(err)
		}
		members = append(members, compiled)
		originalNodes += len(m.Nodes)
		nodes := []uint32{}
		for _, input := range capture.Effects[mi].EffectInputs {
			observed, err := strconv.ParseFloat(input.Observed, 64)
			if err != nil {
				t.Fatal(err)
			}
			nodes = append(nodes, input.NodeID)
			ports = append(ports, formula.EffectPort{Member: mi, NodeID: input.NodeID, Key: fmt.Sprintf("seed/%d/event/%s", m.Seed, input.EventID), Observed: observed})
		}
		for _, input := range capture.Effects[mi].ResistanceInputs {
			observed, err := strconv.ParseFloat(input.Observed, 64)
			if err != nil {
				t.Fatal(err)
			}
			nodes = append(nodes, input.NodeID)
			ports = append(ports, formula.EffectPort{Member: mi, NodeID: input.NodeID, Key: fmt.Sprintf("seed/%d/hit/%d", m.Seed, input.HitID), Observed: observed})
		}
		oracle, err := formula.CompileInterventions(m, actors, coords, nodes)
		if err != nil {
			t.Fatal(err)
		}
		oracles = append(oracles, oracle)
		portNodes = append(portNodes, nodes)
	}
	started = time.Now()
	prepared, err := formula.PrepareParametric(members, ports)
	if err != nil {
		t.Fatal(err)
	}
	prepareMS := float64(time.Since(started)) / float64(time.Millisecond)
	x := make([]float64, len(coords))
	effects := make([]float64, len(ports))
	maxResidual := 0.0
	const points = 24
	var preparedTime, oracleTime time.Duration
	for trial := 0; trial < points; trial++ {
		for j := range x {
			x[j] = float64((trial+j)%7-3) * .001
		}
		if trial == 0 {
			clear(x)
		}
		for j := range effects {
			effects[j] = float64((trial+j)%5-2) * .001
		}
		if trial == 0 {
			clear(effects)
		}
		started = time.Now()
		got, err := prepared.Evaluate(x, effects)
		preparedTime += time.Since(started)
		if err != nil {
			t.Fatal(err)
		}
		want, offset := 0.0, 0
		started = time.Now()
		for mi, oracle := range oracles {
			corrections := map[uint32]float64{}
			for _, node := range portNodes[mi] {
				corrections[node] = effects[offset]
				offset++
			}
			score, err := oracle.Evaluate(x, corrections)
			if err != nil {
				t.Fatal(err)
			}
			want += score.Damage / (float64(capture.Members[mi].DurationMS) / 1000) / float64(len(oracles))
		}
		oracleTime += time.Since(started)
		maxResidual = math.Max(maxResidual, math.Abs(want-got))
		if math.Abs(want-got) > 1e-8*(1+math.Abs(want)) {
			t.Fatalf("changed-input parity: got %g want %g", got, want)
		}
	}
	started = time.Now()
	plain, err := formula.PrepareParametric(members, nil)
	if err != nil {
		t.Fatal(err)
	}
	plainPrepareMS := float64(time.Since(started)) / float64(time.Millisecond)
	maxStatResidual := 0.0
	var freshTime, reuseTime time.Duration
	for trial := 0; trial < 4; trial++ {
		for j := range x {
			x[j] = float64(trial) * .001
		}
		want, err := panel.EvaluateDPS(x)
		if err != nil {
			t.Fatal(err)
		}
		for actor := range actors {
			started = time.Now()
			local, err := plain.Specialize(x, nil, actor)
			reuseTime += time.Since(started)
			if err != nil {
				t.Fatal(err)
			}
			started = time.Now()
			_, err = formula.SpecializeArtifacts(members, x, actor)
			freshTime += time.Since(started)
			if err != nil {
				t.Fatal(err)
			}
			v := make([]float64, len(local.Coordinates()))
			for k, key := range local.Coordinates() {
				for j, c := range coords {
					if c == key {
						v[k] = x[j]
					}
				}
			}
			got, err := local.Evaluate(v)
			if err != nil {
				t.Fatal(err)
			}
			maxStatResidual = math.Max(maxStatResidual, math.Abs(got-want))
			if math.Abs(got-want) > 1e-8*(1+math.Abs(want)) {
				t.Fatal("specialized whole-team response mismatch", got, want)
			}
		}
	}
	t.Logf("engine=%s config_sha256=%s two_seed_captures=2 ordinary_calls=0 source_nodes=%d parameter_nodes=%d artifact_only_nodes=%d ports=%d changed_points=%d max_dps_residual=%.12g stat_residual=%.12g capture_ms=%.3f param_prepare_ms=%.3f artifact_prepare_ms=%.3f param_eval_ms=%.3f reference_eval_ms=%.3f repeated_prepare_specialize_ms=%.3f retained_specialize_ms=%.3f",
		active.ID, contracts.TextSHA256(config), originalNodes, prepared.NodeCount(), plain.NodeCount(), len(ports), points, maxResidual, maxStatResidual, captureMS, prepareMS, plainPrepareMS, float64(preparedTime)/float64(time.Millisecond), float64(oracleTime)/float64(time.Millisecond), float64(freshTime)/float64(time.Millisecond), float64(reuseTime)/float64(time.Millisecond))
}

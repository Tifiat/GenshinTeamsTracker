package optimization

// Source-only gate attached by check_stat_queries.py to the CURRENT selected
// source. One saved config and one/two saved seeds, only set rows removed. No product
// search, ordinary finalist calls or deployment. Remove with the candidate
// observer gate after its installed replacement (Go design, neutral section).
import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/genshinsim/gcsim/pkg/gttcompact"
	"github.com/genshinsim/gcsim/pkg/simulator"
)

func TestNeutralCapturedFixture(t *testing.T) {
	job := os.Getenv("GTT_NEUTRAL_CAPTURE_DIR")
	if job == "" {
		t.Skip("managed neutral capture gate only")
	}
	if job != os.Getenv("GTT_SCRATCH_DIR") {
		t.Fatal("capture must remain in managed scratch")
	}
	var witness struct {
		Seeds  []uint64 `json:"seeds"`
		Inputs []struct {
			Config string `json:"config"`
		} `json:"inputs"`
	}
	data, err := os.ReadFile(os.Getenv("GTT_NEUTRAL_CAPTURE_FIXTURE"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(data, &witness); err != nil {
		t.Fatal(err)
	}
	if len(witness.Inputs) == 0 || len(witness.Seeds) != 2 {
		t.Fatal("missing retained witness")
	}
	// This fixture-only transformation accepts its exact prepared row grammar;
	// production uses setcontext.Context.Replace, not this test helper.
	row := regexp.MustCompile(`^[a-z][a-z0-9_]* add set="[a-z][a-z0-9_]*" count=4;$`)
	lines, removed := strings.Split(witness.Inputs[0].Config, "\n"), 0
	for i, line := range lines {
		if strings.Contains(line, "add set=") {
			if !row.MatchString(line) {
				t.Fatal("unexpected fixture set syntax")
			}
			lines[i] = ""
			removed++
		}
	}
	if removed != 4 {
		t.Fatal("fixture set count changed", removed)
	}
	config := []byte(strings.Join(lines, "\n"))
	seeds := witness.Seeds[:1]
	if os.Getenv("GTT_NEUTRAL_TWO_SEEDS") == "1" {
		seeds = witness.Seeds
	}
	for i, seed := range seeds {
		suffix := ""
		if i > 0 {
			suffix = "-second"
		}
		digest := sha256.Sum256(config)
		request := GTTTraceEquationRequest{SchemaVersion: 1, ContextSHA256: hex.EncodeToString(digest[:]),
			Seed: strconv.FormatUint(seed, 10), Iterations: 1, Workers: 1,
			IgnoreBurstEnergy: true, OutputMode: "compact_ir_v1", IncludeEffectInputs: true}
		requestData, err := json.Marshal(request)
		if err != nil {
			t.Fatal(err)
		}
		configPath, requestPath, resultPath := filepath.Join(job, "neutral.txt"), filepath.Join(job, "neutral-request.json"), filepath.Join(job, "neutral-member"+suffix+".json")
		for name, payload := range map[string][]byte{configPath: config, requestPath: requestData} {
			if err = os.WriteFile(name, payload, 0600); err != nil {
				t.Fatal(err)
			}
		}
		started := time.Now()
		if err = RunGTTTraceEquation(context.Background(), simulator.Options{ConfigPath: configPath, ResultSaveToPath: resultPath}, requestPath); err != nil {
			t.Fatal(err)
		}
		data, err = os.ReadFile(resultPath + ".effects.json")
		if err != nil {
			t.Fatal(err)
		}
		var sidecar struct {
			Neutral *gttcompact.NeutralInputs `json:"neutral"`
		}
		if err = json.Unmarshal(data, &sidecar); err != nil {
			t.Fatal(err)
		}
		n := sidecar.Neutral
		if n == nil || !n.Context.NoSets || n.World == nil || !n.World.Complete || n.Ledger.Truncated || len(n.Stats) == 0 || len(n.Hits) == 0 {
			t.Fatal("incomplete neutral capture")
		}
		if !n.ReadsComplete || len(n.Reads) == 0 {
			t.Fatal("latent stat observations missing")
		}
		t.Logf("latent read roots=%d", len(n.Reads))
		for _, char := range n.Context.Characters {
			if char.Facts["IsHexerei"].Kind != "bool" || char.Facts["NOCharIsSpecial"].Kind != "bool" || char.Facts["Weapon"].Fields["Class"].Kind != "number" {
				t.Fatal("neutral identity facts absent", char.Key)
			}
		}
		modes, zero := map[string]int{}, 0
		for _, p := range n.Stats {
			modes[p.Point.Mode]++
			if p.Point.Order == 0 {
				zero++
			}
		}
		t.Logf("neutral capture seed=%d %s: %.3fs, events=%d worlds=%d hits=%d ports=%d modes=%v unbound_order=%d sidecar_bytes=%d", seed, request.ContextSHA256, time.Since(started).Seconds(), len(n.Ledger.Events), len(n.World.States), len(n.Hits), len(n.Stats), modes, zero, len(data))
		// One independent positive response witness, not one capture per search
		// candidate. The untouched saved config has the four control packages.
		control := []byte(witness.Inputs[0].Config)
		digest = sha256.Sum256(control)
		request.ContextSHA256 = hex.EncodeToString(digest[:])
		request.IncludeEffectInputs = false
		requestData, err = json.Marshal(request)
		if err != nil {
			t.Fatal(err)
		}
		controlPath := filepath.Join(job, "control.txt")
		if err = os.WriteFile(controlPath, control, 0600); err != nil {
			t.Fatal(err)
		}
		if err = os.WriteFile(requestPath, requestData, 0600); err != nil {
			t.Fatal(err)
		}
		started = time.Now()
		if err = RunGTTTraceEquation(context.Background(), simulator.Options{ConfigPath: controlPath, ResultSaveToPath: filepath.Join(job, "control-member"+suffix+".json")}, requestPath); err != nil {
			t.Fatal(err)
		}
		t.Logf("independent control capture seed=%d %s: %.3fs; same saved seed/order/stats/rotation, original set rows", seed, request.ContextSHA256, time.Since(started).Seconds())
	}
}

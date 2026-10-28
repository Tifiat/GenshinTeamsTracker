package seteffects

// Read-only Chasca startup diagnosis, 2026-09-26. Replays an existing product
// event tape; never captures, searches or writes account/engine state. Opt-in
// only, with compiler output owned by managed_optimizer_experiment.py. Retire
// with the parametric research probes once the user-path startup gate closes.
import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestSavedInitialPackageDiagnosis(t *testing.T) {
	run := os.Getenv("GTT_SAVED_INITIAL_RUN")
	if run == "" {
		t.Skip("explicit saved product startup diagnosis only")
	}
	job := os.Getenv("GTT_SCRATCH_DIR")
	if job == "" || filepath.Dir(os.Getenv("GOCACHE")) != job {
		t.Fatal("managed compiler workspace required")
	}
	read := func(path string, value any) {
		t.Helper()
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(data, value); err != nil {
			t.Fatal(err)
		}
	}
	var req contracts.OptimizerRequest
	var bundle SourceBundle
	read(filepath.Join(run, "request.json"), &req)
	read(filepath.Join(run, "set-sources.json"), &bundle)
	if err := req.Validate(); err != nil {
		t.Fatal(err)
	}
	binary, err := os.ReadFile(req.Engine.BinaryPath)
	if err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(binary)
	if hex.EncodeToString(hash[:]) != req.Engine.ArtifactSHA256 {
		t.Fatal("saved engine identity no longer matches")
	}
	catalog, err := CompileSourceBundleForInventory(bundle, req.Engine, bundle.CatalogSHA256, req.Artifacts)
	if err != nil {
		t.Fatal(err)
	}
	paths, err := filepath.Glob(filepath.Join(run, "verification", "contexts", "context-*", "seed-*", "member.json.effects.json"))
	if err != nil || len(paths) != len(req.Stochastic.Seeds) {
		t.Fatalf("unexpected saved panel: %v, members=%d", err, len(paths))
	}
	var sidecars []contracts.EffectInputsOutput
	for _, path := range paths {
		var sidecar contracts.EffectInputsOutput
		read(path, &sidecar)
		member, e := os.ReadFile(filepath.Join(filepath.Dir(path), "member.json"))
		if e != nil {
			t.Fatal(e)
		}
		hash := sha256.Sum256(member)
		if hex.EncodeToString(hash[:]) != sidecar.MemberContentSHA256 {
			t.Fatal("saved member/sidecar identity differs")
		}
		sidecars = append(sidecars, sidecar)
	}
	binding, err := NewNeutralBinding(catalog, sidecars)
	if err != nil {
		t.Fatal(err)
	}
	var choices []RuleChoice
	for _, wearer := range req.Wearers {
		owner := -1
		for i, actor := range sidecars[0].Neutral.Context.Characters {
			if actor.Key == wearer.WearerKey {
				owner = i
			}
		}
		if owner < 0 {
			t.Fatal("saved wearer absent from neutral tape", wearer.WearerKey)
		}
		for _, set := range wearer.SetRequirements() {
			choices = append(choices, RuleChoice{Owner: owner, Key: set.SetUID, Pieces: set.Count})
		}
	}
	cases := [][]RuleChoice{nil, choices}
	for _, choice := range choices {
		cases = append(cases, []RuleChoice{{Owner: choice.Owner, Key: choice.Key, Pieces: 2}}, []RuleChoice{choice})
	}
	for _, test := range cases {
		fast := binding.CompilePackages(test)
		compact := binding.CompilePackagesCompact(test)
		full := binding.compilePackagesJoint(test)
		t.Logf("SAVED_INITIAL choices=%v complete=%v boundaries=%v uncertainty=%v full_boundaries=%v", test, fast.Complete(), fast.Boundaries, fast.Uncertainty, full.Boundaries)
		if fast.Complete() != full.Complete() || !reflect.DeepEqual(fast.Boundaries, full.Boundaries) {
			t.Fatal("cached/full replay boundary mismatch")
		}
		if compact.Complete() != fast.Complete() || !reflect.DeepEqual(compact.Boundaries, fast.Boundaries) {
			t.Fatal("map/compact replay boundary mismatch")
		}
		if os.Getenv("GTT_REQUIRE_INITIAL_COMPLETE") == "1" && !fast.Complete() {
			t.Fatal("repaired initial package still has unknown inputs", fast.Boundaries)
		}
	}
	for i, member := range binding.members {
		queries := make([]RuleQuery, len(member.ports))
		for j, port := range member.ports {
			queries[j] = port.query
		}
		replay := catalog.CompileNeutralRules(member.neutral, choices, queries)
		failures := map[string]int{}
		first := false
		for j, value := range replay.Values {
			if value.Known {
				continue
			}
			q := queries[j]
			owner := member.neutral.Context.Characters[q.Owner].Key
			failures[owner+":"+q.Stat+":"+q.Mode+":"+value.Boundary]++
			if !first {
				t.Logf("SAVED_INITIAL first_unknown seed=%s query=%+v boundary=%s", sidecars[i].Seed, q, value.Boundary)
				first = true
			}
		}
		encoded, err := json.Marshal(failures)
		if err != nil {
			t.Fatal(err)
		}
		t.Logf("SAVED_INITIAL unknown_counts seed=%s counts=%s", sidecars[i].Seed, encoded)
		if os.Getenv("GTT_REQUIRE_INITIAL_COMPLETE") == "1" && len(failures) != 0 {
			t.Fatal("repaired initial package has unknown query ports")
		}
	}
}

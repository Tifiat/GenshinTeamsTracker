package setcontext

// Overlay-only regression over the retained seven engine captures. Names are
// fixture data, never production routing rules. This validates the new context
// renderer/cache/compiler boundary, not a broad static-effect proof producer.
import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

func TestAllSetsContextReplay(t *testing.T) {
	started := time.Now()
	matrix, source, output := os.Getenv("GTT_SET_CONTEXT_MATRIX"), os.Getenv("GTT_SET_CONTEXT_SOURCE"), os.Getenv("GTT_SET_CONTEXT_OUTPUT")
	if matrix == "" || source == "" || output == "" {
		t.Fatal("explicit retained evidence/output paths required")
	}
	read := func(path string) []byte {
		t.Helper()
		b, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	decode := func(path string, dst any) {
		t.Helper()
		if e := json.Unmarshal(read(path), dst); e != nil {
			t.Fatal(e)
		}
	}
	var req contracts.OptimizerRequest
	decode(filepath.Join(source, "request.json"), &req)
	if err := req.Validate(); err != nil {
		t.Fatal(err)
	}
	var catalog struct {
		CatalogFingerprint string `json:"catalog_fingerprint"`
		EngineSHA          string `json:"engine_sha256"`
	}
	decode(filepath.Join(matrix, "catalog.json"), &catalog)
	if catalog.EngineSHA != req.Engine.ArtifactSHA256 {
		t.Fatal("engine fixture binding drift")
	}
	original := string(read(filepath.Join(source, "prepared-config.txt")))
	var refs []string
	for _, line := range strings.Split(original, "\n") {
		if strings.Contains(line, " add stats ") {
			refs = append(refs, line)
		}
	}
	if len(refs) != 4 {
		t.Fatal("reference rows")
	}
	binding := Binding{Engine: req.Engine, CatalogSHA256: catalog.CatalogFingerprint, ReferenceStatsSHA256: contracts.TextSHA256(strings.Join(refs, "\n")), Seeds: req.Stochastic.Seeds[:1]}
	base, err := New(binding, original)
	if err != nil {
		t.Fatal(err)
	}
	var rows []struct {
		Case      string
		SHA       string `json:"sha256"`
		ConfigSHA string `json:"config_sha256"`
		Hits      int
	}
	decode(filepath.Join(matrix, "captures.json"), &rows)
	if len(rows) != 7 {
		t.Fatal("frozen replay matrix changed")
	}
	var timings struct {
		BaseSHA string `json:"source_base_sha256"`
	}
	decode(filepath.Join(matrix, "timings.json"), &timings)
	contexts := map[string]*Context{base.key: base}
	oracles := map[string]contracts.IRSeedMember{}
	loadMember := func(path, wantSHA string) contracts.IRSeedMember {
		b := read(path)
		if contracts.TextSHA256(string(b)) != wantSHA {
			t.Fatal("capture file identity changed:", path)
		}
		v, e := contracts.DecodeSeedMember(b)
		if e != nil {
			t.Fatal(e)
		}
		return v
	}
	oracles[base.key] = loadMember(filepath.Join(matrix, "base.json"), timings.BaseSHA)
	targets := make([]*Context, 0, len(rows))
	for _, row := range rows {
		text := string(read(filepath.Join(matrix, row.Case+".txt")))
		expected, e := New(binding, text)
		if e != nil {
			t.Fatal(e)
		}
		if expected.configSHA != row.ConfigSHA {
			t.Fatal("config identity drift")
		}
		var captureRequest struct {
			ContextSHA   string `json:"context_sha256"`
			Seed         string
			IgnoreEnergy bool `json:"ignore_burst_energy"`
		}
		decode(filepath.Join(matrix, row.Case+"-request.json"), &captureRequest)
		if captureRequest.ContextSHA != expected.configSHA || captureRequest.Seed != strconv.FormatUint(binding.Seeds[0], 10) || !captureRequest.IgnoreEnergy {
			t.Fatal("capture request binding drift")
		}
		changes := map[string][]Set{}
		for _, actor := range base.actors {
			if !reflect.DeepEqual(base.Sets(actor), expected.Sets(actor)) {
				changes[actor] = expected.Sets(actor)
			}
		}
		// The old Python probe wrote changed configs with Windows CRLF while
		// the original capture used LF. Keep capture identities byte-exact;
		// test rendering against a same-newline base instead of laundering a
		// CRLF capture into an LF identity. No product normalization is added.
		renderSource := original
		if strings.Contains(text, "\r\n") && !strings.Contains(original, "\r\n") {
			renderSource = strings.ReplaceAll(original, "\n", "\r\n")
		}
		renderBase, e := New(binding, renderSource)
		if e != nil {
			t.Fatal(e)
		}
		rendered, e := renderBase.Replace(changes)
		if e != nil {
			t.Fatal(e)
		}
		if rendered.text != text || rendered.key != expected.key || rendered.frameKey != renderBase.frameKey {
			t.Fatal("renderer changed non-set context", row.Case)
		}
		contexts[rendered.key] = rendered
		targets = append(targets, rendered)
		oracles[rendered.key] = loadMember(filepath.Join(matrix, row.Case+".json"), row.SHA)
	}
	loads := 0
	s, err := NewSession(func(_ context.Context, c *Context) (Capture, error) {
		loads++
		m, ok := oracles[c.key]
		if !ok {
			t.Fatal("unexpected capture request")
		}
		return Capture{ContextSHA256:c.key, ConfigSHA256:c.configSHA, EngineBindingSHA256:c.binding.Engine.BindingSHA256, Members:[]contracts.IRSeedMember{m}}, nil
	}, 8)
	if err != nil {
		t.Fatal(err)
	}
	baseHandle, err := s.Resolve(context.Background(), base, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	results := make([]map[string]any, 0, len(rows))
	for i, target := range targets {
		tick := time.Now()
		// All changed probe configs share CRLF. Check set-only routing against
		// another real captured context too; otherwise the original LF->CRLF
		// identity guard would mask the effect-replacement decision in this test.
		neighbor := targets[(i+1)%len(targets)]
		policy := Decide(neighbor, target, "", nil, nil)
		if policy.Route != FreshCapture || policy.Reason != "unproved_effect_change" {
			t.Fatal("same-frame real effect change bypassed the proof gate", rows[i].Case, policy)
		}
		h, e := s.Resolve(context.Background(), target, baseHandle, nil)
		if e != nil {
			t.Fatal(e)
		}
		if h.Route() != FreshCapture {
			t.Fatal("unproved real set transition reused old graph")
		}
		got, e := h.EvaluateDPS(nil)
		if e != nil {
			t.Fatal(e)
		}
		m := oracles[target.key]
		want := 0.0
		for _, ch := range m.Channels {
			v, _ := strconv.ParseFloat(ch.BaselineDamage, 64)
			want += v
		}
		want /= float64(m.DurationMS) / 1000
		if math.Abs(got-want) > 1e-7 || h.HitCount() != rows[i].Hits {
			t.Fatalf("fresh graph mismatch %s: %.12f %.12f", rows[i].Case, got, want)
		}
		// Separate compiler-parity check, not another changed-engine oracle.
		raw := map[string]float64{"lauma.em": 40, "kukishinobu.em": -30}
		changed, e := h.EvaluateDPS(raw)
		if e != nil {
			t.Fatal(e)
		}
		interpreted, e := formula.EvaluateSeedMember(m, raw)
		if e != nil {
			t.Fatal(e)
		}
		if math.Abs(changed-interpreted.Damage/(float64(m.DurationMS)/1000)) > 1e-7 {
			t.Fatal("shared compiler response mismatch")
		}
		cached, e := s.Resolve(context.Background(), target, baseHandle, nil)
		if e != nil || cached.Route() != IdentityReuse {
			t.Fatal("complete context cache miss")
		}
		restored, e := s.Resolve(context.Background(), base, h, nil)
		if e != nil || restored.Route() != IdentityReuse {
			t.Fatal("restoration did not reuse original context")
		}
		results = append(results, map[string]any{"case": rows[i].Case, "route": h.Route(), "reason": h.Reason(), "same_frame_policy_reason": policy.Reason, "hits": h.HitCount(), "same_topology": m.TopologySHA256 == oracles[base.key].TopologySHA256, "baseline_dps": got, "absolute_baseline_error": math.Abs(got - want), "cached_reuse": true, "restoration_reuse": true, "resolve_evaluate_ms": float64(time.Since(tick).Microseconds()) / 1000})
	}
	if loads != 8 || s.AttemptedCaptureMembers() != 8 {
		t.Fatal("duplicate provider work")
	}
	receipt := map[string]any{"schema_version": 1, "date": "2026-09-16", "authority": "docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md", "status": "bounded_context_routing_replay_pass", "engine_sha256": req.Engine.ArtifactSHA256, "new_engine_calls": 0, "replayed_members": loads, "context_cases": results, "static_proof_scope": "synthetic complete model only; no real-set structural proof producer enabled", "product_seed_policy_changed": false, "production_ui_or_binary_changed": false, "elapsed_test_seconds": time.Since(started).Seconds()}
	b, err := json.MarshalIndent(receipt, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(output, "context-routing-receipt.json"), b, 0600); err != nil {
		t.Fatal(err)
	}
	t.Logf("PASS: seven real set transitions, eight retained members, zero engine calls; %.3fs", time.Since(started).Seconds())
}

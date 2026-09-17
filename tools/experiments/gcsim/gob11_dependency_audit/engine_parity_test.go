package optimization

// Run through the installed build's generated overlay, not uninstrumented
// source. No gameplay formula is reimplemented by this diagnostic.
import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"testing"

	"github.com/genshinsim/gcsim/pkg/core/event"
	"github.com/genshinsim/gcsim/pkg/core/info"
	"github.com/genshinsim/gcsim/pkg/gcs/ast"
	"github.com/genshinsim/gcsim/pkg/gcs/eval"
	"github.com/genshinsim/gcsim/pkg/gcs/parser"
	"github.com/genshinsim/gcsim/pkg/gttcompact"
	"github.com/genshinsim/gcsim/pkg/optimization/optstats"
	"github.com/genshinsim/gcsim/pkg/simulation"
)

type auditHit struct {
	Frame, Actor int
	Ability      string
	Damage       float64
}

func TestDependencyAuditOrdinaryParity(t *testing.T) {
	dir := os.Getenv("GTT_AUDIT_MATRIX")
	if dir == "" {
		t.Skip("explicit fixture directory required")
	}
	data, err := os.ReadFile(filepath.Join(dir, "jobs.json"))
	if err != nil {
		t.Fatal(err)
	}
	var jobs []struct {
		Case, Config string
		Baseline     bool
	}
	if err = json.Unmarshal(data, &jobs); err != nil {
		t.Fatal(err)
	}
	rows := []any{}
	only := os.Getenv("GTT_AUDIT_CASE")
	for _, job := range jobs {
		if only != "" && job.Case != only {
			continue
		}
		if only == "" && !job.Baseline && job.Config != "spread-tighnari-em-1000.txt" && job.Config != "chasca-bennett-hp_percent-0.466.txt" && job.Config != "flins_1-columbina-hp_percent-0.466.txt" {
			continue
		}
		var modes [2][]auditHit
		var frames [2]int
		var trace optstats.GTTTraceEquationBuffer
		keys := []string{}
		for mode := 0; mode < 2; mode++ {
			content, e := os.ReadFile(filepath.Join(dir, job.Config))
			if e != nil {
				t.Fatal(e)
			}
			file := ast.NewFile()
			cfg, node, e := parser.New(file, string(content)).Parse()
			if e != nil {
				t.Fatal(e)
			}
			cfg.Settings.Iterations = 1
			cfg.Settings.NumberOfWorkers = 1
			cfg.Settings.IgnoreBurstEnergy = true
			cfg.Settings.CollectStats = []string{""}
			core, e := simulation.NewCore(742031889, false, cfg)
			if e != nil {
				t.Fatal(e)
			}
			if mode == 1 {
				optstats.PrepareOptimizerTraceEquation(core)
			}
			evaluator, e := eval.NewEvaluator(file, node, core)
			if e != nil {
				t.Fatal(e)
			}
			sim, e := simulation.New(cfg, evaluator, core)
			if e != nil {
				t.Fatal(e)
			}
			core.Events.Subscribe(event.OnEnemyDamage, func(args ...any) {
				if args[0].(info.Target).Type() != info.TargettableEnemy {
					return
				}
				a := args[1].(*info.AttackEvent)
				modes[mode] = append(modes[mode], auditHit{core.F, a.Info.ActorIndex, a.Info.Abil, args[2].(float64)})
			}, "dependency-audit-parity")
			var collector optstats.CollectorCustomStats[optstats.GTTTraceEquationBuffer]
			if mode == 1 {
				collector, e = optstats.OptimizerTraceEquation(core)
				if e != nil {
					t.Fatal(e)
				}
			}
			if _, e = sim.Run(); e != nil {
				t.Fatal(e)
			}
			frames[mode] = core.F
			if mode == 1 {
				trace = collector.Flush(core)
				trace.Seed = 742031889
				trace.DurationFrames = core.F
				for _, ch := range core.Player.Chars() {
					keys = append(keys, ch.Base.Key.String())
				}
			}
		}
		equal := frames[0] == frames[1] && len(modes[0]) == len(modes[1])
		maxDiff := 0.0
		if equal {
			for i, a := range modes[0] {
				b := modes[1][i]
				maxDiff = math.Max(maxDiff, math.Abs(a.Damage-b.Damage))
				if a.Frame != b.Frame || a.Actor != b.Actor || a.Ability != b.Ability || a.Damage != b.Damage {
					equal = false
					break
				}
			}
		}
		if !equal {
			t.Errorf("%s: tracing altered original simulation; diff %g", job.Config, maxDiff)
		}
		coverage := map[string]int{}
		contributorSizes := map[int]int{}
		for _, h := range trace.Hits {
			reaction := ""
			if h.ReactionFormula != nil {
				reaction = h.ReactionFormula.ReactionType
			}
			key := fmt.Sprintf("%s/%s/%s/amp=%t", h.FormulaKind, reaction, h.Element, h.AmpTotal > 1)
			coverage[key]++
			if h.ContributorGroup != nil {
				contributorSizes[len(h.ContributorGroup.Contributors)]++
			}
		}
		rows = append(rows, map[string]any{"case": job.Case, "config": job.Config, "ordinary_trace_exact": equal, "hits": len(trace.Hits), "frames": frames, "max_damage_difference": maxDiff, "coverage": coverage, "contributor_sizes": contributorSizes})
		if only != "" {
			// Observed values only; no copied gameplay formula or changed source.
			compact, _, e := gttcompact.CompileSeedMember(trace, keys)
			if e != nil {
				t.Fatal(e)
			}
			payload, e := json.Marshal(map[string]any{"hits": trace.Hits, "bindings": trace.SourceValueBindings, "support_graph": gttcompact.DependencyAuditSupportGraph(trace, keys), "state_events": trace.StateEvents, "compact_graph": compact})
			if e != nil {
				t.Fatal(e)
			}
			if e = os.WriteFile(filepath.Join(dir, job.Config+".observed.json"), payload, 0600); e != nil {
				t.Fatal(e)
			}
		}
		// Narrow diagnostic for the only remaining fixed-schedule residual.
		if job.Case == "spread" {
			payload, e := json.MarshalIndent(trace.Hits, "", " ")
			if e != nil {
				t.Fatal(e)
			}
			if e = os.WriteFile(filepath.Join(dir, job.Config+".hits.json"), payload, 0600); e != nil {
				t.Fatal(e)
			}
		}
	}
	payload, err := json.MarshalIndent(rows, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	name := "ordinary-parity-coverage.json"
	if only != "" {
		name = "ordinary-parity-coverage-" + only + ".json"
	}
	if err = os.WriteFile(filepath.Join(dir, name), payload, 0600); err != nil {
		t.Fatal(err)
	}
}

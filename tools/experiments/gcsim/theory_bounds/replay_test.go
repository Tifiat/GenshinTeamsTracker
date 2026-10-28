package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
)

func TestTheorySlackReplay(t *testing.T) {
	path := os.Getenv("GTT_SLACK_REPLAY")
	if path == "" {
		t.Skip("explicit managed replay only")
	}
	var fixture struct {
		DAG           formula.ResearchDAG `json:"dag"`
		Baseline      []float64           `json:"baseline"`
		AbsolutePoint []float64           `json:"absolute_point"`
		ReplayValue   float64             `json:"replay_value"`
		Candidate     struct {
			State    proto.State `json:"feasibility_witness"`
			Packages []struct {
				WearerKey string `json:"wearer_key"`
			} `json:"packages"`
		} `json:"candidate"`
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	p, err := formula.ResearchRestore(fixture.DAG)
	if err != nil {
		t.Fatal(err)
	}
	if err = fixture.Candidate.State.Validate(45, true); err != nil {
		t.Fatal(err)
	}
	e := &feasibleEntry{program: p, coords: p.Coordinates(), baseline: fixture.Baseline, family: "replay:" + fixture.DAG.SHA256}
	if len(e.baseline) != len(e.coords) || len(fixture.AbsolutePoint) != len(e.coords) || len(fixture.Candidate.Packages) != 4 {
		t.Fatal("fixture reference shape")
	}
	req := contracts.OptimizerRequest{}
	for a, w := range fixture.Candidate.Packages {
		req.Wearers = append(req.Wearers, contracts.Wearer{WearerKey: w.WearerKey})
		for j, k := range proto.StatKeys {
			e.indices[a][j] = -1
			for i, c := range e.coords {
				if c == w.WearerKey+"."+k {
					e.indices[a][j] = i
				}
			}
		}
	}
	point := slackPoint(e, fixture.Candidate.State)
	delta := append([]float64(nil), point...)
	for i := range delta {
		if point[i] != fixture.AbsolutePoint[i] {
			t.Fatal("witness/reference mismatch", i)
		}
		delta[i] += e.baseline[i]
	}
	lower, err := p.Evaluate(delta)
	if err != nil || lower != fixture.ReplayValue {
		t.Fatal("replay scalar mismatch", lower, fixture.ReplayValue, err)
	}
	for _, mode := range []string{"baseline_midpoint", "baseline_legal_center", "caps_only", "rational_only", "caps_and_rational"} {
		stage := time.Now()
		d, err := newBoundDomain(e, req)
		if err != nil {
			t.Fatal(err)
		}
		box := d.box()
		center, ref, support := slackParameters(d, box)
		if mode == "baseline_legal_center" {
			center = point
		}
		caps, rationals := 0, 0
		var u float64
		if mode == "baseline_midpoint" || mode == "baseline_legal_center" {
			u = p.ResearchEnvelope(center, ref, support, false).ModelUpper
		} else {
			r := p.ResearchTargeted(center, ref, support, mode != "rational_only", mode != "caps_only")
			u = r.ModelUpper
			caps, rationals = r.Caps, r.Rationals
		}
		if u < lower-1e-6 {
			t.Fatal("replay enclosure below legal point", mode, u, lower)
		}
		emitFeasible(map[string]any{"kind": "slack_offline_root", "variant": mode, "seconds": time.Since(stage).Seconds(), "model_upper": boundNumber(u), "lower": lower, "gap": boundNumber(u - lower), "caps": caps, "rational_blocks": rationals, "strict_upper": "unbounded", "fixture_sha256": fixture.DAG.SHA256})
	}
	// Equal-cost curves for this ONE fixed control; distinct from the original
	// four-control frontier and its top-two threshold. No new lower solve.
	for _, targeted := range []bool{false, true} {
		started := time.Now()
		d, err := newBoundDomain(e, req)
		if err != nil {
			t.Fatal(err)
		}
		root := d.box()
		bound := func(box [][2]float64) float64 {
			center, ref, support := slackParameters(d, box)
			if targeted {
				return p.ResearchTargeted(center, ref, support, true, true).ModelUpper
			}
			return p.ResearchEnvelope(center, ref, support, false).ModelUpper
		}
		type region struct {
			box [][2]float64
			u   float64
		}
		live := []region{{root, bound(root)}}
		splits, pruned := 0, 0
		levels := []float64{.5, 2, 4.8}
		next := 0
		emit := func(level string) {
			u := math.Inf(-1)
			for _, r := range live {
				u = math.Max(u, r.u)
			}
			emitFeasible(map[string]any{"kind": "slack_offline_curve", "targeted": targeted, "level": level, "seconds": time.Since(started).Seconds(), "splits": splits, "live_regions": len(live), "model_pruned": pruned, "model_upper": boundNumber(u), "lower": lower, "source_pruned": 0, "source_upper": "unbounded", "scope": "single Tenacity control; fixed saved legal lower, no outer or top-two certificate"})
		}
		emit("root")
		for len(live) > 0 && splits < 64 && time.Since(started).Seconds() < 4.8 {
			pick := 0
			for i := range live {
				if live[i].u > live[pick].u {
					pick = i
				}
			}
			r := live[pick]
			live = append(live[:pick], live[pick+1:]...)
			if r.u < lower {
				pruned++
				continue
			}
			delta := make([]float64, len(r.box))
			for i, b := range r.box {
				delta[i] = (b[0]+b[1])/2 + e.baseline[i]
			}
			_, g, _, err := p.ValueGradient(delta)
			if err != nil {
				t.Fatal(err)
			}
			axis, best := -1, 0.0
			for i, b := range r.box {
				score := math.Abs(g[i]) * (b[1] - b[0])
				if score > best && b[1]-b[0] > 1e-9 {
					axis, best = i, score
				}
			}
			if axis < 0 {
				live = append(live, r)
				break
			}
			mid := (r.box[axis][0] + r.box[axis][1]) / 2
			for side := 0; side < 2; side++ {
				box := append([][2]float64(nil), r.box...)
				if side == 0 {
					box[axis][1] = mid
				} else {
					box[axis][0] = mid
				}
				u := math.Min(r.u, bound(box))
				contains := true
				for i, x := range point {
					contains = contains && x >= box[i][0]-1e-8 && x <= box[i][1]+1e-8
				}
				if contains && u+1e-6 < lower {
					t.Fatal("targeted branch lost legal witness")
				}
				if u < lower {
					pruned++
				} else {
					live = append(live, region{box, u})
				}
			}
			splits++
			for next < len(levels) && time.Since(started).Seconds() >= levels[next] {
				emit(fmt.Sprintf("checkpoint_%.1fs", levels[next]))
				next++
			}
		}
		emit("final")
	}
}

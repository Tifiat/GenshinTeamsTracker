package search

import (
	"context"
	"errors"
	"math"
	"testing"
)

func TestSingleReplacementsMatchFullFormulaAndPhysicalOracle(t *testing.T) {
	req, ir := searchFixtures(t)
	for _, item := range append(req.Artifacts[:0:0], req.Artifacts...) {
		item.ArtifactID += 100
		req.Artifacts = append(req.Artifacts, item)
	}
	e, index := fixedCandidateEngine(t, req, ir, DefaultConfig())
	dps, err := e.score(index.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	anchor := ScoredAssignment{Assignment: index.Incumbent, DPS: dps}
	rows, err := SingleReplacements(context.Background(), index, e.panel, anchor, 1000, nil)
	if err != nil {
		t.Fatal(err)
	}
	oracle := 0
	for actor := range anchor.Assignment {
		for slot, ids := range index.CandidateIDsBySlot {
			for _, id := range ids {
				trial := anchor.Assignment
				if trial[actor][slot] == id {
					continue
				}
				trial[actor][slot] = id
				if index.ValidateAssignment(trial) == nil {
					oracle++
				}
			}
		}
	}
	if len(rows) != oracle || len(rows) == 0 {
		t.Fatalf("got %d swaps; oracle %d", len(rows), oracle)
	}
	for _, row := range rows {
		if AssignmentDistance(anchor.Assignment, row.Assignment) != 1 || index.ValidateAssignment(row.Assignment) != nil {
			t.Fatal("not a legal single swap")
		}
		full, err := e.score(row.Assignment)
		if err != nil || math.Abs(full-row.DPS) > 1e-8*(1+math.Abs(full)) {
			t.Fatal("full formula mismatch", full, row.DPS, err)
		}
	}
	top, err := SingleReplacements(context.Background(), index, e.panel, anchor, 3, nil)
	if err != nil || len(top) != 3 {
		t.Fatal(err, len(top))
	}
	for i := range top {
		if top[i] != rows[i] {
			t.Fatal("retention changed order")
		}
	}
	empty, err := SingleReplacements(context.Background(), index, e.panel, anchor, 0, nil)
	if err != nil || len(empty) != 0 {
		t.Fatal("zero swaps not honored")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := SingleReplacements(ctx, index, e.panel, anchor, 3, nil); !errors.Is(err, context.Canceled) {
		t.Fatal("cancel ignored", err)
	}
}

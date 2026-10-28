package theorysearch

import (
	"encoding/json"
	"strings"
	"testing"
)

func stage15SnapshotCopy(t *testing.T, source Snapshot) Snapshot {
	t.Helper()
	raw, err := json.Marshal(source)
	if err != nil {
		t.Fatal(err)
	}
	var copy Snapshot
	if err := json.Unmarshal(raw, &copy); err != nil {
		t.Fatal(err)
	}
	return copy
}

func stage15FindSnapshotFamily(rows []FamilyRow, family string) *FamilyRow {
	for i := range rows {
		if rows[i].Family == family {
			return &rows[i]
		}
	}
	return nil
}

func stage15FindSnapshotFamilyBucket(snapshot *Snapshot, family string) ([]FamilyRow, *FamilyRow) {
	if row := stage15FindSnapshotFamily(snapshot.CoLeaders, family); row != nil {
		return snapshot.CoLeaders, row
	}
	if row := stage15FindSnapshotFamily(snapshot.Pending, family); row != nil {
		return snapshot.Pending, row
	}
	return nil, nil
}

func TestStage15ProjectionChecksEverySnapshotRowAndRejectsCorruption(t *testing.T) {
	s, _ := outputFrozenArchive()
	snapshot := s.publish(false)
	projection, err := Stage15Archive(s)
	if err != nil {
		t.Fatal(err)
	}
	if err := Stage15CheckSnapshot(s, snapshot); err != nil {
		t.Fatalf("direct archive check: %v", err)
	}
	if err := Stage15CheckProjection(projection, snapshot); err != nil {
		t.Fatalf("frozen archive check: %v", err)
	}

	mutations := map[string]func(*testing.T, *Snapshot){
		"missing family": func(t *testing.T, copy *Snapshot) {
			t.Helper()
			if len(copy.CoLeaders) == 0 {
				t.Fatal("fixture has no co-leader")
			}
			copy.CoLeaders = copy.CoLeaders[1:]
		},
		"duplicate family": func(t *testing.T, copy *Snapshot) {
			t.Helper()
			copy.CoLeaders = append(copy.CoLeaders, copy.CoLeaders[0])
		},
		"missing alias": func(t *testing.T, copy *Snapshot) {
			t.Helper()
			_, row := stage15FindSnapshotFamilyBucket(copy, "best")
			if row == nil || len(row.Aliases) == 0 {
				t.Fatal("fixture best family has no alias")
			}
			row.Aliases = row.Aliases[1:]
		},
		"duplicate alias": func(t *testing.T, copy *Snapshot) {
			t.Helper()
			_, row := stage15FindSnapshotFamilyBucket(copy, "best")
			if row == nil || len(row.Aliases) == 0 {
				t.Fatal("fixture best family has no alias")
			}
			row.Aliases = append(row.Aliases, row.Aliases[0])
		},
		"illegal witness": func(t *testing.T, copy *Snapshot) {
			t.Helper()
			_, row := stage15FindSnapshotFamilyBucket(copy, "best")
			if row == nil {
				t.Fatal("fixture best family is missing")
			}
			row.Witness45.Lines[0][0][0] = 99
		},
		"reference mismatch": func(t *testing.T, copy *Snapshot) {
			t.Helper()
			copy.ReferenceScore++
		},
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			copy := stage15SnapshotCopy(t, snapshot)
			mutate(t, &copy)
			if err := Stage15CheckProjection(projection, copy); err == nil {
				t.Fatal("corrupted snapshot passed the independent archive check")
			}
		})
	}
}

func TestStage15FrozenProjectionAndSnapshotSurviveLaterSessionMutationAndFinish(t *testing.T) {
	s, _ := outputFrozenArchive()
	first := s.publish(false)
	projection, err := Stage15Archive(s)
	if err != nil {
		t.Fatal(err)
	}
	firstBytes, err := json.Marshal(first)
	if err != nil {
		t.Fatal(err)
	}
	projectionBytes, err := json.Marshal(projection)
	if err != nil {
		t.Fatal(err)
	}

	best := s.archive.pool["best"]
	best.value = 1020
	s.archive.pool["best"] = best
	for key, alias := range s.archive.aliases["best"] {
		alias.ContextSHA256 = strings.Repeat("f", 64)
		alias.Uncertainty[0] = "later-session-mutation"
		alias.Packages[1].Sets[0].SetUID = "later-session-mutation"
		s.archive.aliases["best"][key] = alias
		break
	}
	if _, err := s.Finish(); err != nil {
		t.Fatalf("synthetic Finish: %v", err)
	}
	if err := Stage15CheckProjection(projection, first); err != nil {
		t.Fatalf("frozen projection no longer checks its old publication: %v", err)
	}
	gotFirstBytes, err := json.Marshal(first)
	if err != nil {
		t.Fatal(err)
	}
	gotProjectionBytes, err := json.Marshal(projection)
	if err != nil {
		t.Fatal(err)
	}
	if string(firstBytes) != string(gotFirstBytes) {
		t.Fatal("later session changes mutated the retained Snapshot")
	}
	if string(projectionBytes) != string(gotProjectionBytes) {
		t.Fatal("later session changes mutated the detached archive projection")
	}
}

func TestStage15NativeTerminalCanClearFinishedEarlyOnlyByExplicitProjection(t *testing.T) {
	s, _ := outputFrozenArchive()
	coreSnapshot, err := s.Finish()
	if err != nil {
		t.Fatal(err)
	}
	projection, err := Stage15Archive(s)
	if err != nil {
		t.Fatal(err)
	}
	if err := Stage15CheckProjection(projection, coreSnapshot); err != nil {
		t.Fatalf("core Finish publication: %v", err)
	}
	nativeTerminal := coreSnapshot
	nativeTerminal.FinishedEarly = false
	if err := Stage15CheckProjection(projection, nativeTerminal); err == nil {
		t.Fatal("native FinishedEarly normalization passed without an explicit projection value")
	}
	projection.FinishedEarly = false
	if err := Stage15CheckProjection(projection, nativeTerminal); err != nil {
		t.Fatalf("explicit native terminal metadata: %v", err)
	}
}

func TestStage15ProjectionRejectsIllegalArchivedWitnessAndMismatchedAliasReference(t *testing.T) {
	for _, mode := range []string{"illegal_witness", "alias_reference"} {
		t.Run(mode, func(t *testing.T) {
			s, _ := outputFrozenArchive()
			if mode == "illegal_witness" {
				candidate := s.archive.pool["best"]
				candidate.state.Lines[0][0][0] = 99
				s.archive.pool["best"] = candidate
			} else {
				alias := s.archive.aliases["best"][outputTupleKey(s.archive.pool["best"].packages)]
				alias.TupleKey = "incorrect_tuple_reference"
				s.archive.aliases["best"][outputTupleKey(s.archive.pool["best"].packages)] = alias
			}
			snapshot := s.publish(false)
			projection, err := Stage15Archive(s)
			if err != nil {
				t.Fatal(err)
			}
			if err := Stage15CheckProjection(projection, snapshot); err == nil {
				t.Fatal("invalid archived witness/reference passed")
			}
		})
	}
}

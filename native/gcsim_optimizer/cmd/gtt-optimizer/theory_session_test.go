package main

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryverify"
)

func TestTheoryCommandRequiresDisplayedVersionAndIdentity(t *testing.T) {
	path := filepath.Join(t.TempDir(), "command.json")
	current := theorysearch.Snapshot{SessionID: "one", RequestSHA256: strings.Repeat("a", 64), SnapshotVersion: 3}
	command := theoryCommand{SchemaKind: "gtt_theory_session_command_v1", SessionID: "one", RequestSHA256: current.RequestSHA256, SnapshotVersion: 3, Sequence: 1, Action: "breadth"}
	write := func(c theoryCommand) {
		t.Helper()
		data, e := json.Marshal(c)
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(path, data, 0600); e != nil {
			t.Fatal(e)
		}
	}
	if _, ready, e := readTheoryCommand(path, current, 0); e != nil || ready {
		t.Fatal(ready, e)
	}
	write(command)
	if got, ready, e := readTheoryCommand(path, current, 0); e != nil || !ready || got.Action != "breadth" {
		t.Fatal(got, ready, e)
	}
	if _, ready, e := readTheoryCommand(path, current, 1); e != nil || ready {
		t.Fatal("replayed command", ready, e)
	}
	for _, change := range []func(*theoryCommand){func(c *theoryCommand) { c.SessionID = "two" }, func(c *theoryCommand) { c.RequestSHA256 = strings.Repeat("b", 64) }, func(c *theoryCommand) { c.SnapshotVersion = 2 }, func(c *theoryCommand) { c.Sequence = 2 }, func(c *theoryCommand) { c.Action = "automatic" }} {
		c := command
		change(&c)
		write(c)
		if _, _, e := readTheoryCommand(path, current, 0); e == nil {
			t.Fatal("invalid command accepted", c)
		}
	}
}
func TestTheoryCommandWaitCancelAndFinishAreDistinct(t *testing.T) {
	current := theorysearch.Snapshot{SessionID: "s"}
	outer, cancel := context.WithCancel(context.Background())
	cancel()
	search, stop := searchcontrol.Begin(outer)
	defer stop()
	if _, err := awaitTheoryCommand(search, filepath.Join(t.TempDir(), "absent"), current, 0); err != context.Canceled || theorySoftFinish(search, err) {
		t.Fatal(err)
	}
	marker := filepath.Join(t.TempDir(), "finish")
	if err := os.WriteFile(marker, nil, 0600); err != nil {
		t.Fatal(err)
	}
	search2, stop2 := searchcontrol.Begin(searchcontrol.WithFile(context.Background(), marker))
	defer stop2()
	if _, err := awaitTheoryCommand(search2, filepath.Join(t.TempDir(), "absent"), current, 0); !theorySoftFinish(search2, err) {
		t.Fatal("Finish was treated as Cancel", err)
	}
}
func TestTheorySnapshotUsesNormalProgressEnvelope(t *testing.T) {
	var output bytes.Buffer
	emitter := newProgressEmitter(&output, strings.Repeat("a", 64))
	snapshot := theoryverify.Snapshot{Snapshot: theorysearch.Snapshot{SchemaVersion: 3, SchemaKind: theoryverify.ResultKind, SnapshotVersion: 1, SessionID: "session", RequestSHA256: strings.Repeat("a", 64)}, PublicationVersion: 1}
	if err := emitter.theorySnapshot(snapshot); err != nil {
		t.Fatal(err)
	}
	var row struct {
		contracts.ProgressRecord
		Snapshot theoryverify.Snapshot `json:"theory_snapshot"`
	}
	if err := json.Unmarshal(output.Bytes(), &row); err != nil {
		t.Fatal(err)
	}
	if err := row.ProgressRecord.Validate(); err != nil {
		t.Fatal(err)
	}
	if row.Sequence != 0 || emitter.sequence != 1 || row.Snapshot.SessionID != "session" || row.SchemaKind != contracts.ProgressSchemaKind {
		t.Fatal(row)
	}
}
func TestTheorySessionPolicyBindsDomainsAndRejectsLegacyOverrides(t *testing.T) {
	raw := contracts.OptimizerRequest{}
	for _, name := range []string{"a", "b", "c", "d"} {
		raw.Wearers = append(raw.Wearers, contracts.Wearer{WearerKey: name, TheoryBaseline: &contracts.TheoryArtifactBaseline{MainStats: []contracts.TheoryMainStat{
			{Slot: "flower", Key: "hp"}, {Slot: "plume", Key: "atk"}, {Slot: "sands", Key: "atk_percent"}, {Slot: "goblet", Key: "atk_percent"}, {Slot: "circlet", Key: "crit_rate"},
		}}})
	}
	sources := &seteffects.SourceCatalog{Sets: []seteffects.DiscoveredSet{{Key: "generic", FourPieceModeled: true}}}
	cfg, err := theorySessionConfig(raw, raw, sources, "request", "source", "model", "session")
	if err != nil {
		t.Fatal(err)
	}
	if err = alloc.ValidateFull45(cfg.Initial); err != nil {
		t.Fatal(err)
	}
	original := cfg.Binding
	req := raw
	req.TheoryOptions = &contracts.TheorySearchOptions{AllowedPackages: map[string][][]contracts.SetRequirement{"a": {{{SetUID: "generic", Count: 4}}}}}
	changed, err := theorySessionConfig(raw, req, sources, "request", "source", "model", "session")
	if err != nil || changed.Binding == original || len(changed.Domains[0]) != 1 || len(changed.Original[0].Sets) != 1 {
		t.Fatal(changed, err)
	}
	for _, o := range []*contracts.TheorySearchOptions{{MainChoices: map[string]map[string][]string{"a": {"sands": {"em"}}}}, {RollBounds: map[string]map[string]contracts.TheoryRollBound{"a": {"em": {Min: "1", Max: "2"}}}}, {ScheduleContexts: 1}, {MaxPackageEvaluations: 1}, {MaxAllocationEvaluations: 1}, {MaxPreviews: 1}} {
		req.TheoryOptions = o
		if _, err = theorySessionConfig(raw, req, sources, "request", "source", "model", "session"); err == nil {
			t.Fatal("legacy override silently ignored", o)
		}
	}
	for _, ids := range [][3]string{{"changed", "source", "model"}, {"request", "changed", "model"}, {"request", "source", "changed"}} {
		c, e := theorySessionConfig(raw, raw, sources, ids[0], ids[1], ids[2], "session")
		if e != nil || c.Binding == original {
			t.Fatal("identity change did not invalidate", c, e)
		}
	}
}
func TestTheoryCLIControlsDoNotRerouteSelectedOrAllSets(t *testing.T) {
	for _, mode := range []string{"verify-fgbs", "optimize-all-sets"} {
		if err := run(context.Background(), []string{mode, "missing", "sources", "root", "--theory-control-file", "control"}); err == nil || !strings.Contains(err.Error(), "only for Theory") {
			t.Fatal(mode, err)
		}
	}
	err := run(context.Background(), []string{"optimize-theory", "missing", "sources", "root", "--finish-file", "finish", "--theory-control-file", "control"})
	if err == nil || strings.Contains(err.Error(), "usage:") || strings.Contains(err.Error(), "supported only") {
		t.Fatal("Theory flags did not reach Theory input validation", err)
	}
}
func TestTheorySessionFiniteEnergyFailsBeforeEngineOrRunDirectory(t *testing.T) {
	req, _ := productFixtures(t)
	req = setTestEnergyMode(t, req, false)
	req.Legality.TheorySearch = true
	req.Legality.FixedFourPiece = false
	req.Legality.FixedSetPackages = false
	req.Legality.MaxOffSetPiecesPerWearer = 0
	req.Artifacts = []contracts.Artifact{}
	req.Engine.BinaryPath = filepath.Join(t.TempDir(), "engine-must-never-be-opened")
	req.Engine.Capabilities = append(req.Engine.Capabilities, contracts.NeutralInputsCapability)
	sort.Strings(req.Engine.Capabilities)
	for a := range req.Wearers {
		w := &req.Wearers[a]
		w.SelectedSetUID = ""
		w.SelectedSets = nil
		w.CurrentArtifacts = []contracts.ArtifactAssignment{}
		w.TheoryBaseline = &contracts.TheoryArtifactBaseline{MainStats: []contracts.TheoryMainStat{
			{Slot: "flower", Key: "hp", Value: "4780"}, {Slot: "plume", Key: "atk", Value: "311"},
			{Slot: "sands", Key: "atk_percent", Value: "0.466"}, {Slot: "goblet", Key: "atk_percent", Value: "0.466"}, {Slot: "circlet", Key: "crit_rate", Value: "0.311"},
		}}
	}
	requestBytes, err := contracts.CanonicalJSON(req)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err = contracts.DecodeTheoryRequest(requestBytes); err != nil {
		t.Fatal("invalid finite-energy fixture", err)
	}
	root := t.TempDir()
	requestPath := filepath.Join(root, "request.json")
	sourcePath := filepath.Join(root, "sources.json")
	runRoot := filepath.Join(root, "never-created")
	sourceBytes, err := json.Marshal(seteffects.SourceBundle{SchemaVersion: 1, RuleLibraries: map[string]contracts.SourceText{"test": {Text: "fixture"}}})
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(requestPath, requestBytes, 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(sourcePath, sourceBytes, 0600); err != nil {
		t.Fatal(err)
	}
	if err = optimizeTheorySession(context.Background(), requestPath, sourcePath, runRoot); err == nil || !strings.Contains(err.Error(), "requires infinite energy") {
		t.Fatal("finite energy reached engine/preparation", err)
	}
	if _, err = os.Stat(runRoot); !os.IsNotExist(err) {
		t.Fatal("finite energy created run output", err)
	}
}

package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryverify"
)

type theoryControlKey struct{}
type theoryCommand struct {
	SchemaKind      string `json:"schema_kind"`
	SessionID       string `json:"session_id"`
	RequestSHA256   string `json:"request_sha256"`
	SnapshotVersion int64  `json:"snapshot_version"`
	Sequence        int64  `json:"sequence"`
	Action          string `json:"action"`
}

func readTheoryCommand(path string, current theorysearch.Snapshot, last int64) (theoryCommand, bool, error) {
	var c theoryCommand
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return c, false, nil
	}
	if err != nil {
		return c, false, err
	}
	if len(data) > 65536 {
		return c, false, fmt.Errorf("Theory command too large")
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(&c); err != nil {
		return c, false, err
	}
	var trailing any
	if err = decoder.Decode(&trailing); err != io.EOF {
		return c, false, fmt.Errorf("trailing Theory command data")
	}
	if c.Sequence <= last {
		return c, false, nil
	}
	if c.SchemaKind != "gtt_theory_session_command_v1" || c.SessionID != current.SessionID || c.RequestSHA256 != current.RequestSHA256 ||
		c.SnapshotVersion != current.SnapshotVersion || c.Sequence != last+1 || (c.Action != "breadth" && c.Action != "deep") {
		return c, false, fmt.Errorf("stale or invalid Theory continuation command")
	}
	return c, true, nil
}
func awaitTheoryCommand(ctx context.Context, path string, current theorysearch.Snapshot, last int64) (theoryCommand, error) {
	ticker := time.NewTicker(25 * time.Millisecond)
	defer ticker.Stop()
	for {
		if err := ctx.Err(); err != nil {
			return theoryCommand{}, err
		}
		c, ready, err := readTheoryCommand(path, current, last)
		if err != nil {
			return c, err
		}
		if ready {
			return c, nil
		}
		select {
		case <-ctx.Done():
			return theoryCommand{}, ctx.Err()
		case <-ticker.C:
		}
	}
}

func (emitter *progressEmitter) theorySnapshot(s theoryverify.Snapshot) error {
	stage := "searching"
	if s.Verification.InProgress {
		stage = "simulating_finalists"
	}
	record := contracts.ProgressRecord{SchemaVersion: contracts.SchemaVersion, SchemaKind: contracts.ProgressSchemaKind,
		RequestSHA256: emitter.requestSHA256, Sequence: emitter.sequence, Stage: stage,
		CompletedWork: int64(s.Work.CompletedPasses), TotalWork: 2, ElapsedMS: time.Since(emitter.started).Milliseconds()}
	if err := record.Validate(); err != nil {
		return err
	}
	emitter.sequence++
	return json.NewEncoder(emitter.writer).Encode(struct {
		contracts.ProgressRecord
		Snapshot theoryverify.Snapshot `json:"theory_snapshot"`
	}{record, s})
}

func theorySessionConfig(raw, req contracts.OptimizerRequest, sources *seteffects.SourceCatalog, requestSHA, sourceSHA, modelSHA, sessionID string) (theorysearch.Config, error) {
	var cfg theorysearch.Config
	if o := req.TheoryOptions; o != nil {
		if len(o.MainChoices) > 0 || len(o.RollBounds) > 0 || o.MaxPackageEvaluations > 0 || o.MaxAllocationEvaluations > 0 || o.MaxPreviews > 0 || o.ScheduleContexts > 0 {
			return cfg, fmt.Errorf("Theory H-light does not support legacy allocation/work/schedule overrides")
		}
	}
	catalog := make([]domain.SetCapability, 0, len(sources.Sets))
	for _, s := range sources.Sets {
		catalog = append(catalog, domain.SetCapability{UID: s.Key, TwoPiece: true, FourPiece: s.FourPieceModeled})
	}
	packages, err := theorypackages.Packages(catalog)
	if err != nil {
		return cfg, err
	}
	domains, err := theorySessionAllowedDomains(req, packages)
	if err != nil {
		return cfg, err
	}
	var mains [4][5]string
	for a, w := range raw.Wearers {
		cfg.Wearers[a] = w.WearerKey
		if w.TheoryBaseline == nil || len(w.TheoryBaseline.MainStats) != 5 {
			return cfg, fmt.Errorf("missing Theory main anchor")
		}
		for slot, row := range w.TheoryBaseline.MainStats {
			mains[a][slot] = row.Key
		}
		// The expanded capture deliberately has no bonuses. Honor an explicit
		// allowed domain when it excludes the zero-bonus search start.
		cfg.Original[a] = domain.Package{}
		allowed := false
		for _, p := range domains[a] {
			if len(p.Sets) == 0 {
				allowed = true
			}
		}
		if !allowed {
			cfg.Original[a] = domains[a][0]
		}
	}
	cfg.Initial = alloc.Seed(mains, [4][10]float64{}, 0, 45)
	cfg.Domains = domains
	cfg.RequestSHA256 = requestSHA
	cfg.SessionID = sessionID
	cfg.Binding, err = contracts.CanonicalSHA256(map[string]any{"request": requestSHA, "sources": sourceSHA, "engine": req.Engine,
		"model": modelSHA, "seeds": req.Stochastic.Seeds, "policy": theorysearch.PolicyID, "domains": domains, "initial": cfg.Initial})
	return cfg, err
}

// Preparation captures one neutral universe. Continuations never recapture;
// a separate finite lifetime finalist policy owns ordinary verification.
func optimizeTheorySession(ctx context.Context, requestPath, sourcePath, runRoot string) (resultErr error) {
	sourceBytes, err := os.ReadFile(sourcePath)
	if err != nil {
		return err
	}
	sourceSHA := contracts.TextSHA256(string(sourceBytes))
	raw, req, sources, err := readTheorySetSources(requestPath, sourcePath)
	if err != nil {
		return err
	}
	requestSHA, err := contracts.CanonicalSHA256(raw)
	if err != nil {
		return err
	}
	var nonce [16]byte
	if _, err = rand.Read(nonce[:]); err != nil {
		return err
	}
	// Validate the policy and domain before any capture or output directory.
	cfg, err := theorySessionConfig(raw, req, sources, requestSHA, sourceSHA, "preparation", hex.EncodeToString(nonce[:]))
	if err != nil {
		return err
	}
	policy, err := theoryverify.PolicyFromRequest(raw)
	if err != nil {
		return err
	}
	verified, err := theoryverify.NewArchive(raw, policy)
	if err != nil {
		return err
	}
	renderer, err := theoryverify.Renderer(raw, sources.CatalogSHA256)
	if err != nil {
		return err
	}
	bound, err := engineclient.BindEngine(req)
	if err != nil {
		return err
	}
	checkBinding := func() error {
		payload, e := os.ReadFile(requestPath)
		if e != nil {
			return e
		}
		current, _, e := contracts.DecodeTheoryRequest(payload)
		if e != nil {
			return e
		}
		digest, e := contracts.CanonicalSHA256(current)
		if e != nil {
			return e
		}
		source, e := os.ReadFile(sourcePath)
		if e != nil {
			return e
		}
		if digest != requestSHA || contracts.TextSHA256(string(source)) != sourceSHA {
			return theorysearch.ErrBindingChanged
		}
		return bound.VerifyUnchanged()
	}
	if err = checkBinding(); err != nil {
		return err
	}
	overall, cancel := productContext(ctx, req.Budgets.ProductTimeoutMS)
	defer cancel()
	searchCtx, stop := searchcontrol.Begin(overall)
	defer stop()
	softStop := func(e error) error {
		if theorySoftFinish(searchCtx, e) {
			return theorysearch.ErrNoResult
		}
		return e
	}
	if err = searchCtx.Err(); err != nil {
		return softStop(err)
	}
	if err = os.Mkdir(runRoot, 0700); err != nil {
		return err
	}
	progress := newProgressEmitter(os.Stderr, requestSHA)
	var lastSearch theorysearch.Snapshot
	hasSearch := false
	// Search failures and cancellation cannot roll back completed ordinary
	// receipts. A process-tree kill still retains earlier streamed snapshots.
	defer func() {
		if resultErr != nil && hasSearch {
			retained := verified.Publish(lastSearch)
			retained.Rules["retained_after_error"] = true
			_ = progress.theorySnapshot(retained)
		}
	}()
	if err = progress.emit("compiling_formula", 0, 2, false); err != nil {
		return err
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: requestSHA, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if err != nil {
		return err
	}
	changes := map[string][]setcontext.Set{}
	for _, w := range req.Wearers {
		changes[w.WearerKey] = nil
	}
	base, err = base.Replace(changes)
	if err != nil {
		return err
	}
	captureRoot := filepath.Join(runRoot, "contexts")
	if err = os.Mkdir(captureRoot, 0700); err != nil {
		return err
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, captureRoot)
	if err != nil {
		return err
	}
	closed := false
	defer func() {
		if !closed {
			_ = provider.Close()
		}
	}()
	capturedSession, err := setcontext.NewSession(provider.Capture, len(base.Seeds()))
	if err != nil {
		return err
	}
	captured, err := capturedSession.Resolve(searchCtx, base, nil, nil)
	if err != nil {
		return softStop(err)
	}
	model, err := setcontext.NewNeutralModel(captured, sources)
	if err != nil {
		return err
	}
	cfg, err = theorySessionConfig(raw, req, sources, requestSHA, sourceSHA, captured.GraphSHA256(), cfg.SessionID)
	if err != nil {
		return err
	}
	world, err := theorysearch.NewFormulaWorld(req, base, model, cfg.Binding)
	if err != nil {
		return err
	}
	// A configured common response producer scores its legal proposals through
	// an independent view of the same captured model. Its resolver feedback must
	// never enter First/Breadth or the restored Deep branch; it performs no capture.
	var proposalWorld *theorysearch.FormulaWorld
	if theoryverify.HasResponseProducer(overall) {
		proposalWorld, err = theorysearch.NewFormulaWorld(req, base, model, cfg.Binding)
		if err != nil {
			world.Close()
			return err
		}
		defer proposalWorld.Close()
	}
	offerResponses := func() error {
		return verified.OfferResponseProposals(searchCtx, raw, sources.CatalogSHA256, func(candidate theoryverify.Candidate) (alloc.Objective, error) {
			if proposalWorld == nil {
				return nil, fmt.Errorf("Theory response proposal model is unavailable")
			}
			packages, err := candidate.Packages()
			if err != nil {
				return nil, err
			}
			entry, reasons, err := proposalWorld.Resolve(overall, packages)
			if err != nil {
				return nil, err
			}
			if entry == nil {
				return nil, fmt.Errorf("Theory response proposal objective unavailable: %v", reasons)
			}
			return entry.Objective, nil
		})
	}
	session, err := theorysearch.New(cfg, world)
	if err != nil {
		world.Close()
		return err
	}
	defer session.Close()
	if err = checkBinding(); err != nil {
		return err
	}
	snapshot, err := session.First(searchCtx, cfg.Binding)
	finishedEarly := false
	if err != nil {
		if !theorySoftFinish(searchCtx, err) {
			return err
		}
		finishedEarly = true
	} else {
		lastSearch, hasSearch = snapshot, true
		if err = verified.OfferSearch(snapshot); err != nil {
			return err
		}
		if err = offerResponses(); err != nil {
			return err
		}
		if err = verified.Verify(overall, raw, snapshot, false, renderer, runRoot, runtime.NumCPU(), checkBinding, progress.theorySnapshot, nil); err != nil {
			return err
		}
		searchcontrol.Ready(searchCtx)
	}
	controlPath, _ := ctx.Value(theoryControlKey{}).(string)
	sequence := int64(0)
	for err == nil && controlPath != "" && snapshot.Phase != "deep_baseline" {
		var command theoryCommand
		command, err = awaitTheoryCommand(searchCtx, controlPath, snapshot, sequence)
		if err != nil {
			break
		}
		if err = checkBinding(); err != nil {
			return err
		}
		sequence = command.Sequence
		if command.Action == "breadth" {
			snapshot, err = session.Breadth(searchCtx, cfg.Binding)
		} else {
			snapshot, err = session.Deep(searchCtx, cfg.Binding)
		}
		if err != nil {
			break
		}
		lastSearch, hasSearch = snapshot, true
		if err = verified.OfferSearch(snapshot); err != nil {
			return err
		}
		if err = offerResponses(); err != nil {
			return err
		}
		if err = verified.Verify(overall, raw, snapshot, false, renderer, runRoot, runtime.NumCPU(), checkBinding, progress.theorySnapshot, nil); err != nil {
			return err
		}
		searchcontrol.Ready(searchCtx)
	}
	if err != nil {
		if !theorySoftFinish(searchCtx, err) {
			return err
		}
		finishedEarly = true
	}
	if searchcontrol.Requested(searchCtx) {
		finishedEarly = true
	}
	if err = overall.Err(); err != nil {
		return err
	}
	if err = checkBinding(); err != nil {
		return err
	}
	terminal, err := session.Finish()
	if err != nil {
		return err
	}
	terminal.FinishedEarly = finishedEarly
	lastSearch, hasSearch = terminal, true
	if err = verified.OfferSearch(terminal); err != nil {
		return err
	}
	if err = offerResponses(); err != nil {
		return err
	}
	if err = verified.Verify(overall, raw, terminal, true, renderer, runRoot, runtime.NumCPU(), checkBinding, progress.theorySnapshot, nil); err != nil {
		return err
	}
	// Close/verify the capture owner before emitting terminal success. Python's
	// existing run-directory lease owns removal on Finish, Cancel and failure.
	if err = provider.Close(); err != nil {
		return err
	}
	closed = true
	if err = progress.emit("completed", 2, 2, false); err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"product_result": verified.Publish(terminal)})
}

// Used by local lifecycle tests; cancellation never masquerades as Finish.
func theorySoftFinish(ctx context.Context, err error) bool {
	return errors.Is(err, context.Canceled) && searchcontrol.Requested(ctx) && searchcontrol.FinalizationContext(ctx).Err() == nil
}

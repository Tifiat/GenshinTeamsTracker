// Added only to the leased target test assembly; no production body is edited.
package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
)

type stage15Setup struct {
	raw, req          contracts.OptimizerRequest
	sources           *seteffects.SourceCatalog
	cfg               theorysearch.Config
	rawSHA, sourceSHA string
}

func stage15Emit(v any) {
	b, err := json.Marshal(v)
	if err != nil {
		panic(err)
	}
	fmt.Println("STAGE15_RECEIPT " + string(b))
}
func stage15Bytes(v any) []byte {
	b, err := json.Marshal(v)
	if err != nil {
		panic(err)
	}
	return b
}
func stage15Digest(v any) string { return fmt.Sprintf("%x", sha256.Sum256(stage15Bytes(v))) }
func stage15Write(root, name string, v any) error {
	if filepath.Base(name) != name || root == "" {
		return fmt.Errorf("invalid Stage15 public export")
	}
	return os.WriteFile(filepath.Join(root, name), append(stage15Bytes(v), '\n'), 0600)
}
func stage15Prepare() (stage15Setup, error) {
	var p stage15Setup
	var err error
	p.raw, p.req, p.sources, err = readTheorySetSources(os.Getenv("GTT_STAGE15_REQUEST"), os.Getenv("GTT_STAGE15_SOURCES"))
	if err != nil {
		return p, err
	}
	p.rawSHA, err = contracts.CanonicalSHA256(p.raw)
	if err != nil {
		return p, err
	}
	b, err := os.ReadFile(os.Getenv("GTT_STAGE15_SOURCES"))
	if err != nil {
		return p, err
	}
	p.sourceSHA = contracts.TextSHA256(string(b))
	p.cfg, err = theorySessionConfig(p.raw, p.req, p.sources, p.rawSHA, p.sourceSHA, "preparation", "stage15-preflight")
	if err != nil {
		return p, err
	}
	// The public profile/rotation order is Furina/Xilonen/Chiori/Columbina;
	// production transport sorts wearers before constructing the native config.
	if p.cfg.Wearers != [4]string{"chiori", "columbina", "furina", "xilonen"} ||
		!reflect.DeepEqual(p.req.Stochastic.Seeds, []uint64{742031889, 742031890}) || p.req.Budgets.ProductTimeoutMS != 0 {
		return p, fmt.Errorf("Stage15 team/seeds/default product deadline changed: %v/%v/%d", p.cfg.Wearers, p.req.Stochastic.Seeds, p.req.Budgets.ProductTimeoutMS)
	}
	for a, rows := range p.cfg.Domains {
		if len(rows) != 946 || !reflect.DeepEqual(rows, p.cfg.Domains[0]) || len(p.cfg.Original[a].Sets) != 0 {
			return p, fmt.Errorf("Stage15 default package domain/start changed for actor %d", a)
		}
	}
	bound, err := engineclient.BindEngine(p.req)
	if err != nil {
		return p, err
	}
	return p, bound.VerifyUnchanged()
}
func TestStage15PreparedTargetInputs(t *testing.T) {
	if os.Getenv("GTT_STAGE15_REQUEST") == "" {
		t.Skip("explicit managed preparation required")
	}
	started := time.Now()
	p, err := stage15Prepare()
	if err != nil {
		t.Fatal(err)
	}
	stage15Emit(map[string]any{"kind": "native_input_preflight", "request_sha256": p.rawSHA, "source_sha256": p.sourceSHA,
		"expanded_request_sha256": stage15Digest(p.req), "configuration_sha256": stage15Digest(p.cfg),
		"domains_sha256": stage15Digest(p.cfg.Domains), "initial": p.cfg.Initial, "original": p.cfg.Original,
		"wearers": p.cfg.Wearers, "package_options_per_wearer": 946, "source_catalog_sha256": p.sources.CatalogSHA256,
		"engine": p.req.Engine, "seeds": p.req.Stochastic.Seeds, "prepare_seconds": time.Since(started).Seconds(), "engine_calls": 0})
}

func TestStage15RealFullOutput(t *testing.T) {
	if os.Getenv("GTT_STAGE15_RUN") != "authorized-one-universe" {
		t.Skip("single authorized managed study required")
	}
	prepareStarted := time.Now()
	p, err := stage15Prepare()
	if err != nil {
		t.Fatal(err)
	}
	var nonce [16]byte
	if _, err = rand.Read(nonce[:]); err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{Engine: p.req.Engine, CatalogSHA256: p.sources.CatalogSHA256, ReferenceStatsSHA256: p.rawSHA, Seeds: p.req.Stochastic.Seeds}
	base, err := setcontext.New(binding, p.req.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatal(err)
	}
	empty := map[string][]setcontext.Set{}
	for _, wearer := range p.req.Wearers {
		empty[wearer.WearerKey] = nil
	}
	base, err = base.Replace(empty)
	if err != nil {
		t.Fatal(err)
	}
	root := os.Getenv("GTT_STAGE15_ROOT")
	public := filepath.Join(root, "public")
	if err = os.MkdirAll(public, 0700); err != nil {
		t.Fatal(err)
	}
	caproot := filepath.Join(root, "capture")
	if err = os.Mkdir(caproot, 0700); err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, caproot)
	if err != nil {
		t.Fatal(err)
	}
	defer provider.Close()
	capture, err := setcontext.NewSession(provider.Capture, 2)
	if err != nil {
		t.Fatal(err)
	}
	outerStarted := time.Now()
	outer, stop := context.WithTimeout(context.Background(), 600*time.Second)
	defer stop()
	var offlineStarted time.Time
	var resolver *theorysearch.Stage15Resolver
	var session *theorysearch.Session
	status, failure := "FAIL", ""
	graphSHA := ""
	clocks := map[string]float64{"native_preparation": outerStarted.Sub(prepareStarted).Seconds()}
	defer func() {
		if session != nil {
			if projection, e := theorysearch.Stage15Archive(session); e == nil {
				if status == "PASS_REAL_PRODUCT_SESSION_FULL_OUTPUT" {
					projection.FinishedEarly = false
				}
				if e = stage15Write(public, "final-archive.json", projection); e != nil {
					status, failure = "FAIL", "final public archive retention: "+e.Error()
				}
			}
			session.Close()
		}
		var totals theorysearch.Stage15Totals
		if resolver != nil {
			totals = resolver.Totals()
		}
		if !offlineStarted.IsZero() {
			clocks["offline"] = time.Since(offlineStarted).Seconds()
		}
		clocks["outer"] = time.Since(outerStarted).Seconds()
		if clocks["offline"] > 480 || clocks["outer"] > 600 {
			status, failure = "FAIL", "Stage15 hard clock exceeded during output/retention"
		}
		ledger := map[string]any{"kind": "study_ledger", "status": status, "failure": failure, "capture_attempts": capture.AttemptedCaptureMembers(),
			"capture_budget": 2, "universes": 1, "ordinary_finalists": 0, "capture_timings": provider.Timings(), "clocks_seconds": clocks,
			"work": totals, "request_sha256": p.rawSHA, "source_sha256": p.sourceSHA, "source_catalog_sha256": p.sources.CatalogSHA256,
			"model_graph_sha256": graphSHA, "model_binding": p.cfg.Binding}
		_ = stage15Write(public, "study-ledger.json", ledger)
		stage15Emit(ledger)
	}()
	fail := func(e error) {
		failure = e.Error()
		t.Fatal(e)
	}
	stage15Emit(map[string]any{"kind": "capture_enter", "reserved_maximum": 2, "universes": 1})
	started := time.Now()
	captured, err := capture.Resolve(outer, base, nil, nil)
	clocks["capture"] = time.Since(started).Seconds()
	if err != nil {
		fail(err)
	}
	if capture.AttemptedCaptureMembers() != 2 {
		fail(fmt.Errorf("Stage15 capture count %d differs from2", capture.AttemptedCaptureMembers()))
	}
	graphSHA = captured.GraphSHA256()
	if err = provider.Close(); err != nil {
		fail(err)
	}
	p.cfg, err = theorySessionConfig(p.raw, p.req, p.sources, p.rawSHA, p.sourceSHA, captured.GraphSHA256(), hex.EncodeToString(nonce[:]))
	if err != nil {
		fail(err)
	}
	offlineStarted = time.Now()
	deadline := offlineStarted.Add(480 * time.Second)
	if d, _ := outer.Deadline(); d.Before(deadline) {
		deadline = d
	}
	searchCtx, endSearch := context.WithDeadline(outer, deadline)
	defer endSearch()
	started = time.Now()
	model, err := setcontext.NewNeutralModel(captured, p.sources)
	if err != nil {
		fail(err)
	}
	world, err := theorysearch.NewFormulaWorld(p.req, base, model, p.cfg.Binding)
	clocks["model_initialization"] = time.Since(started).Seconds()
	if err != nil {
		fail(err)
	}
	resolver, err = theorysearch.NewStage15Resolver(world, deadline, 946)
	if err != nil {
		fail(err)
	}
	session, err = theorysearch.New(p.cfg, resolver)
	if err != nil {
		resolver.Close()
		fail(err)
	}
	var retained []theorysearch.Snapshot
	var archives []theorysearch.Stage15Projection
	var snapshotHashes, archiveHashes []string
	labels := []string{"first", "breadth", "deep", "terminal"}
	for index, label := range labels {
		if err = searchCtx.Err(); err != nil {
			fail(err)
		}
		started = time.Now()
		var snapshot theorysearch.Snapshot
		switch index {
		case 0:
			snapshot, err = session.First(searchCtx, p.cfg.Binding)
		case 1:
			snapshot, err = session.Breadth(searchCtx, p.cfg.Binding)
		case 2:
			snapshot, err = session.Deep(searchCtx, p.cfg.Binding)
		case 3:
			snapshot, err = session.Finish()
			// Exact successful-completion normalization used by the native CLI.
			snapshot.FinishedEarly = false
		}
		clocks[label+"_search_refinement_inclusive"] = time.Since(started).Seconds()
		if err != nil {
			fail(err)
		}
		projection, e := theorysearch.Stage15Archive(session)
		if e != nil {
			fail(e)
		}
		if index == 3 {
			projection.FinishedEarly = false
		}
		retained = append(retained, snapshot)
		archives = append(archives, projection)
		snapshotHashes = append(snapshotHashes, stage15Digest(snapshot))
		archiveHashes = append(archiveHashes, stage15Digest(projection))
		started = time.Now()
		// Export actual complete publications before any checker can fail.
		if e = stage15Write(public, label+"-snapshot.json", snapshot); e != nil {
			fail(e)
		}
		if e = stage15Write(public, label+"-archive.json", projection); e != nil {
			fail(e)
		}
		for i := range retained {
			if stage15Digest(retained[i]) != snapshotHashes[i] || stage15Digest(archives[i]) != archiveHashes[i] {
				fail(fmt.Errorf("Stage15 later phase mutated retained publication%d", i))
			}
			if e = theorysearch.Stage15CheckProjection(archives[i], retained[i]); e != nil {
				fail(fmt.Errorf("Stage15 independent output oracle at %s/%d: %w", label, i, e))
			}
		}
		clocks[label+"_output_and_oracle"] = time.Since(started).Seconds()
		stage15Emit(map[string]any{"kind": "publication", "name": label, "snapshot_sha256": snapshotHashes[index],
			"archive_sha256": archiveHashes[index], "version": snapshot.SnapshotVersion, "oracle": "PASS", "retained_publications_unchanged": len(retained),
			"co_leader_families": len(snapshot.CoLeaders), "work": resolver.Totals(), "outer_seconds": time.Since(outerStarted).Seconds()})
	}
	if err = searchCtx.Err(); err != nil {
		fail(err)
	}
	bound, err := engineclient.BindEngine(p.req)
	if err != nil {
		fail(err)
	}
	if err = bound.VerifyUnchanged(); err != nil {
		fail(err)
	}
	status = "PASS_REAL_PRODUCT_SESSION_FULL_OUTPUT"
}

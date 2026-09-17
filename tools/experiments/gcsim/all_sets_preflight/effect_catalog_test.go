package seteffects

// Source-only overlay. Fixture names in assertions designate known witnesses;
// the production analyzer uses generic syntax and engine operation vocabulary.
import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"
)

func TestAllSetEffectCatalog(t *testing.T) {
	var manifest struct {
		Engine     string `json:"engine_sha256"`
		Catalog    string `json:"catalog_sha256"`
		StatSource string `json:"stat_source"`
		AttackSource string `json:"attack_source"`
		ContextSource string `json:"context_source"`
		SourceRun  string `json:"source_run"`
		Items      []struct {
			Key     string
			Sources map[string]string
		}
	}
	raw, err := os.ReadFile(os.Getenv("GTT_EFFECT_MANIFEST"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	vocabulary, err := StatVocabulary([]byte(manifest.StatSource))
	if err != nil {
		t.Fatal(err)
	}
	tags,err:=AttackTagVocabulary([]byte(manifest.AttackSource))
	if err!=nil{t.Fatal(err)}
	curves,err:=ExtractScalarSlices([]byte(manifest.ContextSource),"Resistance","ResMod")
	if err!=nil{t.Fatal(err)}
	if len(curves)!=2 || curves[0].RecipeSHA256!=curves[1].RecipeSHA256{t.Fatal("context curves diverged; no shared curve binding",curves)}
	curveBytes,err:=json.MarshalIndent(curves,"","  ");if err!=nil{t.Fatal(err)}
	if err=os.WriteFile(filepath.Join(os.Getenv("GTT_EFFECT_OUTPUT"),"context-curves.json"),curveBytes,0600);err!=nil{t.Fatal(err)}
	started := time.Now()
	rows := []map[string]any{}
	recipesByKey := map[string][]Recipe{}
	descriptions := map[string]Description{}
	kinds := map[string]int{}
	boundaries := map[string]int{}
	effects := 0
	terms := 0
	constants := 0
	for _, item := range manifest.Items {
		sources := map[string][]byte{}
		for name, text := range item.Sources {
			sources[name] = []byte(text)
		}
		d, e := Discover(sources)
		if e != nil {
			t.Fatal(item.Key, e)
		}
		if e = d.ValidateDiscovery(); e != nil {
			t.Fatal(item.Key, e)
		}
		recipes := d.Recipes()
		recipesByKey[item.Key] = recipes
		known := 0
		descriptions[item.Key] = d
		for _, r := range recipes {
			kinds[r.Effect.Kind]++
			effects++
			for _, term := range r.Terms {
				terms++
				if term.Constant != "" {
					constants++
					known++
				}
			}
		}
		for _, b := range d.Boundaries {
			boundaries[b.Reason]++
		}
		row := map[string]any{"key": item.Key, "source_sha256": d.SourceSHA256, "effects": len(recipes), "constant_terms": known, "callback_edges": len(d.Edges), "boundaries": len(d.Boundaries)}
		rows = append(rows, row)
		signals, e := d.OwnerStatSignals(4, vocabulary)
		if e != nil {
			t.Fatal(e)
		}
		row["owner_signals_4p"] = len(signals.Signals)
		row["unresolved_signals_4p"] = len(signals.UnresolvedEffects)
		bytes, e := json.MarshalIndent(map[string]any{"description": d, "recipes": recipes, "owner_signals_4p": signals}, "", "  ")
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(filepath.Join(os.Getenv("GTT_EFFECT_OUTPUT"), item.Key+".json"), bytes, 0600); e != nil {
			t.Fatal(e)
		}
	}
	for key, kind := range map[string]string{"deepwoodmemories": "resistance", "oceanhuedclam": "new_attack", "flowerofparadiselost": "reaction_bonus", "noblesseoblige": "attack_bonus", "wandererstroupe": "attack_bonus"} {
		found := false
		for _, r := range recipesByKey[key] {
			found = found || r.Effect.Kind == kind
		}
		if !found {
			t.Fatalf("missing generic %s discovery in %s", kind, key)
		}
	}
	sourceSeconds := time.Since(started).Seconds()
	raw, err = os.ReadFile(filepath.Join(manifest.SourceRun, "request.json"))
	if err != nil {
		t.Fatal(err)
	}
	req, err := contracts.DecodeRequest(raw)
	if err != nil {
		t.Fatal(err)
	}
	if req.Engine.ArtifactSHA256 != manifest.Engine {
		t.Fatal("source versus formula engine mismatch")
	}
	memberStarted := time.Now()
	members := []contracts.IRSeedMember{}
	actors := []string{}
	for _, w := range req.Wearers {
		actors = append(actors, w.WearerKey)
	}
	for _, seed := range req.Stochastic.Seeds {
		raw, err = os.ReadFile(filepath.Join(manifest.SourceRun, "compact-member-"+strconv.FormatUint(seed, 10)+".json"))
		if err != nil {
			t.Fatal(err)
		}
		m, e := contracts.DecodeSeedMember(raw)
		if e != nil {
			t.Fatal(e)
		}
		members = append(members, m)
	}
	panel, err := evaluator.CompileMembers(actors, req.Stochastic.Seeds, members)
	if err != nil {
		t.Fatal(err)
	}
	formulaSeconds := time.Since(memberStarted).Seconds()
	probe, err := NewSignalProbe(panel)
	if err != nil {
		t.Fatal(err)
	}
	probeStarted := time.Now()
	responses := []ResponseSignal{}
	for _, item := range manifest.Items {
		for _, count := range []int{2, 4} {
			signals, e := descriptions[item.Key].OwnerStatSignals(count, vocabulary)
			if e != nil {
				t.Fatal(e)
			}
			for _, signal := range signals.Signals {
				for _, actor := range actors {
					response, e := probe.Probe(actor, signal)
					if e != nil {
						t.Fatal(e)
					}
					responses = append(responses, response)
				}
			}
		}
	}
	probeSeconds := time.Since(probeStarted).Seconds()
	exposure,err:=NewExposureProbe(panel,members)
	if err!=nil{t.Fatal(err)}
	featureStarted:=time.Now()
	features:=[]map[string]any{}
	numeric:=0
	for _,item:=range manifest.Items {
		d:=descriptions[item.Key]
		for _,count:=range []int{2,4} {
			for _,r:=range recipesByKey[item.Key] {
				if d.TierApplicability(r.Effect,count)==Excluded{continue}
				for termIndex:=range r.Terms {
					for _,actor:=range actors {
						feature,e:=exposure.Feature(d,r,termIndex,actor,vocabulary,tags)
						if e!=nil{t.Fatal(e)}
						if feature.RawStatProxyDPS!=nil{numeric++}
						features=append(features,map[string]any{"set":item.Key,"pieces":count,"feature":feature})
					}
				}
			}
		}
	}
	featureSeconds:=time.Since(featureStarted).Seconds()
	featureBytes,err:=json.MarshalIndent(features,"","  ")
	if err!=nil{t.Fatal(err)}
	if err=os.WriteFile(filepath.Join(os.Getenv("GTT_EFFECT_OUTPUT"),"channel-features.json"),featureBytes,0600);err!=nil{t.Fatal(err)}
	// Real source witnesses: field mutations and team targets must not vanish.
	gt := recipesByKey["goldentroupe"]
	hasHalf := false
	for _, r := range gt {
		for _, term := range r.Terms {
			hasHalf = hasHalf || term.Constant == "1/2"
		}
	}
	if !hasHalf {
		t.Fatal("helper-updated bonus missing")
	}
	team := false
	for _, r := range recipesByKey["noblesseoblige"] {
		team = team || r.RecipientScope == "team_iteration_member"
	}
	if !team {
		t.Fatal("team recipient unresolved")
	}
	responseBytes, err := json.MarshalIndent(responses, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(os.Getenv("GTT_EFFECT_OUTPUT"), "formula-signals.json"), responseBytes, 0600); err != nil {
		t.Fatal(err)
	}
	receipt := map[string]any{"schema_version": 1, "engine_sha256": manifest.Engine, "catalog_sha256": manifest.Catalog, "source_packages": len(rows), "effects": effects, "amount_terms": terms, "constant_terms": constants, "kinds": kinds, "boundary_counts": boundaries, "packages": rows, "elapsed_seconds_including_evidence_write": sourceSeconds, "saved_formula_decode_compile_seconds": formulaSeconds, "signal_probe_seconds": probeSeconds, "signal_count": len(responses), "unique_formula_evaluations": probe.Evaluations, "new_engine_calls": 0, "replacement_certified": false, "status": "source_discovery_and_old_context_signals_not_activation_or_ranking_acceptance"}
	receipt["stat_vocabulary_sha256"]=fmt.Sprintf("%x",sha256.Sum256([]byte(manifest.StatSource)))
	receipt["attack_vocabulary_sha256"]=fmt.Sprintf("%x",sha256.Sum256([]byte(manifest.AttackSource)))
	receipt["channel_features"]=len(features)
	receipt["channel_features_with_numeric_proxy"]=numeric
	receipt["channel_feature_evaluations"]=exposure.Evaluations
	receipt["channel_feature_seconds"]=featureSeconds
	raw, err = json.MarshalIndent(receipt, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(os.Getenv("GTT_EFFECT_OUTPUT"), "effect-discovery-receipt.json"), raw, 0600); err != nil {
		t.Fatal(err)
	}
	t.Logf("%d packages, %d effect sites, %d terms (%d constant), %.3fs; zero engine calls", len(rows), effects, terms, constants, time.Since(started).Seconds())
}

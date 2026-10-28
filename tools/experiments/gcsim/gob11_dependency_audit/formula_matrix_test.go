package formula

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
)
import "genshinteamstracker/native/gcsim_optimizer/internal/contracts"

// Narrow state-response localization, using the production evaluator on the
// engine's existing support graph. A diagnostic report, not an acceptance gate.
func TestSupportStateAudit(t *testing.T) {
	root := os.Getenv("GOB11_MATRIX_INPUT")
	if root == "" {
		t.Skip("explicit evidence directory required")
	}
	type observed struct {
		SupportGraph contracts.IRSeedMember `json:"support_graph"`
		CompactGraph contracts.IRSeedMember `json:"compact_graph"`
		StateEvents  []map[string]any       `json:"state_events"`
	}
	load := func(name string) observed {
		b, e := os.ReadFile(filepath.Join(root, name+".txt.observed.json"))
		if e != nil {
			t.Fatal(e)
		}
		var o observed
		if e = json.Unmarshal(b, &o); e != nil {
			t.Fatal(e)
		}
		return o
	}
	base := load("chasca")
	channelsByEvent := map[string][]contracts.IRChannel{}
	for _, ch := range base.SupportGraph.Channels {
		id := strings.SplitN(ch.ActorKey, "/", 2)[0]
		channelsByEvent[id] = append(channelsByEvent[id], ch)
	}
	type pointSpec struct {
		name, key string
		value     float64
	}
	var jobs []struct {
		Case, Config string
		Baseline     bool
		Deltas       map[string]float64
	}
	jobBytes, err := os.ReadFile(filepath.Join(root, "jobs.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(jobBytes, &jobs); err != nil {
		t.Fatal(err)
	}
	points := []pointSpec{}
	for _, j := range jobs {
		if j.Case != "chasca" || j.Baseline || len(j.Deltas) != 1 {
			continue
		}
		for key, value := range j.Deltas {
			points = append(points, pointSpec{strings.TrimSuffix(j.Config, ".txt"), key, value})
		}
	}
	rows := []any{}
	for _, point := range points {
		fresh := load(point.name)
		got, e := EvaluateSeedMember(base.SupportGraph, map[string]float64{point.key: point.value})
		if e != nil {
			t.Fatal(e)
		}
		want, e := EvaluateSeedMember(fresh.SupportGraph, nil)
		if e != nil {
			t.Fatal(e)
		}
		identity := func(value map[string]any) string {
			b, _ := json.Marshal([]any{value["kind"], value["frame"], value["provider"], value["owner_index"], value["source_id"], value["operation"], value["key"]})
			return string(b)
		}
		freshEvents := map[string][]map[string]any{}
		for _, ev := range fresh.StateEvents {
			key := identity(ev)
			freshEvents[key] = append(freshEvents[key], ev)
		}
		baseCounts, occurrence := map[string]int{}, map[string]int{}
		for _, ev := range base.StateEvents {
			baseCounts[identity(ev)]++
		}
		differences := []any{}
		total := 0
		unaligned := 0
		for _, ev := range base.StateEvents {
			id := ev["event_id"].(string)
			key := identity(ev)
			matches := freshEvents[key]
			if len(matches) != baseCounts[key] {
				unaligned++
				continue
			}
			fv := matches[occurrence[key]]
			occurrence[key]++
			freshID := fv["event_id"].(string)
			for _, ch := range channelsByEvent[id] {
				a, aok := got.ByActor[ch.ActorKey]
				b, bok := want.ByActor[freshID+strings.TrimPrefix(ch.ActorKey, id)]
				if !aok || !bok || math.Abs(a-b) <= 1e-8*math.Max(1, math.Abs(b)) {
					continue
				}
				total++
				if len(differences) < 12 {
					differences = append(differences, map[string]any{"channel": ch.ActorKey, "predicted": a, "fresh": b, "base_event": ev, "fresh_event": fv})
				}
			}
		}
		predicted, err := EvaluateSeedMember(base.CompactGraph, map[string]float64{point.key: point.value})
		if err != nil {
			t.Fatal(err)
		}
		actual, err := EvaluateSeedMember(fresh.CompactGraph, nil)
		if err != nil {
			t.Fatal(err)
		}
		rows = append(rows, map[string]any{"point": point.name, "differences": total, "unaligned_events": unaligned, "first": differences, "team_predicted": predicted.Damage, "team_fresh": actual.Damage, "team_relative_error": (predicted.Damage - actual.Damage) / actual.Damage})
	}
	data, e := json.MarshalIndent(rows, "", " ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "support-aligned-diagnosis.json"), data, 0600); e != nil {
		t.Fatal(e)
	}
}

func TestArchetypeAudit(t *testing.T) {
	root := os.Getenv("GOB11_MATRIX_INPUT")
	if root == "" {
		t.Skip("explicit bounded matrix required")
	}
	load := func(p string, v any) error {
		b, e := os.ReadFile(filepath.Join(root, p))
		if e != nil {
			return e
		}
		return json.Unmarshal(b, v)
	}
	var jobs []struct {
		Case, Output, Base, Error string
		Baseline                  bool
		Deltas                    map[string]float64
	}
	if e := load("jobs.json", &jobs); e != nil {
		t.Fatal(e)
	}
	results := []any{}
	for _, j := range jobs {
		if only := os.Getenv("GOB11_MATRIX_CASE"); only != "" && j.Case != only {
			continue
		}
		if j.Baseline {
			continue
		}
		row := map[string]any{"case": j.Case, "changed": j.Output, "deltas": j.Deltas}
		results = append(results, row)
		if j.Error != "" {
			row["capture_error"] = j.Error
			continue
		}
		var base, fresh contracts.IRSeedMember
		if e := load(j.Base, &base); e != nil {
			row["error"] = e.Error()
			continue
		}
		if e := load(j.Output, &fresh); e != nil {
			row["error"] = e.Error()
			continue
		}
		if e := contracts.ValidateSeedMember(base); e != nil {
			row["error"] = e.Error()
			continue
		}
		aligned := len(base.Channels) == len(fresh.Channels) && base.DurationMS == fresh.DurationMS
		row["same_topology_hash"] = base.TopologySHA256 == fresh.TopologySHA256
		row["base_hits"] = len(base.Channels)
		row["fresh_hits"] = len(fresh.Channels)
		ignoredZero := 0
		if aligned {
			for i, c := range base.Channels {
				f := fresh.Channels[i]
				if c.ChannelID != f.ChannelID || c.ActorKey != f.ActorKey || c.AttackTag != f.AttackTag || c.Kind != f.Kind || c.DamageType != f.DamageType {
					if c.BaselineDamage == "0" && f.BaselineDamage == "0" {
						ignoredZero++
						continue
					}
					aligned = false
					break
				}
			}
		}
		row["ignored_zero_damage_metadata_changes"] = ignoredZero
		row["aligned"] = aligned
		if len(base.Channels) != len(fresh.Channels) || base.DurationMS != fresh.DurationMS {
			continue
		}
		actorsMap := map[string]bool{}
		coordsMap := map[string]bool{}
		byHit := base
		byHit.Channels = append([]contracts.IRChannel(nil), base.Channels...)
		for i, c := range base.Channels {
			actorsMap[c.ActorKey] = true
			byHit.Channels[i].ActorKey = c.ChannelID
		}
		for _, n := range base.Nodes {
			if n.Coordinate != "" {
				coordsMap[n.Coordinate] = true
			}
		}
		actors, coords := []string{}, []string{}
		for k := range actorsMap {
			actors = append(actors, k)
		}
		for k := range coordsMap {
			coords = append(coords, k)
		}
		sort.Strings(actors)
		sort.Strings(coords)
		score, e := EvaluateSeedMember(byHit, j.Deltas)
		if e != nil {
			row["error"] = e.Error()
			continue
		}
		expected := 0.0
		maxRel := 0.0
		wrong := 0
		groups := map[string]float64{}
		for i, c := range base.Channels {
			want, _ := strconv.ParseFloat(fresh.Channels[i].BaselineDamage, 64)
			got := score.ByActor[c.ChannelID]
			expected += want
			diff := got - want
			key := c.ActorKey + "/" + c.AttackTag + "/" + c.Kind
			groups[key] += diff
			if math.Abs(diff) > 1e-6*math.Max(1, math.Abs(want)) {
				wrong++
			}
			maxRel = math.Max(maxRel, math.Abs(diff)/math.Max(1, math.Abs(want)))
		}
		row["predicted"] = score.Damage
		row["expected"] = expected
		row["relative_error"] = (score.Damage - expected) / expected
		row["max_hit_relative_error"] = maxRel
		row["mismatched_hits"] = wrong
		row["group_errors"] = groups
		if !aligned {
			predictedGroups, freshGroups := map[string][]float64{}, map[string][]float64{}
			key := func(c contracts.IRChannel) string {
				return c.ActorKey + "/" + c.AttackTag + "/" + c.Kind + "/" + c.DamageType
			}
			for _, c := range base.Channels {
				predictedGroups[key(c)] = append(predictedGroups[key(c)], score.ByActor[c.ChannelID])
			}
			for _, c := range fresh.Channels {
				v, _ := strconv.ParseFloat(c.BaselineDamage, 64)
				freshGroups[key(c)] = append(freshGroups[key(c)], v)
			}
			matches := len(predictedGroups) == len(freshGroups)
			maxError := 0.0
			for k, a := range predictedGroups {
				b := freshGroups[k]
				if len(a) != len(b) {
					matches = false
					continue
				}
				sort.Float64s(a)
				sort.Float64s(b)
				for i, v := range a {
					err := math.Abs(v-b[i]) / math.Max(1, math.Abs(b[i]))
					maxError = math.Max(maxError, err)
					if err > 1e-10 {
						matches = false
					}
				}
			}
			row["unordered_group_damage_multiset_matches"] = matches
			row["unordered_group_max_relative_error"] = maxError
		}
		details := []any{}
		for i, c := range base.Channels {
			want, _ := strconv.ParseFloat(fresh.Channels[i].BaselineDamage, 64)
			got := score.ByActor[c.ChannelID]
			if math.Abs(got-want) > 1e-6*math.Max(1, math.Abs(want)) && len(details) < 8 {
				details = append(details, map[string]any{"index": i, "channel": c.ChannelID, "actor": c.ActorKey, "got": got, "want": want})
			}
		}
		row["first_mismatches"] = details
		compiled, e := CompileSeedMember(base, actors, coords)
		if e != nil {
			row["compiled_error"] = e.Error()
			continue
		}
		dense := make([]float64, len(coords))
		for i, k := range coords {
			dense[i] = j.Deltas[k]
		}
		v, e := compiled.EvaluateDense(dense)
		if e != nil {
			row["compiled_error"] = e.Error()
		} else {
			row["dense_interpreter_error"] = v.Damage - score.Damage
		}
	}
	bytes, e := json.MarshalIndent(results, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	name := "response.json"
	if only := os.Getenv("GOB11_MATRIX_CASE"); only != "" {
		name = "response-" + only + ".json"
	}
	if e = os.WriteFile(filepath.Join(root, name), bytes, 0600); e != nil {
		t.Fatal(e)
	}
	t.Log("Diagnostic matrix recorded; passing this runner is NOT acceptance of failed response rows.")
}

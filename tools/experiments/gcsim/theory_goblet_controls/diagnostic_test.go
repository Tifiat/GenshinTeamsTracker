package engineclient

import (
	"encoding/json"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestParseStage16TraceExcludesNonEnemyHits(t *testing.T) {
	payload, seed, configSHA, sourceSHA, requestSHA := stage16TraceFixture(t)
	got, err := parseStage16Trace(payload, seed, configSHA, sourceSHA, requestSHA)
	if err != nil {
		t.Fatal(err)
	}
	if got.DPS != 300 || got.HitCount != 2 || got.AllHitCount != 4 || got.NonEnemyHitCount != 2 {
		t.Fatalf("unexpected hit aggregate: %+v", got)
	}
	if len(got.PerActorDamage) != 4 || got.PerActorDamage[0].Damage != 100.5 ||
		got.PerActorDamage[1].Damage != 0 || got.PerActorDamage[2].Damage != 49.5 ||
		got.PerActorDamage[3].Damage != 0 {
		t.Fatalf("unexpected per-actor damage: %+v", got.PerActorDamage)
	}
	if len(got.UnsupportedCodes) != 3 || got.UnsupportedCodes[0] != "hit_note" ||
		got.UnsupportedCodes[1] != "non_enemy_note" || got.UnsupportedCodes[2] != "root_note" {
		t.Fatalf("unexpected unsupported codes: %v", got.UnsupportedCodes)
	}
}

func TestParseStage16TraceRejectsBadSeedConfigAndDuration(t *testing.T) {
	payload, seed, configSHA, sourceSHA, requestSHA := stage16TraceFixture(t)
	var document map[string]any
	if err := json.Unmarshal(payload, &document); err != nil {
		t.Fatal(err)
	}

	t.Run("seed", func(t *testing.T) {
		changed := cloneStage16Fixture(t, document)
		changed["seed"] = "702"
		encoded, err := json.Marshal(changed)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := parseStage16Trace(encoded, seed, configSHA, sourceSHA, requestSHA); err == nil {
			t.Fatal("bad seed was accepted")
		}
	})

	t.Run("config", func(t *testing.T) {
		wrongConfigSHA := contracts.TextSHA256("different config")
		if _, err := parseStage16Trace(payload, seed, wrongConfigSHA, sourceSHA, requestSHA); err == nil {
			t.Fatal("trace with a different config binding was accepted")
		}
	})

	t.Run("duration", func(t *testing.T) {
		changed := cloneStage16Fixture(t, document)
		changed["duration_frames"] = 0
		encoded, err := json.Marshal(changed)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := parseStage16Trace(encoded, seed, configSHA, sourceSHA, requestSHA); err == nil {
			t.Fatal("zero duration was accepted")
		}
	})
}

func stage16TraceFixture(t *testing.T) ([]byte, uint64, string, string, string) {
	t.Helper()
	const seed = uint64(701)
	configSHA := contracts.TextSHA256("fixture config")
	sourceSHA := contracts.TextSHA256("normalized fixture config\n")
	request := stage16TraceRequest{
		SchemaVersion: 1, ContextSHA256: configSHA, Seed: "701", Iterations: 1,
		Workers: 1, IgnoreBurstEnergy: true,
	}
	requestBytes, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	requestSHA := contracts.TextSHA256(string(requestBytes))
	document := map[string]any{
		"schema_version":       6,
		"capability":           "gtt_trace_equation_v6",
		"context_sha256":       configSHA,
		"request_sha256":       requestSHA,
		"source_config_sha256": sourceSHA,
		"formula_sha256":       contracts.TextSHA256("fixture formula"),
		"target_sha256":        contracts.TextSHA256("fixture target"),
		"seed":                 "701",
		"duration_frames":      30,
		"character_keys":       []string{"chiori", "columbina", "furina", "xilonen"},
		"unsupported":          []string{"root_note"},
		"hits": []map[string]any{
			{"hit_id": 1, "actor_index": 0, "target_type": 0, "reported_damage": 100.5, "unsupported": []string{"hit_note"}},
			{"hit_id": 2, "actor_index": 2, "target_type": 0, "reported_damage": 49.5, "unsupported": []string{}},
			{"hit_id": 3, "actor_index": 1, "target_type": 1, "reported_damage": 900.0, "unsupported": []string{"non_enemy_note"}},
			{"hit_id": 4, "actor_index": 3, "target_type": 2, "reported_damage": 500.0, "unsupported": []string{}},
		},
	}
	payload, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	return payload, seed, configSHA, sourceSHA, requestSHA
}

func cloneStage16Fixture(t *testing.T, source map[string]any) map[string]any {
	t.Helper()
	encoded, err := json.Marshal(source)
	if err != nil {
		t.Fatal(err)
	}
	var clone map[string]any
	if err := json.Unmarshal(encoded, &clone); err != nil {
		t.Fatal(err)
	}
	return clone
}

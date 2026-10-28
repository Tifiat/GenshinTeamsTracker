package seteffects

import (
	"strings"
	"testing"
)

func scheduleTestProgram(t *testing.T, source string) *ruleProgram {
	t.Helper()
	program, err := compileRuleProgram(map[string][]byte{
		"internal/artifacts/synthetic/schedule.go": []byte("package sample\n" + source),
	}, nil)
	if err != nil {
		t.Fatal(err)
	}
	return program
}

func TestScheduleMetadataRespectsCountEarlyReturnAndReachableHelpers(t *testing.T) {
	program := scheduleTestProgram(t, `
import attributes "github.com/genshinsim/gcsim/pkg/attributes"
type Set struct { count int }
type Core struct{}
func NewSet(a, b int, count int) (*Set, error) {
    set := &Set{count: count}
    if count < 4 { return set, nil }
    applySchedule(nil)
    return set, nil
}
func applySchedule(c *Core) {
    _ = attributes.AtkSpd
    c.QueueAttack(1)
    c.QueueCharTask(1)
}
func (s *Set) Init() error { return nil }
`)
	catalog := &SourceCatalog{
		Stats: map[string]string{"github.com/genshinsim/gcsim/pkg/attributes.AtkSpd": "atkspd%"},
		Sets:  []DiscoveredSet{{Key: "synthetic", rule: program}},
	}
	rows := catalog.ScheduleCaptureMetadata()
	if len(rows) != 1 || len(rows[0].Tiers) != 2 {
		t.Fatalf("unexpected metadata rows: %+v", rows)
	}
	two, four := rows[0].Tiers[0], rows[0].Tiers[1]
	if two.Potential || !two.AnalysisComplete {
		t.Fatalf("early-returned 2-piece tier was marked hazardous: %+v", two)
	}
	if !four.Potential || !four.AnalysisComplete {
		t.Fatalf("reachable 4-piece hazard was missed: %+v", four)
	}
	joined := strings.Join(four.Reasons, ",")
	if !strings.Contains(joined, "attack_speed_source") || !strings.Contains(joined, "queued_attack_source") {
		t.Fatalf("missing source-derived reasons: %v", four.Reasons)
	}
	if strings.Contains(joined, "QueueCharTask") || strings.Contains(joined, "queued_combat_output") {
		t.Fatalf("unclassified queue methods were promoted: %v", four.Reasons)
	}
	needed, reasons := catalog.RequiresScheduleCapture([]RuleChoice{{Owner: 1, Key: "synthetic", Pieces: 2}})
	if needed || len(reasons) != 0 {
		t.Fatalf("inactive tier returned capture hint: %v %v", needed, reasons)
	}
	needed, reasons = catalog.RequiresScheduleCapture([]RuleChoice{{Owner: 1, Key: "synthetic", Pieces: 4}})
	if !needed || len(reasons) != 2 || !strings.Contains(strings.Join(reasons, " "), "schedule_capture_potential") {
		t.Fatalf("missing 4-piece potential hints: %v %v", needed, reasons)
	}
}

func TestScheduleMetadataOnlyClassifiesKnownAttackQueueAPIs(t *testing.T) {
	program := scheduleTestProgram(t, `
type Set struct{}
type Core struct{}
func NewSet(a, b, count int) (*Set, error) { var c *Core; c.QueueCharTask(1); c.QueueOtherTask(1); c.QueueAttackWithSnapShot(1); return &Set{}, nil }
func (s *Set) Init() error { return nil }
`)
	catalog := &SourceCatalog{Sets: []DiscoveredSet{{Key: "synthetic", rule: program}}}
	rows := catalog.ScheduleCaptureMetadata()
	for _, tier := range rows[0].Tiers {
		if !tier.Potential || !tier.AnalysisComplete || len(tier.Reasons) != 1 || tier.Reasons[0] != "queued_attack_source" {
			t.Fatalf("unexpected exact queue classification: %+v", tier)
		}
	}
}

func TestScheduleMetadataMarksUnavailableAnalysisUnknown(t *testing.T) {
	catalog := &SourceCatalog{Sets: []DiscoveredSet{{Key: "synthetic"}}}
	rows := catalog.ScheduleCaptureMetadata()
	if len(rows) != 1 {
		t.Fatal(rows)
	}
	for _, tier := range rows[0].Tiers {
		if tier.AnalysisComplete || tier.Potential || len(tier.Reasons) == 0 {
			t.Fatalf("unparsed rule was incorrectly reported as safe: %+v", tier)
		}
	}
}

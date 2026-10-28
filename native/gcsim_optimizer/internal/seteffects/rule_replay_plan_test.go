package seteffects

import (
	"reflect"
	"testing"
)

func TestPreparedReplayMatchesPublicOrder(t *testing.T) {
	neutral := ruleTestNeutral()
	queries := []RuleQuery{
		{Order: 30, Frame: 12, Active: 1, Owner: 0, Kind: "stat", Mode: "stat", Stat: "atk%"},
		{Order: 20, Frame: 11, Active: 1, Owner: 1, Kind: "stat", Mode: "stat", Stat: "hp%"},
		{Order: 20, Frame: 11, Active: 1, Owner: 0, Kind: "stat", Mode: "stat", Stat: "def%"},
	}
	ports := make([]neutralBoundPort, len(queries))
	for i, query := range queries {
		ports[i].query = query
	}
	member := neutralBoundMember{neutral: neutral, ports: ports, queries: queries, queryOrder: []int{1, 2, 0}}
	gotQueries, order := member.preparedQueries()
	if &gotQueries[0] != &queries[0] || !reflect.DeepEqual(order, []int{1, 2, 0}) {
		t.Fatal("prepared query order changed")
	}
	catalog := &SourceCatalog{}
	for _, symbolic := range []bool{false, true} {
		ordinary := catalog.replayNeutralRules(neutral, nil, queries, symbolic)
		prepared := catalog.replayNeutralRulesPrepared(neutral, nil, gotQueries, symbolic, order)
		if !reflect.DeepEqual(ordinary, prepared) {
			t.Fatalf("prepared replay diverged (symbolic=%v): ordinary=%+v prepared=%+v", symbolic, ordinary, prepared)
		}
	}
	// Public callers can supply arbitrary slices; their chronological order is
	// still derived afresh, while a binding keeps its constructor-owned plan.
	queries[0], queries[1] = queries[1], queries[0]
	ordinary := catalog.ReplayNeutralRules(neutral, nil, queries)
	if len(ordinary.Values) != len(queries) || ordinary.Boundary != "" {
		t.Fatalf("public replay failed after reordering: %+v", ordinary)
	}
}

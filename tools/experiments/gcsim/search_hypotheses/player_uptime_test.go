package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"reflect"
	"testing"
)

func TestHypothesisApproximateUptimeIsolation(t *testing.T) {
	b := &NeutralBinding{members: []neutralBoundMember{{ports: []neutralBoundPort{
		{dimension: 0, query: RuleQuery{Owner: 0, Kind: "stat", Mode: "stat", Stat: "cr"}},
		{dimension: 1, query: RuleQuery{Owner: 0, Kind: "stat", Mode: "stat", Stat: "cr"}},
		{dimension: 2, query: RuleQuery{Owner: 1, Kind: "stat", Mode: "stat", Stat: "cr"}},
		{dimension: 3, query: RuleQuery{Owner: 1, Kind: "stat", Mode: "stat", Stat: "cr"}},
		{dimension: 4, query: RuleQuery{Owner: 0, Kind: "stat", Mode: "non_extra_stat", Stat: "cr"}},
	}}}}
	c := NeutralExpressions{raw: []float64{0, .25, 0, .5, .75}}
	t.Setenv("GTT_HYPOTHESIS_UPTIME", "mean")
	if got := b.hypothesisApproximate(c); !reflect.DeepEqual(got, []float64{.125, .125, .25, .25, .75}) {
		t.Fatal(got)
	}
	t.Setenv("GTT_HYPOTHESIS_UPTIME", "peak")
	if got := b.hypothesisApproximate(c); !reflect.DeepEqual(got, []float64{.25, .25, .5, .5, .75}) {
		t.Fatal(got)
	}
	c.Effects = map[string]*formula.InputExpression{"dependent": {Operation: "add"}}
	if got := b.hypothesisApproximate(c); !reflect.DeepEqual(got, c.raw) {
		t.Fatal("symbolic component changed")
	}
	t.Setenv("GTT_HYPOTHESIS_UPTIME", "")
	c.Effects = nil
	if got := b.hypothesisApproximate(c); !reflect.DeepEqual(got, c.raw) {
		t.Fatal("oracle path changed")
	}
}

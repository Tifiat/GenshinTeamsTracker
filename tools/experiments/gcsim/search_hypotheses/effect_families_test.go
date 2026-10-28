package seteffects

import (
    "math"
    "testing"
    "reflect"
    "genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

func TestHypothesisEffectFamiliesExactBitsAndOwnership(t *testing.T) {
    b := &NeutralBinding{}
    a := neutralComponent{raw: []float64{0, 0.18, 80}, usable: true}
    c := neutralComponent{raw: []float64{0, 0.18, 80}, usable: true}
    b.hypothesisIdentify(&a); b.hypothesisIdentify(&c)
    if a.hypothesisIdentity != c.hypothesisIdentity { t.Fatal("identical effects differ") }
    c.raw[0] = math.Copysign(0, -1)
    b.hypothesisIdentify(&c)
    if a.hypothesisIdentity == c.hypothesisIdentity { t.Fatal("raw float bits ignored") }
    c.raw = []float64{80, 0.18, 0}
    b.hypothesisIdentify(&c)
    if a.hypothesisIdentity == c.hypothesisIdentity { t.Fatal("port ownership ignored") }
    a.expressions = map[int]*formula.InputExpression{0: {Operation: "artifact", Key: "a"}}
    c.expressions = a.expressions
    b.hypothesisIdentify(&a); b.hypothesisIdentify(&c)
    if a.hypothesisIdentity == c.hypothesisIdentity { t.Fatal("symbolic equality guessed") }
    out := NeutralExpressions{raw: []float64{1}, Constants: []float64{1}, Uncertainty: []string{"diagnostic"}}
    out.footprint.write("actual-source")
    for i:=0; i<260; i++ { b.hypothesisRetainPayload(string(rune(i)), out) }
    if len(b.hypothesisPayloads) != 128 || b.hypothesisPayloadValues != 256 { t.Fatal("unbounded cache", len(b.hypothesisPayloads), b.hypothesisPayloadValues) }
    for _, stored := range b.hypothesisPayloads {
        if len(stored.Uncertainty)!=0 || len(stored.footprint.writes)!=0 { t.Fatal("foreign source diagnostics retained") }
    }
}

func TestHypothesisFamiliesKeepSourceDiagnosticsAndDependencyMerges(t *testing.T) {
    a, c, e, other := RuleChoice{0,"a",2}, RuleChoice{0,"c",2}, RuleChoice{0,"e",2}, RuleChoice{1,"other",4}
    leaf := &formula.InputExpression{Operation:"read", Key:"stat-root"}
    b := &NeutralBinding{catalog:&SourceCatalog{}, keys:[]string{"one","two"},
        members:[]neutralBoundMember{{neutral:ruleTestNeutral(), ports:[]neutralBoundPort{{dimension:0},{dimension:1}}}},
        components:map[RuleChoice]neutralComponent{}, groups:map[string]neutralComponent{}}
    for _, choice := range []RuleChoice{a,c,e} {
        component := neutralComponent{raw:[]float64{1,0}, usable:true, uncertainty:[]string{choice.Key}}
        component.footprint.write(choice.Key)
        b.hypothesisIdentify(&component)
        b.components[choice]=component
    }
    dependent := neutralComponent{raw:[]float64{0,0}, usable:true, expressions:map[int]*formula.InputExpression{1:leaf}}
    dependent.footprint.read("e")
    b.hypothesisIdentify(&dependent)
    b.components[other]=dependent
    joint := neutralComponent{raw:[]float64{9,0}, usable:true}
    b.hypothesisIdentify(&joint)
    b.groups[ruleChoicesKey([]RuleChoice{e,other})]=joint
    for _, choice := range []RuleChoice{a,c,a,c} {
        choices:=[]RuleChoice{choice,other}
        got:=b.CompilePackagesSparse(choices)
        want:=b.CompilePackages(choices)
        expanded:=map[string]*formula.InputExpression{}
        for i,key:=range b.keys {
            if x,ok:=got.SparseEffects[i];ok { expanded[key]=x } else { expanded[key]=&formula.InputExpression{Operation:"constant",Value:got.Constants[i]} }
        }
        if !got.Complete() || !reflect.DeepEqual(expanded,want.Effects) || !reflect.DeepEqual(got.Uncertainty,want.Uncertainty) || !reflect.DeepEqual(got.footprint,want.footprint) { t.Fatal("payload/source data diverged",choice,got,want) }
    }
    if b.stats.FamilyHits!=3 { t.Fatal("identical family not reused",b.stats) }
    got:=b.CompilePackagesSparse([]RuleChoice{e,other})
    if !got.Complete() || got.Constants[0]!=9 || b.stats.Merges==0 { t.Fatal("family cache skipped source interaction",got,b.stats) }
}

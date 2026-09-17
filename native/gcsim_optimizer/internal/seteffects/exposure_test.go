package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"testing"
)

type channelFixture struct{}

func (channelFixture) Coordinates() []string { return []string{"holder.damage_bonus"} }
func (channelFixture) EvaluateChannelDPS(d []float64) ([][]float64, error) {
	return [][]float64{{100 + 100*d[0], 900}}, nil
}

func TestChannelGuideNeverInventsBonusResponseForUnrepresentedReaction(t *testing.T) {
	m := contracts.IRSeedMember{DurationMS: 1000, Channels: []contracts.IRChannel{{ActorKey: "holder", AttackTag: "tag/1", BaselineDamage: "100"}, {ActorKey: "holder", AttackTag: "tag/2", BaselineDamage: "900"}}}
	p, e := NewExposureProbe(channelFixture{}, []contracts.IRSeedMember{m})
	if e != nil {
		t.Fatal(e)
	}
	r := Recipe{Effect: Effect{ID: "test", Kind: "attack_bonus"}, RecipientScope: "owner", Terms: []Term{{Coordinate: "dmg", Constant: "1/2"}}}
	got, e := p.Feature(Description{}, r, 0, "holder", map[string]string{"dmg": "dmg%"}, nil)
	if e != nil || got.RawStatProxyDPS == nil || *got.RawStatProxyDPS != 50 || got.PossibleDamageDPS != 1000 {
		t.Fatal(got, e)
	}
	r.Effect.Kind = "reaction_bonus"
	got, e = p.Feature(Description{}, r, 0, "holder", nil, nil)
	if e != nil || got.RawStatProxyDPS != nil {
		t.Fatal("invented reaction multiplier", got, e)
	}
	if p.Evaluations != 2 {
		t.Fatal("unnecessary formula calculation", p.Evaluations)
	}
	m.Channels[0].BaselineDamage = "101"
	if _, e = NewExposureProbe(channelFixture{}, []contracts.IRSeedMember{m}); e == nil {
		t.Fatal("mismatched metadata accepted")
	}
}

type teamChannelFixture struct{}

func (teamChannelFixture) Coordinates() []string { return []string{"a.em", "b.em"} }
func (teamChannelFixture) EvaluateChannelDPS(d []float64) ([][]float64, error) {
	return [][]float64{{(10 + d[0]) * (10 + d[1])}}, nil
}
func TestTeamProxyPerturbsRecipientsTogether(t *testing.T) {
	m := contracts.IRSeedMember{DurationMS: 1000, Channels: []contracts.IRChannel{{ActorKey: "a", AttackTag: "tag/1", BaselineDamage: "100"}}}
	p, e := NewExposureProbe(teamChannelFixture{}, []contracts.IRSeedMember{m})
	if e != nil {
		t.Fatal(e)
	}
	r := Recipe{Effect: Effect{ID: "team", Kind: "stat"}, RecipientScope: "team_iteration_member", Terms: []Term{{Coordinate: "em", Constant: "1"}}}
	f, e := p.Feature(Description{}, r, 0, "a", map[string]string{"em": "em"}, nil)
	if e != nil || f.RawStatProxyDPS == nil || *f.RawStatProxyDPS != 21 {
		t.Fatal("lost joint interaction", f, e)
	}
	if e = p.Reanchor(map[string]float64{"a.em": 100}); e != nil {
		t.Fatal(e)
	}
	f, e = p.Feature(Description{}, r, 0, "a", map[string]string{"em": "em"}, nil)
	if e != nil || f.RawStatProxyDPS == nil || *f.RawStatProxyDPS != 121 {
		t.Fatal("guide kept old stat anchor/cache", f, e)
	}
	if e = p.Reanchor(map[string]float64{"absent.em": 100}); e == nil {
		t.Fatal("unknown panel stat accepted")
	}
}

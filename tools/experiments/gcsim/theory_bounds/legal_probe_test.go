package formula

import (
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"testing"
)

// Exhaust all points of a deliberately tiny legal subdomain: two circlet
// mains, two line identities and quarter upgrades on two selected lines.
func TestResearchAlternativesExhaustLegalMainLineQuarterGrid(t *testing.T) {
	var mains [4][5]string
	for a := range mains {
		mains[a] = [5]string{"hp", "atk", "atk_percent", "anemo_damage_bonus", "crit_rate"}
	}
	points := [][]float64{}
	for _, main := range []string{"crit_rate", "crit_damage"} {
		for _, other := range []int{0, 8} {
			for a := 0; a <= 20; a++ {
				for b := 0; b <= 20-a; b++ {
					s := proto.Seed(mains, [4][10]float64{}, 1, 45)
					s.Mains[0][4] = main
					s.Upgrades = [4][5][4]float64{}
					crit := 2
					if main == "crit_damage" {
						crit = 3
					}
					s.Lines[0][4] = [4]int{crit, 1, 6, other}
					s.Upgrades[0][4] = [4]float64{float64(a) / 4, float64(b) / 4, 0, 0}
					if err := s.Validate(45, true); err != nil {
						t.Fatal(err)
					}
					rolls := s.Rolls()
					v := []float64{rolls[0][3] * proto.Values[3], rolls[0][2] * proto.Values[2], rolls[0][1] * proto.Values[1]}
					for _, m := range s.Mains[0] {
						switch m {
						case "crit_rate":
							v[0] += proto.MainValues[m]
						case "crit_damage":
							v[1] += proto.MainValues[m]
						case "atk_percent":
							v[2] += proto.MainValues[m]
						}
					}
					points = append(points, v)
				}
			}
		}
	}
	p, n := testProgram(3)
	x, y, z := n(opArtifactStat, 0, 0), n(opArtifactStat, 0, 1), n(opArtifactStat, 0, 2)
	one := n(opConstant, 1, -1)
	negative := n(opConstant, -.2, -1)
	base := n(opAdd, 0, -1, one, y)
	product := n(opMultiply, 0, -1, x, base)
	cap := n(opMin, 0, -1, z, one)
	signed := n(opMultiply, 0, -1, negative, x)
	low := n(opAdd, 0, -1, product, cap, signed)
	jump := n(opConstant, 5, -1)
	n(opSelectLT, 0, -1, x, one, low, jump)
	support := researchFiniteSupport(points)
	center, ref := []float64{.5, 1, 1}, []float64{0, 0, 0}
	a := p.ResearchEnvelope(center, ref, support, false)
	b := p.ResearchPlanes(center, ref, support)
	for _, point := range points {
		v, err := p.Evaluate(point)
		if err != nil || v > a.ModelUpper+1e-8 || v > b.ModelUpper+1e-8 {
			t.Fatal(point, v, a, b, err)
		}
	}
}

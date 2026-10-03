package seteffects

import "testing"

func TestRulePieceTierSurvivesSavedCountAndClosure(t *testing.T) {
	const source = `
type Set struct { Count int }
func (s *Set) Enabled() bool { count := s.Count; return count >= 4 }
func Start(count int) float64 {
 s := &Set{Count: count}
 later := func() float64 { if s.Enabled() { return 7 }; return 3 }
 if count < 2 { return 0 }
 return later()
}`
	for count := 2; count <= 5; count++ {
		vm := testRule(t, source, nil)
		got, err := vm.entry("Start", pieceTier(count))
		want := float64(3)
		if count >= 4 {
			want = 7
		}
		if err != nil || got != want {
			t.Fatal(count, got, err)
		}
	}
}

func TestRulePieceTierRejectsNonEquivalentCountUses(t *testing.T) {
	for _, source := range []string{
		`func Start(count int) float64 { if count == 2 { return 1 }; return 0 }`,
		`func Start(count int) float64 { return float64(count) }`,
		`func Start(count int) float64 { return count * 2.0 }`,
		`func Start(count int) float64 { a := []float64{1,2,3,4}; return a[count] }`,
	} {
		vm := testRule(t, source, nil)
		if value, err := vm.entry("Start", pieceTier(2)); err == nil {
			t.Fatal("physical-count distinction lost", source, value)
		}
	}
}

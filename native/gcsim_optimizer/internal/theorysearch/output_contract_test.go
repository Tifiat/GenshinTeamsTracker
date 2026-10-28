package theorysearch

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/theory"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

// These are frozen publication-contract fixtures, not captured numerical
// evidence or a search-quality oracle. Expected bands/counts are declared below;
// the oracle never calls deficit, allocations, State.Rolls or solver validators.
var outputStatKeys = [10]string{
	"atk", "atk_percent", "crit_damage", "crit_rate", "def",
	"def_percent", "em", "energy_recharge", "hp", "hp_percent",
}

var outputStatValues = [10]float64{
	19.45, .0583, .0777, .0389, 23.15,
	.0729, 23.31, .0648, 298.75, .0583,
}

var outputLegalMains = [5][]string{
	{"hp"}, {"atk"},
	{"atk_percent", "def_percent", "em", "energy_recharge", "hp_percent"},
	{"anemo_damage_bonus", "atk_percent", "cryo_damage_bonus", "def_percent", "dendro_damage_bonus", "electro_damage_bonus", "em", "geo_damage_bonus", "hp_percent", "hydro_damage_bonus", "physical_damage_bonus", "pyro_damage_bonus"},
	{"atk_percent", "crit_damage", "crit_rate", "def_percent", "em", "healing_bonus", "hp_percent"},
}

type outputFamilyWant struct {
	score      float64
	deficit    float64
	refinement int
	group      bool
	sensitive  bool
	reason     string
	witness    alloc.State
	aliases    map[string]Alias
}

type outputContractWant struct {
	request, session, phase                string
	version                                int64
	terminal                               bool
	reference                              float64
	wearers                                [4]string
	families                               map[string]outputFamilyWant
	unavailable                            map[string]Unavailable
	totalFamilies, totalTuples             int
	groupFamilies, groupTuples             int
	sensitivityFamilies, sensitivityTuples int
	domainTuples, unseenTuples             string
	covered                                bool
	work                                   Work
}

func outputFixturePackage(sets ...contracts.SetRequirement) domain.Package {
	return domain.Package{Sets: append([]contracts.SetRequirement{}, sets...)}
}

// Encode the explicit wire identity independently of the search package-key
// helper, so a duplicated/missing tuple cannot be concealed by that helper.
func outputTupleKey(p [4]domain.Package) string {
	var keys [4]string
	for actor, pkg := range p {
		if len(pkg.Sets) == 0 {
			keys[actor] = "none"
			continue
		}
		parts := make([]string, len(pkg.Sets))
		for i, set := range pkg.Sets {
			parts[i] = fmt.Sprintf("%s:%d", set.SetUID, set.Count)
		}
		keys[actor] = strings.Join(parts, "+")
	}
	return strings.Join(keys[:], "|")
}

func outputPackageRows(p [4]domain.Package, wearers [4]string) []PackageRow {
	rows := make([]PackageRow, 4)
	for actor, pkg := range p {
		rows[actor] = PackageRow{WearerKey: wearers[actor], Sets: append([]contracts.SetRequirement{}, pkg.Sets...)}
	}
	return rows
}

func outputFixtureWitness(variant int) alloc.State {
	s := alloc.State{Mains: [4][5]string{
		{"hp", "atk", "atk_percent", "geo_damage_bonus", "crit_rate"},
		{"hp", "atk", "hp_percent", "hydro_damage_bonus", "healing_bonus"},
		{"hp", "atk", "energy_recharge", "em", "crit_damage"},
		{"hp", "atk", "def_percent", "physical_damage_bonus", "em"},
	}}
	upgrades := [4]float64{.25, 1, 1.75, 2}
	for actor := range s.Mains {
		for slot, main := range s.Mains[actor] {
			line := 0
			for offset := 0; line < 4; offset++ {
				stat := (variant + 3*actor + 2*slot + offset) % 10
				if outputStatKeys[stat] != main {
					s.Lines[actor][slot][line] = stat
					s.Upgrades[actor][slot][line] = upgrades[(variant+actor+slot+line)%4]
					line++
				}
			}
		}
	}
	return s
}

func outputWitnessRolls(s alloc.State) ([4][10]float64, error) {
	var rolls [4][10]float64
	for actor := range s.Mains {
		actorUpgrades := 0.0
		for slot, main := range s.Mains[actor] {
			legal := false
			for _, choice := range outputLegalMains[slot] {
				legal = legal || main == choice
			}
			if !legal {
				return rolls, fmt.Errorf("wearer %d slot %d illegal main %q", actor, slot, main)
			}
			seen := map[int]bool{}
			slotUpgrades := 0.0
			for line, stat := range s.Lines[actor][slot] {
				if stat < 0 || stat >= 10 || seen[stat] || outputStatKeys[stat] == main {
					return rolls, fmt.Errorf("wearer %d slot %d illegal initial line %d", actor, slot, line)
				}
				seen[stat] = true
				u := s.Upgrades[actor][slot][line]
				if math.IsNaN(u) || math.IsInf(u, 0) || u < 0 || math.Abs(4*u-math.Round(4*u)) > 1e-8 {
					return rolls, fmt.Errorf("wearer %d slot %d non-quarter upgrade", actor, slot)
				}
				slotUpgrades += u
				rolls[actor][stat] += 1 + u
			}
			if slotUpgrades > 5+1e-8 {
				return rolls, fmt.Errorf("wearer %d slot %d exceeds five upgrades", actor, slot)
			}
			actorUpgrades += slotUpgrades
		}
		if math.Abs(actorUpgrades-25) > 1e-8 {
			return rolls, fmt.Errorf("wearer %d has %g upgrades, expected 25", actor, actorUpgrades)
		}
	}
	return rolls, nil
}

func outputCheckAllocations(got []theory.WearerAllocation, state alloc.State, wearers [4]string) error {
	rolls, err := outputWitnessRolls(state)
	if err != nil {
		return err
	}
	if len(got) != 4 {
		return fmt.Errorf("allocation wearer count %d, expected four", len(got))
	}
	slots := [5]string{"flower", "plume", "sands", "goblet", "circlet"}
	for actor, row := range got {
		if row.WearerKey != wearers[actor] || len(row.MainStats) != 5 || len(row.Substats) != 10 {
			return fmt.Errorf("allocation owner/main/substat coverage for wearer %d", actor)
		}
		for slot, key := range slots {
			if row.MainStats[key] != state.Mains[actor][slot] {
				return fmt.Errorf("allocation main projection for wearer %d slot %s", actor, key)
			}
		}
		seen := map[string]bool{}
		spent := 0.0
		for _, stat := range row.Substats {
			index := -1
			for i, key := range outputStatKeys {
				if key == stat.StatKey {
					index = i
				}
			}
			if index < 0 || seen[stat.StatKey] {
				return fmt.Errorf("allocation duplicate/unknown substat for wearer %d", actor)
			}
			seen[stat.StatKey] = true
			units := rolls[actor][index]
			if !outputNear(stat.RollUnits, units) || !outputNear(stat.StatValue, units*outputStatValues[index]) {
				return fmt.Errorf("allocation roll/stat projection for wearer %d stat %s", actor, stat.StatKey)
			}
			spent += units
		}
		if !outputNear(spent, 45) || !outputNear(row.SpentRollUnits, 45) || !outputNear(row.UnspentRollUnits, 0) {
			return fmt.Errorf("allocation budget projection for wearer %d", actor)
		}
	}
	return nil
}

func outputNear(a, b float64) bool {
	return !math.IsNaN(a) && !math.IsInf(a, 0) && math.Abs(a-b) <= 1e-9
}

func outputFrozenArchive() (*Session, outputContractWant) {
	wearers := [4]string{"archive-a", "archive-b", "archive-c", "archive-d"}
	cfg := Config{Binding: "frozen-output-binding", RequestSHA256: strings.Repeat("a", 64),
		SessionID: "frozen-output-session", Wearers: wearers, Initial: outputFixtureWitness(0)}
	for i := 0; i < 10; i++ {
		uid := fmt.Sprintf("a%02d", i)
		var pkg domain.Package
		switch i % 4 {
		case 0:
			pkg = outputFixturePackage()
			if i != 0 {
				pkg = outputFixturePackage(contracts.SetRequirement{SetUID: uid, Count: 2})
			}
		case 1:
			pkg = outputFixturePackage(contracts.SetRequirement{SetUID: uid, Count: 2})
		case 2:
			pkg = outputFixturePackage(contracts.SetRequirement{SetUID: uid, Count: 4})
		case 3:
			pkg = outputFixturePackage(contracts.SetRequirement{SetUID: uid, Count: 2}, contracts.SetRequirement{SetUID: fmt.Sprintf("z%02d", i), Count: 2})
		}
		cfg.Domains[0] = append(cfg.Domains[0], pkg)
	}
	cfg.Domains[1] = []domain.Package{
		outputFixturePackage(contracts.SetRequirement{SetUID: "b00", Count: 4}),
		outputFixturePackage(contracts.SetRequirement{SetUID: "b01", Count: 2}, contracts.SetRequirement{SetUID: "z01", Count: 2}),
	}
	cfg.Domains[2] = []domain.Package{outputFixturePackage(), outputFixturePackage(contracts.SetRequirement{SetUID: "c01", Count: 2})}
	cfg.Domains[3] = []domain.Package{
		outputFixturePackage(contracts.SetRequirement{SetUID: "d00", Count: 4}),
		outputFixturePackage(contracts.SetRequirement{SetUID: "d01", Count: 2}, contracts.SetRequirement{SetUID: "z02", Count: 2}),
	}
	tuple := func(indices [4]int) [4]domain.Package {
		var p [4]domain.Package
		for actor, index := range indices {
			p[actor] = cfg.Domains[actor][index]
		}
		return p
	}
	cfg.Original = tuple([4]int{9, 0, 0, 0}) // Equipped/shallow is not the archived best.
	work := Work{Formula: 37, Gradient: 11, AllocationAttempts: 9, AliasHits: 23,
		CompletedPasses: 2, DeepBundles: 0, CompletedSweeps: 16, IndependentStarts: 13, TransferredStarts: 7}
	s := &Session{cfg: cfg, active: newBranch(nil, cfg.Initial), archive: newBranch(nil, cfg.Initial), phase: "breadth_light", version: 40}
	s.active.work = work
	s.archive.work = Work{Formula: 999} // Output must project the active branch, not archive work.
	want := outputContractWant{request: cfg.RequestSHA256, session: cfg.SessionID, phase: "breadth_light", version: 41,
		reference: 1000, wearers: wearers, families: map[string]outputFamilyWant{}, unavailable: map[string]Unavailable{},
		totalFamilies: 10, totalTuples: 17, groupFamilies: 7, groupTuples: 13,
		sensitivityFamilies: 4, sensitivityTuples: 7, domainTuples: "80", unseenTuples: "61", work: work}
	// Boundary deltas are much larger than the publication rounding tolerance.
	// 951 is close to 969.99999, but cannot enter by chaining through that row.
	sources := []struct {
		family           string
		score, deficit   float64
		refinement       int
		group, sensitive bool
		reason           string
		aliases          [][4]int
	}{
		{"best", 1000, 0, 2, true, true, "", [][4]int{{0, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 1}}},
		{"best-tie", 1000, 0, 0, true, true, "", [][4]int{{1, 0, 0, 0}}},
		{"inside-two", 980.00001, 1.999999, 0, true, true, "", [][4]int{{2, 0, 0, 0}}},
		{"on-two", 980, 2, 1, true, true, "", [][4]int{{3, 0, 0, 0}, {3, 1, 1, 0}}},
		{"outside-two", 979.99999, 2.000001, 2, true, false, "", [][4]int{{4, 0, 0, 0}}},
		{"inside-three", 970.00001, 2.999999, 0, true, false, "", [][4]int{{5, 0, 0, 0}, {5, 1, 0, 1}}},
		{"on-three", 970, 3, 1, true, false, "", [][4]int{{6, 0, 0, 0}, {6, 0, 1, 0}, {6, 1, 1, 1}}},
		{"outside-three", 969.99999, 3.000001, 1, false, false, "below_practical_band_not_deeply_refined", [][4]int{{7, 0, 0, 0}}},
		{"chained-tail", 951, 4.9, 2, false, false, "below_practical_band", [][4]int{{8, 0, 0, 0}, {8, 1, 1, 1}}},
		{"shallow-low", 800, 20, 0, false, false, "below_practical_band_not_deeply_refined", [][4]int{{9, 0, 0, 0}}},
	}
	for i, source := range sources {
		state := outputFixtureWitness(i)
		p := tuple(source.aliases[0])
		s.archive.pool[source.family] = candidate{packages: p, state: state, value: source.score, family: source.family}
		s.archive.refined[source.family] = source.refinement
		s.archive.aliases[source.family] = map[string]Alias{}
		family := outputFamilyWant{score: source.score, deficit: source.deficit, refinement: source.refinement,
			group: source.group, sensitive: source.sensitive, reason: source.reason, witness: state, aliases: map[string]Alias{}}
		for _, indices := range source.aliases {
			p := tuple(indices)
			key := outputTupleKey(p)
			contextSHA := fmt.Sprintf("%x", sha256.Sum256([]byte("frozen-output-context:"+key)))
			alias := Alias{TupleKey: key, Packages: outputPackageRows(p, wearers), ContextSHA256: contextSHA,
				Uncertainty: []string{"unknown_source_operand:" + source.family, "unbounded_source_tail:" + key}}
			family.aliases[key] = alias
			// Do not share any nested expectation slices with the archived input.
			s.archive.aliases[source.family][key] = Alias{TupleKey: key, Packages: outputPackageRows(p, wearers),
				ContextSHA256: alias.ContextSHA256, Uncertainty: append([]string{}, alias.Uncertainty...)}
			s.archive.visited[key] = source.family
		}
		want.families[source.family] = family
	}
	for i, indices := range [][4]int{{7, 1, 1, 1}, {9, 1, 1, 0}} {
		p := tuple(indices)
		key := outputTupleKey(p)
		reasons := []string{"unknown_source_identifier", fmt.Sprintf("unmodeled_activation_%d", i)}
		want.unavailable[key] = Unavailable{TupleKey: key, Packages: outputPackageRows(p, wearers), Reasons: append([]string{}, reasons...)}
		s.archive.unavailable[key] = Unavailable{TupleKey: key, Packages: outputPackageRows(p, wearers), Reasons: append([]string{}, reasons...)}
		s.archive.visited[key] = ""
	}
	return s, want
}

func outputCheckSnapshot(got Snapshot, want outputContractWant) error {
	if got.SchemaVersion != 2 || got.SchemaKind != "gtt_gcsim_optimizer_theory_result_v2" ||
		got.RequestSHA256 != want.request || got.SessionID != want.session || got.SnapshotVersion != want.version ||
		got.Phase != want.phase || got.PolicyID != "theory_h_light_common_h_20261010_v1" || got.FinishedEarly != want.terminal {
		return errors.New("snapshot schema/identity/version/phase/terminal projection")
	}
	if got.Status != "success" || got.SearchStatus != "partial" || got.ResponseStatus != "formula_only" ||
		got.SourceUpper != "unbounded" || got.OuterUpper != "unbounded" ||
		!outputNear(got.ReferenceScore, want.reference) || got.PracticalBandPercent != 3 || got.SensitivityBandPercent != 2 {
		return errors.New("snapshot reference/bands/unknown bounds/status")
	}
	if got.TotalFoundFamilies != want.totalFamilies || got.TotalFoundTuples != want.totalTuples ||
		got.FoundGroupFamilies != want.groupFamilies || got.FoundGroupTuples != want.groupTuples ||
		got.SensitivityGroupFamilies != want.sensitivityFamilies || got.SensitivityGroupTuples != want.sensitivityTuples ||
		got.DomainTuples != want.domainTuples || got.UnseenTuples != want.unseenTuples || got.FullCartesianCovered != want.covered || got.Work != want.work {
		return errors.New("snapshot exact totals/coverage/active work")
	}
	rules := map[string]any{"budget_roll_units_per_wearer": 45, "quarter_grid": true, "all_found_aliases": true,
		"reference_scope": "best_attained_across_found_branches", "practical_group_rank": "unordered_equivalent_group",
		"full_search_optimality_proved": false, "final_solution_cache_enabled": false}
	// JSON round trips represent numbers as float64; compare their wire forms.
	rulesRaw, _ := json.Marshal(rules)
	gotRulesRaw, _ := json.Marshal(got.Rules)
	if string(rulesRaw) != string(gotRulesRaw) {
		return errors.New("snapshot unsupported rank/optimality/cache rule")
	}
	families, tuples := map[string]bool{}, map[string]string{}
	totalTuples, groupFamilies, groupTuples, sensitivityFamilies, sensitivityTuples := 0, 0, 0, 0, 0
	for _, bucket := range []struct {
		rows  []FamilyRow
		group bool
	}{{got.CoLeaders, true}, {got.Pending, false}} {
		for _, row := range bucket.rows {
			expect, known := want.families[row.Family]
			if !known || families[row.Family] || bucket.group != expect.group {
				return fmt.Errorf("unknown/duplicate/misplaced family %q", row.Family)
			}
			families[row.Family] = true
			if !outputNear(row.FormulaDPS, expect.score) || !outputNear(row.DeficitPercent, expect.deficit) ||
				row.RefinementLevel != expect.refinement || row.Reason != expect.reason || row.Witness45 != expect.witness {
				return fmt.Errorf("family score/deficit/refinement/reason/witness %q", row.Family)
			}
			if err := outputCheckAllocations(row.Allocations, row.Witness45, want.wearers); err != nil {
				return fmt.Errorf("family %q: %w", row.Family, err)
			}
			if len(row.Aliases) != len(expect.aliases) {
				return fmt.Errorf("alias multiplicity for family %q", row.Family)
			}
			local := map[string]bool{}
			for _, alias := range row.Aliases {
				expectedAlias, known := expect.aliases[alias.TupleKey]
				if !known || local[alias.TupleKey] || tuples[alias.TupleKey] != "" || !reflect.DeepEqual(alias, expectedAlias) {
					return fmt.Errorf("alias set/provenance/packages/ownership %q", alias.TupleKey)
				}
				local[alias.TupleKey], tuples[alias.TupleKey] = true, row.Family
			}
			totalTuples += len(local)
			if bucket.group {
				groupFamilies++
				groupTuples += len(local)
			}
			if expect.sensitive {
				sensitivityFamilies++
				sensitivityTuples += len(local)
			}
		}
	}
	if len(families) != len(want.families) || len(families) != got.TotalFoundFamilies || totalTuples != got.TotalFoundTuples ||
		groupFamilies != got.FoundGroupFamilies || groupTuples != got.FoundGroupTuples ||
		sensitivityFamilies != got.SensitivityGroupFamilies || sensitivityTuples != got.SensitivityGroupTuples {
		return errors.New("exhaustive family/tuple sets differ from declared totals")
	}
	unavailable := map[string]bool{}
	for _, row := range got.Unavailable {
		expect, known := want.unavailable[row.TupleKey]
		if !known || unavailable[row.TupleKey] || tuples[row.TupleKey] != "" || !reflect.DeepEqual(row, expect) {
			return fmt.Errorf("unavailable tuple/reasons/packages/ownership %q", row.TupleKey)
		}
		unavailable[row.TupleKey] = true
	}
	if len(unavailable) != len(want.unavailable) {
		return errors.New("unavailable tuple set incomplete")
	}
	return nil
}

func outputMustCheck(t *testing.T, got Snapshot, want outputContractWant) {
	t.Helper()
	if err := outputCheckSnapshot(got, want); err != nil {
		t.Fatal(err)
	}
}

func outputJSON(t *testing.T, value any) string {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}

func outputCopySnapshot(t *testing.T, value Snapshot) Snapshot {
	t.Helper()
	var copy Snapshot
	if err := json.Unmarshal([]byte(outputJSON(t, value)), &copy); err != nil {
		t.Fatal(err)
	}
	return copy
}

func TestTheoryOutputContractFrozenArchiveExhaustiveProjection(t *testing.T) {
	s, want := outputFrozenArchive()
	got := s.publish(false)
	outputMustCheck(t, got, want)
	if len(got.CoLeaders) <= 5 {
		t.Fatal("fixture must exercise uncapped practical group")
	}
	// The full 10x2x2x2 domain is independent of found or available tuples.
	total := 1
	for _, rows := range s.cfg.Domains {
		total *= len(rows)
	}
	if total != 80 || total-17-2 != 61 {
		t.Fatal("frozen Cartesian fixture drift")
	}
	// Group order carries no strict rank; both unequal scores and exact ties are
	// accepted in reverse order, as are aliases of the same arithmetic family.
	for i, j := 0, len(got.CoLeaders)-1; i < j; i, j = i+1, j-1 {
		got.CoLeaders[i], got.CoLeaders[j] = got.CoLeaders[j], got.CoLeaders[i]
	}
	for i := range got.CoLeaders {
		aliases := got.CoLeaders[i].Aliases
		for a, b := 0, len(aliases)-1; a < b; a, b = a+1, b-1 {
			aliases[a], aliases[b] = aliases[b], aliases[a]
		}
	}
	outputMustCheck(t, got, want)
}

func TestTheoryOutputContractFullTupleCoverageKeepsUnknownBounds(t *testing.T) {
	s, want := outputFrozenArchive()
	for _, a := range s.cfg.Domains[0] {
		for _, b := range s.cfg.Domains[1] {
			for _, c := range s.cfg.Domains[2] {
				for _, d := range s.cfg.Domains[3] {
					p := [4]domain.Package{a, b, c, d}
					if _, visited := s.archive.visited[outputTupleKey(p)]; !visited {
						s.archive.visited[outputTupleKey(p)] = "visited_without_lower_witness"
					}
				}
			}
		}
	}
	want.unseenTuples, want.covered = "0", true
	outputMustCheck(t, s.publish(false), want)
}

func outputFamilyRow(out *Snapshot, family string) *FamilyRow {
	for i := range out.CoLeaders {
		if out.CoLeaders[i].Family == family {
			return &out.CoLeaders[i]
		}
	}
	for i := range out.Pending {
		if out.Pending[i].Family == family {
			return &out.Pending[i]
		}
	}
	panic("unknown frozen family: " + family)
}

func TestTheoryOutputContractReferenceAdvancesPerArchivedSnapshot(t *testing.T) {
	s, want := outputFrozenArchive()
	first := s.publish(false)
	outputMustCheck(t, first, want)
	firstBytes := outputJSON(t, first)
	best := s.archive.pool["best"]
	best.value, best.state = 1020, outputFixtureWitness(11)
	s.archive.pool["best"] = best
	want.version, want.reference = 42, 1020
	want.groupFamilies, want.groupTuples, want.sensitivityFamilies, want.sensitivityTuples = 2, 4, 2, 4
	// Every row is compared directly with the new 1020 reference. These
	// classifications are declared, rather than inferred by the oracle.
	updates := map[string]struct {
		score, deficit   float64
		group, sensitive bool
		reason           string
	}{
		"best":          {1020, 0, true, true, ""},
		"best-tie":      {1000, 100 * 20.0 / 1020, true, true, ""},
		"inside-two":    {980.00001, 100 * 39.99999 / 1020, false, false, "below_practical_band_not_deeply_refined"},
		"on-two":        {980, 100 * 40.0 / 1020, false, false, "below_practical_band_not_deeply_refined"},
		"outside-two":   {979.99999, 100 * 40.00001 / 1020, false, false, "below_practical_band"},
		"inside-three":  {970.00001, 100 * 49.99999 / 1020, false, false, "below_practical_band_not_deeply_refined"},
		"on-three":      {970, 100 * 50.0 / 1020, false, false, "below_practical_band_not_deeply_refined"},
		"outside-three": {969.99999, 100 * 50.00001 / 1020, false, false, "below_practical_band_not_deeply_refined"},
		"chained-tail":  {951, 100 * 69.0 / 1020, false, false, "below_practical_band"},
		"shallow-low":   {800, 100 * 220.0 / 1020, false, false, "below_practical_band_not_deeply_refined"},
	}
	for family, update := range updates {
		row := want.families[family]
		row.score, row.deficit, row.group, row.sensitive, row.reason = update.score, update.deficit, update.group, update.sensitive, update.reason
		if family == "best" {
			row.witness = best.state
		}
		want.families[family] = row
	}
	outputMustCheck(t, s.publish(false), want)
	if outputJSON(t, first) != firstBytes {
		t.Fatal("new archived reference mutated the earlier snapshot")
	}
}

func TestTheoryOutputContractZeroAndNegativeReference(t *testing.T) {
	for _, mode := range []string{"zero", "negative"} {
		t.Run(mode, func(t *testing.T) {
			s, want := outputFrozenArchive()
			negativeScores := map[string]float64{"best": -1000, "best-tie": -1000,
				"inside-two": -1019.99999, "on-two": -1020, "outside-two": -1020.00001,
				"inside-three": -1029.99999, "on-three": -1030, "outside-three": -1030.00001,
				"chained-tail": -1049, "shallow-low": -1200}
			want.reference = -1000
			if mode == "zero" {
				want.reference = 0
				want.groupFamilies, want.groupTuples, want.sensitivityFamilies, want.sensitivityTuples = 2, 4, 2, 4
			}
			for family, expected := range want.families {
				expected.score = negativeScores[family]
				if mode == "zero" {
					expected.score, expected.deficit, expected.group, expected.sensitive = -1, 100, false, false
					expected.reason = "below_practical_band_not_deeply_refined"
					if expected.refinement == 2 {
						expected.reason = "below_practical_band"
					}
					if family == "best" || family == "best-tie" {
						expected.score, expected.deficit, expected.group, expected.sensitive, expected.reason = 0, 0, true, true, ""
					}
				}
				candidate := s.archive.pool[family]
				candidate.value = expected.score
				s.archive.pool[family], want.families[family] = candidate, expected
			}
			outputMustCheck(t, s.publish(false), want)
		})
	}
}

func TestTheoryOutputContractOracleRejectsCorruption(t *testing.T) {
	s, want := outputFrozenArchive()
	valid := s.publish(false)
	outputMustCheck(t, valid, want)
	mutations := []struct {
		name   string
		mutate func(*Snapshot)
	}{
		{"duplicate_replaces_alias_without_changing_length", func(out *Snapshot) { row := outputFamilyRow(out, "best"); row.Aliases[1] = row.Aliases[0] }},
		{"alias_lost_from_family", func(out *Snapshot) { row := outputFamilyRow(out, "on-three"); row.Aliases = row.Aliases[:2] }},
		{"replacement_family_keeps_all_counts", func(out *Snapshot) { outputFamilyRow(out, "best-tie").Family = "unfound-replacement-family" }},
		{"missing_group_family_with_consistent_counts", func(out *Snapshot) {
			for i, row := range out.CoLeaders {
				if row.Family == "best-tie" {
					out.CoLeaders = append(out.CoLeaders[:i], out.CoLeaders[i+1:]...)
					break
				}
			}
			out.TotalFoundFamilies--
			out.TotalFoundTuples--
			out.FoundGroupFamilies--
			out.FoundGroupTuples--
			out.SensitivityGroupFamilies--
			out.SensitivityGroupTuples--
		}},
		{"missing_pending_family", func(out *Snapshot) { out.Pending = out.Pending[:2] }},
		{"five_family_truncation", func(out *Snapshot) { out.CoLeaders = out.CoLeaders[:5]; out.FoundGroupFamilies = 5 }},
		{"wrong_practical_band", func(out *Snapshot) {
			row := *outputFamilyRow(out, "outside-three")
			for i, pending := range out.Pending {
				if pending.Family == row.Family {
					out.Pending = append(out.Pending[:i], out.Pending[i+1:]...)
					break
				}
			}
			out.CoLeaders = append(out.CoLeaders, row)
		}},
		{"chained_tail_promoted", func(out *Snapshot) {
			row := *outputFamilyRow(out, "chained-tail")
			for i, pending := range out.Pending {
				if pending.Family == row.Family {
					out.Pending = append(out.Pending[:i], out.Pending[i+1:]...)
					break
				}
			}
			out.CoLeaders = append(out.CoLeaders, row)
		}},
		{"wrong_practical_percent", func(out *Snapshot) { out.PracticalBandPercent = 2 }},
		{"wrong_sensitivity_percent", func(out *Snapshot) { out.SensitivityBandPercent = 3 }},
		{"equipped_or_branch_reference", func(out *Snapshot) { out.ReferenceScore = 800 }},
		{"wrong_sensitivity_reference", func(out *Snapshot) { out.SensitivityGroupFamilies = 5; out.SensitivityGroupTuples = 8 }},
		{"wrong_deficit", func(out *Snapshot) { outputFamilyRow(out, "on-three").DeficitPercent = 2 }},
		{"wrong_pending_reason", func(out *Snapshot) { outputFamilyRow(out, "outside-three").Reason = "excluded" }},
		{"wrong_refinement", func(out *Snapshot) { outputFamilyRow(out, "shallow-low").RefinementLevel = 2 }},
		{"wrong_context", func(out *Snapshot) { outputFamilyRow(out, "best").Aliases[0].ContextSHA256 = strings.Repeat("f", 64) }},
		{"unknown_uncertainty_erased", func(out *Snapshot) { outputFamilyRow(out, "best").Aliases[0].Uncertainty = []string{} }},
		{"package_set_uid", func(out *Snapshot) {
			outputFamilyRow(out, "on-three").Aliases[0].Packages[0].Sets[0].SetUID = "foreign-set"
		}},
		{"package_set_count", func(out *Snapshot) { outputFamilyRow(out, "on-three").Aliases[0].Packages[0].Sets[0].Count = 2 }},
		{"package_wearer_ownership", func(out *Snapshot) { outputFamilyRow(out, "best").Aliases[0].Packages[1].WearerKey = "archive-a" }},
		{"allocation_wearer_ownership", func(out *Snapshot) { outputFamilyRow(out, "best").Allocations[1].WearerKey = "archive-a" }},
		{"witness_slot_line", func(out *Snapshot) {
			outputFamilyRow(out, "best").Witness45.Lines[0][0][1] = outputFamilyRow(out, "best").Witness45.Lines[0][0][0]
		}},
		{"witness_upgrade", func(out *Snapshot) { outputFamilyRow(out, "best").Witness45.Upgrades[0][0][0] += .25 }},
		{"main_stat_projection", func(out *Snapshot) { outputFamilyRow(out, "best").Allocations[0].MainStats["sands"] = "em" }},
		{"roll_unit_projection", func(out *Snapshot) { outputFamilyRow(out, "best").Allocations[0].Substats[0].RollUnits += .25 }},
		{"stat_value_projection", func(out *Snapshot) { outputFamilyRow(out, "best").Allocations[0].Substats[0].StatValue += .01 }},
		{"substat_duplicate_replaces_stat", func(out *Snapshot) {
			row := outputFamilyRow(out, "best")
			row.Allocations[0].Substats[1] = row.Allocations[0].Substats[0]
		}},
		{"spent_budget_projection", func(out *Snapshot) { outputFamilyRow(out, "best").Allocations[0].SpentRollUnits = 44.75 }},
		{"unspent_budget_projection", func(out *Snapshot) { outputFamilyRow(out, "best").Allocations[0].UnspentRollUnits = .25 }},
		{"unavailable_omitted", func(out *Snapshot) { out.Unavailable = out.Unavailable[:1] }},
		{"unavailable_duplicate", func(out *Snapshot) { out.Unavailable[1] = out.Unavailable[0] }},
		{"unavailable_reasons_erased", func(out *Snapshot) { out.Unavailable[0].Reasons = []string{} }},
		{"unavailable_wearer_ownership", func(out *Snapshot) { out.Unavailable[0].Packages[0].WearerKey = "archive-d" }},
		{"total_family_count", func(out *Snapshot) { out.TotalFoundFamilies++ }},
		{"total_tuple_count", func(out *Snapshot) { out.TotalFoundTuples++ }},
		{"group_family_count", func(out *Snapshot) { out.FoundGroupFamilies++ }},
		{"group_tuple_count", func(out *Snapshot) { out.FoundGroupTuples++ }},
		{"sensitivity_family_count", func(out *Snapshot) { out.SensitivityGroupFamilies++ }},
		{"sensitivity_tuple_count", func(out *Snapshot) { out.SensitivityGroupTuples++ }},
		{"domain_total", func(out *Snapshot) { out.DomainTuples = "79" }},
		{"unseen_total", func(out *Snapshot) { out.UnseenTuples = "0" }},
		{"full_coverage_claim", func(out *Snapshot) { out.FullCartesianCovered = true }},
		{"false_strict_rank", func(out *Snapshot) { out.Rules["practical_group_rank"] = "strict_formula_rank" }},
		{"false_optimality", func(out *Snapshot) { out.Rules["full_search_optimality_proved"] = true }},
		{"false_source_upper", func(out *Snapshot) { out.SourceUpper = "1000" }},
		{"false_outer_upper", func(out *Snapshot) { out.OuterUpper = "1000" }},
		{"unsupported_search_completion", func(out *Snapshot) { out.SearchStatus = "complete" }},
	}
	for _, mutation := range mutations {
		t.Run(mutation.name, func(t *testing.T) {
			corrupt := outputCopySnapshot(t, valid)
			outputMustCheck(t, corrupt, want)
			mutation.mutate(&corrupt)
			if err := outputCheckSnapshot(corrupt, want); err == nil {
				t.Fatal("independent oracle accepted corrupted output")
			}
		})
	}
}

func TestTheoryOutputContractIndependentFull45Domain(t *testing.T) {
	valid := outputFixtureWitness(0)
	if _, err := outputWitnessRolls(valid); err != nil {
		t.Fatal(err)
	}
	mutations := []struct {
		name   string
		mutate func(*alloc.State)
	}{
		{"illegal_main", func(s *alloc.State) { s.Mains[0][0] = "em" }},
		{"duplicate_initial_line", func(s *alloc.State) { s.Lines[0][0][1] = s.Lines[0][0][0] }},
		{"main_stat_initial_line", func(s *alloc.State) { s.Lines[0][0][0] = 8 }},
		{"invalid_initial_line", func(s *alloc.State) { s.Lines[0][0][0] = 10 }},
		{"negative_upgrade", func(s *alloc.State) { s.Upgrades[0][0][0] = -.25 }},
		{"nonfinite_upgrade", func(s *alloc.State) { s.Upgrades[0][0][0] = math.NaN() }},
		{"off_quarter_grid", func(s *alloc.State) { s.Upgrades[0][0][0] += .1; s.Upgrades[0][0][1] -= .1 }},
		{"slot_exceeds_five_even_at_full45", func(s *alloc.State) { s.Upgrades[0][0][0] += .25; s.Upgrades[0][1][0] -= .25 }},
		{"missing_upgrade_at_legal_upper_budget", func(s *alloc.State) { s.Upgrades[0][0][0] -= .25 }},
	}
	for _, mutation := range mutations {
		t.Run(mutation.name, func(t *testing.T) {
			corrupt := valid
			mutation.mutate(&corrupt)
			if _, err := outputWitnessRolls(corrupt); err == nil {
				t.Fatal("independent domain oracle accepted illegal witness")
			}
		})
	}
}

func TestTheoryOutputContractExportVerifiedFrozenSnapshot(t *testing.T) {
	s, want := outputFrozenArchive()
	got := s.publish(true)
	want.terminal = true
	outputMustCheck(t, got, want)
	path, enabled := os.LookupEnv("GTT_THEORY_OUTPUT_EXPORT")
	if !enabled {
		return
	}
	if path == "" {
		t.Fatal("GTT_THEORY_OUTPUT_EXPORT requires a managed job output path")
	}
	raw, err := json.MarshalIndent(got, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = file.Write(append(raw, '\n')); err != nil {
		_ = file.Close()
		t.Fatal(err)
	}
	if err = file.Close(); err != nil {
		t.Fatal(err)
	}
}

// The compact live fixture has three allocation-sensitive arithmetic families,
// a fourth-wearer exact alias, and an unavailable source tuple. There is no
// engine provider, file, callback or capture operation in this resolver.
type outputLiveLedger struct{ worlds []*outputLiveWorld }
type outputLiveWorld struct {
	ledger               *outputLiveLedger
	resolves, objectives int
	closed               bool
	closes               int
	failResolve          error
}

func outputLiveConfig() Config {
	cfg := Config{Binding: "live-output-binding", RequestSHA256: strings.Repeat("b", 64), SessionID: "live-output-session",
		Wearers: [4]string{"live-a", "live-b", "live-c", "live-d"}, Initial: outputFixtureWitness(0)}
	for i := 0; i < 4; i++ {
		cfg.Domains[0] = append(cfg.Domains[0], outputFixturePackage(contracts.SetRequirement{SetUID: fmt.Sprintf("live-a%d", i), Count: 4}))
	}
	cfg.Domains[1] = []domain.Package{outputFixturePackage()}
	cfg.Domains[2] = []domain.Package{outputFixturePackage(contracts.SetRequirement{SetUID: "live-c0", Count: 2})}
	cfg.Domains[3] = []domain.Package{
		outputFixturePackage(contracts.SetRequirement{SetUID: "live-d0", Count: 4}),
		outputFixturePackage(contracts.SetRequirement{SetUID: "live-d1", Count: 2}, contracts.SetRequirement{SetUID: "live-z1", Count: 2}),
	}
	for actor := range cfg.Original {
		cfg.Original[actor] = cfg.Domains[actor][0]
	}
	return cfg
}

func newOutputLiveSession(t *testing.T) (*Session, *outputLiveWorld, *outputLiveLedger) {
	t.Helper()
	ledger := &outputLiveLedger{}
	world := &outputLiveWorld{ledger: ledger}
	ledger.worlds = append(ledger.worlds, world)
	s, err := New(outputLiveConfig(), world)
	if err != nil {
		t.Fatal(err)
	}
	return s, world, ledger
}

func outputLiveObjective(state alloc.State, family int) (float64, [4][10]float64) {
	// Evaluate continuous trial states too; publication legality is independently
	// checked by outputWitnessRolls, rather than constraining this objective.
	var rolls, gradient [4][10]float64
	for actor := range state.Lines {
		for slot := range state.Lines[actor] {
			for line, stat := range state.Lines[actor][slot] {
				rolls[actor][stat] += 1 + state.Upgrades[actor][slot][line]
			}
		}
	}
	value := 5000 + 8*float64(family)
	if family == 2 {
		value -= 500
	}
	for actor, row := range rolls {
		for stat, units := range row {
			weight := .2 + .02*float64((stat+3*actor+family)%10)
			value += weight*units - .002*units*units
			gradient[actor][stat] = weight - .004*units
		}
		for _, main := range state.Mains[actor] {
			if main == "em" {
				value += .1
			}
			if main == "crit_rate" {
				value += .2
			}
		}
	}
	// A foreign-owner term makes the fixture sensitive to two allocations at
	// once without relying on any captured formula or numerical policy helper.
	delta := rolls[0][3] - rolls[1][6]
	value -= .001 * delta * delta
	gradient[0][3] -= .002 * delta
	gradient[1][6] += .002 * delta
	return value, gradient
}

func (w *outputLiveWorld) Resolve(ctx context.Context, p [4]domain.Package) (*Entry, []string, error) {
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	if w.closed {
		return nil, nil, errors.New("closed live output fixture")
	}
	if w.failResolve != nil {
		return nil, nil, w.failResolve
	}
	w.resolves++
	family := -1
	for i := 0; i < 4; i++ {
		if p[0].Sets[0].SetUID == fmt.Sprintf("live-a%d", i) {
			family = i
		}
	}
	if family < 0 {
		return nil, nil, errors.New("tuple outside live output fixture")
	}
	if family == 3 {
		if p[3].Sets[0].SetUID == "live-d0" {
			return nil, nil, nil
		} // Explicit fallback reason must survive.
		return nil, []string{"unknown_source_operand", "activation_unavailable"}, nil
	}
	key := outputTupleKey(p)
	return &Entry{Family: fmt.Sprintf("live-family-%d", family), ContextSHA256: fmt.Sprintf("%x", sha256.Sum256([]byte("live-output-context:"+key))),
		Uncertainty: []string{"unknown_fixture_branch", "source_lineage:" + key},
		Objective: func(state alloc.State, _ bool) (float64, [4][10]float64, error) {
			if w.closed {
				return 0, [4][10]float64{}, errors.New("closed live output objective")
			}
			w.objectives++
			value, gradient := outputLiveObjective(state, family)
			return value, gradient, nil
		}}, nil, nil
}

func (w *outputLiveWorld) Fork() (Resolver, error) {
	if w.closed {
		return nil, errors.New("fork of closed live output fixture")
	}
	n := *w
	n.closes = 0
	w.ledger.worlds = append(w.ledger.worlds, &n)
	return &n, nil
}

func (w *outputLiveWorld) Close() {
	if !w.closed {
		w.closed = true
		w.closes++
	}
}

func outputCheckLiveSnapshot(t *testing.T, out Snapshot, cfg Config) {
	t.Helper()
	if out.TotalFoundFamilies != 3 || len(out.CoLeaders) != 2 || len(out.Pending) != 1 || len(out.Unavailable) == 0 ||
		out.SourceUpper != "unbounded" || out.OuterUpper != "unbounded" || out.SearchStatus != "partial" ||
		out.Rules["practical_group_rank"] != "unordered_equivalent_group" || out.Rules["full_search_optimality_proved"] != false {
		t.Fatal("live fixture lost pending/unavailable/unknown/practical-group semantics")
	}
	if out.Work.Formula == 0 || out.Work.Gradient == 0 || out.Work.AllocationAttempts == 0 {
		t.Fatal("live fixture did not run allocation-sensitive work")
	}
	tupleSeen := map[string]bool{}
	for _, rows := range [][]FamilyRow{out.CoLeaders, out.Pending} {
		for _, row := range rows {
			if err := outputCheckAllocations(row.Allocations, row.Witness45, cfg.Wearers); err != nil {
				t.Fatal(err)
			}
			if len(row.Aliases) == 0 {
				t.Fatal("live family lacks an exact alias")
			}
			for _, alias := range row.Aliases {
				if len(alias.Packages) != 4 || tupleSeen[alias.TupleKey] || alias.ContextSHA256 != fmt.Sprintf("%x", sha256.Sum256([]byte("live-output-context:"+alias.TupleKey))) || !reflect.DeepEqual(alias.Uncertainty, []string{"unknown_fixture_branch", "source_lineage:" + alias.TupleKey}) {
					t.Fatal("live alias multiplicity/source uncertainty changed")
				}
				var p [4]domain.Package
				for actor, pkg := range alias.Packages {
					if pkg.WearerKey != cfg.Wearers[actor] {
						t.Fatal("live alias wearer ownership changed")
					}
					p[actor] = domain.Package{Sets: pkg.Sets}
				}
				if outputTupleKey(p) != alias.TupleKey {
					t.Fatal("live tuple identity changed")
				}
				tupleSeen[alias.TupleKey] = true
			}
		}
	}
	for _, u := range out.Unavailable {
		if len(u.Reasons) == 0 || len(u.Packages) != 4 || tupleSeen[u.TupleKey] {
			t.Fatal("live unavailable source tuple lost diagnosis")
		}
		for actor, pkg := range u.Packages {
			if pkg.WearerKey != cfg.Wearers[actor] {
				t.Fatal("live unavailable wearer ownership changed")
			}
		}
	}
}

func outputCheckLiveClosed(t *testing.T, ledger *outputLiveLedger) {
	t.Helper()
	if len(ledger.worlds) != 2 {
		t.Fatalf("expected only initial resolver and its checkpoint, got %d", len(ledger.worlds))
	}
	for i, w := range ledger.worlds {
		if !w.closed || w.closes != 1 {
			t.Fatalf("live resolver %d closes=%d closed=%t", i, w.closes, w.closed)
		}
	}
}

func TestTheoryOutputContractLiveSnapshotsRemainImmutableAcrossActions(t *testing.T) {
	for _, mode := range []string{"breadth-deep-finish", "cancel-breadth", "cancel-deep", "failure-breadth", "failure-deep", "binding-failure"} {
		t.Run(mode, func(t *testing.T) {
			s, world, ledger := newOutputLiveSession(t)
			defer s.Close()
			ctx := context.Background()
			initial := s.cfg.Initial
			perturbed := initial
			perturbed.Upgrades[0][0][0] += .25
			perturbed.Upgrades[0][0][3] -= .25
			v, _ := outputLiveObjective(initial, 0)
			changed, _ := outputLiveObjective(perturbed, 0)
			if outputNear(v, changed) {
				t.Fatal("live fixture objective is allocation-insensitive")
			}
			first, err := s.First(ctx, s.cfg.Binding)
			if err != nil {
				t.Fatal(err)
			}
			outputCheckLiveSnapshot(t, first, s.cfg)
			snapshots := []Snapshot{first}
			frozen := []string{outputJSON(t, first)}
			assertFrozen := func() {
				t.Helper()
				for i, snapshot := range snapshots {
					if outputJSON(t, snapshot) != frozen[i] {
						t.Fatalf("%s mutated publication %d nested contents", mode, i)
					}
				}
			}
			if mode == "breadth-deep-finish" || strings.HasSuffix(mode, "deep") {
				breadth, err := s.Breadth(ctx, s.cfg.Binding)
				if err != nil {
					t.Fatal(err)
				}
				outputCheckLiveSnapshot(t, breadth, s.cfg)
				if breadth.SnapshotVersion <= first.SnapshotVersion {
					t.Fatal("breadth snapshot version did not increase")
				}
				snapshots, frozen = append(snapshots, breadth), append(frozen, outputJSON(t, breadth))
				assertFrozen()
			}
			sentinel := errors.New("live output continuation failure")
			version := s.version
			switch mode {
			case "breadth-deep-finish":
				deep, err := s.Deep(ctx, s.cfg.Binding)
				if err != nil {
					t.Fatal(err)
				}
				outputCheckLiveSnapshot(t, deep, s.cfg)
				if deep.SnapshotVersion <= snapshots[len(snapshots)-1].SnapshotVersion {
					t.Fatal("deep snapshot version did not increase")
				}
				snapshots, frozen = append(snapshots, deep), append(frozen, outputJSON(t, deep))
				assertFrozen()
				terminal, err := s.Finish()
				if err != nil {
					t.Fatal(err)
				}
				outputCheckLiveSnapshot(t, terminal, s.cfg)
				if !terminal.FinishedEarly || terminal.SnapshotVersion <= deep.SnapshotVersion {
					t.Fatal("Finish did not publish a distinct terminal version")
				}
			case "cancel-breadth", "cancel-deep":
				cancelled, cancel := context.WithCancel(ctx)
				cancel()
				var out Snapshot
				if mode == "cancel-breadth" {
					out, err = s.Breadth(cancelled, s.cfg.Binding)
				} else {
					out, err = s.Deep(cancelled, s.cfg.Binding)
				}
				if !errors.Is(err, context.Canceled) || out.Status == "success" || out.FinishedEarly || s.version != version {
					t.Fatal("Cancel returned/published terminal success")
				}
				// Session.Finish also serves the CLI's explicit soft-Finish path.
				// Actual Cancel-versus-soft-Finish intent is gated at the CLI seam.
			case "failure-breadth", "failure-deep":
				world.failResolve = sentinel
				s.preDeep.world.(*outputLiveWorld).failResolve = sentinel
				var out Snapshot
				if mode == "failure-breadth" {
					out, err = s.Breadth(ctx, s.cfg.Binding)
				} else {
					out, err = s.Deep(ctx, s.cfg.Binding)
				}
				if !errors.Is(err, sentinel) || out.Status == "success" || s.version != version {
					t.Fatal("failed action published a successful snapshot")
				}
				if out, err = s.Finish(); !errors.Is(err, sentinel) || out.Status == "success" {
					t.Fatal("fatal failure became terminal success")
				}
			case "binding-failure":
				out, err := s.Deep(ctx, "changed-binding")
				if !errors.Is(err, ErrBindingChanged) || out.Status == "success" || s.version != version {
					t.Fatal("binding invalidation published success")
				}
				if out, err = s.Finish(); !errors.Is(err, ErrBindingChanged) || out.Status == "success" {
					t.Fatal("binding invalidation became terminal success")
				}
			}
			assertFrozen()
			s.Close()
			assertFrozen()
			outputCheckLiveClosed(t, ledger)
		})
	}
}

func outputLiveOwnedFingerprint(t *testing.T, s *Session) string {
	t.Helper()
	witnesses, scores := map[string]alloc.State{}, map[string]float64{}
	for family, row := range s.archive.pool {
		witnesses[family], scores[family] = row.state, row.value
	}
	return outputJSON(t, struct {
		Config      Config
		Witnesses   map[string]alloc.State
		Scores      map[string]float64
		Aliases     map[string]map[string]Alias
		Unavailable map[string]Unavailable
		Refined     map[string]int
		Visited     map[string]string
	}{s.cfg, witnesses, scores, s.archive.aliases, s.archive.unavailable, s.archive.refined, s.archive.visited})
}

func outputCorruptExposedSnapshot(out *Snapshot) {
	for _, rows := range [][]FamilyRow{out.CoLeaders, out.Pending} {
		for i := range rows {
			row := &rows[i]
			row.Witness45.Mains[0][0], row.Witness45.Lines[0][0][0], row.Witness45.Upgrades[0][0][0] = "foreign-main", -1, -1
			row.Allocations[0].WearerKey = "foreign-owner"
			row.Allocations[0].MainStats["flower"] = "foreign-main"
			row.Allocations[0].Substats[0].StatKey = "foreign-stat"
			row.Allocations[0].Substats[0].RollUnits, row.Allocations[0].Substats[0].StatValue = -1, -1
			for j := range row.Aliases {
				alias := &row.Aliases[j]
				alias.Packages[0].WearerKey, alias.Packages[0].Sets[0].SetUID, alias.Packages[0].Sets[0].Count = "foreign-owner", "foreign-set", 2
				alias.ContextSHA256, alias.Uncertainty[0] = "foreign-context", "foreign-uncertainty"
			}
		}
	}
	for i := range out.Unavailable {
		out.Unavailable[i].Packages[0].WearerKey = "foreign-owner"
		out.Unavailable[i].Packages[0].Sets[0].SetUID = "foreign-set"
		out.Unavailable[i].Reasons[0] = "foreign-reason"
	}
	out.Rules["all_found_aliases"] = false
}

func TestTheoryOutputContractLiveExposedMutationCannotReachSession(t *testing.T) {
	s, _, ledger := newOutputLiveSession(t)
	defer s.Close()
	ctx := context.Background()
	first, err := s.First(ctx, s.cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	outputCheckLiveSnapshot(t, first, s.cfg)
	firstBytes, owned := outputJSON(t, first), outputLiveOwnedFingerprint(t, s)
	outputCorruptExposedSnapshot(&first)
	if outputLiveOwnedFingerprint(t, s) != owned {
		t.Fatal("consumer mutation reached session-owned nested data")
	}
	again := s.publish(false)
	version := again.SnapshotVersion
	again.SnapshotVersion = first.SnapshotVersion
	if outputJSON(t, again) != firstBytes {
		t.Fatal("consumer mutation reached a separately published snapshot")
	}
	again.SnapshotVersion = version
	againBytes := outputJSON(t, again)
	breadth, err := s.Breadth(ctx, s.cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	outputCheckLiveSnapshot(t, breadth, s.cfg)
	owned = outputLiveOwnedFingerprint(t, s)
	outputCorruptExposedSnapshot(&breadth)
	if outputLiveOwnedFingerprint(t, s) != owned {
		t.Fatal("breadth result mutation reached session-owned nested data")
	}
	deep, err := s.Deep(ctx, s.cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	outputCheckLiveSnapshot(t, deep, s.cfg)
	deepBytes, owned := outputJSON(t, deep), outputLiveOwnedFingerprint(t, s)
	terminal, err := s.Finish()
	if err != nil {
		t.Fatal(err)
	}
	outputCheckLiveSnapshot(t, terminal, s.cfg)
	outputCorruptExposedSnapshot(&terminal)
	if outputLiveOwnedFingerprint(t, s) != owned || outputJSON(t, deep) != deepBytes || outputJSON(t, again) != againBytes {
		t.Fatal("terminal result mutation reached the archive or an earlier immutable publication")
	}
	outputCheckLiveClosed(t, ledger)
}

func TestTheoryOutputContractLiveConfigIsOwnedBeforeFirst(t *testing.T) {
	cfg := outputLiveConfig()
	ledger := &outputLiveLedger{}
	world := &outputLiveWorld{ledger: ledger}
	ledger.worlds = append(ledger.worlds, world)
	s, err := New(cfg, world)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	owned := outputJSON(t, s.cfg)
	cfg.Domains[0][0].Sets[0].SetUID = "foreign-domain"
	cfg.Original[2].Sets[0].SetUID = "foreign-original"
	cfg.Initial.Mains[0][0], cfg.Initial.Lines[0][0][0], cfg.Initial.Upgrades[0][0][0] = "foreign-main", -1, -1
	if outputJSON(t, s.cfg) != owned {
		t.Fatal("caller retained mutable session config ownership")
	}
	first, err := s.First(context.Background(), s.cfg.Binding)
	if err != nil {
		t.Fatal(err)
	}
	outputCheckLiveSnapshot(t, first, s.cfg)
	s.Close()
	outputCheckLiveClosed(t, ledger)
}

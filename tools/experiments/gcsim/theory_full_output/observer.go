package theorysearch

import (
	"encoding/json"
	"fmt"
	"math"
	"math/big"
	"reflect"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/theory"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

// Stage15Projection is a detached, JSON-stable copy of the session inputs and
// output archive at one publication boundary. It intentionally contains only
// public candidate, alias, allocation, domain, visit, and progress data.
type Stage15Projection struct {
	Binding       string               `json:"binding"`
	RequestSHA256 string               `json:"request_sha256"`
	SessionID     string               `json:"session_id"`
	Wearers       [4]string            `json:"wearers"`
	Initial       alloc.State          `json:"initial"`
	Original      [4]domain.Package    `json:"original"`
	Domains       [4][]domain.Package  `json:"domains"`
	Phase         string               `json:"phase"`
	Version       int64                `json:"version"`
	Terminal      bool                 `json:"terminal"`
	FinishedEarly bool                 `json:"finished_early"`
	Work          Work                 `json:"active_branch_work"`
	Families      []Stage15Family      `json:"families"`
	Unavailable   []Stage15Unavailable `json:"unavailable"`
	Visited       []Stage15Visited     `json:"visited"`
}

// Stage15Family preserves archive map identity even when a family has aliases
// but no complete candidate witness yet.
type Stage15Family struct {
	Family            string            `json:"family"`
	HasCandidate      bool              `json:"has_candidate"`
	CandidateFamily   string            `json:"candidate_family"`
	Score             float64           `json:"score"`
	CandidatePackages [4]domain.Package `json:"candidate_packages"`
	Witness45         alloc.State       `json:"witness45"`
	RefinementLevel   int               `json:"refinement_level"`
	Aliases           []Stage15Alias    `json:"aliases"`
}

// Stage15Alias keeps both the archive map key and the serialized alias tuple
// key so corruption in either identity remains observable.
type Stage15Alias struct {
	MapKey string `json:"map_key"`
	Value  Alias  `json:"value"`
}

// Stage15Unavailable keeps both the archive map key and the serialized row.
type Stage15Unavailable struct {
	MapKey string      `json:"map_key"`
	Value  Unavailable `json:"value"`
}

// Stage15Visited is one exact archive visit and its resolved family (empty for
// an unavailable tuple). The slice is sorted by TupleKey in a projection.
type Stage15Visited struct {
	TupleKey string `json:"tuple_key"`
	Family   string `json:"family"`
}

// Stage15Archive returns a detached copy, including after a failed action or
// Close. Failure does not invent a publication; Version and Phase retain the
// session's actual values, and callers should pair this projection only with a
// Snapshot returned by a successful publication.
func Stage15Archive(s *Session) (Stage15Projection, error) {
	if s == nil || s.archive == nil {
		return Stage15Projection{}, fmt.Errorf("stage15 archive unavailable")
	}
	p := Stage15Projection{
		Binding: s.cfg.Binding, RequestSHA256: s.cfg.RequestSHA256, SessionID: s.cfg.SessionID,
		Wearers: s.cfg.Wearers, Initial: s.cfg.Initial, Original: stage15CopyTuple(s.cfg.Original),
		Phase: s.phase, Version: s.version, Terminal: s.closed, FinishedEarly: s.closed,
		Families: []Stage15Family{}, Unavailable: []Stage15Unavailable{}, Visited: []Stage15Visited{},
	}
	for actor, rows := range s.cfg.Domains {
		p.Domains[actor] = make([]domain.Package, len(rows))
		for i, pkg := range rows {
			p.Domains[actor][i] = stage15CopyPackage(pkg)
		}
	}
	if s.active != nil {
		p.Work = s.active.work
	}

	familyNames := make(map[string]struct{}, len(s.archive.pool)+len(s.archive.aliases)+len(s.archive.refined))
	for family := range s.archive.pool {
		familyNames[family] = struct{}{}
	}
	for family := range s.archive.aliases {
		familyNames[family] = struct{}{}
	}
	for family := range s.archive.refined {
		familyNames[family] = struct{}{}
	}
	names := make([]string, 0, len(familyNames))
	for family := range familyNames {
		names = append(names, family)
	}
	sort.Strings(names)
	for _, family := range names {
		row := Stage15Family{Family: family, Aliases: []Stage15Alias{}}
		if candidate, ok := s.archive.pool[family]; ok {
			row.HasCandidate = true
			row.CandidateFamily = candidate.family
			row.Score = candidate.value
			row.CandidatePackages = stage15CopyTuple(candidate.packages)
			row.Witness45 = candidate.state
		}
		row.RefinementLevel = s.archive.refined[family]
		aliases := s.archive.aliases[family]
		keys := make([]string, 0, len(aliases))
		for key := range aliases {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			row.Aliases = append(row.Aliases, Stage15Alias{MapKey: key, Value: stage15CopyAlias(aliases[key])})
		}
		p.Families = append(p.Families, row)
	}
	unavailableKeys := make([]string, 0, len(s.archive.unavailable))
	for key := range s.archive.unavailable {
		unavailableKeys = append(unavailableKeys, key)
	}
	sort.Strings(unavailableKeys)
	for _, key := range unavailableKeys {
		p.Unavailable = append(p.Unavailable, Stage15Unavailable{MapKey: key, Value: stage15CopyUnavailable(s.archive.unavailable[key])})
	}
	visitedKeys := make([]string, 0, len(s.archive.visited))
	for key := range s.archive.visited {
		visitedKeys = append(visitedKeys, key)
	}
	sort.Strings(visitedKeys)
	for _, key := range visitedKeys {
		p.Visited = append(p.Visited, Stage15Visited{TupleKey: key, Family: s.archive.visited[key]})
	}
	return p, nil
}

// Stage15CheckSnapshot captures the current session and independently checks
// the supplied publication against that detached archive.
func Stage15CheckSnapshot(s *Session, snapshot Snapshot) error {
	p, err := Stage15Archive(s)
	if err != nil {
		return err
	}
	return Stage15CheckProjection(p, snapshot)
}

// Stage15CheckProjection checks a publication against a frozen Stage15Archive.
// Retain one projection for each successful phase publication to recheck old
// snapshots after subsequent session phases or Finish.
func Stage15CheckProjection(p Stage15Projection, got Snapshot) error {
	domains, err := stage15ValidateProjection(p)
	if err != nil {
		return err
	}
	if p.Version <= 0 || got.SchemaVersion != 2 || got.SchemaKind != "gtt_gcsim_optimizer_theory_result_v2" ||
		got.RequestSHA256 != p.RequestSHA256 || got.SessionID != p.SessionID || got.SnapshotVersion != p.Version ||
		got.Phase != stage15PublicationPhase(p.Phase) || got.PolicyID != "theory_h_light_common_h_20261010_v1" ||
		got.FinishedEarly != p.FinishedEarly {
		return fmt.Errorf("snapshot schema/identity/version/phase/terminal projection")
	}
	if got.Status != "success" || got.SearchStatus != "partial" || got.ResponseStatus != "formula_only" ||
		got.SourceUpper != "unbounded" || got.OuterUpper != "unbounded" || got.PracticalBandPercent != 3 ||
		got.SensitivityBandPercent != 2 || got.Work != p.Work {
		return fmt.Errorf("snapshot status/bands/unknown bounds/active work")
	}
	wantRules := map[string]any{
		"budget_roll_units_per_wearer":  45,
		"quarter_grid":                  true,
		"all_found_aliases":             true,
		"reference_scope":               "best_attained_across_found_branches",
		"practical_group_rank":          "unordered_equivalent_group",
		"full_search_optimality_proved": false,
		"final_solution_cache_enabled":  false,
	}
	if !stage15SameJSON(got.Rules, wantRules) {
		return fmt.Errorf("snapshot rules projection")
	}

	families := make(map[string]*Stage15Family, len(p.Families))
	expectedAliases := make(map[string]stage15ExpectedAlias)
	aliasCounts := make(map[string]int, len(p.Families))
	expectedUnavailable := make(map[string]Unavailable, len(p.Unavailable))
	best, hasCandidate := 0.0, false
	for i := range p.Families {
		family := &p.Families[i]
		if family.Family == "" || families[family.Family] != nil {
			return fmt.Errorf("empty/duplicate archive family %q", family.Family)
		}
		families[family.Family] = family
		localAliases := make(map[string]bool, len(family.Aliases))
		for j := range family.Aliases {
			item := &family.Aliases[j]
			key, e := stage15ValidateAlias(item.MapKey, item.Value, p.Wearers, domains)
			if e != nil {
				return fmt.Errorf("family %q: %w", family.Family, e)
			}
			if localAliases[key] || expectedAliases[key].Family != "" {
				return fmt.Errorf("duplicate archive alias tuple %q", key)
			}
			localAliases[key] = true
			expectedAliases[key] = stage15ExpectedAlias{Family: family.Family, Row: &item.Value}
			aliasCounts[family.Family]++
		}
		if family.RefinementLevel < 0 || family.RefinementLevel > 2 {
			return fmt.Errorf("family %q invalid refinement level %d", family.Family, family.RefinementLevel)
		}
		if family.HasCandidate {
			if family.CandidateFamily != family.Family || !stage15Finite(family.Score) {
				return fmt.Errorf("family %q candidate identity/score", family.Family)
			}
			if _, e := stage15WitnessRolls(family.Witness45); e != nil {
				return fmt.Errorf("family %q illegal full45 candidate: %w", family.Family, e)
			}
			candidateKey, e := stage15ValidateTuple(family.CandidatePackages, domains)
			if e != nil {
				return fmt.Errorf("family %q candidate packages: %w", family.Family, e)
			}
			if !localAliases[candidateKey] {
				return fmt.Errorf("family %q candidate tuple lacks its exact alias", family.Family)
			}
			if !hasCandidate || family.Score > best {
				best, hasCandidate = family.Score, true
			}
		}
	}
	for _, item := range p.Unavailable {
		key, e := stage15ValidateUnavailable(item.MapKey, item.Value, p.Wearers, domains)
		if e != nil {
			return e
		}
		if _, exists := expectedUnavailable[key]; exists || expectedAliases[key].Family != "" {
			return fmt.Errorf("duplicate/overlapping unavailable tuple %q", key)
		}
		expectedUnavailable[key] = item.Value
	}
	visited, e := stage15ValidateVisited(p.Visited, domains)
	if e != nil {
		return e
	}
	for key, expected := range expectedAliases {
		family, ok := visited[key]
		if !ok || family != expected.Family {
			return fmt.Errorf("alias tuple %q absent from or inconsistent with visited projection", key)
		}
	}
	for key := range expectedUnavailable {
		family, ok := visited[key]
		if !ok || family != "" {
			return fmt.Errorf("unavailable tuple %q absent from or inconsistent with visited projection", key)
		}
	}
	for key, family := range visited {
		if family == "" {
			if _, ok := expectedUnavailable[key]; !ok {
				return fmt.Errorf("visited unavailable tuple %q lacks unavailable row", key)
			}
		} else if expected := expectedAliases[key]; expected.Family != family {
			return fmt.Errorf("visited tuple %q family has no matching alias", key)
		}
	}

	if !stage15Close(got.ReferenceScore, best) || (!hasCandidate && got.ReferenceScore != 0) {
		return fmt.Errorf("snapshot reference score differs from archived best")
	}
	product := new(big.Int).Set(domains.total)
	remaining := new(big.Int).Sub(product, big.NewInt(int64(len(visited))))
	if remaining.Sign() < 0 || got.DomainTuples != product.String() || got.UnseenTuples != remaining.String() ||
		got.FullCartesianCovered != (remaining.Sign() == 0) {
		return fmt.Errorf("snapshot exact domain/visited/coverage counts")
	}

	seenFamilies := make(map[string]bool)
	seenTuples := make(map[string]string, len(expectedAliases))
	seenUnavailable := make(map[string]bool, len(expectedUnavailable))
	totalTuples, groupFamilies, groupTuples, sensitivityFamilies, sensitivityTuples := 0, 0, 0, 0, 0
	checkBucket := func(rows []FamilyRow, group bool) error {
		for i := range rows {
			row := &rows[i]
			family := families[row.Family]
			if family == nil || !family.HasCandidate || seenFamilies[row.Family] {
				return fmt.Errorf("unknown/duplicate snapshot family %q", row.Family)
			}
			deficit := stage15Deficit(best, family.Score)
			inPractical := deficit <= 3+1e-12
			inSensitivity := deficit <= 2+1e-12
			if group != inPractical {
				return fmt.Errorf("family %q misplaced across co-leader/pending output", row.Family)
			}
			reason := ""
			if !inPractical {
				reason = "below_practical_band"
				if family.RefinementLevel < 2 {
					reason = "below_practical_band_not_deeply_refined"
				}
			}
			if !stage15Close(row.FormulaDPS, family.Score) || !stage15Close(row.DeficitPercent, deficit) ||
				row.RefinementLevel != family.RefinementLevel || row.Reason != reason || row.Witness45 != family.Witness45 {
				return fmt.Errorf("family score/deficit/refinement/reason/witness %q", row.Family)
			}
			if e := stage15CheckAllocations(row.Allocations, row.Witness45, p.Wearers); e != nil {
				return fmt.Errorf("family %q: %w", row.Family, e)
			}
			wantAliasCount := aliasCounts[row.Family]
			if len(row.Aliases) != wantAliasCount {
				return fmt.Errorf("alias multiplicity for family %q", row.Family)
			}
			local := make(map[string]bool, len(row.Aliases))
			for _, alias := range row.Aliases {
				key, e := stage15ValidateAlias(alias.TupleKey, alias, p.Wearers, domains)
				if e != nil {
					return fmt.Errorf("snapshot family %q alias: %w", row.Family, e)
				}
				expected, ok := expectedAliases[key]
				if !ok || expected.Family != row.Family || local[key] || seenTuples[key] != "" || !reflect.DeepEqual(alias, *expected.Row) {
					return fmt.Errorf("alias set/provenance/packages/ownership %q", key)
				}
				local[key], seenTuples[key] = true, row.Family
			}
			seenFamilies[row.Family] = true
			totalTuples += len(local)
			if group {
				groupFamilies++
				groupTuples += len(local)
			}
			if inSensitivity {
				sensitivityFamilies++
				sensitivityTuples += len(local)
			}
		}
		return nil
	}
	if e := checkBucket(got.CoLeaders, true); e != nil {
		return e
	}
	if e := checkBucket(got.Pending, false); e != nil {
		return e
	}
	wantCandidateFamilies, wantCandidateTuples := 0, 0
	for _, family := range p.Families {
		if family.HasCandidate {
			wantCandidateFamilies++
			wantCandidateTuples += len(family.Aliases)
			if len(family.Aliases) == 0 {
				return fmt.Errorf("family %q candidate has no exact alias", family.Family)
			}
		}
	}
	if len(seenFamilies) != wantCandidateFamilies || totalTuples != wantCandidateTuples ||
		got.TotalFoundFamilies != wantCandidateFamilies || got.TotalFoundTuples != wantCandidateTuples ||
		got.FoundGroupFamilies != groupFamilies || got.FoundGroupTuples != groupTuples ||
		got.SensitivityGroupFamilies != sensitivityFamilies || got.SensitivityGroupTuples != sensitivityTuples {
		return fmt.Errorf("snapshot exhaustive family/tuple sets and exact totals")
	}
	for _, row := range got.Unavailable {
		key, e := stage15ValidateUnavailable(row.TupleKey, row, p.Wearers, domains)
		if e != nil {
			return fmt.Errorf("snapshot unavailable row: %w", e)
		}
		expected, ok := expectedUnavailable[key]
		if !ok || seenUnavailable[key] || seenTuples[key] != "" || !reflect.DeepEqual(row, expected) {
			return fmt.Errorf("unavailable tuple/reasons/packages/ownership %q", key)
		}
		seenUnavailable[key] = true
	}
	if len(seenUnavailable) != len(expectedUnavailable) {
		return fmt.Errorf("snapshot unavailable tuple set incomplete")
	}
	return nil
}

type stage15DomainIndex struct {
	packages [4]map[string]domain.Package
	total    *big.Int
}

type stage15ExpectedAlias struct {
	Family string
	Row    *Alias
}

func stage15ValidateProjection(p Stage15Projection) (stage15DomainIndex, error) {
	index := stage15DomainIndex{total: big.NewInt(1)}
	if p.Binding == "" || p.RequestSHA256 == "" || p.SessionID == "" {
		return index, fmt.Errorf("stage15 projection missing session identity")
	}
	owners := map[string]bool{}
	for actor, rows := range p.Domains {
		if p.Wearers[actor] == "" || owners[p.Wearers[actor]] || len(rows) == 0 {
			return index, fmt.Errorf("stage15 projection invalid wearer/domain %d", actor)
		}
		owners[p.Wearers[actor]] = true
		index.packages[actor] = make(map[string]domain.Package, len(rows))
		for _, pkg := range rows {
			if err := stage15ValidatePackage(pkg); err != nil {
				return index, fmt.Errorf("stage15 domain package for wearer %q: %w", p.Wearers[actor], err)
			}
			key := stage15PackageKey(pkg)
			if _, duplicate := index.packages[actor][key]; duplicate {
				return index, fmt.Errorf("stage15 duplicate package in wearer %q domain", p.Wearers[actor])
			}
			index.packages[actor][key] = pkg
		}
		index.total.Mul(index.total, big.NewInt(int64(len(rows))))
	}
	if _, err := stage15WitnessRolls(p.Initial); err != nil {
		return index, fmt.Errorf("stage15 initial allocation is not legal full45: %w", err)
	}
	if _, err := stage15ValidateTuple(p.Original, index); err != nil {
		return index, fmt.Errorf("stage15 original tuple: %w", err)
	}
	return index, nil
}

func stage15ValidateAlias(mapKey string, row Alias, wearers [4]string, domains stage15DomainIndex) (string, error) {
	var packages [4]domain.Package
	if mapKey == "" || len(row.Packages) != 4 {
		return "", fmt.Errorf("alias key/package count")
	}
	for actor, item := range row.Packages {
		if item.WearerKey != wearers[actor] {
			return "", fmt.Errorf("alias wearer ownership at %d", actor)
		}
		packages[actor] = domain.Package{Sets: stage15CopySets(item.Sets)}
		if err := stage15ValidatePackage(packages[actor]); err != nil {
			return "", fmt.Errorf("alias package %d: %w", actor, err)
		}
		if _, ok := domains.packages[actor][stage15PackageKey(packages[actor])]; !ok {
			return "", fmt.Errorf("alias package %d outside wearer domain", actor)
		}
	}
	key := stage15TupleKey(packages)
	if mapKey != key || row.TupleKey != key {
		return "", fmt.Errorf("alias map/wire tuple identity differs from independent tuple")
	}
	return key, nil
}

func stage15ValidateUnavailable(mapKey string, row Unavailable, wearers [4]string, domains stage15DomainIndex) (string, error) {
	var packages [4]domain.Package
	if mapKey == "" || len(row.Packages) != 4 || len(row.Reasons) == 0 {
		return "", fmt.Errorf("unavailable key/package/reason coverage")
	}
	for actor, item := range row.Packages {
		if item.WearerKey != wearers[actor] {
			return "", fmt.Errorf("unavailable wearer ownership at %d", actor)
		}
		packages[actor] = domain.Package{Sets: stage15CopySets(item.Sets)}
		if err := stage15ValidatePackage(packages[actor]); err != nil {
			return "", fmt.Errorf("unavailable package %d: %w", actor, err)
		}
		if _, ok := domains.packages[actor][stage15PackageKey(packages[actor])]; !ok {
			return "", fmt.Errorf("unavailable package %d outside wearer domain", actor)
		}
	}
	key := stage15TupleKey(packages)
	if mapKey != key || row.TupleKey != key {
		return "", fmt.Errorf("unavailable map/wire tuple identity differs from independent tuple")
	}
	return key, nil
}

func stage15ValidateTuple(tuple [4]domain.Package, domains stage15DomainIndex) (string, error) {
	for actor, pkg := range tuple {
		if err := stage15ValidatePackage(pkg); err != nil {
			return "", fmt.Errorf("package %d: %w", actor, err)
		}
		if _, ok := domains.packages[actor][stage15PackageKey(pkg)]; !ok {
			return "", fmt.Errorf("package %d outside wearer domain", actor)
		}
	}
	return stage15TupleKey(tuple), nil
}

func stage15ValidateVisited(rows []Stage15Visited, domains stage15DomainIndex) (map[string]string, error) {
	visited := make(map[string]string, len(rows))
	for _, row := range rows {
		if row.TupleKey == "" {
			return nil, fmt.Errorf("empty visited tuple key")
		}
		if _, duplicate := visited[row.TupleKey]; duplicate {
			return nil, fmt.Errorf("duplicate visited tuple %q", row.TupleKey)
		}
		parts := strings.Split(row.TupleKey, "|")
		if len(parts) != 4 {
			return nil, fmt.Errorf("visited tuple %q has wrong arity", row.TupleKey)
		}
		for actor, part := range parts {
			if _, ok := domains.packages[actor][part]; !ok {
				return nil, fmt.Errorf("visited tuple %q package %d outside domain", row.TupleKey, actor)
			}
		}
		visited[row.TupleKey] = row.Family
	}
	if domains.total.Cmp(big.NewInt(int64(len(visited)))) < 0 {
		return nil, fmt.Errorf("visited tuple count exceeds Cartesian domain")
	}
	return visited, nil
}

func stage15ValidatePackage(pkg domain.Package) error {
	if len(pkg.Sets) > 2 {
		return fmt.Errorf("package has more than two set requirements")
	}
	for i, set := range pkg.Sets {
		if set.SetUID == "" || (set.Count != 2 && set.Count != 4) ||
			(len(pkg.Sets) == 2 && set.Count != 2) || (i > 0 && pkg.Sets[i-1].SetUID >= set.SetUID) {
			return fmt.Errorf("package requirements are not canonical")
		}
	}
	return nil
}

func stage15PackageKey(pkg domain.Package) string {
	if len(pkg.Sets) == 0 {
		return "none"
	}
	parts := make([]string, len(pkg.Sets))
	for i, set := range pkg.Sets {
		parts[i] = fmt.Sprintf("%s:%d", set.SetUID, set.Count)
	}
	return strings.Join(parts, "+")
}

func stage15TupleKey(tuple [4]domain.Package) string {
	var parts [4]string
	for actor, pkg := range tuple {
		parts[actor] = stage15PackageKey(pkg)
	}
	return strings.Join(parts[:], "|")
}

func stage15PublicationPhase(phase string) string {
	if phase == "" {
		return "first_light"
	}
	return phase
}

func stage15Deficit(reference, score float64) float64 {
	if reference == 0 {
		if score == 0 {
			return 0
		}
		return 100
	}
	return 100 * (reference - score) / math.Abs(reference)
}

var stage15StatKeys = [10]string{
	"atk", "atk_percent", "crit_damage", "crit_rate", "def",
	"def_percent", "em", "energy_recharge", "hp", "hp_percent",
}

var stage15StatValues = [10]float64{
	19.45, .0583, .0777, .0389, 23.15,
	.0729, 23.31, .0648, 298.75, .0583,
}

var stage15LegalMains = [5][]string{
	{"hp"}, {"atk"},
	{"atk_percent", "def_percent", "em", "energy_recharge", "hp_percent"},
	{"anemo_damage_bonus", "atk_percent", "cryo_damage_bonus", "def_percent", "dendro_damage_bonus", "electro_damage_bonus", "em", "geo_damage_bonus", "hp_percent", "hydro_damage_bonus", "physical_damage_bonus", "pyro_damage_bonus"},
	{"atk_percent", "crit_damage", "crit_rate", "def_percent", "em", "healing_bonus", "hp_percent"},
}

func stage15WitnessRolls(state alloc.State) ([4][10]float64, error) {
	var rolls [4][10]float64
	for actor := range state.Mains {
		actorUpgrades := 0.0
		for slot, main := range state.Mains[actor] {
			legal := false
			for _, choice := range stage15LegalMains[slot] {
				legal = legal || main == choice
			}
			if !legal {
				return rolls, fmt.Errorf("wearer %d slot %d illegal main %q", actor, slot, main)
			}
			seen := [10]bool{}
			slotUpgrades := 0.0
			for line, stat := range state.Lines[actor][slot] {
				if stat < 0 || stat >= len(stage15StatKeys) || seen[stat] || stage15StatKeys[stat] == main {
					return rolls, fmt.Errorf("wearer %d slot %d illegal initial line %d", actor, slot, line)
				}
				seen[stat] = true
				u := state.Upgrades[actor][slot][line]
				if !stage15Finite(u) || u < 0 || math.Abs(4*u-math.Round(4*u)) > 1e-8 {
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

func stage15CheckAllocations(got []theory.WearerAllocation, state alloc.State, wearers [4]string) error {
	rolls, err := stage15WitnessRolls(state)
	if err != nil {
		return err
	}
	if len(got) != 4 {
		return fmt.Errorf("allocation wearer count %d, expected four", len(got))
	}
	slots := [5]string{"flower", "plume", "sands", "goblet", "circlet"}
	for actor, row := range got {
		if row.WearerKey != wearers[actor] || len(row.MainStats) != 5 || len(row.Substats) != 10 {
			return fmt.Errorf("allocation wearer/main/substat coverage for wearer %d", actor)
		}
		for slot, key := range slots {
			if row.MainStats[key] != state.Mains[actor][slot] {
				return fmt.Errorf("allocation main projection for wearer %d slot %s", actor, key)
			}
		}
		seen := [10]bool{}
		spent := 0.0
		for _, stat := range row.Substats {
			index := -1
			for i, key := range stage15StatKeys {
				if key == stat.StatKey {
					index = i
				}
			}
			if index < 0 || seen[index] {
				return fmt.Errorf("allocation duplicate/unknown substat for wearer %d", actor)
			}
			seen[index] = true
			units := rolls[actor][index]
			if !stage15Close(stat.RollUnits, units) || !stage15Close(stat.StatValue, units*stage15StatValues[index]) {
				return fmt.Errorf("allocation roll/stat projection for wearer %d stat %s", actor, stat.StatKey)
			}
			spent += units
		}
		if !stage15Close(spent, 45) || !stage15Close(row.SpentRollUnits, 45) || !stage15Close(row.UnspentRollUnits, 0) {
			return fmt.Errorf("allocation budget projection for wearer %d", actor)
		}
	}
	return nil
}

func stage15Finite(value float64) bool { return !math.IsNaN(value) && !math.IsInf(value, 0) }

func stage15Close(a, b float64) bool {
	return stage15Finite(a) && stage15Finite(b) && math.Abs(a-b) <= 1e-9
}

func stage15SameJSON(a, b any) bool {
	aRaw, aErr := json.Marshal(a)
	bRaw, bErr := json.Marshal(b)
	return aErr == nil && bErr == nil && string(aRaw) == string(bRaw)
}

func stage15CopySets(sets []contracts.SetRequirement) []contracts.SetRequirement {
	return append([]contracts.SetRequirement{}, sets...)
}

func stage15CopyPackage(pkg domain.Package) domain.Package {
	return domain.Package{Sets: stage15CopySets(pkg.Sets)}
}

func stage15CopyTuple(tuple [4]domain.Package) [4]domain.Package {
	for actor := range tuple {
		tuple[actor] = stage15CopyPackage(tuple[actor])
	}
	return tuple
}

func stage15CopyPackageRows(rows []PackageRow) []PackageRow {
	out := make([]PackageRow, len(rows))
	for i, row := range rows {
		out[i] = PackageRow{WearerKey: row.WearerKey, Sets: stage15CopySets(row.Sets)}
	}
	return out
}

func stage15CopyAlias(row Alias) Alias {
	return Alias{TupleKey: row.TupleKey, Packages: stage15CopyPackageRows(row.Packages),
		ContextSHA256: row.ContextSHA256, Uncertainty: append([]string{}, row.Uncertainty...)}
}

func stage15CopyUnavailable(row Unavailable) Unavailable {
	return Unavailable{TupleKey: row.TupleKey, Packages: stage15CopyPackageRows(row.Packages),
		Reasons: append([]string{}, row.Reasons...)}
}

package theorysearch

// Synthetic compiled arithmetic checks for allocation translation and branch
// ownership. These do not claim source activation or engine-response coverage.
import (
	"math"
	"sort"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

func compiledTheoryWorld(t *testing.T, nonlinear bool) (*FormulaWorld, alloc.State, string) {
	t.Helper()
	actors := []string{"actor_a", "actor_b", "actor_c", "actor_d"}
	coordinates := []string{"actor_a.hp", "actor_a.hp_percent", "actor_b.hp"}
	member := contracts.IRSeedMember{Seed: 1, DurationMS: 2000, TopologySHA256: strings.Repeat("a", 64), OpaqueBoundaries: []contracts.IROpaqueBoundary{}}
	add := func(operation, coordinate, value string, inputs ...uint32) uint32 {
		id := uint32(len(member.Nodes) + 1)
		operands := make([]contracts.IRInput, len(inputs))
		for index, input := range inputs {
			operands[index] = contracts.IRInput{NodeID: input, Relation: "operand"}
		}
		sort.Slice(operands, func(i, j int) bool { return operands[i].NodeID < operands[j].NodeID })
		member.Nodes = append(member.Nodes, contracts.IRNode{NodeID: id, Operation: operation, Coordinate: coordinate, Value: value, Inputs: operands})
		return id
	}
	x := add("artifact_stat", coordinates[0], "")
	z := add("artifact_stat", coordinates[1], "")
	y := add("artifact_stat", coordinates[2], "")
	two := add("constant", "", "2")
	var root uint32
	baselineDamage := "100"
	if nonlinear {
		// The compiler evaluates (10+x+2*z)*(20+y), then divides by 2s.
		twoZ := add("multiply", "", "", two, z)
		ten := add("constant", "", "10")
		left := add("add", "", "", ten, x, twoZ)
		twenty := add("constant", "", "20")
		right := add("add", "", "", twenty, y)
		root = add("multiply", "", "", left, right)
		baselineDamage = "200"
	} else {
		// The compiler evaluates 100+2*x+4*z+3*y, then divides by 2s.
		twoX := add("multiply", "", "", two, x)
		four := add("constant", "", "4")
		fourZ := add("multiply", "", "", four, z)
		three := add("constant", "", "3")
		threeY := add("multiply", "", "", three, y)
		hundred := add("constant", "", "100")
		root = add("add", "", "", hundred, twoX, fourZ, threeY)
	}
	member.Channels = []contracts.IRChannel{{ChannelID: "hit/000001", Kind: "direct", ActorKey: actors[0], AttackTag: "tag/1", DamageType: "physical", RootNodeID: root, HitCount: 1, BaselineDamage: baselineDamage, ResponseCoordinates: coordinates}}
	panel, err := evaluator.CompileMembers(actors, []uint64{1}, []contracts.IRSeedMember{member})
	if err != nil {
		t.Fatal(err)
	}
	program, err := panel.ArtifactProgramForActors(make([]float64, len(coordinates)), 0, 1, 2, 3)
	if err != nil {
		t.Fatal(err)
	}
	var mains [4][5]string
	var gradient [4][10]float64
	request := contracts.OptimizerRequest{}
	for actor, name := range actors {
		mains[actor] = [5]string{"hp", "atk", "hp_percent", "pyro_damage_bonus", "crit_rate"}
		gradient[actor][8], gradient[actor][9] = 10, 9
		// An irrelevant DEF upgrade supplies a legal quarter transfer to HP.
		gradient[actor][4] = 11
		request.Wearers = append(request.Wearers, contracts.Wearer{WearerKey: name})
	}
	anchor := alloc.Seed(mains, gradient, 0, 45)
	if err := alloc.ValidateFull45(anchor); err != nil {
		t.Fatal(err)
	}
	rolls := anchor.Rolls()
	entry := &formulaEntry{
		program: program, coords: program.Coordinates(),
		at:       map[string]int{coordinates[0]: 0, coordinates[1]: 1, coordinates[2]: 2},
		baseline: []float64{-(4780 + rolls[0][8]*298.75), -(.466 + rolls[0][9]*.0583), -(4780 + rolls[1][8]*298.75)},
	}
	for actor := range entry.indices {
		for stat := range entry.indices[actor] {
			entry.indices[actor][stat] = -1
		}
	}
	entry.indices[0][8], entry.indices[0][9], entry.indices[1][8] = 0, 1, 2
	family := "linear"
	if nonlinear {
		family = "nonlinear"
	}
	order, targetOrder := make([]string, 1, 8), make([]string, 1, 8)
	order[0], targetOrder[0] = family, "tuple"
	world := &FormulaWorld{
		req: request, binding: "synthetic-compiler-fixture", entries: map[string]*formulaEntry{family: entry}, order: order,
		targets: map[string]targetEntry{"tuple": {family: family, context: "fixture-context", codes: []string{"fixture-code"}}}, targetOrder: targetOrder,
	}
	return world, anchor, family
}

func moveTheoryQuarterToHP(t *testing.T, state alloc.State, actor int) alloc.State {
	t.Helper()
	for slot, lines := range state.Lines[actor] {
		to, from := -1, -1
		for line, stat := range lines {
			if stat == 8 {
				to = line
			} else if stat != 9 && state.Upgrades[actor][slot][line] >= .25 {
				from = line
			}
		}
		if to >= 0 && from >= 0 {
			state.Upgrades[actor][slot][from] -= .25
			state.Upgrades[actor][slot][to] += .25
			if err := alloc.ValidateFull45(state); err != nil {
				t.Fatal(err)
			}
			return state
		}
	}
	t.Fatal("fixture has no legal quarter transfer to HP")
	return state
}

func TestFormulaWorldCompiledDPSAndRollGradients(t *testing.T) {
	for _, nonlinear := range []bool{false, true} {
		world, anchor, family := compiledTheoryWorld(t, nonlinear)
		t.Run(family, func(t *testing.T) {
			defer world.Close()
			changedMain := alloc.ReplaceMain(anchor, 0, 2, "em", [4][10]float64{}, 45)
			points := []struct {
				name    string
				state   alloc.State
				x, z, y float64
			}{
				{"anchor", anchor, 0, 0, 0},
				{"wearer_a_quarter", moveTheoryQuarterToHP(t, anchor, 0), .25 * 298.75, 0, 0},
				{"wearer_b_quarter", moveTheoryQuarterToHP(t, anchor, 1), 0, 0, .25 * 298.75},
				{"changed_main", changedMain, 0, -.466, 0},
			}
			objective := world.objective(world.entries[family])
			for _, point := range points {
				t.Run(point.name, func(t *testing.T) {
					if err := alloc.ValidateFull45(point.state); err != nil {
						t.Fatal(err)
					}
					want := (100 + 2*point.x + 4*point.z + 3*point.y) / 2
					dx, dz, dy := 1.0, 2.0, 1.5
					if nonlinear {
						want = (10 + point.x + 2*point.z) * (20 + point.y) / 2
						dx, dz, dy = (20+point.y)/2, 20+point.y, (10+point.x+2*point.z)/2
					}
					var wantGradient [4][10]float64
					wantGradient[0][8], wantGradient[0][9], wantGradient[1][8] = dx*298.75, dz*.0583, dy*298.75
					value, gradient, err := objective(point.state, true)
					if err != nil || math.Abs(value-want) > 1e-10*(1+math.Abs(want)) {
						t.Fatalf("compiled DPS %g; want %g; err %v", value, want, err)
					}
					for actor := range gradient {
						for stat, got := range gradient[actor] {
							expected := wantGradient[actor][stat]
							if math.Abs(got-expected) > 1e-10*(1+math.Abs(expected)) {
								t.Fatalf("roll gradient actor %d stat %d = %g; want %g", actor, stat, got, expected)
							}
						}
					}
					valueOnly, unusedGradient, err := objective(point.state, false)
					if err != nil || math.Float64bits(valueOnly) != math.Float64bits(value) || unusedGradient != [4][10]float64{} {
						t.Fatalf("value-only compiler route changed DPS or returned a gradient: %g %v", valueOnly, err)
					}
				})
			}
		})
	}
}

func TestFormulaWorldForkOwnsEntriesTargetsFIFOAndScratch(t *testing.T) {
	parent, anchor, family := compiledTheoryWorld(t, true)
	defer parent.Close()
	parentObjective := parent.objective(parent.entries[family])
	want, wantGradient, err := parentObjective(anchor, true)
	if err != nil {
		t.Fatal(err)
	}
	fork := func() *FormulaWorld {
		t.Helper()
		resolver, err := parent.Fork()
		if err != nil {
			t.Fatal(err)
		}
		world, ok := resolver.(*FormulaWorld)
		if !ok {
			t.Fatal("fork returned a different resolver type")
		}
		return world
	}
	branch, sibling := fork(), fork()
	defer branch.Close()
	defer sibling.Close()
	if branch.entries[family] == parent.entries[family] || branch.entries[family].program == parent.entries[family].program || branch.entries[family].program == sibling.entries[family].program {
		t.Fatal("fork shares mutable entry/program objects")
	}
	branchObjective, siblingObjective := branch.objective(branch.entries[family]), sibling.objective(sibling.entries[family])
	if _, _, err := branchObjective(moveTheoryQuarterToHP(t, anchor, 0), true); err != nil {
		t.Fatal(err)
	}
	if value, gradient, err := parentObjective(anchor, true); err != nil || math.Float64bits(value) != math.Float64bits(want) || gradient != wantGradient {
		t.Fatal("child scratch changed the parent's cached objective")
	}
	if _, _, err := siblingObjective(moveTheoryQuarterToHP(t, anchor, 1), true); err != nil {
		t.Fatal(err)
	}
	if _, _, err := parentObjective(alloc.ReplaceMain(anchor, 0, 2, "em", [4][10]float64{}, 45), true); err != nil {
		t.Fatal(err)
	}
	for _, objective := range []alloc.Objective{parentObjective, branchObjective, siblingObjective} {
		value, gradient, err := objective(anchor, true)
		if err != nil || math.Float64bits(value) != math.Float64bits(want) || gradient != wantGradient {
			t.Fatalf("fork arithmetic differs after perturbed evaluation: %g %v", value, err)
		}
	}
	entry := branch.entries[family]
	entry.coords[0], entry.baseline[0] = "changed", 1
	entry.at["actor_a.hp"], entry.indices[0][8] = 2, -1
	branch.order[0], branch.targetOrder[0] = "changed", "changed"
	target := branch.targets["tuple"]
	target.codes[0] = "changed"
	delete(branch.entries, family)
	delete(branch.targets, "tuple")
	for _, world := range []*FormulaWorld{parent, sibling} {
		if world.entries[family] == nil || world.entries[family].coords[0] != "actor_a.hp" || world.entries[family].at["actor_a.hp"] != 0 || world.entries[family].indices[0][8] != 0 ||
			world.order[0] != family || world.targetOrder[0] != "tuple" || world.targets["tuple"].codes[0] != "fixture-code" {
			t.Fatal("child mutation changed parent/sibling entries, index maps, target diagnostics, or FIFO order")
		}
		value, gradient, err := world.objective(world.entries[family])(anchor, true)
		if err != nil || math.Float64bits(value) != math.Float64bits(want) || gradient != wantGradient {
			t.Fatal("child mutation changed parent/sibling baseline or scratch")
		}
	}
	branch.Close()
	if _, _, err := branchObjective(anchor, true); err == nil {
		t.Fatal("closed fork accepted its retained objective")
	}
	if value, gradient, err := parentObjective(anchor, true); err != nil || math.Float64bits(value) != math.Float64bits(want) || gradient != wantGradient {
		t.Fatal("closing a fork changed the parent objective")
	}
}

func TestFormulaWorldCloseRejectsRetainedObjective(t *testing.T) {
	world, anchor, family := compiledTheoryWorld(t, false)
	entry := world.entry(family, "fixture-context", []string{"fixture-code"})
	if entry == nil {
		t.Fatal("compiled fixture entry unavailable")
	}
	world.Close()
	world.Close()
	for _, wantGradient := range []bool{false, true} {
		if _, _, err := entry.Objective(anchor, wantGradient); err == nil || !strings.Contains(err.Error(), "closed") {
			t.Fatalf("closed world accepted retained objective: %v", err)
		}
	}
	if fork, err := world.Fork(); err == nil || fork != nil {
		t.Fatal("closed world accepted another fork")
	}
	if !world.closed || world.entries != nil || world.targets != nil || world.order != nil || world.targetOrder != nil {
		t.Fatal("Close retained mutable world caches")
	}
}

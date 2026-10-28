package formula

import (
	"math"
	"testing"
)

func affineProbeProgram(t *testing.T, coordinates []string, root func(func(compiledNode) uint32) uint32) *ArtifactProgram {
	t.Helper()
	b := newProgramBuilder(coordinates)
	add := func(n compiledNode) uint32 {
		id, err := b.add(n)
		if err != nil {
			t.Fatal(err)
		}
		return id
	}
	return b.finish(root(add))
}

func affineProbeCoreRoot(add func(compiledNode) uint32) uint32 {
	x := add(compiledNode{op: opArtifactStat, coordinate: 0})
	y := add(compiledNode{op: opArtifactStat, coordinate: 1})
	three := add(compiledNode{op: opConstant, coordinate: -1, value: 3})
	yPlusThree := add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{y, three}})
	product := add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{x, yPlusThree}})
	return add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{product, y}})
}

func affineProbeCore(t *testing.T, coordinates []string) *ArtifactProgram {
	return affineProbeProgram(t, coordinates, affineProbeCoreRoot)
}

func TestPositiveAffineOfProvesNestedStructuralTransform(t *testing.T) {
	coordinates := []string{"chasca.atk%", "furina.hp%"}
	reference := affineProbeCore(t, coordinates)
	candidate := affineProbeProgram(t, coordinates, func(add func(compiledNode) uint32) uint32 {
		core := affineProbeCoreRoot(add)
		two := add(compiledNode{op: opConstant, coordinate: -1, value: 2})
		three := add(compiledNode{op: opConstant, coordinate: -1, value: 3})
		seven := add(compiledNode{op: opConstant, coordinate: -1, value: 7})
		inner := add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{core, two}})
		scaled := add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{inner, three}})
		return add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{scaled, seven}})
	})

	a, b, ok := candidate.PositiveAffineOf(reference)
	if !ok || a != 3 || b != 13 {
		t.Fatalf("PositiveAffineOf = (%v, %v, %v), want (3, 13, true)", a, b, ok)
	}
}

func TestPositiveAffineOfRejectsSamePointButDifferentDamageComponent(t *testing.T) {
	coordinates := []string{"chasca.skill", "furina.skill"}
	teamTotal := affineProbeProgram(t, coordinates, func(add func(compiledNode) uint32) uint32 {
		chascaSkill := add(compiledNode{op: opArtifactStat, coordinate: 0})
		furinaSkill := add(compiledNode{op: opArtifactStat, coordinate: 1})
		ten := add(compiledNode{op: opConstant, coordinate: -1, value: 10})
		fifty := add(compiledNode{op: opConstant, coordinate: -1, value: 50})
		chascaDamage := add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{chascaSkill, ten}})
		furinaDamage := add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{furinaSkill, fifty}})
		return add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{chascaDamage, furinaDamage}})
	})
	chascaSkillBonusComponent := affineProbeProgram(t, coordinates, func(add func(compiledNode) uint32) uint32 {
		chascaSkill := add(compiledNode{op: opArtifactStat, coordinate: 0})
		ten := add(compiledNode{op: opConstant, coordinate: -1, value: 10})
		return add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{chascaSkill, ten}})
	})

	// At this anchor both objectives happen to be 20. A point match is not a
	// proof: Furina's independent skill damage changes the team total only.
	teamAtAnchor, err := teamTotal.Evaluate([]float64{2, 0})
	if err != nil {
		t.Fatal(err)
	}
	componentAtAnchor, err := chascaSkillBonusComponent.Evaluate([]float64{2, 0})
	if err != nil || teamAtAnchor != componentAtAnchor {
		t.Fatalf("fixture anchor values differ: team=%v component=%v err=%v", teamAtAnchor, componentAtAnchor, err)
	}
	if _, _, ok := chascaSkillBonusComponent.PositiveAffineOf(teamTotal); ok {
		t.Fatal("accepted one-character damage component as an affine team-total objective")
	}
}

func TestPositiveAffineOfRejectsDomainAndUnknownBoundaries(t *testing.T) {
	base := affineProbeCore(t, []string{"chasca.atk%", "furina.hp%"})
	otherCoordinates := affineProbeCore(t, []string{"chasca.atk%", "furina.hp%", "ororon.em"})
	if _, _, ok := base.PositiveAffineOf(otherCoordinates); ok {
		t.Fatal("accepted different coordinate schemas")
	}
	unknown := affineProbeCore(t, []string{"chasca.atk%", "furina.hp%"})
	unknown.unresolved = true
	if _, _, ok := base.PositiveAffineOf(unknown); ok {
		t.Fatal("accepted unresolved objective")
	}
	negative := affineProbeProgram(t, []string{"chasca.atk%", "furina.hp%"}, func(add func(compiledNode) uint32) uint32 {
		core := affineProbeCoreRoot(add)
		minusOne := add(compiledNode{op: opConstant, coordinate: -1, value: -1})
		return add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{core, minusOne}})
	})
	if _, _, ok := negative.PositiveAffineOf(base); ok {
		t.Fatal("accepted a negative objective scale")
	}
	zero := affineProbeProgram(t, []string{"chasca.atk%", "furina.hp%"}, func(add func(compiledNode) uint32) uint32 {
		core := affineProbeCoreRoot(add)
		zero := add(compiledNode{op: opConstant, coordinate: -1, value: math.Copysign(0, -1)})
		return add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{core, zero}})
	})
	if _, _, ok := zero.PositiveAffineOf(base); ok {
		t.Fatal("accepted a zero-scale objective")
	}
}

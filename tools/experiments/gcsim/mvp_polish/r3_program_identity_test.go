package setcontext

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"testing"
)

func TestR3ProgramIdentityMembershipAndEviction(t *testing.T) {
	t.Setenv("GTT_R3_PROGRAM_IDENTITY", "1")
	a, b := &formula.ParametricProgram{}, &formula.ParametricProgram{}
	one, two, three := [32]byte{1}, [32]byte{2}, [32]byte{3}
	m := &NeutralModel{programCache: map[[32]byte]*formula.ParametricProgram{one: a, two: b}, programOrder: [][32]byte{one, two}}
	if key, ok := m.r3ProgramKey(a); !ok || key != one {
		t.Fatal("retained identity lost")
	}
	if _, ok := m.r3ProgramKey(&formula.ParametricProgram{}); ok {
		t.Fatal("foreign identity admitted")
	}
	m.programOrder = m.programOrder[1:]
	m.r3ForgetProgramKey(one, a)
	delete(m.programCache, one)
	if _, ok := m.r3ProgramKey(a); ok {
		t.Fatal("evicted identity resurrected")
	}
	m.programCache[three] = a
	m.r3RememberProgramKey(three, a)
	if key, ok := m.r3ProgramKey(a); !ok || key != three {
		t.Fatal("retained re-entry lost")
	}
	delete(m.programCache, three)
	if _, ok := m.r3ProgramKey(a); ok {
		t.Fatal("stale reverse identity was trusted")
	}
	t.Setenv("GTT_R3_PROGRAM_IDENTITY", "0")
	if key, ok := m.r3ProgramKey(b); !ok || key != two {
		t.Fatal("control lookup differs")
	}
}

func TestR3ProgramIdentityDuplicatePointerRemoval(t *testing.T) {
	t.Setenv("GTT_R3_PROGRAM_IDENTITY", "1")
	a := &formula.ParametricProgram{}
	one, two := [32]byte{1}, [32]byte{2}
	m := &NeutralModel{programCache: map[[32]byte]*formula.ParametricProgram{one: a, two: a}, programOrder: [][32]byte{one, two}}
	m.r3ProgramKey(a)
	m.r3RememberProgramKey(one, a)
	m.programOrder = m.programOrder[1:]
	m.r3ForgetProgramKey(one, a)
	delete(m.programCache, one)
	if key, ok := m.r3ProgramKey(a); !ok || key != two || len(m.r3ProgramKeys) != 1 {
		t.Fatal("duplicate exact key lost on eviction")
	}
}

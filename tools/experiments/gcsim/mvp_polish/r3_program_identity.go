package setcontext

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"os"
)

func (m *NeutralModel) r3ProgramKey(program *formula.ParametricProgram) ([32]byte, bool) {
	if os.Getenv("GTT_R3_PROGRAM_IDENTITY") != "1" {
		for key, cached := range m.programCache {
			if cached == program {
				return key, true
			}
		}
		return [32]byte{}, false
	}
	if m.r3ProgramKeys == nil {
		m.r3ProgramKeys = make(map[*formula.ParametricProgram][32]byte, len(m.programCache))
		for key, cached := range m.programCache {
			if cached != nil {
				m.r3ProgramKeys[cached] = key
			}
		}
	}
	key, found := m.r3ProgramKeys[program]
	// A reverse index never makes an evicted or foreign pointer applicable.
	return key, found && program != nil && m.programCache[key] == program
}

func (m *NeutralModel) r3RememberProgramKey(key [32]byte, program *formula.ParametricProgram) {
	if m.r3ProgramKeys != nil && os.Getenv("GTT_R3_PROGRAM_IDENTITY") == "1" {
		m.r3ProgramKeys[program] = key
	}
}

func (m *NeutralModel) r3ForgetProgramKey(key [32]byte, program *formula.ParametricProgram) {
	if previous, ok := m.r3ProgramKeys[program]; !ok || previous != key {
		return
	}
	delete(m.r3ProgramKeys, program)
	// Duplicate pointers under several exact keys are legal. This rare eviction
	// repair stays bounded by the existing retained cache and does no new reuse.
	for _, other := range m.programOrder {
		if other != key && m.programCache[other] == program {
			m.r3ProgramKeys[program] = other
			break
		}
	}
}

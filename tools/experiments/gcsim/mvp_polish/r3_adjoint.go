package formula

import "os"

// The gradient returned by ValueGradient still owns a fresh allocation. Only
// the internal reverse-pass adjoints survive until this sequential owner dies.
func (p *ArtifactProgram) r3AdjointScratch() []float64 {
	if os.Getenv("GTT_R3_ADJOINT_REUSE") != "1" {
		return make([]float64, len(p.nodes))
	}
	if len(p.r3Adjoints) != len(p.nodes) {
		p.r3Adjoints = make([]float64, len(p.nodes))
	} else {
		clear(p.r3Adjoints)
	}
	return p.r3Adjoints
}

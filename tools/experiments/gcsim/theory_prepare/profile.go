package setcontext

import (
	"crypto/sha256"
	"encoding/binary"
	"math"
)

// Scratch-only counters. No numerical branch depends on them.
type ResearchPrepareStats struct {
	HitCalls, MissCalls, KeyBytes, Evictions, PeakEntries, PeakNodes int
	KeySeconds, HitSeconds, MissSeconds, OrderSeconds, RegionSeconds float64
	ValidationSeconds                                                float64
}

func (m *NeutralModel) ResearchPrepareProfile() ResearchPrepareStats {
	return m.researchPrepare
}

// Identical SHA256 input bytes in identical projection order, with fixed local
// scratch instead of allocating eight bytes per live port on every lookup.
// The caller still validates every value, including all latent input ports.
func researchChunkedConstantDigest(values []float64, dimensions []int) [32]byte {
	h := sha256.New()
	var chunk [4096]byte
	at := 0
	for _, dimension := range dimensions {
		binary.LittleEndian.PutUint64(chunk[at:], math.Float64bits(values[dimension]))
		at += 8
		if at == len(chunk) {
			h.Write(chunk[:])
			at = 0
		}
	}
	h.Write(chunk[:at])
	var digest [32]byte
	h.Sum(digest[:0])
	return digest
}

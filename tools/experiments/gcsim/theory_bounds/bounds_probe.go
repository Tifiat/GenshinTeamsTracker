package formula

// Research-only adapter, copied into managed scratch. The runner adds one
// support callback to the existing affine enclosure; source arithmetic is
// otherwise unchanged. This is a guarded float enclosure, not a formal proof.
import "math"

type ResearchEnvelopeResult struct {
	Upper, ModelUpper               float64
	Nodes, Dimensions, SupportCalls int
	Unresolved                      bool
}

// ResearchEnvelope encloses this fixed DAG over the complete domain represented
// by support. Inputs and center are absolute artifact stats; ref converts them
// to the local deltas consumed by this program. support must enclose every
// feasible dot product, including mandatory lines and all remaining mains.
// ModelUpper is only a surrogate bound when source dependencies are unresolved.
func (p *ArtifactProgram) ResearchEnvelope(center, ref []float64, support func([]float64) (float64, float64), naturalOnly bool) ResearchEnvelopeResult {
	r := ResearchEnvelopeResult{Upper: math.Inf(1), ModelUpper: math.Inf(1), Nodes: len(p.nodes), Dimensions: len(p.coordinates), Unresolved: p.unresolved}
	if len(center) != len(p.coordinates) || len(ref) != len(center) || len(center) > boundDimensions || support == nil {
		return r
	}
	for i := range center {
		if !isFinite(center[i]) || !isFinite(ref[i]) {
			return r
		}
	}
	b := artifactBound{d: len(center), cache: map[boundVector][2]float64{}}
	copy(b.mean[:], center)
	b.research = func(w boundVector) (float64, float64) {
		if v, ok := b.cache[w]; ok {
			return v[0], v[1]
		}
		r.SupportCalls++
		lo, hi := support(w[:b.d])
		offset, magnitude := 0.0, math.Abs(lo)+math.Abs(hi)
		for j := 0; j < b.d; j++ {
			offset += w[j] * b.mean[j]
			magnitude += math.Abs(w[j] * b.mean[j])
		}
		guard := 2e-12 * (1 + magnitude)
		lo, hi = down(lo-offset-guard), up(hi-offset+guard)
		if !isFinite(lo) || !isFinite(hi) || lo > hi {
			lo, hi = math.Inf(-1), math.Inf(1)
		}
		b.cache[w] = [2]float64{lo, hi}
		return lo, hi
	}
	if !naturalOnly {
		r.ModelUpper, _ = p.boundUpper(&b, ref)
	} else {
		values := make([]affineValue, len(p.nodes))
		for i, n := range p.nodes {
			var lo, hi float64
			var ok bool
			if n.op == opArtifactStat {
				var w boundVector
				w[n.coordinate] = 1
				lo, hi = b.support(w)
				lo, hi = down(lo+center[n.coordinate]-ref[n.coordinate]), up(hi+center[n.coordinate]-ref[n.coordinate])
				ok = isFinite(lo) && isFinite(hi)
			} else {
				lo, hi, ok = naturalInterval(n, values)
			}
			if !ok || lo > hi {
				return r
			}
			v := affineInterval(lo, hi)
			if n.op == opConstant {
				v = affineValue{c: n.value}
			}
			v.lo, v.hi, v.enclosed = lo, hi, true
			values[i] = v
		}
		r.ModelUpper = values[p.root].hi
	}
	if !p.unresolved {
		r.Upper = r.ModelUpper
	}
	return r
}

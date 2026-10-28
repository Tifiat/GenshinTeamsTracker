package theoryprototype

import (
	"fmt"
	"math"
)

// WindowConfig limits each actor/stat roll total to its starting value plus or
// minus Radius. MaxExpansions is the number of permitted radius doublings;
// zero keeps a fixed window. ProbeWide separately checks the full fixed-layout
// domain from the input and stat-focused starts.
type WindowConfig struct {
	Radius        float64
	MaxExpansions int
	ProbeWide     bool
}

type WindowResult struct {
	State           State
	Value           float64
	Evaluations     int
	RejectedOutside int
	Expansions      int
	WideProbed      bool
	WideEvaluations int
	WideSeedProbes  int
	Radius          float64
	Stop            string
}

// WindowOptimize runs bounded SPG on fixed mains and lines. The finite score
// used outside the current roll window rejects those trial points; it is not
// Euclidean projection and a local/interior stop does not certify a global
// optimum. Every returned state is a feasible quarter-grid witness.
func WindowOptimize(obj Objective, start State, cfg Config, window WindowConfig) (WindowResult, error) {
	var out WindowResult
	if obj == nil {
		return out, fmt.Errorf("nil objective")
	}
	var err error
	cfg, err = normalizedConfig(cfg)
	if err != nil {
		return out, err
	}
	if cfg.Method != "spg" {
		return out, fmt.Errorf("window optimization requires spg")
	}
	if err := start.Validate(cfg.Budget, true); err != nil {
		return out, err
	}
	if !finite(window.Radius) || window.Radius < 0 || window.MaxExpansions < 0 {
		return out, fmt.Errorf("invalid roll-window radius or expansion limit")
	}
	cap := cfg.Budget - 20
	radius := math.Min(window.Radius, cap)
	center := start.Rolls()
	baseValue, _, err := obj(start, false)
	out.Evaluations++
	if err != nil {
		return out, err
	}
	if !finite(baseValue) {
		return out, fmt.Errorf("non-finite initial objective")
	}
	rejectedValue := math.Nextafter(baseValue, math.Inf(-1))
	if !finite(rejectedValue) {
		rejectedValue = baseValue
	}
	out.State, out.Value, out.Radius = start, baseValue, radius
	for {
		rejectedBefore := out.RejectedOutside
		bounded := func(candidate State, needGradient bool) (float64, [4][10]float64, error) {
			out.Evaluations++
			if !insideRollWindow(candidate, center, radius) {
				out.RejectedOutside++
				return rejectedValue, [4][10]float64{}, nil
			}
			return obj(candidate, needGradient)
		}
		r, runErr := Optimize(bounded, out.State, cfg)
		if runErr != nil {
			out.Stop = "objective_error"
			return out, runErr
		}
		if insideRollWindow(r.State, center, radius) && quarterBetter(r.Value, out.Value) {
			out.State, out.Value = r.State, r.Value
		}
		boundary := radius < cap-1e-9 &&
			(out.RejectedOutside > rejectedBefore || rollWindowBoundary(out.State, start, center, radius, cap))
		if boundary && out.Expansions < window.MaxExpansions {
			radius = math.Min(cap, math.Max(radius*2, radius+.25))
			out.Radius = radius
			out.Expansions++
			continue
		}
		if window.ProbeWide {
			out.WideProbed = true
			wide, wideErr := wideRollCheckpoint(obj, start, cfg, &out)
			if wideErr != nil {
				out.Stop = "objective_error"
				return out, wideErr
			}
			if quarterBetter(wide.Value, out.Value) {
				if insideRollWindow(wide.State, center, radius) {
					out.State, out.Value = wide.State, wide.Value
					out.Stop = "wide_probe_improvement"
					return out, nil
				}
				if out.Expansions < window.MaxExpansions {
					out.Expansions++
					out.Radius = cap
					out.State, out.Value = wide.State, wide.Value
					out.Stop = "wide_probe_expansion"
					return out, nil
				}
				out.Stop = "window_cap_wide_better"
				return out, nil
			}
		}
		if radius >= cap-1e-9 {
			out.Stop = "full_domain_local"
		} else if boundary {
			out.Stop = "window_cap"
		} else {
			out.Stop = "interior_window"
		}
		return out, nil
	}
}

func insideRollWindow(state State, center [4][10]float64, radius float64) bool {
	rolls := state.Rolls()
	for actor := range rolls {
		for stat, value := range rolls[actor] {
			if math.Abs(value-center[actor][stat]) > radius+1e-8 {
				return false
			}
		}
	}
	return true
}

func rollWindowBoundary(state, start State, center [4][10]float64, radius, cap float64) bool {
	rolls := state.Rolls()
	for actor := range rolls {
		for stat, value := range rolls[actor] {
			count := 0
			for slot := range start.Lines[actor] {
				for _, lineStat := range start.Lines[actor][slot] {
					if lineStat == stat {
						count++
					}
				}
			}
			minimum := float64(count)
			maximum := minimum + math.Min(cap, 5*float64(count))
			lower, upper := center[actor][stat]-radius, center[actor][stat]+radius
			if upper < maximum-1e-9 && value >= upper-.25-1e-9 ||
				lower > minimum+1e-9 && value <= lower+.25+1e-9 {
				return true
			}
		}
	}
	return false
}

func wideRollCheckpoint(obj Objective, start State, cfg Config, out *WindowResult) (Result, error) {
	counted := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		out.Evaluations++
		out.WideEvaluations++
		return obj(state, needGradient)
	}
	bestSeed, bestSeedValue := start, math.Inf(-1)
	cap := cfg.Budget - 20
	for actor := range start.Lines {
		for stat := range StatKeys {
			candidate := start
			candidate.Upgrades[actor] = [5][4]float64{}
			remaining := cap
			found := false
			for slot := range candidate.Lines[actor] {
				for line, lineStat := range candidate.Lines[actor][slot] {
					if lineStat == stat && remaining > 0 {
						u := math.Min(5, remaining)
						candidate.Upgrades[actor][slot][line] = u
						remaining -= u
						found = true
					}
				}
			}
			if !found || candidate == start {
				continue
			}
			out.WideSeedProbes++
			value, _, err := counted(candidate, false)
			if err != nil {
				return Result{}, err
			}
			if !finite(value) {
				return Result{}, fmt.Errorf("non-finite wide checkpoint score")
			}
			if value > bestSeedValue {
				bestSeed, bestSeedValue = candidate, value
			}
		}
	}
	baseline, err := Optimize(counted, start, cfg)
	if err != nil {
		return baseline, err
	}
	if bestSeed == start {
		return baseline, nil
	}
	extreme, err := Optimize(counted, bestSeed, cfg)
	if err != nil {
		return extreme, err
	}
	if quarterBetter(extreme.Value, baseline.Value) {
		return extreme, nil
	}
	return baseline, nil
}

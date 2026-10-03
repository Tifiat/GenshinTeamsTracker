package evaluator

// Search views specialize the already prepared neutral aggregate. They do not
// reread hit IR, impersonate fresh captures, or supply stale per-actor scores.
import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"slices"
	"strings"
)

func (panel *Panel) ParametricView(program *formula.ParametricProgram, uncertainty []string) (*Panel, error) {
	if panel == nil || program == nil || len(program.EffectKeys()) != 0 || !slices.Equal(panel.coordinates, program.Coordinates()) {
		return nil, fmt.Errorf("bound parametric view differs from neutral coordinates")
	}
	if len(uncertainty) > 0 {
		program = program.WithoutPruning()
	}
	view := &Panel{coordinates: panel.Coordinates(), actorKeys: panel.ActorKeys(), prepared: program, parametricView: true, opaqueReasons: append(panel.OpaqueReasons(), uncertainty...)}
	// New effects can connect formerly latent stats to foreign damage. Until an
	// actor-root projection is retained, conservative all-consumer links avoid
	// falsely freezing a support wearer or omitting a paired inventory exchange.
	for _, key := range view.coordinates {
		owner, _, _ := strings.Cut(key, ".")
		view.ledger = append(view.ledger, ResponseLedgerEntry{Coordinate: key, ProviderActor: owner, ConsumerActors: view.ActorKeys()})
	}
	baseline, err := view.EvaluateDPS(make([]float64, len(view.coordinates)))
	if err != nil {
		return nil, err
	}
	view.baseline.MeanDPS = baseline
	return view, nil
}

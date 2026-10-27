package allsets

import (
	"context"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"testing"
)

func TestR1RouterBlocksEveryExtraContextCapture(t *testing.T) {
	t.Setenv("GTT_R1_SINGLE_NEUTRAL", "1")
	_, base, sources, _, _ := coordinatorFixture(t)
	target, err := base.Replace(map[string][]setcontext.Set{base.Actors()[0]: {{UID: "generic", Count: 4}}})
	if err != nil {
		t.Fatal(err)
	}
	for _, kind := range []contracts.MechanicBoundaryKind{contracts.MechanicScheduleChange, contracts.MechanicUnknownOperation, contracts.MechanicUnsupportedSource, contracts.MechanicAnalysisBudget, contracts.MechanicInvalidOperation} {
		router := scheduleContextRouter{sources: sources, model: mechanicRouteProbe{contracts.MechanicBoundary{Kind: kind, Reason: "synthetic"}}, attempts: map[string]scheduleCaptureOutcome{}}
		h, _, e := router.Resolve(context.Background(), target)
		if e == nil || h != nil {
			t.Fatal("extra capture was not rejected", kind, e)
		}
	}
}
func TestR1ConnectedNeutralSearchKeepsFullActorPath(t *testing.T) {
	t.Setenv("GTT_R1_SINGLE_NEUTRAL", "1")
	TestNeutralSearchIndependentOfResultLimits(t)
}

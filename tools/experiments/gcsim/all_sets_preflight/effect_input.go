package gttcompact

// Experimental annotation only; does NOT alter IR arithmetic or expose proof.
// Node IDs are usable only with the exact graph of this capture, not by label
// or float equality. Duplicate/ambiguous ports are rejected rather than guessed.
import (
	"strings"
	"strconv"
	"github.com/genshinsim/gcsim/pkg/optimization/optstats"
)

type EffectInput struct {
	EventID string `json:"event_id"`
	NodeID uint32 `json:"node_id"`
	Kind string `json:"kind"`
	Owner string `json:"owner"`
	AttackTag string `json:"attack_tag"`
	Observed string `json:"observed"`
}

func collectEffectInputs(buffer optstats.GTTTraceEquationBuffer,owners []string,support supportProgram)[]EffectInput{
	out:=[]EffectInput{}
	for _,event:=range buffer.StateEvents {
		if event.Channel==nil || !strings.HasPrefix(*event.Channel,"effect_input:") || event.OwnerIndex==nil || *event.OwnerIndex<0 || *event.OwnerIndex>=len(owners) || event.Value==nil {continue}
		node,ok:=support.eventNodes[event.EventID];if !ok || !closeEnough(node.baseline,*event.Value){continue}
		tag:=""
		for _,field:=range event.NumericPayload {
			if field.Key=="attack_tag" && field.Value>=0 && field.Value==float64(int(field.Value)){tag="tag/"+strconv.Itoa(int(field.Value))}
		}
		if tag==""{continue}
		out=append(out,EffectInput{event.EventID,node.id,strings.TrimPrefix(*event.Channel,"effect_input:"),owners[*event.OwnerIndex],tag,decimal(*event.Value)})
	}
	return out
}

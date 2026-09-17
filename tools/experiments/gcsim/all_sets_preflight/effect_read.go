package gtttrace

// Experimental observer overlay, not installed. Annotates the already existing
// numeric sum; no extra event, modifier evaluation or gameplay/RNG operation.
// Intended successor: versioned neutral effect-input sidecar, see Go design.
func (r *Runtime) RecordEffectRead(source,channel string,owner,tag int,operator string,inputs []NumericRef,value float64,evidence DependencyEvidence)string{
	id:=r.RecordNumericEval(source,operator,inputs,value,evidence)
	if id=="" || len(r.stateEvents)==0{return id}
	row:=&r.stateEvents[len(r.stateEvents)-1]
	if row.EventID!=id{return id}
	row.Channel=optionalString("effect_input:"+channel)
	row.OwnerIndex=optionalInt(owner)
	row.NumericPayload=[]NumericPayload{{Key:"attack_tag",Value:float64(tag),Reference:LiteralRef(float64(tag))}}
	return id
}

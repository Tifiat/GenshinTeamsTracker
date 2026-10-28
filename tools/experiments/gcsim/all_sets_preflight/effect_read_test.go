package gtttrace

import "testing"

func TestEffectReadAnnotationDoesNotAddAnEventOrLoseZeroOwner(t *testing.T){
	for _,enabled:=range []bool{true,false}{
		r:=NewRuntime();if enabled{r.Enable()}
		id:=r.RecordEffectRead("","reaction_bonus",0,31,"literal",nil,0,IncompleteEvidence("test"))
		rows:=r.StateEvents()
		if !enabled {if id!="" || len(rows)!=0{t.Fatal("disabled changed")};continue}
		if len(rows)!=1 || rows[0].EventID!=id || rows[0].OwnerIndex==nil || *rows[0].OwnerIndex!=0 || rows[0].Value==nil || *rows[0].Value!=0 || rows[0].NumericPayload[0].Value!=31{t.Fatal(rows)}
		if rows[0].Operation==nil || *rows[0].Operation!="literal" || len(rows[0].Inputs)!=0 {t.Fatal("arithmetic changed")}
	}
}

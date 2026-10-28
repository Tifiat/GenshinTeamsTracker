package seteffects

import (
 "encoding/json"
 "math"
 "os"
 "path/filepath"
 "testing"
 "time"
 "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
 "genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

func TestSourceResistanceCapturedResponses(t *testing.T){
 dir:=os.Getenv("GTT_RESISTANCE_OUTPUT")
 raw,e:=os.ReadFile(os.Getenv("GTT_CONTEXT_CURVES"));if e!=nil{t.Fatal(e)}
 var curves []ScalarSlice;if e=json.Unmarshal(raw,&curves);e!=nil{t.Fatal(e)}
 type capture struct{
  Member contracts.IRSeedMember `json:"member"`
  Audit struct{Inputs []ResistanceInput `json:"resistance_inputs"`} `json:"audit"`
  Owners []string `json:"owners"`
  Element string `json:"element"`
 }
 rows:=[]any{}
 for _,name:=range []string{"bloom","cloud"}{
  load:=func(mode string)capture{raw,e:=os.ReadFile(filepath.Join(dir,name+"-"+mode+".json"));if e!=nil{t.Fatal(e)};var c capture;if e=json.Unmarshal(raw,&c);e!=nil{t.Fatal(e)};return c}
  base,fresh:=load("baseline"),load("offset")
  if base.Member.DurationMS!=fresh.Member.DurationMS || len(base.Member.Channels)!=len(fresh.Member.Channels){t.Fatal("changed schedule")}
  for i,a:=range base.Member.Channels{b:=fresh.Member.Channels[i];if a.ActorKey!=b.ActorKey || a.DamageType!=b.DamageType || a.AttackTag!=b.AttackTag{t.Fatal("changed hit alignment")}}
  sha,e:=contracts.CanonicalSHA256(base.Member);if e!=nil{t.Fatal(e)}
  probe,e:=NewResistanceProbe(base.Member,base.Owners,ResistanceEnvelope{1,sha,base.Audit.Inputs},curves);if e!=nil{t.Fatal(name,e)}
  expected,e:=formula.EvaluateSeedMember(fresh.Member,nil);if e!=nil{t.Fatal(e)}
  original,e:=formula.EvaluateSeedMember(base.Member,nil);if e!=nil{t.Fatal(e)}
  start:=time.Now();gain,n,e:=probe.Increment(base.Element,-.3);if e!=nil{t.Fatal(e)}
  seconds:=time.Since(start).Seconds()
  scale:=1000/float64(base.Member.DurationMS)
  predicted:=original.Damage*scale+gain;want:=expected.Damage*scale
  residual:=math.Abs(predicted-want)/math.Max(1,math.Abs(want))
  if residual>1e-9{t.Errorf("%s resistance response %g != %g residual=%g",name,predicted,want,residual)}
  // All accepted hit formulas in these fixtures must expose their terminal
  // resistance, including direct reactions and contributor-group output.
  if len(base.Audit.Inputs)!=len(base.Member.Channels){t.Errorf("%s incomplete ports: %d/%d",name,len(base.Audit.Inputs),len(base.Member.Channels))}
  // No extra control needed: compare this observer's baseline to the prior
  // reaction-observer capture to check zero-change semantic parity.
  var old capture;bytes,e:=os.ReadFile(filepath.Join(os.Getenv("GTT_PREVIOUS_INPUTS"),name+"-baseline.json"));if e!=nil{t.Fatal(e)}
  if e=json.Unmarshal(bytes,&old);e!=nil{t.Fatal(e)}
  before,e:=formula.EvaluateSeedMember(old.Member,nil);if e!=nil{t.Fatal(e)}
  if math.Abs(before.Damage-original.Damage)>1e-9*math.Max(1,before.Damage){t.Fatal("zero-change baseline mismatch")}
  rows=append(rows,map[string]any{"case":name,"ports":len(base.Audit.Inputs),"matched_inputs":n,"baseline_dps":original.Damage*scale,"predicted_dps":predicted,"fresh_dps":want,"relative_residual":residual,"evaluation_seconds":seconds,"new_engine_calls_in_replay":0})
 }
 raw,e=json.MarshalIndent(rows,"","  ");if e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(dir,"resistance-response-receipt.json"),raw,0600);e!=nil{t.Fatal(e)}
}

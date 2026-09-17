package seteffects

// Join source recipes and exact capture-bound ports. This produces proposal
// features only: no summed set DPS, pruning proof, simulation or chosen build.
import (
 "encoding/json"
 "os"
 "path/filepath"
	"sort"
 "testing"
 "time"
 "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
 "genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
 "genshinteamstracker/native/gcsim_optimizer/internal/allsets"
)

func TestJoinedGuideFeatures(t *testing.T){
 dir:=os.Getenv("GTT_GUIDE_CATALOG");out:=os.Getenv("GTT_GUIDE_OUTPUT")
 read:=func(path string,v any){t.Helper();b,e:=os.ReadFile(path);if e!=nil{t.Fatal(e)};if e=json.Unmarshal(b,v);e!=nil{t.Fatal(e)}}
 var manifest struct{Engine string `json:"engine_sha256"`;Stat,Attack,Element string;Items []struct{Key string}}
 // Explicit wire labels for the source manifest, not display-name guessing.
 var src struct{Stat string `json:"stat_source"`;Attack string `json:"attack_source"`;Element string `json:"element_source"`}
 read(filepath.Join(dir,"manifest.json"),&manifest);read(filepath.Join(dir,"manifest.json"),&src)
 stats,e:=StatVocabulary([]byte(src.Stat));if e!=nil{t.Fatal(e)}
 tags,e:=AttackTagVocabulary([]byte(src.Attack));if e!=nil{t.Fatal(e)}
 elements,e:=ElementVocabulary([]byte(src.Element));if e!=nil{t.Fatal(e)}
 var curves []ScalarSlice;read(filepath.Join(dir,"context-curves.json"),&curves)
 type source struct{Description Description `json:"description"`;Recipes []Recipe `json:"recipes"`}
 sources:=map[string]source{}
 for _,item:=range manifest.Items{var d source;read(filepath.Join(dir,item.Key+".json"),&d);sources[item.Key]=d}
 receipts:=[]any{}
 for _,name:=range []string{"bloom","cloud"}{
  var cap struct{
   Member contracts.IRSeedMember `json:"member"`
   Inputs []EffectInput `json:"inputs"`
   Owners []string `json:"owners"`
   Audit struct{Resistance []ResistanceInput `json:"resistance_inputs"`} `json:"audit"`
  }
  read(filepath.Join(os.Getenv("GTT_GUIDE_CAPTURES"),name+"-baseline.json"),&cap)
  sha,e:=contracts.CanonicalSHA256(cap.Member);if e!=nil{t.Fatal(e)}
  started:=time.Now()
  actors:=append([]string(nil),cap.Owners...);sort.Strings(actors)
  panel,e:=evaluator.CompileMembers(actors,[]uint64{cap.Member.Seed},[]contracts.IRSeedMember{cap.Member});if e!=nil{t.Fatal(e)}
  exposure,e:=NewExposureProbe(panel,[]contracts.IRSeedMember{cap.Member});if e!=nil{t.Fatal(e)}
  input,e:=NewInputProbe(cap.Member,cap.Owners,InputEnvelope{1,sha,cap.Inputs});if e!=nil{t.Fatal(e)}
  resistance,e:=NewResistanceProbe(cap.Member,cap.Owners,ResistanceEnvelope{1,sha,cap.Audit.Resistance},curves);if e!=nil{t.Fatal(e)}
  compileSeconds:=time.Since(started).Seconds();started=time.Now()
  rows:=[]any{};numeric:=map[string]int{};unresolved:=map[string]int{}
  hints:=map[allsets.HintKey]allsets.Hint{}
  for _,item:=range manifest.Items{
   src:=sources[item.Key];d:=src.Description
   for _,pieces:=range []int{2,4}{for _,wearer:=range cap.Owners{for _,r:=range src.Recipes{
    if d.TierApplicability(r.Effect,pieces)==Excluded{continue}
    key:=allsets.HintKey{Wearer:wearer,Set:item.Key,Pieces:pieces};h:=hints[key]
    h.Shared=h.Shared||r.RecipientScope=="team_iteration_member"||r.Effect.Kind=="resistance"
    h.NewOutput=h.NewOutput||r.Effect.Kind=="new_attack"
    h.Unresolved=h.Unresolved||len(r.Terms)==0
    if len(r.Terms)==0{unresolved[r.Effect.Kind]++}
    for i:=range r.Terms{
     var feature any;represented:=false;gain:=0.0
     switch r.Effect.Kind{
     case "reaction_bonus":
      f,e:=input.Feature(d,r,i,wearer,tags);if e!=nil{t.Fatal(e)};feature=f;represented=f.IncrementDPS!=nil;if represented{gain=*f.IncrementDPS}
     case "resistance":
      f,e:=resistance.Feature(r,i,elements);if e!=nil{t.Fatal(e)};feature=f;represented=f.IncrementDPS!=nil;if represented{gain=*f.IncrementDPS}
     default:
      f,e:=exposure.Feature(d,r,i,wearer,stats,tags);if e!=nil{t.Fatal(e)};feature=f;represented=f.RawStatProxyDPS!=nil;if represented{gain=*f.RawStatProxyDPS}
     }
     if represented{numeric[r.Effect.Kind]++}else{unresolved[r.Effect.Kind]++}
     group:=SharedModifierKey(r)
     if group!=""{if h.SharedGroups==nil{h.SharedGroups=map[string]float64{}};if gain>h.SharedGroups[group]{h.SharedGroups[group]=gain}}else if gain>h.PeakIncrement{h.PeakIncrement=gain}
     h.Unresolved=h.Unresolved||!represented
     rows=append(rows,map[string]any{"set":item.Key,"pieces":pieces,"wearer":wearer,"kind":r.Effect.Kind,"feature":feature})
    }
    hints[key]=h
   }}}
  }
  elapsed:=time.Since(started).Seconds()
  orderedHints:=[]any{}
  for _,item:=range manifest.Items{for _,pieces:=range []int{2,4}{for _,wearer:=range cap.Owners{key:=allsets.HintKey{Wearer:wearer,Set:item.Key,Pieces:pieces};h,ok:=hints[key];if !ok{h.Unresolved=true};orderedHints=append(orderedHints,map[string]any{"key":key,"hint":h})}}}
  hintBytes,e:=json.Marshal(orderedHints);if e!=nil{t.Fatal(e)}
  if e=os.WriteFile(filepath.Join(out,name+"-hints.json"),hintBytes,0600);e!=nil{t.Fatal(e)}
  b,e:=json.Marshal(rows);if e!=nil{t.Fatal(e)}
  if e=os.WriteFile(filepath.Join(out,name+"-joined-features.json"),b,0600);e!=nil{t.Fatal(e)}
  receipts=append(receipts,map[string]any{"case":name,"seed":cap.Member.Seed,"graph_sha256":sha,"features":len(rows),"numeric_features_by_kind":numeric,"unresolved_terms_by_kind":unresolved,"compile_seconds":compileSeconds,"feature_seconds":elapsed,"new_engine_calls":0,"status":"source_input_join_not_whole_set_or_activation_proof"})
 }
 b,e:=json.MarshalIndent(receipts,"","  ");if e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(out,"joined-guide-receipt.json"),b,0600);e!=nil{t.Fatal(e)}
}

package allsets

import (
 "context"
 "encoding/json"
 "os"
 "path/filepath"
 "strconv"
 "testing"
 "time"
 "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
 "genshinteamstracker/native/gcsim_optimizer/internal/domain"
 "genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func TestSavedAccountProposalQueue(t *testing.T){
 source,out:=os.Getenv("GTT_QUEUE_SOURCE"),os.Getenv("GTT_QUEUE_OUTPUT")
 read:=func(path string)[]byte{t.Helper();b,e:=os.ReadFile(path);if e!=nil{t.Fatal(e)};return b}
 req,e:=contracts.DecodeRequest(read(filepath.Join(source,"request.json")));if e!=nil{t.Fatal(e)}
 var manifest struct{Engine string `json:"engine_sha256"`;Items []struct{Key string;Four bool `json:"four_piece_modeled"`}}
 if e=json.Unmarshal(read(filepath.Join(os.Getenv("GTT_QUEUE_CATALOG"),"manifest.json")),&manifest);e!=nil{t.Fatal(e)}
 if manifest.Engine!=req.Engine.ArtifactSHA256{t.Fatal("engine/source identity mismatch")}
 var rows []struct{Key HintKey;Hint Hint}
 if e=json.Unmarshal(read(filepath.Join(os.Getenv("GTT_QUEUE_GUIDE"),"bloom-hints.json")),&rows);e!=nil{t.Fatal(e)}
 hints:=map[HintKey]Hint{};for _,r:=range rows{if _,ok:=hints[r.Key];ok{t.Fatal("duplicate hint")};hints[r.Key]=r.Hint}
 members:=[]contracts.IRSeedMember{};actors:=[]string{}
 for _,w:=range req.Wearers{actors=append(actors,w.WearerKey)}
 for _,seed:=range req.Stochastic.Seeds{m,e:=contracts.DecodeSeedMember(read(filepath.Join(source,"compact-member-"+strconv.FormatUint(seed,10)+".json")));if e!=nil{t.Fatal(e)};members=append(members,m)}
 panel,e:=evaluator.CompileMembers(actors,req.Stochastic.Seeds,members);if e!=nil{t.Fatal(e)}
 index,e:=domain.Build(req,panel.Coordinates());if e!=nil{t.Fatal(e)}
 catalog:=[]domain.SetCapability{};for _,item:=range manifest.Items{catalog=append(catalog,domain.SetCapability{UID:item.Key,TwoPiece:true,FourPiece:item.Four})}
 started:=time.Now();result,e:=Propose(context.Background(),index,panel,catalog,hints,16);if e!=nil{t.Fatal(e)}
 elapsed:=time.Since(started).Seconds()
 for _,p:=range result.Queue{t.Log(index.Wearers[p.Wearer].WearerKey,p.Package.Key(),p.Lane,p.RawContextDPS,p.Hint.PeakIncrement)}
 b,e:=json.MarshalIndent(map[string]any{"queue":result,"elapsed_seconds":elapsed,"new_engine_calls":0,"status":"bounded_proposal_only_not_replacement_or_search_acceptance","wearers":actors,"limit":16,"guide_seed_count":1,"raw_stat_panel_seeds":req.Stochastic.Seeds},"","  ");if e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(out,"proposal-queue.json"),b,0600);e!=nil{t.Fatal(e)}
}

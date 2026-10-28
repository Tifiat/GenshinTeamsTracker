package allsets

import (
 "context"
 "encoding/json"
 "math"
 "os"
 "path/filepath"
 "reflect"
 "strconv"
 "strings"
 "testing"
 "time"
 "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
 "genshinteamstracker/native/gcsim_optimizer/internal/domain"
 "genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
 "genshinteamstracker/native/gcsim_optimizer/internal/finalists"
 "genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

func TestAutomaticQueueWinnerResponse(t *testing.T){
 read:=func(path string)[]byte{t.Helper();b,e:=os.ReadFile(path);if e!=nil{t.Fatal(e)};return b}
 req,e:=contracts.DecodeRequest(read(filepath.Join(os.Getenv("GTT_QUEUE_SOURCE"),"request.json")));if e!=nil{t.Fatal(e)}
 var report struct{Rows []struct{Wearer,Package string;Winner domain.Assignment;DPS float64 `json:"winner_formula_dps"`}}
 if e=json.Unmarshal(read(os.Getenv("GTT_QUEUE_RECEIPT")),&report);e!=nil{t.Fatal(e)}
 if len(report.Rows)!=4{t.Fatal("expected exactly four proposals")};best:=report.Rows[0]
 for _,row:=range report.Rows{if row.DPS>best.DPS{best=row}}
 if len(req.Stochastic.Seeds)!=2{t.Fatal("two controls required")}
 var catalog struct{Catalog string `json:"catalog_sha256"`};if e=json.Unmarshal(read(filepath.Join(os.Getenv("GTT_QUEUE_CATALOG"),"manifest.json")),&catalog);e!=nil{t.Fatal(e)}
 refs:=[]string{};for _,line:=range strings.Split(req.Context.PreparedConfig.Text,"\n"){if strings.Contains(line," add stats "){refs=append(refs,line)}}
 binding:=setcontext.Binding{Engine:req.Engine,CatalogSHA256:catalog.Catalog,ReferenceStatsSHA256:contracts.TextSHA256(strings.Join(refs,"\n")),Seeds:req.Stochastic.Seeds}
 base,e:=setcontext.New(binding,req.Context.PreparedConfig.Text);if e!=nil{t.Fatal(e)}
 index,e:=domain.Build(req,nil);if e!=nil{t.Fatal(e)}
 var packages [4]domain.Package;actor:=-1
 for i,w:=range index.Wearers{packages[i]=domain.Package{Sets:w.SelectedSets};if w.WearerKey==best.Wearer{actor=i}}
 if actor<0{t.Fatal("unknown winner wearer")}
 p:=domain.Package{}
 for _,s:=range strings.Split(best.Package,"+"){v:=strings.Split(s,":");if len(v)!=2{t.Fatal("bad package")};n,e:=strconv.Atoi(v[1]);if e!=nil{t.Fatal(e)};p.Sets=append(p.Sets,contracts.SetRequirement{SetUID:v[0],Count:n})}
 packages[actor]=p
 view,e:=index.ForPackages(packages,best.Winner,nil);if e!=nil{t.Fatal(e)}
 counts,e:=view.SelectedSetCounts(best.Winner);if e!=nil{t.Fatal(e)}
 sets:=[]setcontext.Set{};for _,s:=range counts[actor]{sets=append(sets,setcontext.Set{UID:s.SetUID,Count:s.Count})}
 target,e:=base.Replace(map[string][]setcontext.Set{best.Wearer:sets});if e!=nil{t.Fatal(e)}
 renderReq:=req;renderReq.Context.PreparedConfig.Text=target.Config();renderReq.Wearers=append([]contracts.Wearer(nil),req.Wearers...)
 for i:=range renderReq.Wearers{renderReq.Wearers[i].SelectedSetUID="";renderReq.Wearers[i].SelectedSets=packages[i].Sets}
 rendered,e:=finalists.RenderConfig(renderReq,view,best.Winner,1,1);if e!=nil{t.Fatal(e)}
 if !reflect.DeepEqual(base.Actors(),target.Actors()){t.Fatal("initialization order changed")}
 bound,e:=engineclient.BindEngine(req);if e!=nil{t.Fatal(e)};defer func(){if e:=bound.VerifyUnchanged();e!=nil{t.Error(e)}}()
 if !strings.Contains(rendered.Text,"ignore_burst_energy=true"){t.Fatal("fixture no longer infinite-energy")}
 output:=os.Getenv("GTT_QUEUE_OUTPUT");ctx,cancel:=context.WithTimeout(context.Background(),60*time.Second);defer cancel()
 start:=time.Now();actual:=0.0
 for _,seed:=range req.Stochastic.Seeds{
  cap,e:=bound.RunCompact(ctx,rendered.Text,filepath.Join(output,"winner-"+strconv.FormatUint(seed,10)),seed,true);if e!=nil{t.Fatal(e)}
  total:=0.0;for _,ch:=range cap.Member.Channels{value,e:=strconv.ParseFloat(ch.BaselineDamage,64);if e!=nil{t.Fatal(e)};total+=value}
  actual+=total*1000/float64(cap.Member.DurationMS)/2
 }
 residual:=math.Abs(actual-best.DPS)/math.Max(1,math.Abs(actual))
 receipt:=map[string]any{"wearer":best.Wearer,"package":best.Package,"formula_dps":best.DPS,"fresh_expected_dps":actual,"relative_residual":residual,"new_engine_calls":2,"wall_seconds":time.Since(start).Seconds(),"ordinary_measurement":false}
 b,e:=json.MarshalIndent(receipt,"","  ");if e!=nil{t.Fatal(e)};if e=os.WriteFile(filepath.Join(output,"winner-response-receipt.json"),b,0600);e!=nil{t.Fatal(e)}
 t.Log(best.Wearer,best.Package,best.DPS,actual,residual)
 if residual>1e-9{t.Fatalf("candidate response differs; investigate before acceptance")}
}

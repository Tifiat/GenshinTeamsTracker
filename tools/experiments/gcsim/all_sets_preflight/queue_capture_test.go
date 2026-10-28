package allsets

import (
 "context"
 "encoding/json"
 "os"
 "path/filepath"
 "strconv"
 "strings"
 "testing"
 "time"
 "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
 "genshinteamstracker/native/gcsim_optimizer/internal/domain"
 "genshinteamstracker/native/gcsim_optimizer/internal/search"
 "genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

// Exactly four automatically proposed changed contexts x two seeds. Saved
// baseline members are replayed. No per-artifact or ordinary simulations.
func TestFourAutomaticPackageCaptures(t *testing.T){
 source,out:=os.Getenv("GTT_QUEUE_SOURCE"),os.Getenv("GTT_QUEUE_OUTPUT")
 read:=func(path string)[]byte{t.Helper();b,e:=os.ReadFile(path);if e!=nil{t.Fatal(e)};return b}
 req,e:=contracts.DecodeRequest(read(filepath.Join(source,"request.json")));if e!=nil{t.Fatal(e)}
 var proposal struct{Queue ProposalReport}
 if e=json.Unmarshal(read(os.Getenv("GTT_QUEUE_RECEIPT")),&proposal);e!=nil{t.Fatal(e)}
 if len(proposal.Queue.Queue)<4 || len(req.Stochastic.Seeds)!=2{t.Fatal("fixed capture budget input changed")}
 var manifest struct{Engine string `json:"engine_sha256"`;Catalog string `json:"catalog_sha256"`}
 if e=json.Unmarshal(read(filepath.Join(os.Getenv("GTT_QUEUE_CATALOG"),"manifest.json")),&manifest);e!=nil{t.Fatal(e)}
 if manifest.Engine!=req.Engine.ArtifactSHA256{t.Fatal("engine binding changed")}
 original:=string(read(filepath.Join(source,"prepared-config.txt")))
 if original!=req.Context.PreparedConfig.Text{t.Fatal("config binding changed")}
 refs:=[]string{};for _,line:=range strings.Split(original,"\n"){if strings.Contains(line," add stats "){refs=append(refs,line)}}
 binding:=setcontext.Binding{Engine:req.Engine,CatalogSHA256:manifest.Catalog,ReferenceStatsSHA256:contracts.TextSHA256(strings.Join(refs,"\n")),Seeds:req.Stochastic.Seeds}
 base,e:=setcontext.New(binding,original);if e!=nil{t.Fatal(e)}
 provider,e:=setcontext.NewEngineProvider(binding,out);if e!=nil{t.Fatal(e)};defer provider.Close()
 newCalls:=0;timings:=[]float64{}
 session,e:=setcontext.NewSession(func(ctx context.Context,c *setcontext.Context)(setcontext.Capture,error){
  if c.Key()!=base.Key(){newCalls+=2;start:=time.Now();cap,e:=provider.Capture(ctx,c);timings=append(timings,time.Since(start).Seconds());return cap,e}
  capture:=setcontext.Capture{ContextSHA256:c.Key(),ConfigSHA256:c.ConfigSHA256(),EngineBindingSHA256:req.Engine.BindingSHA256}
  for _,seed:=range binding.Seeds{
   suffix:=strconv.FormatUint(seed,10)
   var saved struct{ContextSHA string `json:"context_sha256"`;Seed string}
   if e:=json.Unmarshal(read(filepath.Join(source,"compact-request-"+suffix+".json")),&saved);e!=nil{return capture,e}
   if saved.ContextSHA!=req.Context.TraceContextSHA256 || saved.Seed!=suffix{t.Fatal("saved capture binding changed")}
   m,e:=contracts.DecodeSeedMember(read(filepath.Join(source,"compact-member-"+suffix+".json")));if e!=nil{return capture,e};capture.Members=append(capture.Members,m)
  };return capture,nil
 },10);if e!=nil{t.Fatal(e)}
 ctx,cancel:=context.WithTimeout(context.Background(),150*time.Second);defer cancel()
 baseline,e:=session.Resolve(ctx,base,nil,nil);if e!=nil{t.Fatal(e)}
 panel,e:=baseline.SearchPanel();if e!=nil{t.Fatal(e)}
 index,e:=domain.Build(req,panel.Coordinates());if e!=nil{t.Fatal(e)}
 cfg:=search.DefaultConfig();cfg.MaxExpandedPerActor=1000
 start:=time.Now();rows,e:=Refine(ctx,index,base,baseline,session,proposal.Queue.Queue[:4],cfg);if e!=nil{t.Fatal(e)}
 total:=time.Since(start).Seconds()
 result:=[]any{}
 for _,row:=range rows{
  best:=row.Step.Finalists[0];for _,f:=range row.Step.Finalists{if f.DPS>best.DPS{best=f}}
  result=append(result,map[string]any{"wearer":index.Wearers[row.Proposal.Wearer].WearerKey,"package":row.Proposal.Package.Key(),"priority_not_candidate_dps":row.Proposal.Priority,"winner_formula_dps":best.DPS,"winner":best.Assignment,"context_sha256":row.Context.Key(),"expanded":row.Step.Expanded})
  t.Log(index.Wearers[row.Proposal.Wearer].WearerKey,row.Proposal.Package.Key(),best.DPS)
 }
 b,e:=json.MarshalIndent(map[string]any{"new_engine_calls":newCalls,"provider_seconds":timings,"refine_total_seconds":total,"baseline_dps":panel.Baseline().MeanDPS,"rows":result,"ordinary_finalist_calls":0,"candidate_stat_response_controls":0,"status":"automatic_queue_own_context_refinement_not_quality_acceptance"},"","  ");if e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(out,"automatic-capture-receipt.json"),b,0600);e!=nil{t.Fatal(e)}
 if newCalls!=8{t.Fatal("unexpected capture budget",newCalls)}
}

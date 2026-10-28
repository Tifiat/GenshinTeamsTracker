// Added only to one leased frozen target; no production body is edited.
package main

import (
 "context"
 "crypto/rand"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "os"
 "path/filepath"
 "reflect"
 "testing"
 "time"

 "genshinteamstracker/native/gcsim_optimizer/internal/contracts"
 "genshinteamstracker/native/gcsim_optimizer/internal/domain"
 "genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
 "genshinteamstracker/native/gcsim_optimizer/internal/finalists"
 "genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
 "genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
 alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
 "genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
)

type s16Setup struct {
 raw, req contracts.OptimizerRequest
 sources *seteffects.SourceCatalog
 cfg theorysearch.Config
 rawSHA, sourceSHA string
 baseline alloc.State
}
type s16Case struct {
 ID string
 Packages [4]domain.Package
 Mains [4][5]string
 Unlocked [4][5]bool
}
type s16Row struct {
 Case s16Case `json:"case"`
 Status string `json:"status"`
 Family string `json:"family,omitempty"`
 ContextSHA string `json:"context_sha256,omitempty"`
 Uncertainty []string `json:"uncertainty"`
 Search alloc.ConstrainedResult `json:"search"`
 SearchSeconds float64 `json:"search_seconds"`
 SelectedConfigSHA string `json:"selected_config_sha256,omitempty"`
 InvariantSHA string `json:"invariant_sha256,omitempty"`
 MutableRows []string `json:"mutable_rows,omitempty"`
 Failure string `json:"failure,omitempty"`
}
func s16Bytes(v any) []byte { b,e:=json.Marshal(v);if e!=nil{panic(e)};return b }
func s16SHA(v any) string { return contracts.TextSHA256(string(s16Bytes(v))) }
func s16Emit(v any) { fmt.Println("STAGE16_RECEIPT "+string(s16Bytes(v))) }
func s16Write(root,name string,v any) error {
 if root==""||filepath.Base(name)!=name{return fmt.Errorf("invalid Stage16 export")}
 return os.WriteFile(filepath.Join(root,name),append(s16Bytes(v),'\n'),0600)
}
func s16Cases() []s16Case {
 mains := [4][5]string{
  {"hp","atk","def_percent","geo_damage_bonus","crit_damage"},
  {"hp","atk","hp_percent","hp_percent","crit_damage"},
  {"hp","atk","hp_percent","hydro_damage_bonus","crit_damage"},
  {"hp","atk","def_percent","geo_damage_bonus","crit_rate"},
 }
 sets := [4]string{"huskofopulentdreams","archaicpetra","goldentroupe","scrolloftheheroofcindercity"}
 out:=make([]s16Case,0,6)
 for _,id:=range []string{"B","F","C","FC","A","S"} {
  row:=s16Case{ID:id,Mains:mains}
  current:=sets
  switch id{
  case "F":row.Mains[2][3]="hp_percent"
  case "C":row.Mains[0][3]="def_percent"
  case "FC":row.Mains[2][3]="hp_percent";row.Mains[0][3]="def_percent"
  case "A":current[1]="aubadeofmorningstarandmoon"
  case "S":current[1]="silkenmoonsserenade"
  }
  if id=="A"||id=="S"{row.Unlocked[1][2]=true;row.Unlocked[1][3]=true;row.Unlocked[1][4]=true}
  for a,key:=range current{row.Packages[a]=domain.Package{Sets:[]contracts.SetRequirement{{SetUID:key,Count:4}}}}
  out=append(out,row)
 }
 return out
}
func s16Prepare() (p s16Setup,err error) {
 p.raw,p.req,p.sources,err=readTheorySetSources(os.Getenv("GTT_STAGE16_REQUEST"),os.Getenv("GTT_STAGE16_SOURCES"))
 if err!=nil{return p,err}
 p.rawSHA,err=contracts.CanonicalSHA256(p.raw);if err!=nil{return p,err}
 source,err:=os.ReadFile(os.Getenv("GTT_STAGE16_SOURCES"));if err!=nil{return p,err}
 p.sourceSHA=contracts.TextSHA256(string(source))
 p.cfg,err=theorySessionConfig(p.raw,p.req,p.sources,p.rawSHA,p.sourceSHA,"preparation","stage16-preflight");if err!=nil{return p,err}
 if p.cfg.Wearers!=[4]string{"chiori","columbina","furina","xilonen"}||!reflect.DeepEqual(p.req.Stochastic.Seeds,[]uint64{742031889,742031890})||p.req.Budgets.ProductTimeoutMS!=0{return p,fmt.Errorf("Stage16 input order/seeds/deadline changed")}
 for a,rows:=range p.cfg.Domains{if len(rows)!=946||!reflect.DeepEqual(rows,p.cfg.Domains[0])||len(p.cfg.Original[a].Sets)!=0{return p,fmt.Errorf("Stage16 default domain/start changed")}}
 saved,err:=os.ReadFile(os.Getenv("GTT_STAGE16_BASELINE"));if err!=nil{return p,err}
 if err=json.Unmarshal(saved,&p.baseline);err!=nil{return p,err}
 if err=alloc.ValidateFull45(p.baseline);err!=nil{return p,err}
 if p.baseline.Mains!=s16Cases()[0].Mains{return p,fmt.Errorf("archived B mains changed")}
 bound,err:=engineclient.BindEngine(p.req);if err!=nil{return p,err};return p,bound.VerifyUnchanged()
}
func s16Replace(base *setcontext.Context,wearers [4]string,packages [4]domain.Package)(*setcontext.Context,error){
 changes:=map[string][]setcontext.Set{}
 for a,wearer:=range wearers{for _,s:=range packages[a].Sets{changes[wearer]=append(changes[wearer],setcontext.Set{UID:s.SetUID,Count:s.Count})}}
 return base.Replace(changes)
}
func TestStage16PreparedInputs(t *testing.T){
 if os.Getenv("GTT_STAGE16_REQUEST")==""{t.Skip("explicit leased preparation required")}
 p,e:=s16Prepare();if e!=nil{t.Fatal(e)}
 binding:=setcontext.Binding{Engine:p.req.Engine,CatalogSHA256:p.sources.CatalogSHA256,ReferenceStatsSHA256:p.rawSHA,Seeds:p.req.Stochastic.Seeds}
 base,e:=setcontext.New(binding,p.req.Context.PreparedConfig.Text);if e!=nil{t.Fatal(e)}
 invariant,e:=finalists.Stage16Invariant(base.Config(),p.cfg.Wearers);if e!=nil{t.Fatal(e)}
 for _,c:=range s16Cases(){
  target,e:=s16Replace(base,p.cfg.Wearers,c.Packages);if e!=nil{t.Fatal(e)}
  state:=alloc.Seed(c.Mains,[4][10]float64{},0,45)
  rendered,e:=finalists.RenderStage16(target.Config(),p.cfg.Wearers,state);if e!=nil{t.Fatal(e)}
  got,e:=finalists.Stage16Invariant(rendered.Text,p.cfg.Wearers);if e!=nil||got!=invariant{t.Fatalf("case%s changes input remainder: %s/%s/%v",c.ID,got,invariant,e)}
 }
 s16Emit(map[string]any{"kind":"native_input_preflight","engine_calls":0,"request_sha256":p.rawSHA,"source_sha256":p.sourceSHA,"source_catalog_sha256":p.sources.CatalogSHA256,"engine":p.req.Engine,"seeds":p.req.Stochastic.Seeds,"cases":s16Cases(),"input_invariant_sha256":invariant,"baseline_witness_sha256":s16SHA(p.baseline)})
}
func TestStage16SixControls(t *testing.T){
 if os.Getenv("GTT_STAGE16_RUN")!="authorized-one-universe-six-controls"{t.Skip("one authorized managed study required")}
 p,e:=s16Prepare();if e!=nil{t.Fatal(e)}
 root:=os.Getenv("GTT_STAGE16_ROOT");public:=filepath.Join(root,"public")
 if e=os.MkdirAll(public,0700);e!=nil{t.Fatal(e)}
 binding:=setcontext.Binding{Engine:p.req.Engine,CatalogSHA256:p.sources.CatalogSHA256,ReferenceStatsSHA256:p.rawSHA,Seeds:p.req.Stochastic.Seeds}
 base,e:=setcontext.New(binding,p.req.Context.PreparedConfig.Text);if e!=nil{t.Fatal(e)}
 empty:=map[string][]setcontext.Set{};for _,w:=range p.req.Wearers{empty[w.WearerKey]=nil}
 base,e=base.Replace(empty);if e!=nil{t.Fatal(e)}
 invariant,e:=finalists.Stage16Invariant(base.Config(),p.cfg.Wearers);if e!=nil{t.Fatal(e)}
 caproot:=filepath.Join(root,"capture");if e=os.Mkdir(caproot,0700);e!=nil{t.Fatal(e)}
 provider,e:=setcontext.NewEffectEngineProvider(binding,caproot);if e!=nil{t.Fatal(e)};defer provider.Close()
 capture,e:=setcontext.NewSession(provider.Capture,2);if e!=nil{t.Fatal(e)}
 var nonce [16]byte;if _,e=rand.Read(nonce[:]);e!=nil{t.Fatal(e)}
 outerStarted:=time.Now();outer,stop:=context.WithTimeout(context.Background(),900*time.Second);defer stop()
 var resolver *theorysearch.Stage15Resolver
 rows:=[]s16Row{};diagnostics:=[]map[string]any{}
 clocks:=map[string]float64{};status,failure:="FAIL","";graphSHA:="";ordinaryAttempts:=0
 defer func(){
  var work theorysearch.Stage15Totals
  if resolver!=nil{work=resolver.Totals();resolver.Close()}
  clocks["outer_native"]=time.Since(outerStarted).Seconds()
  ledger:=map[string]any{"kind":"study_ledger","status":status,"failure":failure,"capture_attempts":capture.AttemptedCaptureMembers(),"capture_budget":2,"universes":1,"ordinary_diagnostic_attempts":ordinaryAttempts,"ordinary_budget":12,"capture_timings":provider.Timings(),"clocks_seconds":clocks,"work":work,"request_sha256":p.rawSHA,"source_sha256":p.sourceSHA,"source_catalog_sha256":p.sources.CatalogSHA256,"model_graph_sha256":graphSHA,"cases_completed":len(rows),"diagnostics":diagnostics}
  _=s16Write(public,"study-ledger.json",ledger);s16Emit(ledger)
 }()
 fail:=func(err error){failure=err.Error();t.Fatal(err)}
 // Reserving both possible attempts survives a hard process failure.
 if e=s16Write(public,"capture-call-ledger.json",map[string]any{"maximum":2,"seeds":p.req.Stochastic.Seeds,"universe_maximum":1,"reserved":2,"attempts_including_failures":true});e!=nil{fail(e)}
 s16Emit(map[string]any{"kind":"capture_enter","reserved_maximum":2,"universes":1})
 started:=time.Now();captured,e:=capture.Resolve(outer,base,nil,nil);clocks["capture"]=time.Since(started).Seconds();if e!=nil{fail(e)}
 if capture.AttemptedCaptureMembers()!=2{fail(fmt.Errorf("capture count differs from2"))}
 graphSHA=captured.GraphSHA256();if e=provider.Close();e!=nil{fail(e)}
 p.cfg,e=theorySessionConfig(p.raw,p.req,p.sources,p.rawSHA,p.sourceSHA,graphSHA,hex.EncodeToString(nonce[:]));if e!=nil{fail(e)}
 offlineStarted:=time.Now();deadline:=offlineStarted.Add(480*time.Second)
 searchCtx,endSearch:=context.WithDeadline(outer,deadline);defer endSearch()
 started=time.Now();model,e:=setcontext.NewNeutralModel(captured,p.sources);if e!=nil{fail(e)}
 world,e:=theorysearch.NewFormulaWorld(p.req,base,model,p.cfg.Binding);clocks["cold_model"]=time.Since(started).Seconds();if e!=nil{fail(e)}
 resolver,e=theorysearch.NewStage15Resolver(world,deadline,946);if e!=nil{fail(e)}
 configs:=map[string]string{}
 for _,c:=range s16Cases(){
  row:=s16Row{Case:c,Status:"UNAVAILABLE"}
  started=time.Now();entry,codes,resolveErr:=resolver.Resolve(searchCtx,c.Packages);row.Uncertainty=codes
  if resolveErr!=nil{row.Status="FAILED";row.Failure=resolveErr.Error();rows=append(rows,row);break}
  if entry==nil{row.SearchSeconds=time.Since(started).Seconds();rows=append(rows,row);continue}
  row.Family,row.ContextSHA,row.Uncertainty=entry.Family,entry.ContextSHA256,entry.Uncertainty
  result,searchErr:=alloc.RunConstrained(searchCtx,entry.Objective,p.baseline,c.Mains,c.Unlocked)
  row.Search,row.SearchSeconds=result,time.Since(started).Seconds()
  if searchErr!=nil{row.Status="FAILED";row.Failure=searchErr.Error();rows=append(rows,row);break}
  if e=alloc.ValidateFull45(result.State);e!=nil{fail(e)}
  for a:=range result.State.Mains{for slot,main:=range result.State.Mains[a]{if !c.Unlocked[a][slot]&&main!=c.Mains[a][slot]{fail(fmt.Errorf("case%s escaped fixed main",c.ID))}}}
  target,err:=s16Replace(base,p.cfg.Wearers,c.Packages);if err!=nil{fail(err)}
  rendered,err:=finalists.RenderStage16(target.Config(),p.cfg.Wearers,result.State);if err!=nil{fail(err)}
  row.InvariantSHA,err=finalists.Stage16Invariant(rendered.Text,p.cfg.Wearers);if err!=nil||row.InvariantSHA!=invariant{fail(fmt.Errorf("selected case%s changed input remainder",c.ID))}
  row.SelectedConfigSHA=rendered.SHA256;row.Status="COMPLETE"
  configs[c.ID]=rendered.Text
  // This config contains only public virtual profiles/rotation and artifact stats.
  for _,line:=range splitStage16Lines(rendered.Text){if isStage16Mutable(line,p.cfg.Wearers){row.MutableRows=append(row.MutableRows,line)}}
  rows=append(rows,row)
  s16Emit(map[string]any{"kind":"case_completed","case":c.ID,"value":result.Value,"fixed_main_value":result.FixedMainsValue,"seconds":row.SearchSeconds,"formula":resolver.Totals().Formula})
  if e=s16Write(public,"comparison.json",map[string]any{"schema_kind":"gtt_theory_goblet_controls_comparison_v1","cases":rows,"wearers":p.cfg.Wearers,"archived_reference":145991.01064839284,"input_invariant_sha256":invariant,"all_candidates_frozen":false});e!=nil{fail(e)}
 }
 all:=len(rows)==6;for _,row:=range rows{if row.Status!="COMPLETE"{all=false}}
 if e=s16Write(public,"comparison.json",map[string]any{"schema_kind":"gtt_theory_goblet_controls_comparison_v1","cases":rows,"wearers":p.cfg.Wearers,"archived_reference":145991.01064839284,"input_invariant_sha256":invariant,"all_candidates_frozen":all});e!=nil{fail(e)}
 clocks["offline_native"]=time.Since(offlineStarted).Seconds()
 resolver.Close()
 if clocks["offline_native"]>480||searchCtx.Err()!=nil{fail(fmt.Errorf("shared offline guard exhausted; partial retained"))}
 if !all{fail(fmt.Errorf("six-case offline result incomplete; no diagnostic panel"))}
 plan:=[]map[string]any{}
 for _,row:=range rows{plan=append(plan,map[string]any{"case":row.Case.ID,"config_sha256":row.SelectedConfigSHA,"witness_sha256":s16SHA(row.Search.State),"invariant_sha256":row.InvariantSHA})}
 if e=s16Write(public,"diagnostic-plan.json",map[string]any{"cases":plan,"seeds":p.req.Stochastic.Seeds,"maximum":12,"iterations_per_member":1,"candidates_frozen":true});e!=nil{fail(e)}
 bound,e:=engineclient.BindEngine(p.req);if e!=nil{fail(e)}
 started=time.Now()
 for _,row:=range rows{for _,seed:=range p.req.Stochastic.Seeds{
  if ordinaryAttempts>=12{fail(fmt.Errorf("ordinary diagnostic hard cap"))}
  if e=outer.Err();e!=nil{fail(e)}
  ordinaryAttempts++
  name:=fmt.Sprintf("diagnostic-entry-%s-%d.json",row.Case.ID,seed)
  if e=s16Write(public,name,map[string]any{"case":row.Case.ID,"seed":seed,"attempt":ordinaryAttempts,"iterations":1,"workers":1,"config_sha256":row.SelectedConfigSHA,"mode":"seeded_actual_raw_trace","timestamp":time.Now().UTC().Format(time.RFC3339Nano)});e!=nil{fail(e)}
  measured,err:=bound.RunStage16Diagnostic(outer,configs[row.Case.ID],filepath.Join(root,fmt.Sprintf("ordinary-%s-%d",row.Case.ID,seed)),seed)
  if err==nil&&!reflect.DeepEqual(measured.CharacterKeys,base.Actors()){err=fmt.Errorf("diagnostic changed actor declaration order")}
  record:=map[string]any{"case":row.Case.ID,"seed":seed,"attempt":ordinaryAttempts,"result":measured,"status":"PASS"}
  if err!=nil{record["status"]="FAIL";record["failure"]=err.Error()}
  diagnostics=append(diagnostics,record)
  if e=s16Write(public,"diagnostic-results.json",diagnostics);e!=nil{fail(e)}
  s16Emit(map[string]any{"kind":"diagnostic_completed","case":row.Case.ID,"seed":seed,"attempt":ordinaryAttempts,"status":record["status"]})
  if err!=nil{fail(err)}
 }}
 clocks["ordinary_panel"]=time.Since(started).Seconds()
 if e=bound.VerifyUnchanged();e!=nil{fail(e)}
 if outer.Err()!=nil{fail(outer.Err())}
 status="PASS_SIX_CONTROLS_ONE_UNIVERSE"
}


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
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestTwoJointContextCaptures(t *testing.T){
	root,guideDir,captureDir,out:=os.Getenv("GTT_TRANSFER_ROOT"),os.Getenv("GTT_TRANSFER_GUIDE"),os.Getenv("GTT_TRANSFER_CAPTURE"),os.Getenv("GTT_TRANSFER_OUTPUT")
	read:=func(path string)[]byte{b,e:=os.ReadFile(path);if e!=nil{t.Fatal(e)};return b}
	decode:=func(path string,value any){if e:=json.Unmarshal(read(path),value);e!=nil{t.Fatal(e)}}
	var engine contracts.EngineBinding;decode(filepath.Join(guideDir,"engine.json"),&engine)
	var bundle seteffects.SourceBundle;decode(filepath.Join(guideDir,"sources.json"),&bundle)
	sources,e:=seteffects.CompileSourceBundle(bundle,engine,bundle.CatalogSHA256);if e!=nil{t.Fatal(e)}
	raw:=read(filepath.Join(root,".codex_tmp/selected-2plus2-20260916/run/request.json"));req,e:=contracts.DecodeRequest(raw);if e!=nil{t.Fatal(e)}
	config:=string(read(filepath.Join(captureDir,"bloom/config.txt")))
	firstRaw:=read(filepath.Join(captureDir,"bloom/member.json"));first,e:=contracts.DecodeSeedMember(firstRaw);if e!=nil{t.Fatal(e)}
	var effects contracts.EffectInputsOutput;decode(filepath.Join(captureDir,"bloom/member.json.effects.json"),&effects)
	if effects.MemberContentSHA256!=contracts.TextSHA256(string(firstRaw))||len(req.Stochastic.Seeds)!=2||req.Stochastic.Seeds[0]!=first.Seed{t.Fatal("saved baseline binding changed")}
	binding:=setcontext.Binding{Engine:engine,CatalogSHA256:bundle.CatalogSHA256,ReferenceStatsSHA256:contracts.TextSHA256(string(raw)),Seeds:req.Stochastic.Seeds}
	base,e:=setcontext.New(binding,config);if e!=nil{t.Fatal(e)}
	provider,e:=setcontext.NewEffectEngineProvider(binding,out);if e!=nil{t.Fatal(e)};defer func(){if e:=provider.Close();e!=nil{t.Error(e)}}()
	bound,e:=engineclient.BindEngine(contracts.OptimizerRequest{Engine:engine});if e!=nil{t.Fatal(e)}
	ctx,cancel:=context.WithTimeout(context.Background(),270*time.Second);defer cancel()
	newCalls:=0;baselineCaptureMS:=0.0
	session,e:=setcontext.NewSession(func(ctx context.Context,c *setcontext.Context)(setcontext.Capture,error){
		if c.Key()!=base.Key(){newCalls+=2;return provider.Capture(ctx,c)}
		cap:=setcontext.Capture{ContextSHA256:c.Key(),ConfigSHA256:c.ConfigSHA256(),EngineBindingSHA256:engine.BindingSHA256,Members:[]contracts.IRSeedMember{first},Effects:[]contracts.EffectInputsOutput{effects}}
		seed:=binding.Seeds[1];newCalls++
		result,e:=bound.RunCompactWithEffects(ctx,config,filepath.Join(out,"baseline-"+strconv.FormatUint(seed,10)),seed,true);if e!=nil{return cap,e}
		baselineCaptureMS=result.ProcessMS+result.DecodeMS
		cap.Members=append(cap.Members,result.Member);cap.Effects=append(cap.Effects,*result.Effects);return cap,nil
	},6);if e!=nil{t.Fatal(e)}
	started:=time.Now();handle,e:=session.Resolve(ctx,base,nil,nil);if e!=nil{t.Fatal(e)}
	panel,e:=handle.SearchPanel();if e!=nil{t.Fatal(e)};index,e:=domain.Build(req,panel.Coordinates());if e!=nil{t.Fatal(e)}
	cfg:=search.DefaultConfig();solver,e:=search.New(index,panel,cfg);if e!=nil{t.Fatal(e)}
	searchStart:=time.Now();selected,e:=solver.Run(ctx);if e!=nil{t.Fatal(e)};selectedSeconds:=time.Since(searchStart).Seconds()
	var packages [4]domain.Package;for i,w:=range index.Wearers{packages[i]=domain.Package{Sets:w.SelectedSets}}
	index,e=index.ForPackages(packages,selected.Leader.Assignment,panel.Coordinates());if e!=nil{t.Fatal(e)}
	guideStart:=time.Now();guide,e:=BuildGuide(ctx,index,handle,sources);if e!=nil{t.Fatal(e)}
	catalog:=[]domain.SetCapability{};for _,s:=range sources.Sets{catalog=append(catalog,domain.SetCapability{UID:s.Key,TwoPiece:true,FourPiece:s.FourPieceModeled})}
	proposals,e:=guide.ProposeTransfers(ctx,index,handle,catalog,2);if e!=nil{t.Fatal(e)};guideSeconds:=time.Since(guideStart).Seconds()
	if len(proposals.Queue)!=2{t.Fatal("fixed two-context pilot unavailable",len(proposals.Queue))}
	refineStart:=time.Now();rows,e:=RefineTransfers(ctx,index,base,handle,session,proposals.Queue,cfg);if e!=nil{t.Fatal(e)};refineSeconds:=time.Since(refineStart).Seconds()
	summaries:=[]any{};best:=selected.Leader.DPS
	for _,row:=range rows{
		leader:=row.Result.Leader
		if leader.DPS>best{best=leader.DPS}
		keys:=[]string{};for _,p:=range row.Proposal.Packages{keys=append(keys,p.Key())}
		summaries=append(summaries,map[string]any{"actors":row.Proposal.Actors,"packages":keys,"context_sha256":row.Context.Key(),"formula_dps":leader.DPS,"winner":leader.Assignment,"opaque_reasons":row.Result.OpaqueReasons})
		t.Log("joint",row.Proposal.Actors,keys,leader.DPS)
	}
	receipt:=map[string]any{"status":"two_joint_contexts_default_FGBS_comparison_not_ordinary_or_UI_acceptance","new_n1_calls":newCalls,"ordinary_calls":0,"seed_count":len(binding.Seeds),"selected_search_config":cfg,"selected_formula_dps":selected.Leader.DPS,"best_formula_dps":best,"baseline_capture_ms":baselineCaptureMS,"selected_search_seconds":selectedSeconds,"guide_seconds":guideSeconds,"joint_refine_seconds":refineSeconds,"total_seconds":time.Since(started).Seconds(),"provider_timings":provider.Timings(),"rows":summaries,"selected_winner":selected.Leader.Assignment}
	b,e:=json.MarshalIndent(receipt,"","  ");if e!=nil{t.Fatal(e)};if e=os.WriteFile(filepath.Join(out,"transfer-capture-receipt.json"),b,0600);e!=nil{t.Fatal(e)}
	if newCalls!=5{t.Fatal("unexpected engine budget",newCalls)}
}

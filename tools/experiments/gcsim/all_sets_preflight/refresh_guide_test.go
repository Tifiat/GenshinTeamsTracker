package allsets

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestBoundGuideRefresh(t *testing.T){
	root,out,capdir:=os.Getenv("GTT_REFRESH_ROOT"),os.Getenv("GTT_REFRESH_OUTPUT"),os.Getenv("GTT_REFRESH_CAPTURE")
	read:=func(path string,v any){b,e:=os.ReadFile(path);if e!=nil{t.Fatal(e)};if e=json.Unmarshal(b,v);e!=nil{t.Fatal(e)}}
	var bundle seteffects.SourceBundle;read(filepath.Join(out,"sources.json"),&bundle)
	var engine contracts.EngineBinding;read(filepath.Join(out,"engine.json"),&engine)
	started:=time.Now();sources,e:=seteffects.CompileSourceBundle(bundle,engine,bundle.CatalogSHA256);if e!=nil{t.Fatal(e)}
	sourceSeconds:=time.Since(started).Seconds()
	raw,e:=os.ReadFile(filepath.Join(root,".codex_tmp/selected-2plus2-20260916/run/request.json"));if e!=nil{t.Fatal(e)}
	req,e:=contracts.DecodeRequest(raw);if e!=nil{t.Fatal(e)}
	config,e:=os.ReadFile(filepath.Join(capdir,"bloom/config.txt"));if e!=nil{t.Fatal(e)}
	mraw,e:=os.ReadFile(filepath.Join(capdir,"bloom/member.json"));if e!=nil{t.Fatal(e)}
	member,e:=contracts.DecodeSeedMember(mraw);if e!=nil{t.Fatal(e)}
	var sidecar contracts.EffectInputsOutput;read(filepath.Join(capdir,"bloom/member.json.effects.json"),&sidecar)
	if sidecar.MemberContentSHA256!=contracts.TextSHA256(string(mraw)){t.Fatal("saved member changed")}
	c,e:=setcontext.New(setcontext.Binding{Engine:engine,CatalogSHA256:bundle.CatalogSHA256,ReferenceStatsSHA256:contracts.TextSHA256(string(raw)),Seeds:[]uint64{member.Seed}},string(config));if e!=nil{t.Fatal(e)}
	provider:=func(_ context.Context,target *setcontext.Context)(setcontext.Capture,error){return setcontext.Capture{ContextSHA256:target.Key(),ConfigSHA256:target.ConfigSHA256(),EngineBindingSHA256:engine.BindingSHA256,Members:[]contracts.IRSeedMember{member},Effects:[]contracts.EffectInputsOutput{sidecar}},nil}
	session,_:=setcontext.NewSession(provider,1);handle,e:=session.Resolve(context.Background(),c,nil,nil);if e!=nil{t.Fatal(e)}
	panel,e:=handle.SearchPanel();if e!=nil{t.Fatal(e)};index,e:=domain.Build(req,panel.Coordinates());if e!=nil{t.Fatal(e)}
	caps:=[]domain.SetCapability{};for _,s:=range sources.Sets{caps=append(caps,domain.SetCapability{UID:s.Key,TwoPiece:true,FourPiece:s.FourPieceModeled})}
	started=time.Now();guide,e:=BuildGuide(context.Background(),index,handle,sources);if e!=nil{t.Fatal(e)};guideSeconds:=time.Since(started).Seconds()
	queue,e:=guide.Propose(context.Background(),index,handle,caps,16);if e!=nil{t.Fatal(e)}
	started=time.Now();transfers,e:=guide.ProposeTransfers(context.Background(),index,handle,caps,8);if e!=nil{t.Fatal(e)};transferSeconds:=time.Since(started).Seconds()
	for _,p:=range transfers.Queue{
		view,e:=index.ForPackages(p.Packages,p.Seed,panel.Coordinates());if e!=nil{t.Fatal(e)}
		d,e:=view.DenseDeltas(p.Seed);if e!=nil{t.Fatal(e)};full,e:=panel.EvaluateDPS(d);if e!=nil||math.Abs(full-p.RawContextDPS)>1e-8{t.Fatal("wrong transfer counterfactual")}
		for actor:=0;actor<4;actor++{if actor!=p.Actors[0]&&actor!=p.Actors[1]&&p.Seed[actor]!=index.Incumbent[actor]{t.Fatal("transfer stole reserved IDs")}}
	}
	if len(transfers.Queue)==0{t.Fatal("no known shared opportunity transfer in real fixture")}
	transferBytes,e:=json.MarshalIndent(transfers,"","  ");if e!=nil{t.Fatal(e)};if e=os.WriteFile(filepath.Join(out,"transfer-proposals.json"),transferBytes,0600);e!=nil{t.Fatal(e)}
	cfg:=search.DefaultConfig();cfg.MaxExpandedPerActor=1000
	solver,e:=search.New(index,panel,cfg);if e!=nil{t.Fatal(e)}
	step,e:=solver.RefineWearer(context.Background(),index.Incumbent,0);if e!=nil{t.Fatal(e)}
	var packages [4]domain.Package;for i,w:=range index.Wearers{packages[i]=domain.Package{Sets:w.SelectedSets}}
	if len(step.Finalists)==0{t.Fatal("no item-refinement finalist")}
	changed,e:=index.ForPackages(packages,step.Finalists[0].Assignment,panel.Coordinates());if e!=nil{t.Fatal(e)}
	if changed.Incumbent==index.Incumbent{t.Fatal("test needs an actual changed legal artifact anchor")}
	if _,e=guide.Propose(context.Background(),changed,handle,caps,16);e==nil{t.Fatal("stale guide accepted")}
	started=time.Now();refreshed,e:=BuildGuide(context.Background(),changed,handle,sources);if e!=nil{t.Fatal(e)};refreshSeconds:=time.Since(started).Seconds()
	newQueue,e:=refreshed.Propose(context.Background(),changed,handle,caps,16);if e!=nil{t.Fatal(e)}
	for _,proposal:=range newQueue.Queue{
		pkg:=packages;pkg[proposal.Wearer]=proposal.Package
		view,e:=changed.ForPackages(pkg,proposal.Seed,panel.Coordinates());if e!=nil{t.Fatal(e)}
		delta,e:=view.DenseDeltas(proposal.Seed);if e!=nil{t.Fatal(e)}
		full,e:=panel.EvaluateDPS(delta);if e!=nil{t.Fatal(e)}
		if math.Abs(full-proposal.RawContextDPS)>1e-8*math.Max(1,math.Abs(full)){t.Fatal("refreshed queue lost unchanged actor stats",full,proposal.RawContextDPS)}
	}
	different:=0;for k,h:=range guide.hints{other:=refreshed.hints[k];if h.PeakIncrement!=other.PeakIncrement{different++}}
	if different==0{t.Fatal("real guide did not react to changed stats")}
	row:=map[string]any{"status":"source_bound_one_seed_offline_refresh_pass_not_full_product_acceptance","new_engine_calls":0,"source_discovery_seconds":sourceSeconds,"guide_seconds":guideSeconds,"refresh_seconds":refreshSeconds,"source_sets":len(sources.Sets),"features":guide.Features,"unresolved_features":guide.Unresolved,"queue_count":len(queue.Queue),"refreshed_queue_count":len(newQueue.Queue),"changed_hint_peaks":different,"stale_guide_rejected":true}
	row["status"]="source_bound_one_seed_offline_refresh_and_transfer_proposals_pass_not_full_product_acceptance"
	row["transfer_seconds"],row["transfer_count"],row["transfer_joint_seeds"],row["transfer_raw_evaluations"]=transferSeconds,len(transfers.Queue),transfers.JointSeeds,transfers.RawEvaluations
	b,e:=json.MarshalIndent(row,"","  ");if e!=nil{t.Fatal(e)};if e=os.WriteFile(filepath.Join(out,"refresh-guide-receipt.json"),b,0600);e!=nil{t.Fatal(e)}
}

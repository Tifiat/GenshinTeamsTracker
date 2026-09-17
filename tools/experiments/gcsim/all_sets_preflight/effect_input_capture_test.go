package optimization

// Explicit four-simulation research control: two fixed saved rotations, each
// unchanged and with one artificial +0.1 reaction-bonus modifier. No game rule
// is reimplemented; this tests exact read ownership and downstream arithmetic,
// NOT real-set activation, replacement or product search quality.
import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
	"github.com/genshinsim/gcsim/pkg/core/info"
	"github.com/genshinsim/gcsim/pkg/core/attributes"
	"github.com/genshinsim/gcsim/pkg/core/player/character"
	"github.com/genshinsim/gcsim/pkg/gcs/ast"
	"github.com/genshinsim/gcsim/pkg/gcs/eval"
	"github.com/genshinsim/gcsim/pkg/gcs/parser"
	"github.com/genshinsim/gcsim/pkg/gttcompact"
	"github.com/genshinsim/gcsim/pkg/modifier"
	"github.com/genshinsim/gcsim/pkg/optimization/optstats"
	"github.com/genshinsim/gcsim/pkg/simulation"
)

func TestEffectInputControlledCaptures(t *testing.T){
	var jobs []struct{Case,Config,Owner,Element string}
	data,e:=os.ReadFile(os.Getenv("GTT_EFFECT_JOBS"));if e!=nil{t.Fatal(e)}
	if e=json.Unmarshal(data,&jobs);e!=nil{t.Fatal(e)}
	if len(jobs)!=2{t.Fatal("budget requires exactly two controls")}
	out:=os.Getenv("GTT_EFFECT_INPUT_OUTPUT")
	rows:=[]any{}
	for _,job:=range jobs {
		content,e:=os.ReadFile(job.Config);if e!=nil{t.Fatal(e)}
		for _,mode:=range []string{"baseline","offset"}{
			started:=time.Now()
			file:=ast.NewFile();cfg,node,e:=parser.New(file,string(content)).Parse();if e!=nil{t.Fatal(e)}
			cfg.Settings.Iterations=1;cfg.Settings.NumberOfWorkers=1;cfg.Settings.IgnoreBurstEnergy=true;cfg.Settings.CollectStats=[]string{""}
			core,e:=simulation.NewCore(742031889,false,cfg);if e!=nil{t.Fatal(e)}
			optstats.PrepareOptimizerTraceEquation(core)
			ev,e:=eval.NewEvaluator(file,node,core);if e!=nil{t.Fatal(e)}
			sim,e:=simulation.New(cfg,ev,core);if e!=nil{t.Fatal(e)}
			found:=false
			keys:=[]string{}
			for _,ch:=range core.Player.Chars(){
				keys=append(keys,ch.Base.Key.String())
				if ch.Base.Key.String()!=job.Owner{continue};found=true
				if mode=="offset" && os.Getenv("GTT_EFFECT_CONTROL")!="resistance" {ch.AddReactBonusMod(character.ReactBonusMod{Base:modifier.NewBase("gtt-research-only-offset",-1),Amount:func(info.AttackInfo)float64{return .1}})}
			}
			if mode=="offset" && os.Getenv("GTT_EFFECT_CONTROL")=="resistance" {
				for _,target:=range core.Combat.Enemies(){
					enemy,ok:=target.(info.Enemy);if !ok{t.Fatal("control target is not enemy")}
					enemy.AddResistMod(info.ResistMod{Base:modifier.NewBase("gtt-research-resistance",1000000),Ele:attributes.StringToEle(job.Element),Value:-.3})
				}
			}
			if !found{t.Fatal("control owner not found")}
			collector,e:=optstats.OptimizerTraceEquation(core);if e!=nil{t.Fatal(e)}
			if _,e=sim.Run();e!=nil{t.Fatal(e)}
			buffer:=collector.Flush(core);buffer.Seed=742031889;buffer.DurationFrames=core.F
			member,audit,e:=gttcompact.CompileSeedMember(buffer,keys);if e!=nil{t.Fatal(e)}
			if len(audit.EffectInputs)==0{t.Fatal("read inputs not exported")}
			payload,e:=json.Marshal(map[string]any{"member":member,"inputs":audit.EffectInputs,"audit":audit,"owners":keys,"case":job.Case,"owner":job.Owner,"mode":mode,"element":job.Element})
			if e!=nil{t.Fatal(e)}
			if e=os.WriteFile(filepath.Join(out,job.Case+"-"+mode+".json"),payload,0600);e!=nil{t.Fatal(e)}
			rows=append(rows,map[string]any{"case":job.Case,"mode":mode,"hits":len(member.Channels),"inputs":len(audit.EffectInputs),"wall_seconds":time.Since(started).Seconds()})
			t.Log(job.Case,mode,len(member.Channels),"hits",len(audit.EffectInputs),"inputs")
		}
	}
	data,e=json.MarshalIndent(rows,"","  ");if e!=nil{t.Fatal(e)}
	if e=os.WriteFile(filepath.Join(out,"capture-receipt.json"),data,0600);e!=nil{t.Fatal(e)}
}

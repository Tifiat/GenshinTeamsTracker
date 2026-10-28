package engineclient

// Two opt-in n1 calls through the real binary/client. No ordinary validation,
// account writes or installation. Compare the retained research graphs and
// exercise the typed sidecar all the way into the existing neutral probes.
import (
	"context"
	"encoding/json"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestObserverCandidateTransportParity(t *testing.T){
	root:=os.Getenv("GTT_OBSERVER_ROOT");source:=os.Getenv("GTT_OBSERVER_SOURCE");out:=os.Getenv("GTT_OBSERVER_OUTPUT")
	if root==""||source==""||out==""{t.Skip("explicit isolated inputs required")}
	binary:=filepath.Join(source,"build/gtt-gcsim.exe")
	bytes,e:=os.ReadFile(binary);if e!=nil{t.Fatal(e)}
	infoBytes,e:=exec.Command(binary,"-gtt-info").Output();if e!=nil{t.Fatal(e)}
	var info struct{Capabilities []string `json:"capabilities"`;SourceSHA string `json:"source_manifest_body_sha256"`}
	if e=json.Unmarshal(infoBytes,&info);e!=nil{t.Fatal(e)}
	bound,e:=BindEngine(contracts.OptimizerRequest{Engine:contracts.EngineBinding{BinaryPath:binary,ArtifactSHA256:contracts.TextSHA256(string(bytes)),SourceManifestSHA256:info.SourceSHA,Capabilities:info.Capabilities}});if e!=nil{t.Fatal(e)}
	defer func(){if e:=bound.VerifyUnchanged();e!=nil{t.Error(e)}}()
	damageSource,e:=os.ReadFile(filepath.Join(source,"pkg/enemy/damage.go"));if e!=nil{t.Fatal(e)}
	curves,e:=seteffects.ExtractScalarSlices(damageSource,"Resistance","ResMod");if e!=nil{t.Fatal(e)}
	rows:=[]any{}
	for _,job:=range []struct{name,config string}{
		{"bloom",".codex_tmp/selected-2plus2-20260916/run/prepared-config.txt"},
		{"cloud",".codex_tmp/gob11-gp3-production-20260916/flins_1/selected-20260916-132613-fd420284/prepared-config.txt"},
	}{
		config,e:=os.ReadFile(filepath.Join(root,job.config));if e!=nil{t.Fatal(e)}
		priorBytes,e:=os.ReadFile(filepath.Join(root,".codex_tmp/all-sets-resistance-inputs-20260916",job.name+"-baseline.json"));if e!=nil{t.Fatal(e)}
		var prior struct{Member contracts.IRSeedMember `json:"member"`; Owners []string `json:"owners"`};if e=json.Unmarshal(priorBytes,&prior);e!=nil{t.Fatal(e)}
		got,e:=bound.RunCompactWithEffects(context.Background(),string(config),filepath.Join(out,job.name),prior.Member.Seed,true);if e!=nil{t.Fatal(e)}
		if !reflect.DeepEqual(got.Effects.CharacterKeys,prior.Owners) || got.Member.DurationMS!=prior.Member.DurationMS || len(got.Member.Channels)!=len(prior.Member.Channels){t.Fatal("capture identity changed",job.name)}
		for i,ch:=range got.Member.Channels{old:=prior.Member.Channels[i];if ch.ActorKey!=old.ActorKey||ch.AttackTag!=old.AttackTag||ch.DamageType!=old.DamageType||ch.Kind!=old.Kind{t.Fatal("channel changed",job.name,i)}}
		maxResidual:=0.0;base:=0.0
		for probe:=0;probe<9;probe++{
			delta:=map[string]float64{}
			if probe>0{for _,n:=range got.Member.Nodes{if n.Operation=="artifact_stat"{delta[n.Coordinate]=float64(probe-4)*.001}}}
			a,e:=formula.EvaluateSeedMember(prior.Member,delta);if e!=nil{t.Fatal(e)}
			b,e:=formula.EvaluateSeedMember(got.Member,delta);if e!=nil{t.Fatal(e)}
			residual:=math.Abs(a.Damage-b.Damage)/math.Max(1,math.Abs(a.Damage));maxResidual=math.Max(maxResidual,residual)
			if residual>1e-10{t.Fatalf("%s response %d drift %g",job.name,probe,residual)}
			if probe==0{base=b.Damage*1000/float64(got.Member.DurationMS)}
		}
		sha,e:=contracts.CanonicalSHA256(got.Member);if e!=nil{t.Fatal(e)}
		if _,e=seteffects.NewInputProbe(got.Member,prior.Owners,seteffects.InputEnvelope{SchemaVersion:1,MemberSHA256:sha,Inputs:got.Effects.EffectInputs});e!=nil{t.Fatal(e)}
		if _,e=seteffects.NewResistanceProbe(got.Member,prior.Owners,seteffects.ResistanceEnvelope{SchemaVersion:1,MemberSHA256:sha,Inputs:got.Effects.ResistanceInputs},curves);e!=nil{t.Fatal(e)}
		rows=append(rows,map[string]any{"case":job.name,"expected_dps":base,"max_relative_response_residual":maxResidual,"responses":9,"reaction_inputs":len(got.Effects.EffectInputs),"resistance_inputs":len(got.Effects.ResistanceInputs),"process_ms":got.ProcessMS,"decode_ms":got.DecodeMS})
	}
	receipt:=map[string]any{"status":"clean_source_candidate_transport_parity_not_install_or_product_acceptance","new_n1_calls":2,"source_manifest_sha256":info.SourceSHA,"binary_sha256":bound.artifactSHA256,"rows":rows}
	payload,e:=json.MarshalIndent(receipt,"","  ");if e!=nil{t.Fatal(e)}
	if e=os.WriteFile(filepath.Join(out,"observer-transport-receipt.json"),payload,0600);e!=nil{t.Fatal(e)}
}

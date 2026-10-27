"""R1 opt-in over the reconstructed accepted 403-image ordinary neutral path."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import mechanic_compiler_stage as accepted

ROOT,HERE=accepted.ROOT,Path(__file__).resolve().parent
OUT=ROOT/'docs/optimizer-evidence/2026-10-27-single-trace'
ACCEPTED_MAP='a5262483285f03b982553238f531c9823c8a04d1623c5c3d45b72b200672aa81'
ENGINE_SHA='f1e076b7fa9d292d0bab83aed9d3db0ec917437b288dcc6798cd69f4718f9b93'

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('R1 source seam differs: '+old[:80])
    return text.replace(old,new,1)

def accepted_images():
    images=accepted.images()
    manifest=json.loads((accepted.OUT/'stage22-final-v1-release.json').read_bytes())['source_images']
    differing={k for k,v in images.items() if hashlib.sha256(v).hexdigest()!=manifest.get(k)}
    patch=ROOT/'docs/optimizer-evidence/2026-10-25-formula-preparation/dispatch-v3-product.patch'
    raw=patch.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='c73ffaf41255bc4dd981410df2d5109de2820133a37fc96bbbb2f5794d455f1c':raise ValueError('accepted reverse patch differs')
    permitted={'internal/seteffects/'+name+'.go' for name in ('neutral_expressions','rule_program','rule_resources')}
    if differing-permitted:raise ValueError('unreviewed accepted-source drift')
    lines=raw.decode().splitlines(True);current=None;i=0
    while i<len(lines):
        row=lines[i]
        if row.startswith('+++ b/'):current=row[6:].strip();i+=1;continue
        if row.startswith('@@ '):
            i+=1;before=[];after=[]
            while i<len(lines) and not lines[i].startswith(('@@ ','--- a/')):
                row=lines[i]
                if row.startswith((' ','-')):before.append(row[1:])
                if row.startswith((' ','+')):after.append(row[1:])
                i+=1
            if current in differing:images[current]=once(images[current].decode(),''.join(after),''.join(before)).encode()
            continue
        i+=1
    mapping={k:hashlib.sha256(v).hexdigest() for k,v in sorted(images.items())}
    if mapping!=manifest or hashlib.sha256(json.dumps(mapping,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=ACCEPTED_MAP:raise ValueError('accepted403 reconstruction differs')
    return images

def native_images():
    images=accepted_images()
    name='internal/seteffects/neutral_binding.go';text=images[name].decode()
    text=once(text,'type NeutralBinding struct {','type NeutralBinding struct {\n r1Frozen bool\n r1Stats R1FrozenStats')
    images[name]=text.encode()
    name='internal/seteffects/neutral_expressions.go';text=images[name].decode()
    text=once(text,'type NeutralExpressions struct {','type NeutralExpressions struct {\n r1Frozen bool')
    text=once(text,'sort.Strings(out.Uncertainty)\n\treturn out','sort.Strings(out.Uncertainty)\n return b.r1Freeze(choices,out)')
    images[name]=text.encode()
    name='internal/seteffects/neutral_composition.go';text=images[name].decode()
    text=once(text,'usable: out.Complete() && out.footprint.trackedStats()','usable: out.Complete() && !out.r1Frozen && out.footprint.trackedStats()')
    images[name]=text.encode()
    name='internal/setcontext/neutral.go';text=images[name].decode()
    text=once(text,'"fmt"','"fmt"\n "os"')
    text=once(text,'type NeutralModelStats struct {','type NeutralModelStats struct {\n R1 *seteffects.R1FrozenStats `json:"r1,omitempty"`')
    text=once(text,'stats := m.stats','stats := m.stats\n if os.Getenv("GTT_R1_SINGLE_NEUTRAL")=="1" {snapshot:=m.binding.R1FrozenStats();stats.R1=&snapshot}')
    text=once(text,'binding.EnableOwnedWorldViewReuse()','binding.EnableOwnedWorldViewReuse()\n if os.Getenv("GTT_R1_SINGLE_NEUTRAL")=="1"{binding.EnableR1FrozenResiduals()}')
    text=once(text,'m.stats.RuleSeconds += time.Since(start).Seconds()','m.stats.RuleSeconds += time.Since(start).Seconds()\n if resolution!=nil{resolution.MechanicBoundaries=append([]contracts.MechanicBoundary(nil),effects.MechanicBoundaries...)}')
    images[name]=text.encode()
    name='internal/allsets/neutral_coordinator.go';text=images[name].decode()
    if '"os"' not in text:text=once(text,'"fmt"','"fmt"\n "os"')
    text=once(text,'return r.capture(ctx, target, reasons)','if os.Getenv("GTT_R1_SINGLE_NEUTRAL")=="1" {return nil,reasons,fmt.Errorf("R1 neutral model unavailable; context recapture forbidden")}\n return r.capture(ctx, target, reasons)')
    text=once(text,'key := target.Key()\n\tif r.captures.AttemptedCaptureMembers()', 'if os.Getenv("GTT_R1_SINGLE_NEUTRAL")=="1" {return nil,reasons,fmt.Errorf("R1 extra context capture forbidden")}\n key := target.Key()\n\tif r.captures.AttemptedCaptureMembers()')
    images[name]=text.encode()
    images['internal/seteffects/r1_frozen_neutral.go']=(HERE/'r1_frozen_neutral.go').read_bytes()
    images['internal/seteffects/r1_frozen_neutral_test.go']=(HERE/'r1_frozen_neutral_test.go').read_bytes()
    images['internal/allsets/r1_router_test.go']=(HERE/'r1_router_test.go').read_bytes()
    images['internal/projectionmetrics/metrics.go']=(HERE/'r1_metrics.go').read_bytes()
    images['cmd/gtt-optimizer/whole_counts.go']=(HERE/'whole_chasca_native_metrics.go').read_bytes()
    def instrument(name,signature,code):
        text=images[name].decode()
        if '"genshinteamstracker/native/gcsim_optimizer/internal/projectionmetrics"' not in text:
            if 'import (' in text:text=once(text,'import (','import (\n "genshinteamstracker/native/gcsim_optimizer/internal/projectionmetrics"')
            elif 'import "math"' in text:text=once(text,'import "math"','import ("math";"genshinteamstracker/native/gcsim_optimizer/internal/projectionmetrics")')
            else:raise ValueError('R1 telemetry import surface differs')
        images[name]=once(text,signature,signature+'\n '+code).encode()
    for name,signature,count in [
        ('internal/formula/artifact_program.go','func (p *ArtifactProgram) Evaluate(delta []float64) (float64, error) {','artifact.evaluate_calls'),
        ('internal/formula/program_gradient.go','func (p *ArtifactProgram) ValueGradient(delta []float64) (value float64, gradient []float64, smooth bool, err error) {','artifact.gradient_calls'),
        ('internal/setcontext/neutral.go','func NewNeutralModel(h *Handle, sources *seteffects.SourceCatalog) (*NeutralModel, error) {','r1.neutral_models'),
    ]:instrument(name,signature,'projectionmetrics.Count("'+count+'",1)')
    for name,signature,phase in [
        ('internal/seteffects/neutral_expressions.go','func (b *NeutralBinding) compilePackagesJoint(choices []RuleChoice) NeutralExpressions {','r1.joint_rule_compile'),
        ('internal/setcontext/neutral.go','func (m *NeutralModel) resolve(target *Context, resolution *MechanicResolution) (*Handle, []string, error) {','r1.resolve_inclusive'),
    ]:instrument(name,signature,'end:=projectionmetrics.Begin("'+phase+'");defer end()')
    for name,command,stem in [('internal/engineclient/compact.go','cmd','engine.compact'),('internal/engineclient/ordinary.go','command','engine.ordinary')]:
        text=images[name].decode();text=once(text,'import (','import (\n "genshinteamstracker/native/gcsim_optimizer/internal/projectionmetrics"')
        call='combined, err := '+command+'.CombinedOutput()'
        images[name]=once(text,call,'projectionmetrics.Count("'+stem+'.process_attempts",1)\n '+call+'\n if err==nil{projectionmetrics.Count("'+stem+'.process_exit_success",1)}').encode()
    name='cmd/gtt-optimizer/all_sets.go';text=images[name].decode()
    text=once(text,'import (','import (\n "genshinteamstracker/native/gcsim_optimizer/internal/projectionmetrics"')
    text=once(text,'started := time.Now()','finishCounts,countErr:=beginWholeChascaCounters(runRoot);if countErr!=nil{return countErr};defer finishCounts()\n started := time.Now()')
    text=once(text,'scores := []search.ScoredAssignment{}','projectionmetrics.Count("search.selected_finalists",uint64(len(result.Finalists)))\n scores := []search.ScoredAssignment{}')
    text=once(text,'wrapper["support_response"] = responseReceipt','projectionmetrics.Count("product.rendered_candidates",uint64(len(product.Candidates)))\n wrapper["support_response"] = responseReceipt')
    images[name]=text.encode()
    return images

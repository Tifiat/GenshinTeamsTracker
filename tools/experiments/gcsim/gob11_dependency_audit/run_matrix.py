"""Evaluate retained traces with the project's real interpreter/dense scorer."""
from pathlib import Path
import argparse,json,os,subprocess
p=argparse.ArgumentParser(__doc__)
p.add_argument('--matrix',type=Path,required=True)
args=p.parse_args()
here=Path(__file__).resolve().parent
root=here.parents[3]
matrix=args.matrix.resolve()
overlay=matrix/'formula-overlay.json'
overlay.write_text(json.dumps({'Replace':{str(root/'native/gcsim_optimizer/internal/formula/gtt_dependency_matrix_test.go'):str(here/'formula_matrix_test.go')}}))
env=dict(os.environ,GOB11_MATRIX_INPUT=str(matrix))
env.pop('GOB11_MATRIX_CASE',None)
subprocess.run(['C:/Program Files/Go/bin/go.exe','test','-overlay',str(overlay),'./internal/formula','-run','TestArchetypeAudit','-count=1','-v'],cwd=root/'native/gcsim_optimizer',env=env,check=True)

"""R2 changes only R1's final ordinary verification call and additive receipts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from . import r1_single_trace as r1

ROOT, HERE = r1.ROOT, Path(__file__).resolve().parent
OUT = ROOT / 'docs/optimizer-evidence/2026-10-27-staged-finalists'
R1_MAP = '2f050c8565072d8cd667240943663f87b5c0b75510e32c2d30d8991dfc58281c'

def overlay(images):
    mapping={k:hashlib.sha256(v).hexdigest() for k,v in sorted(images.items())}
    if hashlib.sha256(json.dumps(mapping,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=R1_MAP:
        raise ValueError('R2 requires the exact reviewed R1 image map')
    images=dict(images)
    name='internal/finalists/verify.go'
    text=images[name].decode()
    text=r1.once(text,'type VerificationResult struct {','type VerificationResult struct {\n Staged *StagedVerification `json:"staged,omitempty"`')
    images[name]=text.encode()
    name='cmd/gtt-optimizer/all_sets.go'
    text=images[name].decode()
    text=r1.once(text,'finalists.VerifyDynamicWavesWithRenderer(overall, req, scores, renderer, filepath.Join(runRoot, "final-n500"), 500, 4, runtime.NumCPU())',
                 'finalists.VerifyStagedWavesWithRenderer(overall, req, scores, renderer, filepath.Join(runRoot, "final-staged"), 4, runtime.NumCPU())')
    images[name]=text.encode()
    images['internal/finalists/r2_staged_finalists.go']=(HERE/'r2_staged_finalists.go').read_bytes()
    test=HERE/'r2_staged_finalists_test.go'
    if test.is_file(): images['internal/finalists/r2_staged_finalists_test.go']=test.read_bytes()
    product_test=HERE/'r2_product_test.go'
    if product_test.is_file(): images['cmd/gtt-optimizer/r2_product_test.go']=product_test.read_bytes()
    return images

def native_images(): return overlay(r1.native_images())

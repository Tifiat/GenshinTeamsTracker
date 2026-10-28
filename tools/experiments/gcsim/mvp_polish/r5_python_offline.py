"""Record the small R5 Python gate against its prospective exact code image."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import tempfile
import unittest

from .r5_python import OUT, python_images, map_sha, mapping, sha


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--label',required=True)
    parser.add_argument('--test',action='append')
    args=parser.parse_args()
    output=OUT/(args.label+'.json'); log=output.with_suffix('.log')
    if output.exists() or log.exists():raise FileExistsError(output)
    before=python_images(); stream=io.StringIO()
    record={'schema':'r5_python_offline_v1','engine_calls':0,'search_calls':0,
            'source_files':mapping(before),'source_map_sha256':map_sha(before)}
    # The image must precede even the managed-owner helper's product imports.
    prefix='tools.experiments.gcsim.mvp_polish.test_r5_python'
    suite=(unittest.defaultTestLoader.loadTestsFromNames([prefix+'.R5PythonTests.'+name for name in args.test])
           if args.test else unittest.defaultTestLoader.loadTestsFromName(prefix))
    from tools.managed_optimizer_experiment import managed_scratch
    with managed_scratch() as job:
        oldtemp=tempfile.tempdir
        tempfile.tempdir=str(job)
        try:
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
            from .test_r5_python import IMAGE
            imports=IMAGE.verify()
            record.update(status='passed' if result.wasSuccessful() else 'failed',
                          tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                          imported_product_sources=imports,
                          source_unchanged=python_images()==before)
        finally:
            tempfile.tempdir=oldtemp
    record['job_removed']=not job.exists()
    log.write_bytes(stream.getvalue().encode())
    record['log_sha256']=sha(log.read_bytes())
    output.write_bytes((json.dumps(record,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({k:v for k,v in record.items() if k not in ('source_files','imported_product_sources')}))
    return 0 if record['status']=='passed' and record['source_unchanged'] else 1


if __name__=='__main__':
    raise SystemExit(main())

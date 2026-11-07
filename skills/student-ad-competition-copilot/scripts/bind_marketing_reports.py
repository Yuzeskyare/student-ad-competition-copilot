"""Bind already generated native/export reports and the actual export record."""
import argparse,json
from pathlib import Path
from review_contract import inside,load,digest
from validate_marketing_plan_run import technical_pass


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir','source','native-report','export-report','export-record','output'): p.add_argument('--'+name,required=True)
    a=p.parse_args();root=Path(a.run_dir).resolve()
    def ref(name):
        path=inside(root,name)
        return dict(path=path.relative_to(root).as_posix(),sha256=digest(path))
    bundle=dict(kind='marketing-technical-bundle-v1',source=ref(a.source),native_report=ref(a.native_report),export_report=ref(a.export_report),export_record=ref(a.export_record))
    passed,detail=technical_pass(bundle,bundle['source']['sha256'],root)
    if not passed: raise ValueError(detail)
    output=inside(root,a.output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:json.dump(bundle,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status='pass',report=ref(a.output))))

if __name__=='__main__':main()

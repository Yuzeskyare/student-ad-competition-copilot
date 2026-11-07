"""Run existing presentation checks against the actual editable PPTX; no rendering or semantic scoring."""
import argparse, json, subprocess, sys
from pathlib import Path
from review_contract import digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--presentation-tools',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists(): raise ValueError('Preserve the original technical report; use a new output')
    source=a.input.resolve(); before=digest(source); checks={}
    for name,script in [('package','inspect_presentation_package_integrity.py'),('layout','inspect_presentation_layout_geometry.py'),('table_arithmetic','native_table_arithmetic_gate.py')]:
        tool=(a.presentation_tools/script).resolve()
        command=[sys.executable,'-X','utf8','-B',str(tool),str(source),'--fail-on-findings']
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        raw=json.loads(result.stdout) if result.stdout.strip() else {'error':result.stderr}
        passed=result.returncode==0 and (raw.get('status')=='pass' if name=='package' else raw.get('finding_count')==0 if name=='layout' else raw.get('passed') is True)
        checks[name]=dict(passed=passed,command=command,tool_sha256=digest(tool),result=raw)
    if digest(source)!=before: raise ValueError('PPTX changed during native checks')
    errors=[name for name,row in checks.items() if not row['passed']]
    report=dict(kind='marketing-native-technical-v1',input=dict(path=str(source),sha256=before),
                technical_validation_status='fail' if errors else 'pass',error_failures=errors,checks=checks,
                slide_count=checks['package']['result'].get('slide_count'),
                boundary='Package, geometry and table arithmetic only. Actual rendering and AI visual/content review remain separate.')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['technical_validation_status'],errors=errors)))
    return int(bool(errors))

if __name__=='__main__': raise SystemExit(main())

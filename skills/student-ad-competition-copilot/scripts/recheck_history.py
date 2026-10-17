"""Recheck original pixels/records under this package; never execute production."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from review_contract import bound_file, load, read_contract, digest, inside
from execution_contract import verify_complete_artworks, package_checker_hashes
from package_upgrade_contract import validate_historical_guard, upgrade_chain

def recheck(root, manifest):
    from PIL import Image, ImageChops
    from validate_submission import validate_file
    contract,rows=read_contract(root,manifest)
    upgrade_chain(root,manifest)
    requests={r['sha256']:(r,load(bound_file(root,r))) for r in contract['production_requests']}
    guards=[]
    for ref in contract['production_receipts']:
        receipt=load(bound_file(root,ref));request_ref,request=requests[receipt['request_sha256']]
        source=validate_historical_guard(root,manifest,receipt,request,request_ref,rows)
        guards.append(dict(receipt=ref,source_package=source,pre_dispatch_only=receipt.get('production_state')=='authorized',content_pass_granted=False))
    releases=verify_complete_artworks(root,manifest,contract)
    # Reuse the same native technical checker as normal submission validation.
    from validate_submission import SKILL_ROOT
    profiles=load(SKILL_ROOT/'references/competitions/submission-profiles.json')
    from PIL import ImageSequence
    pixels=[];seen=set()
    for row in manifest.get('core_creative_review',{}).get('assessments',[]):
        profile=profiles['profiles'][manifest['competition']]
        ref=row['observed_image']
        if ref['sha256'] in seen:continue
        seen.add(ref['sha256']);path=bound_file(root,ref)
        result,checks=validate_file(path,profile,Image,ImageSequence)
        render=load(bound_file(root,row['render_record']))
        natives=[v for v in render['views'] if v['scale']=='native']
        if len(natives)!=1 or natives[0]['file']!=ref:raise ValueError('History render/native binding mismatch')
        with Image.open(path) as im:native=im.convert('RGB')
        for view in render['views']:
            with Image.open(bound_file(root,view['file'])) as im:actual=im.convert('RGB')
            if view['scale']=='thumbnail':
                expected=native.copy();expected.thumbnail(actual.size,Image.Resampling.LANCZOS)
            elif view['scale']=='detail':
                if view['native_sha256']!=ref['sha256']:raise ValueError('History detail uses stale pixels')
                expected=native.crop(view['native_bounds']);expected=expected.resize((round(expected.width*view['zoom']),round(expected.height*view['zoom'])),Image.Resampling.LANCZOS)
            else:expected=native
            if expected.size!=actual.size or ImageChops.difference(expected,actual).getbbox() is not None:raise ValueError('History render view pixels differ from original source')
        pixels.append(dict(artwork=ref,original_render=row['render_record'],result=result,checks=checks,
                           technical_pass=all(c['passed'] for c in checks if c.get('severity')=='error')))
    return dict(kind='native-history-recheck',run_id=manifest['run_id'],checked_at=datetime.now(timezone.utc).isoformat(),
                checker_sha256=package_checker_hashes(),upgrade_chain=manifest.get('package_upgrades'),guards=guards,releases=releases,
                pixel_checks=pixels,content_pass_granted=False,production_executed=False,image_generation_calls=0)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('run-dir','manifest','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();root=Path(a.run_dir).resolve();out=inside(root,a.output)
    if out.exists():p.error('Use a new receipt path; preserve historical evidence')
    try:
        result=recheck(root,load(inside(root,a.manifest)))
        out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(status='rechecked',guards=len(result['guards']),pixels=len(result['pixel_checks']),content_pass_granted=False)))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        print(json.dumps(dict(status='blocked',reason=str(e),executed=False),ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())

"""Accept hash-bound historical guards only through verified package archives."""
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import hashlib
import json
import zipfile
from review_contract import bound_file, load, timestamp

_ARCHIVES = {}

def require(value, reason):
    if not value: raise ValueError(reason)

def archive_identity(root, ref):
    path=bound_file(root,ref)
    key=(str(path),ref['sha256'])
    if key in _ARCHIVES:return _ARCHIVES[key]
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        require(len(names)==len(set(names)) and z.testzip() is None,'Invalid package archive')
        prefix='student-ad-competition-copilot/'
        require(all(n.startswith(prefix) and not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names),'Unsafe package archive')
        v=json.loads(z.read(prefix+'version.json'))
        files={r['path']:r for r in v['files']}
        require(len(files)==len(v['files']) and set(names)=={prefix+n for n in files}|{prefix+'version.json'},'Package file inventory mismatch')
        for n,r in files.items():
            data=z.read(prefix+n)
            require(hashlib.sha256(data).hexdigest()==r['sha256'] and len(data)==r['bytes'],'Package bytes differ from manifest')
        hashes={n:r['sha256'] for n,r in files.items() if n.startswith('scripts/') and n.endswith('.py')}
        identity=dict(version=v['version'],status=v.get('status'),checker_sha256=hashes,archive=ref)
        _ARCHIVES[key]=identity
        return identity

def upgrade_chain(root, manifest):
    ref=manifest.get('package_upgrades')
    review_ref=manifest.get('candidate_review_recheck')
    if review_ref is not None:
        require(ref is None, 'Choose installed upgrade history or a candidate review recheck')
        return candidate_review_source(root, manifest, review_ref)
    if ref is None:return []
    chain=load(bound_file(root,ref))
    require(set(chain)=={'kind','run_id','upgrades'} and chain['kind']=='package-upgrade-chain' and chain['run_id']==manifest['run_id'],'Upgrade chain must bind the current run')
    rows=chain['upgrades'];require(isinstance(rows,list) and rows,'Empty upgrade chain')
    previous=None;at=None;result=[]
    for row in rows:
        require(set(row)=={'from_version','to_version','from_package','to_package','upgraded_at'},'Invalid upgrade entry fields')
        old=archive_identity(root,row['from_package']);new=archive_identity(root,row['to_package'])
        require(old['version']==row['from_version'] and new['version']==row['to_version'] and old['version']!=new['version'],'Upgrade version/archive mismatch')
        when=timestamp(row['upgraded_at'])
        require(when<=datetime.now(timezone.utc) and (at is None or at<=when),'Upgrade time must be chronological')
        require(previous is None or old==previous,'Upgrade chain is not contiguous')
        result.append(dict(old,upgraded_at=row['upgraded_at']))
        previous=new;at=when
    from execution_contract import package_checker_hashes
    current=load(Path(__file__).resolve().parent.parent/'version.json')
    require(previous['version']==current['version'] and previous['checker_sha256']==package_checker_hashes(),'Upgrade chain must end at the executing package')
    return result


def candidate_review_source(root, manifest, ref):
    from execution_contract import package_checker_hashes
    from review_contract import read_contract
    require(manifest.get('run_scope')=='production-candidate' and manifest.get('category')=='print-ad',
            'Candidate recheck is for print production-candidate review only')
    contract, _ = read_contract(root, manifest)
    require(not contract['final_artifacts'] and contract['content_status']=='pending',
            'Candidate recheck cannot certify an adopted or delivered artwork')
    record=load(bound_file(root,ref))
    require(set(record)=={'kind','run_id','from_package','to_package','rechecked_at'}
            and record['kind']=='candidate-review-recheck-v1' and record['run_id']==manifest['run_id'],
            'Candidate review recheck must bind the current run and package archives')
    source=archive_identity(root,record['from_package'])
    target=archive_identity(root,record['to_package'])
    current=load(Path(__file__).resolve().parent.parent/'version.json')
    require(source['status']==target['status']==current['status']=='development-candidate'
            and source['version']!=target['version'] and target['version']==current['version']
            and target['checker_sha256']==package_checker_hashes(),
            'Candidate review archives must bind the original candidate and the executing candidate')
    require(timestamp(record['rechecked_at'])<=datetime.now(timezone.utc),'Candidate review recheck cannot be in the future')
    return [dict(source, review_only=True, rechecked_at=record['rechecked_at'])]


def guard_source(root, manifest, receipt):
    from execution_contract import package_checker_hashes
    identity=receipt.get('guard_identity',{})
    require(set(identity)=={'profile','entrypoint','checker_sha256'} and identity['profile']=='package-guard-v1' and identity['entrypoint']=='scripts/guard_production.py','Invalid native guard identity')
    hashes=identity['checker_sha256'];current=package_checker_hashes()
    if hashes==current:
        # Validate a supplied chain even if this particular guard is current.
        upgrade_chain(root,manifest)
        return dict(version=load(Path(__file__).resolve().parent.parent/'version.json')['version'],historical=False)
    matches=[x for x in upgrade_chain(root,manifest) if x['checker_sha256']==hashes
             and timestamp(receipt['checked_at'])<=timestamp(x.get('rechecked_at') or x['upgraded_at'])]
    require(len(matches)==1,'Foreign guard source is absent from registered upgrade chain')
    source=matches[0]
    result=dict(version=source['version'],historical=True,package=source['archive'])
    if source.get('review_only'):result['review_only']=True
    return result

def validate_historical_guard(root, manifest, receipt, request, request_ref, rows):
    from review_contract import fingerprint, request_decision, validate_request_inputs, inside
    source=guard_source(root,manifest,receipt)
    require(receipt.get('run_id')==manifest['run_id'] and receipt.get('request')==request and receipt.get('request_sha256')==request_ref['sha256'] and receipt.get('request_id')==request['id'],'Historical guard request/run binding mismatch')
    validate_request_inputs(root,request)
    for ref in request.get('input_files',[]):bound_file(root,ref)
    at=timestamp(receipt['checked_at']);require(at<=datetime.now(timezone.utc),'Future guard')
    eligible={k:r for k,r in rows.items() if timestamp(r['checked_at'])<=at}
    _,decision=request_decision(root,request_ref,eligible)
    require(receipt.get('decision_id')==decision['id'] and receipt.get('decision_sha256')==fingerprint(decision) and receipt.get('authorization_kind')==decision['stage'],'Historical guard decision binding mismatch')
    require(receipt.get('status')=='authorized' and receipt.get('dispatch_checked') is True and receipt.get('content_pass_granted') is False,'Historical evidence is not a dispatch release')
    control=load(bound_file(root,receipt.get('execution_control')))
    require(control.get('run_id')==manifest['run_id'] and control.get('state')=='active','Historical guard lacks its bound active control')
    outputs=receipt.get('outputs',[])
    if receipt.get('production_state')=='completed':
        require(receipt.get('executed') is True and receipt.get('command_returncode')==0 and {r['path'] for r in outputs}==set(request.get('output_files',[])),'Incomplete historical production output binding')
        for ref in outputs:bound_file(root,ref)
    elif request.get('operation') in {'external', 'model'}:
        require(receipt.get('executed') is False and receipt.get('production_state')=='authorized','Invalid historical predispatch release')
    else:raise ValueError('Historical local production has not completed')
    return source

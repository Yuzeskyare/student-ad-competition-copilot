"""Pixel-only triptych projections; private author checks never enter checker inputs."""
import json
import hashlib
from pathlib import Path
from review_contract import bound_file, digest, inside, load

PROFILE = 'print-review-projection-v1'


def binding_name(reference):
    key=json.dumps(reference,sort_keys=True,separators=(',',':')).encode('utf-8')
    return '_review-private/'+hashlib.sha256(key).hexdigest()+'.binding.json'


def ref(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=digest(path))


def write_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Immutable evidence conflict: '+str(path))
    else:
        with path.open('xb') as f:
            f.write(data)


def project(root, original, element_id, destination):
    source = bound_file(root, original)
    value = load(source)
    panels = {role: {k: value['panels'][role][k] for k in ('source','bounds','zoom')}
              for role in ('official','generated','final')}
    result = dict(contract=PROFILE, element_id=element_id, image=value['image'],
                  panels=panels, source_sha256=original['sha256'])
    # Private source is addressed only by hash; the checker receives no path to it.
    private = inside(root, '_review-private/'+original['sha256']+'.json')
    write_once(private, source.read_bytes())
    target = inside(root, destination)
    write_once(target, (json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    binding = dict(original=original, projection=ref(root,target))
    write_once(inside(root,binding_name(binding['projection'])),
               (json.dumps(binding,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    validate(root, binding['projection'], element_id)
    return binding['projection']


def validate(root, reference, element_id=None):
    value = load(bound_file(root, reference))
    if value.get('contract') != PROFILE:
        return value  # Historical immutable records retain their original contract.
    if set(value) != {'contract','element_id','image','panels','source_sha256'}:
        raise ValueError('Review projection fields must be only images/crops/element_id/hashes')
    if element_id is not None and value['element_id'] != element_id:
        raise ValueError('Review projection element_id differs from current product')
    binding = load(inside(root,binding_name(reference)))
    if binding.get('projection') != reference or binding['original']['sha256'] != value['source_sha256']:
        raise ValueError('Review projection reverse binding differs')
    original = load(bound_file(root,binding['original']))
    frozen = inside(root,'_review-private/'+value['source_sha256']+'.json')
    if digest(frozen) != value['source_sha256'] or load(frozen) != original:
        raise ValueError('Private author metadata changed')
    expected = dict(contract=PROFILE,element_id=value['element_id'],image=original['image'],
                    panels={r:{k:original['panels'][r][k] for k in ('source','bounds','zoom')}
                            for r in ('official','generated','final')},source_sha256=value['source_sha256'])
    if value != expected:
        raise ValueError('Review projection differs from bound original image/crops')
    bound_file(root,value['image'])
    for p in value['panels'].values():
        if set(p) != {'source','bounds','zoom'}:
            raise ValueError('Review panel contains author fields')
        bound_file(root,p['source'])
    return value


def original_record(root, reference):
    value = validate(root, reference)
    if value.get('contract') == PROFILE:
        return load(inside(root,'_review-private/'+value['source_sha256']+'.json'))
    return value

"""Freeze one content-addressed rollout shared by multiple member bindings."""
import argparse
import json
from pathlib import Path
from review_contract import inside, load, bound_file, digest
from review_projection import write_once, ref


def freeze(root, bindings, destination, shared_rollout=None):
    target=inside(root,destination)
    if target.exists():raise ValueError('Use a new shared evidence destination')
    outputs=[];objects={}
    # Validate full original lifecycle before making any new binding.
    from desktop_host_evidence import completed_image_event
    for entry in bindings:
        binding=load(bound_file(root,entry['binding']));request=load(bound_file(root,entry['request']))
        completed_image_event(root,binding,request)
        source=bound_file(root,shared_rollout or binding['evidence']);sha=digest(source)
        path=target/'objects'/(sha+'.jsonl')
        write_once(path,source.read_bytes());objects[sha]=ref(root,path)
        copied=dict(binding,evidence=objects[sha])
        completed_image_event(root,copied,request)
        output=target/(str(len(outputs)+1)+'-binding.json')
        write_once(output,(json.dumps(copied,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        outputs.append(dict(original=entry['binding'],binding=ref(root,output),request=entry['request']))
    index=dict(profile='shared-frozen-rollout-v1',bindings=outputs,objects=list(objects.values()),
               originals_preserved=True,full_native_validation=True)
    write_once(target/'index.json',(json.dumps(index,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    return index


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--payload',required=True);args=p.parse_args();root=args.run_dir.resolve()
    try:print(json.dumps(freeze(root,**load(inside(root,args.payload))),ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps(dict(status='failed',reason=str(exc))));return 1


if __name__=='__main__':raise SystemExit(main())

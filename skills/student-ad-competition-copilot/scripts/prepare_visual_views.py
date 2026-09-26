"""Produce deterministic review views from an existing target-application render."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from review_contract import digest, inside


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('run-dir','source','version','unit','native','renderer','execution-evidence','output-dir'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--target-renderer-verified',action='store_true')
    parser.add_argument('--crop',action='append',type=lambda s:[int(v) for v in s.split(',')])
    parser.add_argument('--full-page-detail',action='store_true',help='Explicit legacy/full-page enlargement when needed')
    parser.add_argument('--zoom',type=float,default=2)
    parser.add_argument('--thumbnail-width',type=int,default=320)
    args=parser.parse_args()
    from PIL import Image
    root=Path(args.run_dir).resolve()
    source,native,evidence=[inside(root,v) for v in (args.source,args.native,args.execution_evidence)]
    if not all(p.is_file() for p in (source,native,evidence)):parser.error('Source, native render and renderer execution evidence must exist')
    dest=inside(root,args.output_dir)
    if dest.exists():parser.error('Use a new output directory; do not overwrite reviewed views')
    image=Image.open(native).convert('RGB')
    crops=args.crop or ([[0,0,image.width,image.height]] if args.full_page_detail else [])
    if not 1.5<=args.zoom<=4 or args.thumbnail_width<1:parser.error('Invalid viewing scale')
    for crop in crops:
        if len(crop)!=4 or not 0<=crop[0]<crop[2]<=image.width or not 0<=crop[1]<crop[3]<=image.height:
            parser.error('Crop must lie within native render, in pixels')
    def ref(path):return {'path':path.relative_to(root).as_posix(),'sha256':digest(path)}
    dest.mkdir(parents=True)
    views=[{'id':'native','scale':'native','file':ref(native)}]
    thumb=image.copy();width=min(args.thumbnail_width,max(1,image.width//3))
    thumb.thumbnail((width,max(1,round(image.height*width/image.width))),Image.Resampling.LANCZOS)
    thumbpath=dest/'thumbnail.png';thumb.save(thumbpath)
    views.append({'id':'thumbnail','scale':'thumbnail','file':ref(thumbpath)})
    for i,crop in enumerate(crops,1):
        detail=image.crop(crop);detail=detail.resize((round(detail.width*args.zoom),round(detail.height*args.zoom)),Image.Resampling.LANCZOS)
        path=dest/f'detail-{i}.png';detail.save(path)
        views.append({'id':f'detail-{i}','scale':'detail','file':ref(path),'native_bounds':crop,'zoom':args.zoom,'native_sha256':digest(native)})
    record={'source':dict(ref(source),version=args.version,units=[args.unit]),'renderer':args.renderer,
            'target_renderer_verified':args.target_renderer_verified,'execution_evidence':ref(evidence),
            'created_at':datetime.now(timezone.utc).isoformat(),'views':views}
    output=dest/'render-record.json';output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'render_record':ref(output),'views':len(views),'visual_quality_assessed':False},ensure_ascii=False))


if __name__=='__main__':
    main()

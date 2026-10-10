"""Produce deterministic review views from an existing target-application render."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from review_contract import digest, inside


def product_tools(argv):
    """Prepare product triptychs/pixel proofs without generating or editing images."""
    from PIL import Image
    from visual_review_contract import product_triptych, exact_pixel_diff
    parser=argparse.ArgumentParser(description='product-triptych: --input panel JSON; pixel-proof: --before/--after/--mask. All paths relative to --run-dir.')
    parser.add_argument('operation',choices=['product-triptych','pixel-proof'])
    parser.add_argument('--run-dir',required=True); parser.add_argument('--output-dir',required=True)
    parser.add_argument('--input'); parser.add_argument('--before'); parser.add_argument('--after'); parser.add_argument('--mask')
    args=parser.parse_args(argv); root=Path(args.run_dir).resolve(); dest=inside(root,args.output_dir)
    if dest.exists(): parser.error('Use a new output directory')
    def ref(path): return {'path':path.relative_to(root).as_posix(),'sha256':digest(path)}
    if args.operation=='product-triptych':
        if not args.input: parser.error('--input is required')
        record=json.loads(inside(root,args.input).read_text(encoding='utf-8'))
        sheet=product_triptych(root,record); dest.mkdir(parents=True)
        sheet.save(dest/'triptych.png'); record['image']=ref(dest/'triptych.png'); name='triptych.json'
    else:
        if not all([args.before,args.after,args.mask]): parser.error('--before/--after/--mask are required')
        before,after,mask=[inside(root,p) for p in [args.before,args.after,args.mask]]
        with Image.open(before) as b,Image.open(after) as a,Image.open(mask) as m: record=exact_pixel_diff(b,a,m)
        record.update(before=ref(before),after=ref(after),allowed_mask=ref(mask)); name='pixel-proof.json'; dest.mkdir(parents=True)
    path=dest/name; path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'record':ref(path),'visual_quality_assessed':False},ensure_ascii=False))
    return 1 if record.get('outside_changed_pixels',0) else 0


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    if len(sys.argv)>1 and sys.argv[1] in {'product-triptych','pixel-proof'}: return product_tools(sys.argv[1:])
    parser=argparse.ArgumentParser(description=__doc__,epilog='Additional operations: product-triptych --help; pixel-proof --help')
    for name in ('run-dir','source','version','unit','renderer','execution-evidence','output-dir'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--native',required=True,help='Existing raster render (PNG/JPEG), not SVG; --source identifies the editable source')
    parser.add_argument('--target-renderer-verified',action='store_true')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--crop',action='append',type=lambda s:[int(v) for v in s.split(',')],metavar='LEFT,TOP,RIGHT,BOTTOM',help='Pixel edges, NOT width/height; repeat for multiple details')
    group.add_argument('--crop-xywh',action='append',type=lambda s:[int(v) for v in s.split(',')],metavar='LEFT,TOP,WIDTH,HEIGHT',help='Explicit alternative; never inferred from --crop values')
    parser.add_argument('--full-page-detail',action='store_true',help='Explicit legacy/full-page enlargement when needed')
    parser.add_argument('--zoom',type=float,default=2,help='Detail enlargement from 1.5 to 4 inclusive (default: 2)')
    parser.add_argument('--thumbnail-width',type=int,default=320)
    args=parser.parse_args()
    from PIL import Image, UnidentifiedImageError
    root=Path(args.run_dir).resolve()
    source,native,evidence=[inside(root,v) for v in (args.source,args.native,args.execution_evidence)]
    if not all(p.is_file() for p in (source,native,evidence)):parser.error('Source, native render and renderer execution evidence must exist')
    dest=inside(root,args.output_dir)
    if dest.exists():parser.error('Use a new output directory; do not overwrite reviewed views')
    try:
        with Image.open(native) as source_image:
            image=source_image.convert('RGB')
    except (UnidentifiedImageError,OSError) as exc:
        parser.error('--native must be a readable raster render; render SVG in the target application first: '+str(exc))
    crops=args.crop or ([[0,0,image.width,image.height]] if args.full_page_detail else [])
    if args.crop_xywh:
        if any(len(c)!=4 or c[2]<=0 or c[3]<=0 for c in args.crop_xywh):
            parser.error('--crop-xywh requires left,top,positive-width,positive-height')
        crops=[[x,y,x+w,y+h] for x,y,w,h in args.crop_xywh]
    if not 1.5<=args.zoom<=4 or args.thumbnail_width<1:parser.error('--zoom must be from 1.5 to 4; --thumbnail-width must be positive')
    for crop in crops:
        if len(crop)!=4 or not 0<=crop[0]<crop[2]<=image.width or not 0<=crop[1]<crop[3]<=image.height:
            parser.error(f'Crop {crop} must lie within {image.width}x{image.height}; --crop uses left,top,right,bottom. For width/height use --crop-xywh. Example full image: --crop 0,0,{image.width},{image.height}')
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
    print(json.dumps({'render_record':ref(output),'views':len(views),'files':[v['file'] for v in views],'visual_quality_assessed':False},ensure_ascii=False))


if __name__=='__main__':
    raise SystemExit(main())

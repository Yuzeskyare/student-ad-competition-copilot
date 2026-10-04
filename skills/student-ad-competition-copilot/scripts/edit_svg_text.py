"""Edit exact native SVG text slots by ID into a new source; never certify rendering."""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from review_contract import inside, load, bound_file, digest


def edit(root, spec, destination):
    source = bound_file(root, spec['source'])
    output = inside(root, destination)
    if output.exists():
        raise ValueError('Use a new output path; preserve the reviewed source')
    raw = source.read_bytes()
    # Entity expansion and external DTDs are not needed for native text editing.
    if re.search(br'<!DOCTYPE|<!ENTITY', raw, re.I):
        raise ValueError('DTD/entity SVG is unsupported; use the native editor')
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.fromstring(raw, parser=parser)
    changes = spec.get('changes')
    if not isinstance(changes, list) or not changes:
        raise ValueError('Provide exact text/tspan IDs with before and after text')
    seen = set()
    for change in changes:
        ident = change['id']
        nodes = [n for n in tree.iter() if n.get('id') == ident]
        if not ident or ident in seen or len(nodes) != 1:
            raise ValueError('Expected exactly one unique SVG object: '+str(ident))
        seen.add(ident)
        node = nodes[0]
        if node.tag.rsplit('}',1)[-1]=='g' and 'text_index' in change:
            leaves=[n for n in node.iter() if isinstance(n.tag,str) and n.tag.rsplit('}',1)[-1] in {'text','tspan'} and not len(n)]
            index=change['text_index']
            if type(index) is not int or type(change.get('expected_text_nodes')) is not int or len(leaves)!=change['expected_text_nodes'] or not 0<=index<len(leaves):
                raise ValueError('Group text count/index differs from explicit expected slots: '+ident)
            node=leaves[index]
        if node.tag.rsplit('}', 1)[-1] not in {'text','tspan'} or len(node):
            raise ValueError('Target a leaf text/tspan ID or an explicit group text_index/count; never metadata: '+ident)
        if not isinstance(change.get('after'), str) or (node.text or '') != change.get('before'):
            raise ValueError('Visible text differs from expected before text: '+ident)
        node.text = change['after']
    # Preserve the root namespace prefix used for normal SVG presentation.
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
    data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
    if digest(source) != spec['source']['sha256']:
        raise ValueError('Source changed during edit')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(data)
    return dict(status='source-edited-render-required', output=dict(path=destination, sha256=digest(output)),
                changed_ids=sorted(seen), visual_quality_certified=False,
                next_action='Render this new source and inspect visible copy, layout, dependencies and preserved relations before updating current artifacts')


def main():
    import sys
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--spec',required=True,help='Run-relative JSON: source {path,sha256}, changes [{id,before,after}]')
    parser.add_argument('--output',required=True,help='New run-relative SVG')
    args=parser.parse_args()
    try:
        root=args.run_dir.resolve()
        print(json.dumps(edit(root,load(inside(root,args.spec)),args.output),ensure_ascii=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError,AttributeError,ET.ParseError) as exc:
        print(json.dumps(dict(status='failed',reason=str(exc)),ensure_ascii=False));return 1

if __name__=='__main__': raise SystemExit(main())

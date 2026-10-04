#!/usr/bin/env python3
"""Read-only SVG source inspection; never certifies rendered quality or approval."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, unquote_to_bytes, urlsplit
import xml.etree.ElementTree as ET


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect(source: Path, root: Path, scene_id=None, expected_scene_sha256=None):
    root, source = root.resolve(), source.resolve()
    if not source.is_relative_to(root) or not source.is_file():
        raise ValueError('Source must be a file inside the explicit dependency root')
    if bool(scene_id) != bool(expected_scene_sha256):
        raise ValueError('scene-id and expected-scene-sha256 must be supplied together')
    raw = source.read_bytes()
    tree = ET.fromstring(raw)
    result = dict(source=str(source), source_sha256=sha(raw), dependency_root=str(root),
                  text_candidates=[], process_label_candidates=[], images=[], dependencies=[],
                  errors=[], scene_binding='not-checked', requires_visual_review=True,
                  limitations=['Text paths and raster text require actual render inspection.',
                               'CSS visibility, layout, font shaping and visual equivalence are not certified.',
                               'Generation-call provenance and approval require their original bound records.'])
    errors = result['errors']
    seen = set()

    def resolve_ref(value):
        if not value or value.startswith('#'):
            return None
        if value.startswith('data:'):
            head, payload = value.split(',', 1)
            data = base64.b64decode(re.sub(r'\s+', '', payload), validate=True) if ';base64' in head else unquote_to_bytes(payload)
            return dict(kind='embedded', sha256=sha(data), bytes=len(data))
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            raise ValueError('External/absolute URI is not read: ' + value)
        local = (source.parent / unquote(parsed.path)).resolve()
        if not local.is_relative_to(root):
            raise ValueError('Dependency escapes explicit root: ' + value)
        if not local.is_file():
            raise ValueError('Missing dependency: ' + value)
        item = dict(kind='local', reference=value, path=str(local), sha256=sha(local.read_bytes()), bytes=local.stat().st_size)
        if str(local) not in seen:
            result['dependencies'].append(item)
            seen.add(str(local))
        return item

    def read_ref(value):
        try:
            return resolve_ref(value)
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
            return None

    def walk(node, excluded=False):
        tag = node.tag.rsplit('}', 1)[-1]
        excluded = excluded or tag in {'defs', 'metadata', 'title', 'desc'}
        if tag == 'text' and not excluded:
            value = ''.join(node.itertext()).strip()
            if value:
                result['text_candidates'].append(value)
                if re.search(r'AI\s*生成|AIGC\s*(?:生成|制作)|AI[-\s]*generated|人工智能生成|由\s*AI\s*制作', value, re.I):
                    result['process_label_candidates'].append(value)
        href = node.get('href') or node.get('{http://www.w3.org/1999/xlink}href')
        ref = read_ref(href) if href else None
        if tag == 'image':
            result['images'].append(dict(id=node.get('id'), reference=ref))
        css = node.get('style', '') + (' '.join(node.itertext()) if tag == 'style' else '')
        for value in re.findall(r'url\(\s*[\'\"]?([^\)\'\"]+)[\'\"]?\s*\)', css):
            read_ref(value.strip())
        if tag == 'style' and re.search(r'@import\b', css, re.I):
            errors.append('CSS @import requires manual dependency inspection; not fetched')
        for child in node:
            walk(child, excluded)

    walk(tree)
    if scene_id:
        selected = [item for item in result['images'] if item['id'] == scene_id]
        if len(selected) != 1 or not selected[0]['reference'] or selected[0]['reference']['sha256'] != expected_scene_sha256:
            errors.append('Selected scene is missing, ambiguous or does not match expected image bytes')
            result['scene_binding'] = 'mismatch'
        else:
            result['scene_binding'] = 'matched'
    result['status'] = 'failed' if errors else 'inspected'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path, help='Explicit dependency root; may span sibling artwork/font folders')
    parser.add_argument('--scene-id')
    parser.add_argument('--expected-scene-sha256')
    parser.add_argument('--output', required=True, type=Path, help='New report file; existing files are never overwritten')
    args = parser.parse_args()
    try:
        result = inspect(args.source, args.root, args.scene_id, args.expected_scene_sha256)
        # Exclusive creation protects artwork, manifests and prior reports from accidental overwrite.
        with args.output.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        print(json.dumps({key: result[key] for key in ('status', 'scene_binding', 'requires_visual_review', 'errors')}, ensure_ascii=False))
        return 1 if result['errors'] else 0
    except (OSError, ValueError, ET.ParseError) as exc:
        print(json.dumps(dict(status='failed', reason=str(exc)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

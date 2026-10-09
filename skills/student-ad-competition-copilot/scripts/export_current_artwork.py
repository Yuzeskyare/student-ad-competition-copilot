#!/usr/bin/env python3
"""Copy the validated current print set to a NEW local directory, never publish."""
import argparse
import json
from pathlib import Path
from review_contract import load, read_contract, bound_file, digest, inside, final_state, validate_receipts
from current_artwork_contract import validate_current, required


def export(root, manifest, destination, package_kind='evidence', seal=False):
    root = root.resolve()
    contract, rows = read_contract(root, manifest)
    if not required(manifest, contract, root) or not contract['final_artifacts']:
        raise ValueError('Explicit bound current set is required; never infer selection from directory names')
    if package_kind not in {'evidence','current-files'}:
        raise ValueError('Choose evidence or current-files package')
    source_checks = validate_current(root, manifest, contract)
    state, _ = final_state(root, contract['final_artifacts'], rows)
    if state != contract['content_status']:
        raise ValueError('Declared content status conflicts with current scoped decisions')
    closure = None
    if seal:
        if package_kind != 'evidence':
            raise ValueError('Sealing requires linked process evidence, not only current files')
        control_path = inside(root, manifest.get('execution_control'))
        control = load(control_path)
        if (control.get('run_id') != manifest['run_id'] or control.get('state') != 'stopped'
                or control.get('monitoring') not in {'not-requested', 'revoked'}
                or not isinstance(control.get('basis'), str) or not control['basis'].strip()):
            raise ValueError('Close production and monitoring before sealing evidence')
        closeout_path = bound_file(root, control.get('closeout_evidence'))
        closeout = load(closeout_path)
        if (closeout.get('run_id') != manifest['run_id'] or closeout.get('status') != 'completed'
                or closeout.get('open_production_requests') != [] or not closeout.get('basis')):
            raise ValueError('Sealing needs actual producer completion and closed process records')
        validate_receipts(root, contract, rows)
        closure = dict(control=dict(path=control_path.relative_to(root).as_posix(), sha256=digest(control_path)),
                       closeout=control['closeout_evidence'])
    target = inside(root, destination)
    if target.exists():
        raise ValueError('Use a new destination; preserve previous selections')
    files = {}

    def collect(value, recursive=True):
        if isinstance(value, list):
            for item in value: collect(item, recursive)
        elif isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                path = bound_file(root, value)
                relative = path.relative_to(root).as_posix()
                if relative not in files:
                    files[relative] = (path, value['sha256'])
                    if recursive and path.suffix.lower() == '.json':
                        collect(load(path))
            for key, item in value.items():
                if key not in {'path', 'sha256'}: collect(item, recursive)
    members = contract['final_artifacts']
    if package_kind == 'evidence':
        collect(members)
        if closure:
            collect(closure)
    else:
        if any(result['svg_scan'] is None for result in source_checks):
            raise ValueError('current-files requires inspected SVG dependencies; use evidence for other source types')
        members = []
        for ref in contract['final_artifacts']:
            bundle=ref['current_source']
            member={k:ref[k] for k in ('path','sha256','version','units')}
            member.update(native=bundle['native'],preview=bundle['preview'])
            if bundle.get('scene'):member['scene']=bundle['scene']['file']
            members.append(member)
        collect(members, recursive=False)
    for result in source_checks:
        for dep in (result['svg_scan'] or {}).get('dependencies', []):
            path = Path(dep['path'])
            files[path.relative_to(root).as_posix()] = (path, dep['sha256'])
    if 'CURRENT-ARTWORKS.json' in files:
        raise ValueError('Reserved output index path conflicts with an input')
    # Validate all input paths before copying; exclusive creation never overwrites.
    target.mkdir(parents=True, exist_ok=False)
    copied = []
    for relative, (path, expected) in files.items():
        output = target/relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as handle: handle.write(path.read_bytes())
        if digest(output) != expected or digest(path) != expected:
            raise ValueError('Source changed during export: '+relative)
        copied.append(dict(path=relative, sha256=digest(output)))
    if closure:
        # Recheck the entire linked collection after copying, not just each file
        # at its individual copy time. This is not an OS-level producer lock.
        for relative, (path, expected) in files.items():
            if digest(path) != expected:
                raise ValueError('Evidence changed before seal completion: '+relative)
    index = dict(run_id=manifest['run_id'], members=members, files=copied,package_kind=package_kind,
                 audit_evidence_included=package_kind=='evidence',
                 content_status=contract['content_status'], source_binding_checked=True,
                 approval_granted_by_export=False, visual_quality_certified=False)
    if closure:
        index['seal'] = dict(status='closed-linked-evidence', closure=closure,
                             scope='Collected linked files only; not a lock or an inventory of unlinked late files')
    with (target/'CURRENT-ARTWORKS.json').open('x', encoding='utf-8') as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--destination', required=True, help='New run-relative directory')
    parser.add_argument('--package-kind',choices=['evidence','current-files'],default='evidence',help='evidence includes linked audit history; current-files includes current SVG/artworks/previews/scenes and inspected dependencies only')
    parser.add_argument('--seal', action='store_true', help='Require producer closeout and stopped control, then recheck all linked evidence')
    args = parser.parse_args()
    try:
        result = export(args.run_dir, load(inside(args.run_dir, args.manifest)), args.destination,args.package_kind,args.seal)
        print(json.dumps(dict(status='copied', members=len(result['members']), files=len(result['files']),
                              approval_granted=False)))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps(dict(status='failed', reason=str(exc))))
        return 1


if __name__ == '__main__': raise SystemExit(main())

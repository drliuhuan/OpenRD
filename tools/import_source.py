"""Identify and extract local installers, archives, or installed resource folders.

This tool never executes a supplied game/installer. External 7-Zip and unshield
only unpack containers. Supported datasets bind to the isolated experimental model.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import re
import subprocess
import tempfile
import time

from source_formats import digest, inspect_payload, st1, pcx_png
from source_cb import engine_tables, decode_cb

MEDIA = {'.lvs', '.lv', '.gin', '.byt', '.pcx', '.pci', '.imc', '.thm',
         '.mid', '.wav', '.avi', '.lng', '.bmp', '.jpg', '.png', '.mp3', '.ogg', '.cnf', '.rls', '.ini'}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.pending')
    for attempt in range(4):
        try:
            pending.write_bytes(data)
            os.replace(pending, path)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(.25 * (attempt + 1))


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(args, logs, label):
    result = subprocess.run(list(map(str, args)), capture_output=True,
                            timeout=180, encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    logs.append(dict(label=label, command=list(map(str, args)),
                     returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
    allowed = (0, 1) if label.startswith('container-') else (0,)
    if result.returncode not in allowed:
        raise ValueError(f'{label} failed: {result.stderr[-500:]}')
    return result.stdout


def safe_name(name):
    name = name.replace('\\', '/')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name:
        raise ValueError(f'Unsafe archive path: {name!r}')


def unpack(source, target, seven, unshield, logs, process_cabs=True):
    listing = run([seven, 'l', '-slt', source], logs, 'container-list')
    # Skip the archive's own absolute path, before the entry separator.
    entries = listing.split('----------', 1)[-1]
    expanded_size = 0
    for line in entries.splitlines():
        if line.startswith('Size = ') and line[7:].strip():
            expanded_size += int(line[7:])
            if expanded_size > 4 * 1024 * 1024 * 1024:
                raise ValueError('Archive expanded size exceeds 4 GiB limit')
        if line.startswith('Path = '):
            name = line[7:].replace('\\', '/')
            # These MSZip SFX cabinets label entries /DATA.TAG etc.; 7-Zip
            # extracts them relative to -o. Do not apply this to ZIP/7z paths.
            if 'Type = Cab' in listing and name.startswith('/') and not name.startswith('//'):
                name = name[1:]
            safe_name(name)
        if line.startswith(('Symbolic Link = ', 'Hard Link = ')):
            raise ValueError('Linked archive entries are unsupported')
    run([seven, 'x', source, '-o' + str(target), '-y'], logs, 'container-extract')
    if not process_cabs:
        return
    for cab in list(target.rglob('*')):
        if cab.name.lower() == 'data1.cab':
            if not unshield:
                logs.append(dict(label='InstallShield', status='unshield required', path=str(cab)))
                continue
            cabout = target / ('installshield-' + digest(str(cab.relative_to(target)).encode())[:8])
            cabout.mkdir()
            names = run([unshield, 'l', cab], logs, 'installshield-list')
            for line in names.splitlines():
                match = re.match(r'^\s+\d+\s+(.+)$', line)
                if match:
                    safe_name(match.group(1))
            run([unshield, '-d', cabout, 'x', cab], logs, 'installshield-extract')


def inspect_tree(source, output, seven='7z', unshield=None, catalog=None, engine=None, profiles=None):
    source = source.resolve()
    output = output.resolve()
    if not source.exists():
        raise ValueError('Source does not exist: ' + str(source))
    if output.exists():
        raise ValueError('Output must be a new directory, to preserve prior evidence')
    if source.is_dir() and (output == source or source in output.parents):
        raise ValueError('Output cannot be inside the input folder')
    report = dict(source=str(source), source_kind='folder' if source.is_dir() else 'container',
                  claims=[], logs=[], files=[], embedded=[], errors=[], version_candidates=[], identified_profiles=[])
    output.mkdir(parents=True)
    if source.is_file():
        report['source_sha256'] = hash_file(source)
        if catalog:
            data = json.loads(Path(catalog).read_text(encoding='utf-8'))
            report['claims'] = [x for x in data.get('demo_installers', [])
                                if x.get('sha256') == report['source_sha256']]
    try:
        with tempfile.TemporaryDirectory(prefix='openrd-import-') as work:
            tree = source
            if source.is_file():
                tree = Path(work) / 'unpacked'
                unpack(source, tree, seven, unshield, report['logs'])
            tables = None
            engines = [Path(engine)] if engine else [p for p in tree.rglob('*')
                        if p.name.lower() == 'rich diamond.exe' and 'crack' not in {x.lower() for x in p.parts}]
            for candidate in engines:
                try:
                    proposed = engine_tables(candidate)
                except (ValueError, struct.error) as exc:
                    if engine:
                        raise
                    report['logs'].append(dict(label='cb-engine-candidate', path=str(candidate), error=str(exc)))
                    continue
                if tables is not None and tables[:2] != proposed[:2]:
                    raise ValueError('Multiple CB table families; specify --engine')
                tables = proposed
                report['cb_engine'] = dict(path=str(candidate), sha256=hash_file(candidate), table=proposed[2])
            for path in sorted(tree.rglob('*')):
                if not path.is_file():
                    continue
                if path.is_symlink() or tree.resolve() not in path.resolve().parents:
                    raise ValueError('Input contains external links')
                rel = path.relative_to(tree).as_posix()
                safe_name(rel)
                ext = path.suffix.lower()
                if ext not in MEDIA and ext != '.exe':
                    continue
                if path.stat().st_size > 128 * 1024 * 1024:
                    report['errors'].append(dict(path=rel, error='File exceeds 128 MiB inspection limit'))
                    continue
                raw = path.read_bytes()
                item = dict(path=rel, bytes=len(raw), sha256=digest(raw), head=raw[:16].hex())
                report['files'].append(item)
                if ext == '.exe':
                    if path.name.lower()=='cceng.exe' and 'crack' not in {x.lower() for x in path.parts}:
                        from source_scripts import byt
                        start=0
                        while True:
                            pos=raw.find(b'CCIb10',start)
                            if pos<0:break
                            start=pos+6
                            for mode in ('inline','reference24'):
                                try:script=byt(raw[pos:pos+1024*1024],mode,embedded=True)
                                except ValueError:continue
                                if script['object_count']<100 or sum(r['opcode']==2 for r in script['records'])<10:continue
                                content=raw[pos:pos+script['stop_offset']]
                                script=byt(content,mode)
                                name=f'embedded/{digest(raw)[:12]}-{pos:x}.byt'
                                save(output/name,content)
                                save(output/'inspection'/(name+'.json'),json.dumps(script,ensure_ascii=False).encode('utf-8'))
                                report.setdefault('embedded_scripts',[]).append(dict(source=rel,offset=pos,path=name,
                                    sha256=digest(content),script={k:v for k,v in script.items() if k!='records'}))
                                break
                    if path.name.lower() == 'cceng.exe' and 'crack' not in {x.lower() for x in path.parts}:
                        from source_legacy import embedded_1999
                        levels = embedded_1999(raw)
                        if levels:
                            name = f'embedded/{digest(raw)[:12]}-1999-maps.json'
                            payload = dict(format='1999 embedded', count=len(levels), levels=levels)
                            content = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                            save(output / name, content)
                            report['embedded'].append(dict(source=rel, path=name, bytes=len(content),
                                sha256=digest(content), levels=len(levels), format='1999 embedded'))
                    # No EXE is copied or run; carve only strictly validated embedded ST1.
                    start = 0
                    while True:
                        pos = raw.find(b'ST1\n', start)
                        if pos < 0:
                            break
                        start = pos + 4
                        try:
                            levels = st1(raw[pos:])
                            content = raw[pos:pos + levels['consumed']]
                            name = f'embedded/{digest(raw)[:12]}-{pos:x}.st1'
                            save(output / name, content)
                            save(output / (name + '.json'), json.dumps(levels, ensure_ascii=False).encode('utf-8'))
                            report['embedded'].append(dict(source=rel, offset=pos, path=name,
                                bytes=len(content), sha256=digest(content), levels=levels['count']))
                        except (ValueError, RecursionError):
                            pass
                    continue
                save(output / 'raw' / rel, raw)
                try:
                    cb = raw[:2] == b'\xcb\xfe' and tables is not None
                    plain, detail = inspect_payload(decode_cb(raw, tables) if cb else raw)
                    if cb:
                        detail.update(wrapper='CB FE', input_bytes=len(raw), input_sha256=digest(raw))
                    item['decoded'] = {k: v for k, v in detail.items() if k != 'levelset'}
                    if plain[:6] == b'CCIb10':
                        from source_scripts import identify_byt
                        script = identify_byt(plain)
                        item['script'] = {k: v for k, v in script.items() if k != 'records'}
                        save(output / 'inspection' / (rel + '.json'),
                             json.dumps(script, ensure_ascii=False).encode('utf-8'))
                    if plain[:6] in (b'CCIg11',b'CCIg12'):
                        from source_scripts import gin
                        script=gin(plain)
                        item['graphics_script']={k:v for k,v in script.items() if k!='records'}
                        save(output/'inspection'/(rel+'.json'),json.dumps(script,ensure_ascii=False).encode('utf-8'))
                    if plain[:3] == b'i\x0ff':
                        from source_theme import parse as parse_theme
                        theme = parse_theme(plain)
                        item['theme_script'] = {k: v for k, v in theme.items() if k != 'records'}
                        save(output / 'inspection' / (rel + '.json'),
                             json.dumps(theme, ensure_ascii=False).encode('utf-8'))
                    if raw[:1] == b'\xca' or cb:
                        save(output / 'decoded' / rel, plain)
                    if detail.get('format') == 'PCX header candidate':
                        png, pixels = pcx_png(plain)
                        save(output / 'images' / (rel + '.png'), png)
                        item['pcx'] = pixels
                    if 'levelset' in detail:
                        levels = detail['levelset']
                        item['levelset'] = {k: v for k, v in levels.items() if k != 'levels'}
                        save(output / 'inspection' / (rel + '.json'),
                             json.dumps(levels, ensure_ascii=False).encode('utf-8'))
                except (ValueError, RecursionError, struct.error) as exc:
                    report['errors'].append(dict(path=rel, error=str(exc)))
            if catalog:
                data = json.loads(Path(catalog).read_text(encoding='utf-8'))
                level_keys = {f['sha256'] for f in report['files'] if f['path'].lower().endswith('.lvs')}
                report['version_candidates'] = [x['id'] for x in data.get('level_files', [])
                                                if x.get('sha256') in level_keys]
                report['claims_note'] = 'Catalog labels are provider claims; shared resource hashes identify a family, not an exact engine version.'
            profile_file = Path(profiles) if profiles else Path(__file__).with_name('source_profiles.json')
            if profile_file.exists():
                known = json.loads(profile_file.read_text(encoding='utf-8'))
                hashes = {f['sha256'] for f in report['files']}
                for profile in known['profiles']:
                    anchors = set(profile['required_sha256'])
                    if anchors and anchors <= hashes:
                        report['identified_profiles'].append(profile)
                exact = [p for p in report['identified_profiles']
                         if p.get('package_sha256') == report.get('source_sha256')]
                if exact:
                    report['identified_profiles'] = exact
            report['pending_payloads'] = [f['path'] for f in report['files']
                if f.get('decoded', {}).get('format') in ('CB resource wrapper', 'unknown CB variant')]
            report['resource_file_count'] = sum(Path(f['path']).suffix.lower() != '.exe' for f in report['files'])
            report['nested_installer_candidates'] = [f['path'] for f in report['files']
                if Path(f['path']).suffix.lower() == '.exe'
                and ('complete' in f['path'].lower() or 'reduced' in f['path'].lower() or Path(f['path']).name.lower() == 'rddemo.exe')]
            from source_framework import bind
            report['framework']=bind(output,report)
    except Exception as exc:
        report['errors'].append(dict(stage='unpack-or-scan', error=str(exc)))
        raise
    finally:
        save(output / 'report.json', json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    return report


def inspect(source, output, seven='7z', unshield=None, catalog=None, engine=None, profiles=None,auto_tools=False):
    """Automatically expand input forms; keep distinct source bundles isolated."""
    from source_inputs import prepare, input_kind
    if seven == '7z' and not shutil.which(seven):
        installed = Path(os.environ.get('ProgramFiles','C:/Program Files')) / '7-Zip/7z.exe'
        if installed.is_file():
            seven = str(installed)
    if not unshield:
        from runtime_tools import find_unshield
        unshield=find_unshield()
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.exists():
        raise ValueError('Source does not exist: ' + str(source))
    if output.exists():
        raise ValueError('Output must be a new directory, to preserve prior evidence')
    if source.is_dir() and source in output.parents:
        raise ValueError('Output cannot be inside the input folder')
    kind = input_kind(source)
    with tempfile.TemporaryDirectory(prefix='openrd-auto-input-') as temporary:
        logs = []
        try:
            roots = prepare(source, Path(temporary), seven, unshield, logs,auto_tools=auto_tools)
            if not roots:
                raise ValueError('No supported game resource folder found after automatic unpacking')
            results = []
            dataset_keys = set()
            for index, candidate in enumerate(roots):
                target = output if len(roots) == 1 else output / 'sources' / str(index + 1)
                result = inspect_tree(candidate['path'], target, seven, unshield, catalog, engine, profiles)
                result['source'] = str(source)
                result['source_kind'] = kind
                result['input_form'] = ('installer-folder' if source.is_dir() and
                    any(log.get('label') == 'automatic-layer' for log in logs) else
                    'game-folder' if source.is_dir() else kind)
                result['input_label'] = candidate['label']
                if source.is_file():
                    result['source_sha256'] = hash_file(source)
                    exact = [p for p in result['identified_profiles']
                             if p.get('package_sha256') == result['source_sha256']]
                    if exact:
                        result['identified_profiles'] = exact
                    if catalog:
                        known = json.loads(Path(catalog).read_text(encoding='utf-8'))
                        result['claims'] = [p for p in known.get('demo_installers', [])
                                            if p.get('sha256') == result['source_sha256']]
                result['input_chain'] = logs
                save(target / 'report.json', json.dumps(result, ensure_ascii=False, indent=2).encode())
                # An already-extracted folder may also retain its original CAB.
                # Deduplicate identical game payloads, excluding setup metadata.
                resource_keys = sorted({Path(f['path']).name.casefold()+':'+f['sha256'] for f in result['files']
                    if (Path(f['path']).suffix.lower() in MEDIA - {'.ini','.cnf','.exe','.dll'} or
                    Path(f['path']).name.casefold() in ('cceng.exe','rich diamond.exe')) and
                    Path(f['path']).name.casefold() != 'setup.bmp'})
                dataset_key = digest(json.dumps(resource_keys).encode())
                if dataset_key in dataset_keys:
                    logs.append(dict(label='duplicate-dataset',path=candidate['label'],fingerprint=dataset_key))
                    continue
                dataset_keys.add(dataset_key)
                results.append((target, result))
            if len(roots) == 1:
                if not results[0][1]['framework']['ready']:
                    raise ValueError('No model-ready dataset: ' + results[0][1]['framework'].get('reason','no levels'))
                return results[0][1]
            bundles, files, errors, embedded, identified = [], [], [], [], []
            for target, result in results:
                prefix = target.relative_to(output).as_posix()
                files.extend(dict(item, path=prefix + '/' + item['path']) for item in result['files'])
                errors.extend(dict(item, source=prefix) for item in result['errors'])
                embedded.extend(dict(item, source_bundle=prefix) for item in result['embedded'])
                identified.extend(result['identified_profiles'])
                if result['framework']['ready']:
                    bundles.append(dict(path=prefix + '/framework/bundle.json', label=result['input_label']))
            if not bundles:
                raise ValueError('Imported sources have no supported model levels')
            from source_framework import combine
            framework = combine(output, bundles)
            report = dict(source=str(source), source_kind=kind, files=files, embedded=embedded,
                          errors=errors, identified_profiles=identified, framework=framework,
                          input_chain=logs, sources=[dict(path=t.relative_to(output).as_posix(),
                          label=r['input_label'], framework=r['framework']) for t,r in results],
                          pending_payloads=[p for _,r in results for p in r['pending_payloads']])
            if source.is_file():
                report['source_sha256'] = hash_file(source)
            save(output / 'report.json', json.dumps(report, ensure_ascii=False, indent=2).encode())
            return report
        except Exception as exc:
            report_path = output / 'report.json'
            failure = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else dict(source=str(source), source_kind=kind, input_chain=logs, errors=[])
            failure['errors'].append(dict(stage='automatic-input',error=str(exc)))
            save(report_path, json.dumps(failure,ensure_ascii=False,indent=2).encode())
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seven-zip', default='7z')
    parser.add_argument('--unshield')
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--engine', type=Path, help='Local engine supplying CB FE tables; read-only')
    parser.add_argument('--profiles', type=Path, help='Verified source fingerprint catalog')
    parser.add_argument('--download-tools',action='store_true',help='Download missing unshield from the verified Scoop package when required')
    args = parser.parse_args()
    result = inspect(args.source, args.output, args.seven_zip, args.unshield, args.catalog, args.engine, args.profiles,auto_tools=args.download_tools)
    print(json.dumps(dict(files=len(result['files']), embedded=len(result['embedded']),
                         errors=len(result['errors']), framework=result['framework'],
                         report=str(args.output / 'report.json')), ensure_ascii=False))
    if result['errors']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

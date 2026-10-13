"""Bind source data to the shared ISO-derived CPU engine, without built-in assets."""
import json
from pathlib import Path
from source_formats import digest


def bind(output, report):
    from import_source import save
    output = Path(output)
    scripts = [(f['path'], f['script']) for f in report['files'] if 'script' in f]
    scripts.extend((f['path'],f['script']) for f in report.get('embedded_scripts',[]) if 'script' in f)
    if len(scripts) != 1:
        return dict(ready=False, reason='A unique parsed BYT is required')
    path, script = scripts[0]
    byt = json.loads((output / 'inspection' / (path + '.json')).read_text(encoding='utf-8'))
    definitions = {}
    for record in byt['records']:
        if record['opcode'] == 1:
            definitions.setdefault(record['tile_code'], record)
    levels = []
    seen_levelsets = set()
    for f in report['files']:
        if 'levelset' not in f:
            continue
        if f['sha256'] in seen_levelsets:
            continue
        seen_levelsets.add(f['sha256'])
        ls = json.loads((output / 'inspection' / (f['path'] + '.json')).read_text(encoding='utf-8'))
        for level in ls['levels']:
            variants = level.get('variants', [dict(table=None, rows=level['rows'])])
            # Identical tables produce one entry; differing CCLS tables stay explicit.
            unique = set()
            for variant in variants:
                key = json.dumps(variant['rows'])
                if key in unique:
                    continue
                unique.add(key)
                levels.append(dict(name=level['name'], number=level['number'], rows=variant['rows'],
                                   source=f['path'], variant=variant['table']))
    for embedded in report['embedded']:
        p = output / embedded['path']
        if p.suffix != '.json':
            p = Path(str(p) + '.json')
        ls = json.loads(p.read_text(encoding='utf-8'))
        levels.extend(dict(name=l['name'], number=l['number'], rows=l['rows'],
                           source=embedded['source'], variant=None) for l in ls['levels'])
    for n, level in enumerate(levels):
        level['id'] = str(n + 1)
        unknown = sorted({tile for row in level['rows'] for tile in row} - set(definitions))
        level['unknown_tiles'] = unknown
        level['loadable'] = not unknown
    media = []
    for f in report['files']:
        if 'pcx' in f:
            media.append(dict(source=f['path'], path='images/' + f['path'] + '.png'))
        elif Path(f['path']).suffix.lower() in ('.wav', '.mid', '.mp3', '.avi'):
            media.append(dict(source=f['path'], path='raw/' + f['path']))
    graphics = None
    gin_entries = [f for f in report['files'] if 'graphics_script' in f]
    if len(gin_entries) == 1:
        graphics = 'inspection/' + gin_entries[0]['path'] + '.json'
    preview={}
    if graphics:
        gin=json.loads((output/graphics).read_text(encoding='utf-8'))
        if gin['format']=='CCIg11':
            from resource_frames import expand,first_frames,signed16
            bitmaps={r['bitmap_id']:r['text'] for r in gin['records'] if r['opcode']==4}
            sprites={r['sprite_id']:r for r in gin['records'] if r['opcode']==35}
            resources={r['resource_id']:r for r in gin['records'] if r['opcode']==36}
            for rid in resources:
                try:frames=first_frames(expand(rid,resources,sprites))
                except (ValueError,KeyError):continue
                if not frames:continue
                components=[]
                # Preview a static first frame, not a native state/time selector.
                for frame in frames[:1]:
                    sprite=frame['sprite']
                    if sprite['empty_rectangle']:continue
                    filename=bitmaps.get(sprite['bitmap_id'],'').lower()
                    matches=[m for m in media if Path(m['source']).name.lower()==filename and m['path'].startswith('images/')]
                    if len(matches)!=1:continue
                    l,t,r,b=sprite['rectangle'];ox,oy=map(signed16,sprite['origin_raw']);dx,dy=map(signed16,frame['offset_raw'])
                    components.append(dict(path=matches[0]['path'],crop=[l,t,r-l+1,b-t+1],offset=[l-ox+dx,t-oy+dy]))
                if components:preview[str(rid)]=components
    bundle = dict(schema=1, byt='inspection/' + path + '.json', gin=graphics,
                  profiles=[p['id'] for p in report['identified_profiles']], levels=levels, media=media,preview=preview,
                  runtime='shared ISO-derived CPU interpreter; source declarations and levels are user data',
                  limitations=['Original timing and native window/rendering are not reproduced',
                               'CCLS tables are explicit alternatives; native default selection not established',
                               'No source native engine is run; source scripts use the same CPU instruction semantics',
                               'Source-specific data does not certify native-version gameplay equivalence'])
    from source_access import restrict
    restrict(bundle)
    content = json.dumps(bundle, ensure_ascii=False).encode('utf-8')
    save(output / 'framework/bundle.json', content)
    return dict(ready=bool(levels), path='framework/bundle.json', sha256=digest(content),
                levels=len(levels), loadable=sum(l['loadable'] for l in levels),
                mode='experimental logical model', native_equivalence=False)


def combine(output, sources):
    """Namespace datasets instead of merging their scripts or resource IDs."""
    from import_source import save
    output = Path(output)
    levels, media, previews, profiles, datasets = [], [], {}, [], []
    for n, source in enumerate(sources, 1):
        bundle = json.loads((output / source['path']).read_text(encoding='utf-8'))
        prefix = Path(source['path']).parent.parent.as_posix()
        dataset = str(n)
        script = prefix + '/' + bundle['byt']
        for level in bundle['levels']:
            levels.append(dict(level, id=dataset + '-' + level['id'], dataset=dataset,
                               byt=script, name=source['label'] + ' · ' + str(level['name'])))
        media.extend(dict(item, path=prefix + '/' + item['path']) for item in bundle['media'])
        previews[dataset] = {rid: [dict(component, path=prefix + '/' + component['path'])
                                 for component in components]
                             for rid, components in bundle.get('preview', {}).items()}
        profiles.extend(bundle['profiles'])
        datasets.append(dict(id=dataset, label=source['label'], bundle=source['path']))
    bundle = dict(schema=2, byt=levels[0]['byt'], gin=None, profiles=profiles,
                  levels=levels, media=media, preview={}, previews=previews, datasets=datasets,
                  runtime='isolated experimental CPU source models',
                  limitations=['Each source uses its own BYT and resource namespace',
                               'Original timing, source access rights and full rendering are not certified'])
    from source_access import restrict
    restrict(bundle)
    content = json.dumps(bundle, ensure_ascii=False).encode('utf-8')
    save(output / 'framework/bundle.json', content)
    return dict(ready=True, path='framework/bundle.json', sha256=digest(content),
                levels=len(levels), loadable=sum(l['loadable'] for l in levels),
                sources=len(datasets), native_equivalence=False)

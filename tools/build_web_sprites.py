"""Read-only PCX/GIN to Canvas atlas, preserving researched sprite origins."""
import base64,json,os
from pathlib import Path
import numpy as np
from PIL import Image
import rdtool
from inspect_iso import inspect
from pcx_decode import decode_pcx
from resource_frames import expand,first_frames,signed16
from runtime_files import save


def main(root=None,iso=None):
    root=Path(root) if root else Path(__file__).resolve().parent.parent
    iso=Path(iso) if iso else root/'Rich Diamond.ISO'
    target=root/'web/assets';target.mkdir(parents=True,exist_ok=True)
    gin=json.loads((root/'evidence/gin-complete-index.json').read_text())
    sprites={r['sprite_id']:r for r in gin['records'] if r['opcode']==35};resources={r['resource_id']:r for r in gin['records'] if r['opcode']==36}
    if iso.is_dir():
        pcx=next(p for p in iso.iterdir() if p.is_file() and p.name.upper()=='ICONS.PCX')
        raw=pcx.read_bytes()
    else:
        entry=next(e for e in inspect(iso)['files'] if e['path']=='ICONS.PCX')
        with iso.open('rb') as source:source.seek(entry['offset']);raw=source.read(entry['size'])
    indexes,palette,_=decode_pcx(rdtool.cc_decompress(raw) if raw[:1]==b'\xca' else raw)
    placements={};x=y=rowheight=0;components={};unsupported=[]
    for sid,sprite in sprites.items():
        if sprite['empty_rectangle']:continue
        l,t,r,b=sprite['rectangle'];w=r-l+1;h=b-t+1
        if x+w>2048:x=0;y+=rowheight+2;rowheight=0
        placements[sid]=dict(x=x,y=y,w=w,h=h,selector=sprite['selector_raw'],dx=l-signed16(sprite['origin_raw'][0]),dy=t-signed16(sprite['origin_raw'][1]));x+=w+2;rowheight=max(rowheight,h)
    mask_atlas=Image.new('RGBA',(2048,y+rowheight),(0,0,0,0))
    atlas=Image.new('RGBA',(2048,y+rowheight),(0,0,0,0));shadow=Image.new('RGBA',atlas.size,(0,0,0,0))
    mask_colors=Image.new('RGBA',atlas.size,(0,0,0,0));masked_source=Image.new('RGBA',atlas.size,(0,0,0,0))
    for sid,p in placements.items():
        l,t,r,b=sprites[sid]['rectangle'];crop=indexes[t:b+1,l:r+1]
        rgba=np.zeros((*crop.shape,4),dtype=np.uint8);rgba[:,:,:3]=palette[crop];rgba[:,:,3]=np.where((crop!=16)&(crop!=32),255,0)
        atlas.paste(Image.fromarray(rgba),(p['x'],p['y']))
        mask_colors.paste(Image.fromarray(rgba),(p['x'],p['y']))
        source_rgba=rgba.copy();source_rgba[:,:,3]=np.where(crop!=16,255,0)
        masked_source.paste(Image.fromarray(source_rgba),(p['x'],p['y']))
        mask_rgba=np.zeros((*crop.shape,4),dtype=np.uint8);mask_rgba[:,:,:3]=255;mask_rgba[:,:,3]=np.where(crop!=16,255,0);mask_atlas.paste(Image.fromarray(mask_rgba),(p['x'],p['y']))
        # Selector 1 can contain BOTH palette pixels and index43 effects.
        # Alien walking bodies also use this selector: preserve colored pixels.
        rgba[crop==43,:3]=0
        rgba[:,:,3]=np.where(crop==43,64,np.where((crop!=16)&(crop!=32),255,0))
        shadow.paste(Image.fromarray(rgba),(p['x'],p['y']))
    for rid in resources:
        try:
            frames=first_frames(expand(rid,resources,sprites))
            components[rid]=[]
            for frame in frames:
                sprite=frame['sprite'];sid=frame['sprite_id']
                if sid not in placements:continue
                l,t,_,_=sprite['rectangle'];ox,oy=map(signed16,sprite['origin_raw']);dx,dy=map(signed16,frame['offset_raw'])
                components[rid].append(dict(sprite=sid,dx=dx+l-ox,dy=dy+t-oy))
        except ValueError:unsupported.append(rid)
    for name,img in [('sprites.png',atlas),('shadows.png',shadow),('masks.png',mask_atlas),('mask-colors.png',mask_colors),('masked-source.png',masked_source)]:
        pending=target/(name+'.pending');img.save(pending,format='PNG');os.replace(pending,target/name)
    manifest=dict(sprites=placements,resources=components,unsupported=unsupported,
        coordinate_index_tables=json.loads((root/'evidence/native-coordinate-index-tables.json').read_text(encoding='utf-8'))['tables'],
        mask_colors='data:image/png;base64,'+base64.b64encode((target/'mask-colors.png').read_bytes()).decode('ascii'),
        masked_source='data:image/png;base64,'+base64.b64encode((target/'masked-source.png').read_bytes()).decode('ascii'),
        terrain_layers=[c['values_raw'] for c in next(r for r in gin['records'] if r['opcode']==38)['commands'] if c['subcommand']==4],
        selectors={rid:{k:r[k] for k in ('subtype','base_resource_id','parameters_raw','resource_references','sprite_reference') if k in r} for rid,r in resources.items()},
        policy='Ordinary atlas skips16/32; masked source skips key16, mask16 skips/mask32 copies/other mask indices write palette colors; selector1 index43 remains approximate')
    save(target/'sprites.json',json.dumps(manifest,separators=(',',':')))
    save(root/'evidence/web-sprite-atlas.json',json.dumps(dict(sprites=len(placements),resources=len(components),unsupported=unsupported,size=list(atlas.size),policy=manifest['policy']),indent=2)+'\n')
    print(json.dumps(dict(sprites=len(placements),resources=len(components),size=list(atlas.size))))


if __name__=='__main__':main()

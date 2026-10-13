"""Automatic, bounded input expansion; user-supplied programs are never run."""
ARCHIVES = {'.zip', '.7z', '.rar', '.cab', '.tar', '.gz', '.bz2', '.xz', '.iso', '.mdf', '.bin'}
EXCLUDED = {'crack', 'cracks', 'keygen', 'patches'}

def cab_magic(path):
    with path.open('rb') as stream:return stream.read(4)


def input_kind(source):
    if source.is_dir():
        return 'folder'
    if source.suffix.lower() in ('.iso', '.mdf', '.bin'):
        return 'disc'
    return 'installer' if source.suffix.lower() == '.exe' else 'archive'


def prepare(source, work, seven, unshield, logs,auto_tools=False):
    from import_source import unpack, run, digest, hash_file, safe_name, save
    roots, seen, containers = [], set(), [0]
    total = [0]
    def excluded(path):
        return any(p.casefold() in EXCLUDED for p in path.parts)
    def validate_tree(tree):
        size, entries = 0, 0
        for p in tree.rglob('*'):
            entries += 1
            if entries > 100000:
                raise ValueError('Input exceeds 100000 filesystem entries')
            if p.is_symlink() or tree.resolve() not in p.resolve().parents:
                raise ValueError('Input contains external links')
            if p.is_file():
                size += p.stat().st_size
            if size > 4 * 1024**3:
                raise ValueError('Input tree exceeds 4 GiB limit')
        return size
    def folder(tree, label, depth):
        validate_tree(tree)
        files = sorted(p for p in tree.rglob('*') if p.is_file() and not excluded(p.relative_to(tree)))
        # A loose dataset is kept separate from children unpacked into TEMP.
        byts = [p for p in files if p.suffix.lower() == '.byt']
        if len({p.parent for p in byts}) > 1:
            selected = set()
            for script in byts:
                candidate = script.parent
                while candidate.parent != tree.parent:
                    parent = candidate.parent
                    if sum(parent in p.parents for p in byts) != 1:
                        break
                    candidate = parent
                if candidate not in selected:
                    selected.add(candidate)
                    roots.append(dict(path=candidate,label=label+' / '+candidate.relative_to(tree).as_posix()))
        elif byts or any(p.name.casefold() == 'cceng.exe' for p in files):
            roots.append(dict(path=tree, label=label))
        for p in files:
            if p.suffix.lower() in ARCHIVES or p.suffix.lower() == '.exe':
                expand(p, label + ' / ' + p.relative_to(tree).as_posix(), depth + 1, optional=True)
    def expand(path, label, depth, optional=False):
        nonlocal unshield
        if depth > 5:
            raise ValueError('Nested input exceeds 5 container layers')
        if path.name.casefold() in ('cceng.exe', 'ccnteng.exe', 'rich diamond.exe'):
            return
        if path.suffix.lower() == '.exe' and any(v in path.stem.casefold() for v in ('crack', 'keygen', 'patch')):
            return
        # Inspect the container only. Plain PE code, game EXEs and opaque CABs
        # are not installers merely because of their extension.
        disc_entries = None
        if path.suffix.lower() in ('.iso', '.mdf', '.bin'):
            from source_disc import Disc
            try:
                disc = Disc(path)
                entries = list(disc.entries())
                anchors = [name.rsplit('/',1)[0] if '/' in name else ''
                           for name,offset,size,directory in entries if not directory and
                           (name.rsplit('/',1)[-1].casefold() in ('rddemo.exe','richdimd.byt','rich diamond.byt','rddemo.byt'))]
                disc_entries = [entry for entry in entries if not entry[3] and
                                (not anchors or any(not a or entry[0].casefold().startswith(a.casefold()+'/') for a in anchors))]
                if sum(entry[2] for entry in disc_entries) > 4 * 1024**3:
                    raise ValueError('Disc extraction exceeds 4 GiB limit')
                mode = 'iso9660'
            except ValueError as exc:
                logs.append(dict(label='disc-native-probe',path=label,error=str(exc)))
        if disc_entries is not None:
            pass
        elif path.suffix.lower()=='.cab' and cab_magic(path)==b'ISc(':
            if not unshield:
                if optional and not auto_tools:
                    return
                from runtime_tools import resolve_unshield
                unshield=resolve_unshield(seven=seven,download=auto_tools)
            try:
                listing = run([unshield, 'l', path], logs, 'installshield-list')
            except ValueError:
                if optional:
                    logs.append(dict(label='opaque-cab-skipped',path=label))
                    return
                raise
            import re
            for line in listing.splitlines():
                match = re.match(r'^\s+\d+\s+(.+)$', line)
                if match:
                    safe_name(match.group(1))
            mode = 'installshield'
        else:
            try:
                listing = run([seven, 'l', '-slt', path], logs, 'container-probe')
            except ValueError:
                if optional:
                    logs.append(dict(label='opaque-file-skipped', path=label))
                    return
                raise
            types = [line[7:].strip().casefold() for line in listing.split('----------',1)[0].splitlines() if line.startswith('Type = ')]
            if not types or all(t in ('pe', 'coff', 'elf') for t in types):
                if optional:
                    return
                raise ValueError('Input is not a supported archive or installer')
            mode = types[-1]
        key = hash_file(path)
        if mode == 'installshield' and re.fullmatch(r'data\d+\.cab',path.name,re.IGNORECASE):
            # InstallShield cabinets depend on neighbouring headers/volumes.
            companions = sorted(p for p in path.parent.iterdir() if p.is_file() and
                                re.fullmatch(r'data\d+\.(cab|hdr)',p.name,re.IGNORECASE))
            key = digest('|'.join(p.name.casefold()+':'+hash_file(p) for p in companions).encode())
        if key in seen:
            logs.append(dict(label='duplicate-container', path=label, sha256=key))
            return
        seen.add(key)
        containers[0] += 1
        if containers[0] > 32:
            raise ValueError('Input exceeds 32 distinct unpacked containers')
        target = work / ('container-' + str(containers[0]))
        if mode == 'iso9660':
            estimated = sum(entry[2] for entry in disc_entries)
        elif mode == 'installshield':
            estimated = sum(int(m.group(1)) for line in listing.splitlines()
                            if (m := re.match(r'^\s+(\d+)\s+.+$',line)))
        else:
            estimated = sum(int(line[7:]) for line in listing.split('----------',1)[-1].splitlines()
                            if line.startswith('Size = ') and line[7:].strip())
            if 'Encrypted = +' in listing:
                raise ValueError('Password-protected input requires prior local decryption')
        if total[0] + estimated > 4 * 1024**3:
            raise ValueError('Cumulative expanded input exceeds 4 GiB limit')
        if mode == 'iso9660':
            target.mkdir()
            for name,offset,length,directory in disc_entries:
                safe_name(name)
                if length > 128 * 1024**2:
                    raise ValueError('Disc entry exceeds 128 MiB extraction limit')
                save(target / name, disc.read(offset,length))
            logs.append(dict(label='disc-extract',path=label,sector=disc.stride,
                             header=disc.header,files=len(disc_entries)))
        elif mode == 'installshield':
            target.mkdir()
            try:
                run([unshield, '-d', target, 'x', path], logs, 'installshield-extract')
            except ValueError as exc:
                if optional:
                    logs.append(dict(label='optional-installshield-failed',path=label,error=str(exc)))
                    return
                raise
        else:
            unpack(path, target, seven, unshield, logs, process_cabs=False)
        size = validate_tree(target)
        total[0] += size
        if total[0] > 4 * 1024**3:
            raise ValueError('Cumulative unpacked input exceeds 4 GiB limit')
        logs.append(dict(label='automatic-layer', input=label, type=mode, depth=depth,
                         sha256=key, expanded_bytes=size))
        folder(target, label, depth)
    if source.is_dir():
        folder(source, source.name, 0)
    else:
        expand(source, source.name, 1)
    return roots

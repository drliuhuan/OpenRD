"""Open the user's approved first-five trial maps; retain all later gates."""
import hashlib
import json

# Content fingerprints, generated from the seven audited imports. Metadata alone
# (profile, ordinal, access_allowed) never grants access to another map.
APPROVED_ROWS = frozenset(('095d8209646ba8f0e3fa909f3a573328a71e8a2ae3a8be10a8f9bea2cb24b7b8', '26b71f7f38f2f1a6432a22ecd2a4e733e159306db154c8bf905ada42545c9ae0', '2c1b0f5d2eac24cab2fb98801379805d8a148396d4569f4d1bb86594077555a5', '40f11a93497e1f959f9f234e567b0a1885a7b9aa162cdabad8e09668367cfb51', '5435932768443bfaf030e509d87faf2508d2bc5941f06b7e67ed646cdfb729b2', '6ad6218165bf233417a79b5f055d4f81dad09f22174a33275f2ad4181def77f1', '7bfe02d13fe6220037c40eccb0698cc706af91c35e2cc474bd2bcd499ec63f68', '81e489a67649196eb5909132f526564b5d642d08a4f1b913138d836c74265412', '868a90de82b93937386bb5559f2c4cde05d919608ba076979be794c3f806650a', '98d409967f5f89c0c328ef0f598d4666a5cdd93de4ff5cedef3803b94b092687', '9fca08b273b05762830d92bc0de2b7b8c859b373411996cb016a3c8e87960519', 'b14172fb6f800a27119ffe972789b24841a831abfac9fc6c58b192ef4d022b30', 'b409d8f617a6b542eb523820fc06f845e9599b09b8e3a648857eaf7343a4af86', 'cc0144696a2f9ae840387dd42286dec06ca10b02f6f25a21c282cf0691e6663d', 'ec43a385308a4efa464fa822eb436a2eccc339cb989664e21cced9e9af6a1f4e', 'ed5ff674cd3e62bd4d03b762e00506a800e3ac5cb136e0a578ddbf452dc9416f'))

MESSAGE = (
    '仅开放已核对来源的前5关；第6关及其他未核实关卡暂不开放。'
    '可使用合法持有的已核验基准 ISO，或其正式/演示数据目录。 '
    'Native demo/licensed access scope is not verified for this source. '
    'Levels are not available: included maps do not establish permission to play. '
    'Use your lawfully held verified reference ISO or its full-game/demo data directory.'
)


def restrict(bundle):
    """Apply policy from this engine, never from user-supplied access flags."""
    for level in bundle.get('levels', []):
        rows = json.dumps(level.get('rows', []), separators=(',', ':')).encode('ascii')
        number = level.get('number')
        allowed = type(number) is int and 1 <= number <= 5 and hashlib.sha256(rows).hexdigest() in APPROVED_ROWS
        unknown = level.get('unknown_tiles', [])
        # Only the fingerprinted, explicitly approved map may use the native
        # undefined-tail compatibility path. Unknown interiors remain closed.
        native_tail = allowed and unknown == [255] and all(
            255 not in row or all(t == 255 for t in row[row.index(255):])
            for row in level.get('rows', []))
        supported = not unknown or native_tail
        level['tiles_supported'] = supported
        level['loadable'] = allowed and supported
        level['access_allowed'] = allowed
    bundle['access'] = dict(status='first-five-approved',
        playable_levels=sum(l['loadable'] for l in bundle.get('levels', [])), reason=MESSAGE)
    return bundle


def require_playable(bundle):
    restrict(bundle)
    if not any(l['loadable'] for l in bundle.get('levels', [])):
        raise ValueError(MESSAGE)
    return bundle

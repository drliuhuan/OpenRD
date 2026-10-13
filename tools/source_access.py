"""Keep source-level access closed until native demo scope is verified."""

MESSAGE = (
    '此来源的原版试玩/授权范围尚未核实，暂不开放关卡；包内包含地图不代表允许游玩。'
    '可使用合法持有的已核验基准 ISO，或其正式/演示数据目录。 '
    'Native demo/licensed access scope is not verified for this source. '
    'Levels are not available: included maps do not establish permission to play. '
    'Use your lawfully held verified reference ISO or its full-game/demo data directory.'
)


def restrict(bundle):
    """Apply policy from this engine, never from user-supplied access flags."""
    for level in bundle.get('levels', []):
        level.setdefault('tiles_supported', bool(level.get('loadable')))
        level['loadable'] = False
        level['access_allowed'] = False
    bundle['access'] = dict(status='unverified', playable_levels=0, reason=MESSAGE)
    return bundle


def require_playable(bundle):
    restrict(bundle)
    raise ValueError(MESSAGE)

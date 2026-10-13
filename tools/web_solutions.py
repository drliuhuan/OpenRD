"""Replay verified community solutions; no client scores are trusted."""
import hashlib,json

def model_fingerprint(root):
    import ast
    pending=['web_playtest'];modules=set()
    while pending:
        name=pending.pop()
        if name in modules:continue
        modules.add(name)
        tree=ast.parse((root/'tools'/f'{name}.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            imports=[node.module] if isinstance(node,ast.ImportFrom) and node.module else [a.name for a in node.names] if isinstance(node,ast.Import) else []
            pending.extend(n for n in imports if (root/'tools'/f'{n}.py').is_file() and n not in modules)
    files=sorted([root/'tools'/f'{name}.py' for name in modules]+[root/'evidence/byt-complete-index.json',root/'evidence/gin-complete-index.json',root/'web/assets/levels.json',root/'web/assets/demo-levels.json'])
    digest=hashlib.sha256()
    for path in files:digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()

def verify_submission(game,route,factory):
    canonical=getattr(game,'trajectory',None)
    if not game.state()['completed'] or game.diagnostic:raise ValueError('只有正常通关的完整轨迹可以提交')
    if canonical is None:raise ValueError('旧存档没有完整轨迹，请从头挑战本关后提交')
    if not isinstance(route,dict) or route!=canonical:raise ValueError('轨迹与本次服务器对局不一致')
    if not 0<len(route['steps'])<=50000 or len(route['steps'])!=game.turn:raise ValueError('轨迹步数不完整或超过提交上限')
    replay=factory(game.scenario)
    for target in route['clicks']:
        if replay.world.pending_transition or replay.diagnostic:raise ValueError('轨迹在通关后仍包含行动')
        replay.click(*target,replay.revision)
    if not replay.state()['completed'] or replay.turn!=game.turn or replay.trajectory['steps']!=route['steps']:raise ValueError('轨迹未通过原始关卡重放验证')
    return route

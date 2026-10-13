"""Debug-only solution playback through unmodified Game.click; no score writes."""
import json,secrets


def answers(level,storage):
    from web_playtest import optimal_solutions,solution_model
    result={}
    optimal=optimal_solutions().get(level)
    if optimal:result['optimal']=dict(steps=optimal['steps'],actions=optimal['actions'],name='当前模型认证最优')
    player=storage.best_solution(level,solution_model(),include_route=True)
    if player:result['player']=player
    else:
        # Older HTTP-only revisions may have different fingerprints. Never trust
        # these routes: start() replays and compares the full recorded trajectory.
        with storage.connect() as db:
            row=db.execute("SELECT b.steps,b.route,COALESCE(p.name,'匿名玩家') FROM best_solutions b LEFT JOIN players p ON p.id=b.player WHERE b.level=? ORDER BY b.steps,b.updated LIMIT 1",(level,)).fetchone()
        if row:result['player']=dict(steps=row[0],trajectory=json.loads(row[1]),name=row[2],requires_validation=True)
    return result


def options(level,storage):
    return [dict(source=source,steps=a['steps'],name=a['name'],requires_validation=a.get('requires_validation',False)) for source,a in answers(level,storage).items()]


def replay_request(game,path,data,storage):
    from web_playtest import Game
    if path=='/api/replay-stop':
        run=getattr(game,'replay_run',None)
        if run and data.get('id')!=run['id']:raise ValueError('重放会话已变化')
        game.replay_run=None
        return dict(frames=[],message='重放已停止，当前局面可继续调试')
    if data.get('revision')!=game.revision:raise ValueError('状态已变化，请刷新后重试')
    if path=='/api/replay-start':
        source=data.get('source');answer=answers(game.scenario,storage).get(source)
        if answer is None:raise ValueError('本关没有所选解法')
        trial=Game(game.scenario)
        targets=[]
        if source=='optimal':
            directions={'U':(0,-1),'D':(0,1),'L':(-1,0),'R':(1,0),'W':(0,0)}
            for action in answer['actions']:
                if trial.world.player is None or trial.world.pending_transition:raise ValueError('解法包含结束后的行动')
                dx,dy=directions[action];x,y=trial.world.player.position
                target=[x+dx,y+dy];targets.append(target)
                trial.click(*target,trial.revision)
        else:
            route=answer['trajectory']
            if not 0<len(route['steps'])<=50000:raise ValueError('玩家轨迹步数不完整')
            for target in route['clicks']:
                if trial.world.player is None or trial.world.pending_transition:raise ValueError('解法包含结束后的行动')
                trial.click(*target,trial.revision);targets.append(target)
            if any(trial.trajectory[k]!=route.get(k) for k in ('level','start','clicks','steps')):raise ValueError('玩家解法与当前规则不一致，无法重放')
        if trial.diagnostic or not trial.state()['completed'] or trial.turn!=answer['steps']:raise ValueError('解法未通过当前完整游戏重放验证')
        previous_revision=game.revision
        game.debug_shield=False;game.reset()
        game.revision=previous_revision+1
        game.replay_run=dict(id=secrets.token_hex(12),source=source,name=answer['name'],total=answer['steps'],index=0,targets=targets)
        return dict(frames=[],message='解法验证通过，开始重放')
    run=getattr(game,'replay_run',None)
    if not run or data.get('id')!=run['id']:raise ValueError('重放已结束或会话已变化')
    if run['index']>=len(run['targets']):raise ValueError('重放已结束')
    result=game.click(*run['targets'][run['index']],game.revision)
    run['index']+=1
    if game.diagnostic:game.replay_run=None;raise ValueError('重放遇到游戏运行错误')
    done=run['index']==len(run['targets'])
    if done:
        if not game.state()['completed'] or game.turn!=run['total']:raise ValueError('重放未按验证结果完成')
        game.replay_run=None
    result['replay_done']=done
    result['message']='重放完成' if done else '重放中'
    return result

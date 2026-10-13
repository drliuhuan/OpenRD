"""Persistent browser profiles, one save per level and best-step rankings."""
import sqlite3
import json
import hashlib
import secrets
import pickle
import zlib
from pathlib import Path
from contextlib import contextmanager

class Storage:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS players(id TEXT PRIMARY KEY,name TEXT); CREATE TABLE IF NOT EXISTS saves(player TEXT,level TEXT,payload BLOB,PRIMARY KEY(player,level)); CREATE TABLE IF NOT EXISTS scores(player TEXT,level TEXT,steps INTEGER,PRIMARY KEY(player,level));')
            db.executescript('CREATE TABLE IF NOT EXISTS solution_submissions(player TEXT,level TEXT,model TEXT,route_hash TEXT,steps INTEGER,route TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(player,level,model,route_hash)); CREATE TABLE IF NOT EXISTS best_solutions(level TEXT,model TEXT,player TEXT,steps INTEGER,route TEXT,updated TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(level,model));')
            if 'last_level' not in {r[1] for r in db.execute('PRAGMA table_info(players)')}:
                db.execute('ALTER TABLE players ADD COLUMN last_level TEXT')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=20)
        try:
            with db:yield db
        finally:db.close()
    def profile(self,token):
        with self.connect() as db:
            row=db.execute('SELECT name FROM players WHERE id=?',(token,)).fetchone() if token else None
            if row is not None:return token,row[0],False
            token=secrets.token_urlsafe(32);db.execute('INSERT INTO players(id,name) VALUES (?,NULL)',(token,))
            return token,None,True
    def name(self,token,name):
        name=str(name).strip()
        if not 1<=len(name)<=24 or any(ord(c)<32 for c in name):raise ValueError('名字需为1至24个可见字符')
        with self.connect() as db:db.execute('UPDATE players SET name=? WHERE id=?',(name,token))
        return name
    def save(self,token,game):
        payload=zlib.compress(pickle.dumps((game,[id(vm) for _,vm in game.world.instances]),protocol=5))
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO saves VALUES (?,?,?)',(token,game.scenario,payload))
    def load(self,token,game):
        with self.connect() as db:row=db.execute('SELECT payload FROM saves WHERE player=? AND level=?',(token,game.scenario)).fetchone()
        if row is None:raise ValueError('本关还没有存档')
        # Only server-generated snapshots are accepted; no upload endpoint.
        restored,old_ids=pickle.loads(zlib.decompress(row[0]));mapping=dict(zip(old_ids,[id(vm) for _,vm in restored.world.instances]))
        for obj,attr in ((restored,'actor_primary'),(restored,'graphic_record_counts'),(restored.world,'graphical_instances'),(restored.world,'overlays'),(restored.world.scheduler,'states')):
            setattr(obj,attr,{mapping.get(k,k):v for k,v in getattr(obj,attr).items()})
        restored.revision=game.revision+1;restored.cached_cell_version=-1
        game.__dict__.clear();game.__dict__.update(restored.__dict__)
    def score(self,token,level,steps):
        with self.connect() as db:db.execute('INSERT INTO scores VALUES (?,?,?) ON CONFLICT(player,level) DO UPDATE SET steps=MIN(steps,excluded.steps)',(token,level,steps))
    def ranking(self,token,level):
        with self.connect() as db:
            rows=db.execute('SELECT s.player,p.name,s.steps FROM scores s JOIN players p ON p.id=s.player WHERE s.level=? AND p.name IS NOT NULL ORDER BY s.steps,s.player',(level,)).fetchall()
        own=next((i+1 for i,row in enumerate(rows) if row[0]==token),None)
        return dict(entries=[dict(rank=i+1,name=row[1],steps=row[2],own=row[0]==token) for i,row in enumerate(rows[:20])],own_rank=own)

    def progress(self,token,levels):
        ids=[l['id'] for l in levels]
        with self.connect() as db:
            passed={r[0] for r in db.execute('SELECT level FROM scores WHERE player=?',(token,))} & set(ids)
            last=db.execute('SELECT last_level FROM players WHERE id=?',(token,)).fetchone()
        # Demo and formal campaigns are parallel, each with its own first level.
        unlocked=[level for i,level in enumerate(ids) if i==0 or level.split('-')[0]!=ids[i-1].split('-')[0] or ids[i-1] in passed]
        last=last[0] if last else None
        campaign=(last or 'level-1').split('-')[0]
        resume=last if last in unlocked and last not in passed else next((level for level in ids if level.split('-')[0]==campaign and level in unlocked and level not in passed),last if last in unlocked else unlocked[0])
        return dict(completed=[level for level in ids if level in passed],unlocked=unlocked,resume=resume)

    def visit(self,token,level):
        with self.connect() as db:db.execute('UPDATE players SET last_level=? WHERE id=?',(level,token))

    def completion_ranking(self,token,levels):
        ids=[l['id'] for l in levels]
        with self.connect() as db:
            rows=db.execute('SELECT s.player,COALESCE(p.name,?),COUNT(*) FROM scores s JOIN players p ON p.id=s.player WHERE s.level IN ('+','.join('?' for _ in ids)+') GROUP BY s.player ORDER BY COUNT(*) DESC,s.player',('匿名玩家',*ids)).fetchall()
        own=next((i+1 for i,row in enumerate(rows) if row[0]==token),None)
        return dict(entries=[dict(rank=i+1,name=row[1],completed=row[2],own=row[0]==token) for i,row in enumerate(rows[:20])],own_rank=own,own_completed=next((r[2] for r in rows if r[0]==token),0))

    def best_solution(self,level,model,include_route=False):
        with self.connect() as db:
            row=db.execute("SELECT b.steps,b.route,b.updated,COALESCE(p.name,'匿名玩家') FROM best_solutions b LEFT JOIN players p ON p.id=b.player WHERE b.level=? AND b.model=?",(level,model)).fetchone()
        if row is None:return None
        result=dict(steps=row[0],updated=row[2],name=row[3],optimal_proven=False)
        if include_route:result['trajectory']=json.loads(row[1])
        return result

    def submit_solution(self,token,level,steps,route,model):
        payload=json.dumps(route,ensure_ascii=False,separators=(',',':'))
        signature=hashlib.sha256(json.dumps(dict(clicks=route['clicks'],steps=route['steps']),sort_keys=True).encode()).hexdigest()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO solution_submissions(player,level,model,route_hash,steps,route) VALUES (?,?,?,?,?,?)',(token,level,model,signature,steps,payload))
            result=db.execute('INSERT INTO best_solutions(level,model,player,steps,route) VALUES (?,?,?,?,?) ON CONFLICT(level,model) DO UPDATE SET player=excluded.player,steps=excluded.steps,route=excluded.route,updated=CURRENT_TIMESTAMP WHERE excluded.steps<best_solutions.steps',(level,model,token,steps,payload))
            improved=result.rowcount>0
            best=db.execute('SELECT steps FROM best_solutions WHERE level=? AND model=?',(level,model)).fetchone()[0]
        return dict(improved=improved,best_steps=best,optimal_proven=False)

    def hall_of_fame(self,levels,model):
        with self.connect() as db:
            records={r[0]:dict(name=r[1],steps=r[2],updated=r[3]) for r in db.execute("SELECT b.level,COALESCE(p.name,'匿名玩家'),b.steps,b.updated FROM best_solutions b LEFT JOIN players p ON p.id=b.player WHERE b.model=?",(model,))}
        return [dict(id=l['id'],number=l['number'],name=l['name'],series=l.get('series','演示关卡'),record=records.get(l['id'])) for l in levels]

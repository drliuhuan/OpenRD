"""Bounded in-memory browser sessions with independent per-game locks."""
from contextlib import contextmanager
from secrets import token_urlsafe
from threading import Lock
from time import monotonic


class SessionCapacityError(Exception):
    pass


class SessionStore:
    def __init__(self,factory,ttl=7200,max_sessions=128,clock=monotonic):
        self.factory=factory;self.ttl=ttl;self.max_sessions=max_sessions;self.clock=clock
        self.sessions={};self.lock=Lock()

    @contextmanager
    def acquire(self,token=None):
        with self.lock:
            now=self.clock()
            for key in list(self.sessions):
                entry=self.sessions[key]
                if not entry['active'] and now-entry['last_seen']>=self.ttl:
                    del self.sessions[key]
            fresh=token not in self.sessions
            if fresh:
                if len(self.sessions)>=self.max_sessions:
                    raise SessionCapacityError('会话容量已满，请稍后重试')
                token=token_urlsafe(32)
                self.sessions[token]=dict(game=self.factory(),lock=Lock(),last_seen=now,active=0)
            entry=self.sessions[token];entry['active']+=1;entry['last_seen']=now
        try:
            with entry['lock']:
                yield token,entry['game'],fresh
        finally:
            with self.lock:
                entry['active']-=1;entry['last_seen']=self.clock()

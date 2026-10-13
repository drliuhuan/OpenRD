"""0x414427..41447A signed-word first-match map rule predicates."""
from byt_vm_core import word

def matches(operator,value,threshold):
    value,threshold=word(value),word(threshold)
    if operator==0:return value==threshold
    if operator==1:return value!=threshold
    if operator==2:return value<threshold
    if operator==3:return value<=threshold
    if operator==4:return value>threshold
    if operator==5:return value>=threshold
    return False

def first_match(branches,value):
    for branch in branches:
        if matches(branch['operator'],value,branch['threshold']):return branch
    return None

def decode_definition(definition):
    """Verified subcommand2 branch fields and subcommand6 head-insert events."""
    branches=[]
    for command in definition['commands']:
        if command['subcommand']==2:
            slot,threshold=command['leading_words_raw']
            operator,class_id=command['bytes_raw']
            parameter,sound=command['trailing_words_raw']
            branches.append(dict(offset=command['offset'],slot=word(slot),threshold=word(threshold),
                                 operator=operator,class_id=class_id,parameter=parameter,sound_id=word(sound),events=[]))
        elif command['subcommand']==6:
            if not branches:raise ValueError('Associated event before rule branch')
            dx,dy,event=command['bytes_raw']
            branches[-1]['events'].insert(0,dict(dx=dx,dy=dy,event=event))
    return branches

def linked_rules(definitions):
    links={}
    for definition in definitions:
        branches=decode_definition(definition)
        for branch in branches:
            target=next((d for d in definitions if d['leading_bytes_raw'][1]==branch['class_id']
                         and d['parameter_raw']==branch['parameter']),None)
            branch['next_definition_offset']=None if target is None else target['offset']
        links[definition['offset']]=branches
    return links

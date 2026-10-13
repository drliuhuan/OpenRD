"""Machine-code-derived readers for nested GIN script records."""
import struct

class Unsupported(ValueError):
    pass

class Reader:
    def __init__(self,data,pos):self.data=data;self.pos=pos
    def take(self,n):
        if self.pos+n>len(self.data):raise ValueError('Truncated script record')
        value=self.data[self.pos:self.pos+n];self.pos+=n;return value
    def byte(self):return self.take(1)[0]
    def words(self,n):return list(struct.unpack(f'<{n}H',self.take(n*2)))
    def string(self):
        if self.data[:6] == b'CCIg12':
            key=list(self.take(3))
            return dict(string_ref=int.from_bytes(bytes(key),'big'),string_key=key)
        ref,size=self.words(2)
        return dict(string_ref=ref,text=self.take(size).decode('latin1'))
    def image_effect(self):
        # 0x436950: u16, byte, u16, nested byte commands.
        record=dict(parameter_raw=self.words(1)[0],flag_raw=self.byte(),
                    second_parameter_raw=self.words(1)[0],commands=[])
        while True:
            sub=self.byte()
            if sub==0:return record
            command=dict(subcommand=sub)
            if sub==1:command.update(self.string());command['values_raw']=self.words(2)
            elif sub==2:command['values_raw']=self.words(8)
            else:raise Unsupported(f'Image effect subcommand {sub} at {self.pos-1:#x}')
            record['commands'].append(command)
    def menu(self):
        record=dict(values_raw=self.words(5),commands=[])
        while True:
            sub=self.byte()
            if sub==0:return record
            command=dict(subcommand=sub)
            if sub==1:command['values_raw']=self.words(1);command.update(self.string())
            elif sub==2:
                command.update(self.string())
                value,count=self.words(2)
                command['parameter_raw']=value
                command['strings']=[self.string() for _ in range(count if count<32768 else 0)]
            elif sub==3:
                command.update(self.string());command['values_raw']=self.words(3)
            elif sub in (4,5,6,12,13,14,15):command.update(self.string())
            elif sub in (*range(7,12),*range(16,24)):
                command['values_raw']=list(self.take(3))
            elif sub in (24,26,27):command['values_raw']=self.words(1)
            elif sub==25:command['values_raw']=self.words(4)
            elif sub==33 and self.data[:6]==b'CCIg12':command.update(self.string())
            elif sub==34 and self.data[:6]==b'CCIg12':
                command['parameter_raw']=self.byte();command.update(self.string())
            elif sub==35 and self.data[:6]==b'CCIg12':
                command['values_raw']=self.words(2);command['flag_raw']=self.byte()
            else:raise Unsupported(f'Menu subcommand {sub} at {self.pos-1:#x}')
            record['commands'].append(command)

    def text_entry(self):
        # 0x4389B0, six header words; dispatch table 0x43940C.
        record=dict(values_raw=self.words(6),commands=[])
        while True:
            sub=self.byte()
            if sub==0:return record
            command=dict(subcommand=sub)
            if sub==1:
                command['values_raw']=self.words(1);command.update(self.string())
            elif sub in (2,3,4,5,6,14,15):pass
            elif sub in (12,13):command.update(self.string())
            elif sub in (*range(7,12),*range(16,24)):
                command['values_raw']=list(self.take(3))
            elif sub==24:command['font_id']=self.words(1)[0]
            elif sub==25:command['values_raw']=self.words(4)
            else:raise Unsupported(f'Text entry subcommand {sub} at {self.pos-1:#x}')
            record['commands'].append(command)

    def edit_field(self):
        # 0x43C660..0x43CAB9, byte dispatch at 0x43C7DE.
        record=dict(font_id=self.words(1)[0],label=self.string(),
                    values_raw=self.words(2),secondary_text=self.string(),
                    commands=[])
        record['commands']=self.field_commands()
        return record

    def label_field(self):
        # 0x43DA80: a nonzero binding replaces the inline label.
        record=dict(font_id=self.words(1)[0],binding_raw=self.words(1)[0])
        if record['binding_raw']==0:record['label']=self.string()
        record['secondary_text']=self.string()
        record['commands']=self.field_commands()
        return record

    def field_commands(self):
        commands=[]
        while True:
            sub=self.byte()
            if sub==0:return commands
            command=dict(subcommand=sub)
            if sub in (1,2):command['color_raw']=list(self.take(3))
            elif sub==3:
                command['flag_raw']=self.byte();command['values_raw']=self.words(2)
            else:raise Unsupported(f'Edit field subcommand {sub} at {self.pos-1:#x}')
            commands.append(command)

    def text_list(self):
        # 0x43D160, dispatch table 0x43D570.
        record=dict(font_id=self.words(1)[0],commands=[])
        while True:
            sub=self.byte()
            if sub==0:return record
            command=dict(subcommand=sub)
            if sub==1:
                command['parameter_raw']=self.words(1)[0];command.update(self.string())
            elif sub in (2,3):command['color_raw']=list(self.take(3))
            elif sub==4:
                command['leading_byte_raw']=self.byte()
                command['values_raw']=self.words(2)
                command['middle_byte_raw']=self.byte()
                command['trailing_words_raw']=self.words(2)
            else:raise Unsupported(f'Text list subcommand {sub} at {self.pos-1:#x}')
            record['commands'].append(command)

    def image_regions(self):
        # 0x437F20 and jump table 0x4384F4. Byte pairs are
        # assembled as little-endian words by the native constructor.
        if self.data[:6]==b'CCIg12':
            size=self.words(1)[0]
            record=dict(text=self.take(size).decode('latin1'))
        else:record=self.string()
        record.update(parameter_raw=self.words(1)[0],commands=[])
        while True:
            sub=self.byte()
            if sub==0:return record
            command=dict(subcommand=sub)
            if sub==1:pass
            elif sub==2:
                command['values_raw']=self.words(6)
                command['flag_raw']=self.byte()
            elif sub==3:
                command['values_raw']=self.words(8)
                command['flags_raw']=list(self.take(2))
                command['trailing_words_raw']=self.words(2)
            elif sub==4:
                command['values_raw']=self.words(10)
                command['flags_raw']=list(self.take(2))
                command['trailing_words_raw']=self.words(2)
            else:raise Unsupported(f'Image regions subcommand {sub} at {self.pos-1:#x}')
            record['commands'].append(command)

    def text_panel(self):
        # 0x439FB0..0x43A6FC; count is tested as signed i16.
        record=dict(sprite_references=self.words(4))
        count=self.words(1)[0]
        record['entries']=[dict(parameter_raw=(v:=self.words(2))[0],
                                sprite_id=v[1]) for _ in range(count if count<32768 else 0)]
        record['geometry_raw']=self.words(10)
        record['font_id']=self.words(1)[0]
        record['colors_raw']=list(self.take(6))
        record['values_raw']=self.words(4)
        record['leading_flags_raw']=list(self.take(2))
        record.update(self.string())
        record['color_raw']=list(self.take(3))
        record['trailing_words_raw']=self.words(4)
        record['trailing_flags_raw']=list(self.take(3))
        return record

def script(data,pos):
    r=Reader(data,pos+1);first,second=r.words(2);kind=r.byte()
    record=dict(offset=pos,opcode=0x42,script_id=first,parameter_raw=second,
                kind_raw=kind,commands=[])
    if kind==1:record['ignored_byte']=r.byte()
    elif kind==2:record['menu']=r.menu()
    elif kind==9:record['text_panel']=r.text_panel()
    elif kind==10:record['text_entry']=r.text_entry()
    elif kind==5:record['edit_field']=r.edit_field()
    elif kind==3:record['label_field']=r.label_field()
    elif kind==4:record['text_list']=r.text_list()
    else:raise Unsupported(f'Script kind {kind} at {pos:#x}')
    while True:
        sub=r.byte()
        if sub==0:break
        command=dict(subcommand=sub)
        if sub==1:command['image_regions']=r.image_regions()
        elif sub==3:command['values_raw']=r.words(1)
        elif sub==2:
            command['leading_bytes_raw']=list(r.take(3))
            command['values_raw']=r.words(4);command['trailing_bytes_raw']=list(r.take(2))
        elif sub==4:pass
        elif sub==5:command['values_raw']=r.words(5)
        elif sub==6:
            # 0x437380..0x4377AE: font, string, eight bytes,
            # four signed coordinate words and three unsigned words.
            command['font_id']=r.words(1)[0]
            command.update(r.string())
            command['flags_and_colors_raw']=list(r.take(8))
            command['values_raw']=r.words(7)
        elif sub==7:command['image_effect']=r.image_effect()
        else:raise Unsupported(f'Script subcommand {sub} at {r.pos-1:#x}')
        record['commands'].append(command)
    record['next_offset']=r.pos
    return record

"""Incremental JSON-string guards; observe raw output, never rewrite content."""
import math


class OutputGuardViolation(ValueError):
    code='knowledge_output_validation'
    retryable=True

    def __init__(self,reason,path,limit=None):
        message=('模型在一个字段中持续重复同一片段，已停止本批并保留输出。' if reason=='repetition'
                 else '模型输出的JSON结构异常，已停止本批并保留输出。' if reason=='json_structure'
                 else '教学档案字段过长，已停止本批并保留输出。')
        super().__init__(message)
        self.details={'reason':reason,'path':list(path),'limit':limit}


class JsonOutputGuard:
    """Track decoded strings across chunks, with per-path limits and tandem loops.

    This is not a JSON repair or semantic validator. Normal repeated field names,
    examples in separate strings, and short repeated mathematical factors pass.
    """
    def __init__(self,field_limits=None):
        self.field_limits=field_limits or {}
        self.reset()

    def reset(self):
        self.stack=[];self.inside=False;self.escaped=False;self.unicode=None
        self.path=();self.key=False;self.text='';self.length=0;self.reason='';self.limit=None
        self.complete=False

    def _path(self):
        if not self.stack:return ()
        parent=self.stack[-1]
        return (*parent['path'],parent['key'] if parent['kind']=='object' else parent['index'])

    def _done(self):
        if self.stack:self.stack[-1]['expect']='comma'

    def _fail(self,reason,limit=None):
        self.reason=reason
        raise OutputGuardViolation(reason,self.path,limit)

    def _check_repetition(self):
        # A long exact tandem loop within one string is a transport anomaly;
        # no formula names, discipline vocabulary or source wording is inspected.
        for period in range(8,min(128,len(self.text)//8)+1):
            repeats=max(8,math.ceil(160/period));size=period*repeats
            if size>len(self.text):continue
            unit=self.text[-period:]
            if len(set(unit))>=3 and self.text[-size:]==unit*repeats:
                self._fail('repetition')

    def _append(self,char):
        if (len(char)==1 and 0xdc00<=ord(char)<=0xdfff and self.text
            and 0xd800<=ord(self.text[-1])<=0xdbff):
            char=chr(0x10000+(ord(self.text[-1])-0xd800)*1024+ord(char)-0xdc00)
            self.text=self.text[:-1]+char
            return
        self.length+=len(char)
        self.text=(self.text+char)[-2048:]
        limit=self.limit
        if limit is not None and self.length>limit:self._fail('field_length',limit)
        if self.length%16==0:self._check_repetition()

    def feed(self,chunk):
        for char in chunk:
            if self.inside:
                if self.unicode is not None:
                    self.unicode+=char
                    if len(self.unicode)==4:
                        try:value=chr(int(self.unicode,16))
                        except ValueError:value='\\u'+self.unicode
                        self.unicode=None;self._append(value)
                elif self.escaped:
                    self.escaped=False
                    if char=='u':self.unicode=''
                    else:self._append({'n':'\n','t':'\t','r':'\r','b':'\b','f':'\f','"':'"','/':'/','\\':'\\'}.get(char,'\\'+char))
                elif char=='\\':self.escaped=True
                elif char=='"':
                    self._check_repetition();self.inside=False
                    if self.key and self.stack:
                        self.stack[-1].update(key=self.text,expect='colon')
                    else:self._done()
                else:self._append(char)
                continue
            if self.complete and not char.isspace():self._fail('json_structure')
            if char=='"':
                self.key=bool(self.stack and self.stack[-1]['kind']=='object' and self.stack[-1]['expect']=='key')
                self.path=(*self.stack[-1]['path'],'<key>') if self.key else self._path()
                self.limit=None if self.key else self.field_limits.get(self.path)
                if not self.key and self.limit is None:
                    self.limit=next((limit for path,limit in self.field_limits.items()if len(path)==len(self.path)
                        and all(a=='*'or a==b for a,b in zip(path,self.path))),None)
                self.inside=True;self.escaped=False;self.unicode=None;self.text='';self.length=0
            elif char in '{[':
                self.stack.append({'kind':'object' if char=='{' else 'array','path':self._path(),
                    'expect':'key' if char=='{' else 'value','key':'','index':0})
            elif char in '}]':
                if not self.stack or self.stack[-1]['kind']!=('object' if char=='}' else 'array'):
                    self._fail('json_structure')
                self.stack.pop()
                if not self.stack:self.complete=True
                self._done()
            elif char==':' and self.stack:self.stack[-1]['expect']='value'
            elif char==',' and self.stack:
                parent=self.stack[-1];parent['expect']='key' if parent['kind']=='object' else 'value'
                if parent['kind']=='array':parent['index']+=1

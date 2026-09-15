"""Managed Markdown memory: source files, derived index, and recoverable mutations.

Only this root owns its index; a separately configured global index is never used.
The journal is auxiliary recovery state, not a replacement memory format.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid


class MemoryError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def slug(name):
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name)
            or name.casefold() == 'memory' or name.upper() in {'CON','PRN','AUX','NUL'}
            or re.fullmatch(r'(COM|LPT)[1-9]', name, re.I)):
        raise MemoryError('memory_name_invalid', 'Use a plain memory name; MEMORY is reserved for the derived index.')
    return name


def scope(meta):
    value = str(meta.get('project') or '')
    return 'global' if value == '*' else 'project:' + value if value else 'legacy'


def visible(meta, project):
    value = str(meta.get('project') or '')
    return not (value and project and value not in {project, '*'})


class MemoryStore:
    def __init__(self, root, parse, build):
        self.root = Path(root).absolute()
        self.parse, self.build = parse, build
        self.index = self.root / 'MEMORY.md'
        self.journal = self.root / '.memory-transaction.json'
        self.receipts = self.root / '.memory-receipts'
        with _LOCKS_GUARD:
            self.mutex = _LOCKS.setdefault(os.path.normcase(str(self.root)), threading.RLock())

    def _plain(self, path):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise MemoryError('memory_link_forbidden', 'Managed memory does not follow links or junctions.')
        if path.exists() and path.is_file() and path.stat().st_nlink > 1:
            raise MemoryError('memory_link_forbidden', 'Managed memory does not mutate linked files.')
        return path

    def _path(self, name):
        path = self._plain(self.root / (slug(name) + '.md'))
        if path.exists() and not path.is_file():
            raise MemoryError('memory_path_invalid', 'The memory target is not a regular file.')
        return path

    @contextlib.contextmanager
    def locked(self):
        with self.mutex:
            for parent in (self.root, *self.root.parents): self._plain(parent)
            self.root.mkdir(parents=True, exist_ok=True)
            lock = self._plain(self.root / '.memory.lock')
            with lock.open('a+b') as stream:
                stream.seek(0, 2)
                if stream.tell() == 0: stream.write(b'0'); stream.flush()
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    self._recover()
                    yield
                finally:
                    stream.seek(0)
                    if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _atomic(self, path, data):
        self._plain(path)
        temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            self._plain(path)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _json(self, path, value):
        self._atomic(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8'))

    @staticmethod
    def _hash(data):
        return hashlib.sha256(data).hexdigest() if data is not None else None

    def _bytes(self, path):
        self._plain(path)
        return path.read_bytes() if path.exists() else None

    def _read(self, name):
        path = self._path(name)
        if not path.exists(): raise MemoryError('memory_not_found', 'The selected memory no longer exists.')
        before = path.stat(); raw = path.read_bytes(); after = path.stat()
        identity = lambda s:(s.st_dev,s.st_ino,s.st_mtime_ns,s.st_size)
        if identity(before) != identity(after):
            raise MemoryError('memory_conflict', 'Memory changed while reading; refresh the selected target.')
        meta, body = self.parse(raw.decode('utf-8-sig'))
        revision = hashlib.sha256(json.dumps(identity(after)).encode() + b'\0' + raw).hexdigest()
        return {'name':name,'meta':meta,'body':body,'raw':raw.decode('utf-8-sig'),
                'revision':revision,'scope':scope(meta),'size':len(body)}

    def _all(self):
        result=[]
        for path in sorted(self.root.glob('*.md')):
            if path.name == 'MEMORY.md': continue
            if path.name.casefold() == 'memory.md':
                raise MemoryError('memory_index_conflict', 'A legacy source name conflicts with the reserved MEMORY.md index. It was not overwritten.')
            result.append(self._read(path.stem))
        return result

    def _rebuild(self):
        lines=[]
        for item in self._all():
            description=' '.join(str(item['meta'].get('description') or '').splitlines())
            lines.append(f"- [{item['name']}]({item['name']}.md) — {description}")
        raw=('\n'.join(lines)+'\n').encode('utf-8')
        if self._bytes(self.index) != raw: self._atomic(self.index, raw)

    def _receipt_path(self, operation):
        self._plain(self.receipts)
        return self.receipts / (hashlib.sha256(operation.encode()).hexdigest()+'.json')

    def _read_receipt(self, path):
        try:
            saved=json.loads(self._plain(path).read_text(encoding='utf-8'))
            if (saved.get('version') != 1 or not isinstance(saved.get('result'),dict)
                    or not isinstance(saved.get('targets'),dict) or not 1 <= len(saved['targets']) <= 2
                    or not re.fullmatch('[0-9a-f]{64}', str(saved.get('fingerprint') or ''))):
                raise ValueError()
            for name,digest in saved['targets'].items():
                self._path(name)
                if digest is not None and not re.fullmatch('[0-9a-f]{64}', str(digest)): raise ValueError()
            return saved
        except MemoryError: raise
        except Exception as exc:
            raise MemoryError('memory_receipt_invalid', 'Memory operation receipt is invalid; no source was changed.') from exc

    def _rollback(self, tx):
        for name, state in tx['files'].items():
            path=self._path(name); current=self._bytes(path)
            before=base64.b64decode(state['before']) if state['before'] is not None else None
            if current == before: continue
            if self._hash(current) != state['afterHash']:
                raise MemoryError('memory_recovery_conflict', 'Memory changed outside the pending operation; recovery stopped without overwriting it.')
            if before is None: path.unlink(missing_ok=True)
            else: self._atomic(path,before)
        self._rebuild()

    def _recover(self):
        self._plain(self.journal)
        if not self.journal.exists(): return
        try:
            tx=json.loads(self.journal.read_text(encoding='utf-8'))
            if (tx.get('version') != 1 or not isinstance(tx.get('files'),dict)
                    or not 1 <= len(tx['files']) <= 2
                    or not re.fullmatch('[0-9a-f]{64}', str(tx.get('fingerprint') or ''))): raise ValueError()
            for name,state in tx['files'].items():
                self._path(name)
                if not isinstance(state,dict) or set(state) != {'before','afterHash'}: raise ValueError()
                if state['before'] is not None: base64.b64decode(state['before'],validate=True)
                if state['afterHash'] is not None and not re.fullmatch('[0-9a-f]{64}',str(state['afterHash'])): raise ValueError()
            receipt=self._receipt_path(tx['operation'])
            if receipt.exists():
                saved=self._read_receipt(receipt)
                if saved.get('fingerprint') != tx['fingerprint']: raise ValueError()
                self._rebuild()
            else: self._rollback(tx)
            self.journal.unlink()
        except MemoryError: raise
        except Exception as exc:
            raise MemoryError('memory_recovery_failed', 'Pending memory recovery could not finish; no new mutation was started.') from exc

    def list(self):
        if not self.root.exists(): return []
        with self.locked():
            self._rebuild()
            return self._all()

    def read(self,name):
        with self.locked(): return self._read(name)

    def _check(self,name,expected,expected_scope):
        item=self._read(name)
        if expected is not None and item['revision'] != expected:
            raise MemoryError('memory_conflict','The selected memory changed; refresh it and confirm the new version.')
        if expected_scope is not None and item['scope'] != expected_scope:
            raise MemoryError('memory_scope_mismatch','The selected memory scope changed; no mutation was performed.')
        return item

    def mutate(self,kind,name,*,raw=None,new_name=None,expected=None,expected_scope=None,operation=None,request_fingerprint=None):
        if kind in {'write','rename'} and not isinstance(raw,bytes):
            raise MemoryError('memory_content_invalid', 'Writing memory requires complete source bytes.')
        name=slug(name);new_name=slug(new_name) if new_name else name
        operation=operation or uuid.uuid4().hex
        if not isinstance(operation, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', operation):
            raise MemoryError('memory_operation_invalid', 'Invalid memory operation ID.')
        fingerprint=request_fingerprint or hashlib.sha256(json.dumps([kind,name,new_name,self._hash(raw),expected,expected_scope],ensure_ascii=False).encode()).hexdigest()
        with self.locked():
            receipt=self._receipt_path(operation)
            if receipt.exists():
                saved=self._read_receipt(receipt)
                if saved.get('fingerprint') != fingerprint:
                    raise MemoryError('memory_operation_conflict','This operation ID belongs to a different memory change.')
                self._rebuild()
                if any(self._hash(self._bytes(self._path(n))) != digest for n,digest in saved['targets'].items()):
                    return {'ok':False,'name':new_name,'replayed':True,'applied':False,
                            'errorCode':'memory_target_changed',
                            'error':'The original operation completed, but its target has since changed or been recreated. Nothing was changed; refresh and confirm a new operation.'}
                return {**saved['result'],'replayed':True,'applied':False}
            self._rebuild()
            path=self._path(name)
            if kind not in {'write','delete','rename'}: raise ValueError('invalid memory operation')
            if kind!='write' or path.exists(): self._check(name,expected,expected_scope)
            elif expected: raise MemoryError('memory_conflict','The selected memory no longer exists.')
            if kind=='rename' and new_name!=name and self._path(new_name).exists():
                raise MemoryError('memory_name_conflict','The new memory name already exists; it was not overwritten.')
            changes={name:raw} if kind=='write' else {name:None} if kind=='delete' else {new_name:raw,name:None}
            if kind=='rename' and new_name==name: changes={name:raw}
            before={n:self._bytes(self._path(n)) for n in changes}
            self.receipts.mkdir(exist_ok=True)
            if all(before[n]==after for n,after in changes.items()):
                result={'ok':True,'name':new_name,'replayed':True,'applied':False,'operation':kind}
                self._json(receipt,{'version':1,'fingerprint':fingerprint,'result':result,
                                   'targets':{n:self._hash(after) for n,after in changes.items()}})
                return result
            tx={'version':1,'operation':operation,'fingerprint':fingerprint,'files':{
                n:{'before':base64.b64encode(before[n]).decode() if before[n] is not None else None,
                   'afterHash':self._hash(after)} for n,after in changes.items()}}
            self._json(self.journal,tx)
            try:
                for n,after in changes.items():
                    target=self._path(n)
                    if self._bytes(target)!=before[n]: raise MemoryError('memory_conflict','Memory changed before mutation; operation stopped.')
                    if after is None: target.unlink()
                    else: self._atomic(target,after)
                self._rebuild()
                result={'ok':True,'name':new_name,'replayed':False,'applied':True,'operation':kind}
                self._json(receipt,{'version':1,'fingerprint':fingerprint,'result':result,
                                   'targets':{n:self._hash(after) for n,after in changes.items()}})
            except Exception as exc:
                try:
                    self._rollback(tx);self.journal.unlink()
                except Exception as recovery:
                    raise MemoryError('memory_recovery_failed','Memory change did not complete; retained recovery state must be resolved before further operations.') from recovery
                if isinstance(exc,MemoryError): raise
                raise MemoryError('memory_write_failed','Memory change failed and the prior source was restored.') from exc
            self.journal.unlink()
            return result

# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'ddrescue',
        ]

import enum
import logging
import re
import os
log = logging.getLogger(__name__)

from .exec import Executable, do_spawn_cmd
from .file import TextFile

LLONG_MAX = 9223372036854775807  # 2^^63-1

class Block(object):

    # pos >= 0 && size >= 0 && pos + size <= LLONG_MAX
    @property
    def pos(self):
        return self._pos

    @pos.setter
    def pos(self, p):
        self._pos = max(p, 0)
        if self._size > LLONG_MAX - self._pos:
            self._size = LLONG_MAX - self._pos

    # pos >= 0 && size >= 0 && pos + size <= LLONG_MAX
    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, s):
        self._size = s
        self.fix_size()

    def __init__(self, p, s):
        self._pos = p
        self._size = s
        if p < 0:
            self._pos = 0
            if s > 0: self._size -= min(s, -p)
            self.fix_size()
        super().__init__()

    def fix_size():  # limit size_ to largest possible value
        if self._size < 0 or self._size > LLONG_MAX - self._pos:
            self._size = LLONG_MAX - self._pos

    @property
    def end(self):
        return self._pos + self._size

    @end.setter
    def end(self, e):
        if e < 0: e = LLONG_MAX
        if self._size <= e:
            self._pos = e - self._size
        else:
            self._pos = 0
            self._size = e

    def shift(self, offset):
        if offset >= 0:
            self._pos += min(offset, LLONG_MAX - self._pos)
            if self._size > LLONG_MAX - self._pos:
                self._size = LLONG_MAX - self._pos
        else:
            self._pos += offset
            if self._pos < 0:
                self._size = max(self._size + self._pos, 0)
                self._pos = 0

    def enlarge(s):
        if s < 0:
            s = LLONG_MAX
        if s > LLONG_MAX - self._pos - self._size:
           s = LLONG_MAX - self._pos - self._size
        self._size += s

    def assign(self, p, s):
        self._pos = p
        self._size = s
        if p < 0:
            self._pos = 0
            if s > 0:
                self._size -= min(s, -p)
        self.fix_size()
        return self

    def align_pos(self, alignment):
        """Align pos to next boundary if size is big enough"""
        if alignment > 1:
            disp = alignment - self._pos % alignment
            if disp < alignment and disp < self._size:
                self._pos += disp
                self._size -= disp

    def align_end(self, alignment):
        """Align end to previous boundary if size is big enough"""
        if alignment > 1:
            rest = self.end % alignment
            if self._size > rest:
                self._size -= rest

    def __eq__(self, other):
        if not isinstance(other, Block):
            return NotImplemented
        return (self._pos, self._size) == (other._pos, other._size)

    def __ne__(self, other):
        if not isinstance(other, Block):
            return NotImplemented
        return (self._pos, self._size) != (other._pos, other._size)

    def __lt__(self, other):
        if not isinstance(other, Block):
            return NotImplemented
        return self.end <= other.pos

    def follows(self, other):
        return self._pos == other.end

    def includes(self, other):
        return self._pos <= b._pos and self.end >= other.end

    def includes_pos(self, pos):
        return self._pos <= pos and self.end > pos

    def strictly_includes(self, pos):
        return self._pos < pos and self.end > pos

    def crop(self, b):
        p = max(self._pos, b._pos)
        s = max(0, min(self.end, b.end) - p)
        self._pos = p
        self._size = s

    def join(self, b):
        if self.follows(b):
            self._pos = b._pos
        elif not b.follows(self):
            return False
        if b._size > LLONG_MAX - self.end:
            raise ValueError("size overflow joining two Blocks.")
        self._size += b._size
        return True

    def shift_boundary(self, n, pos):
        """shift the boundary of two consecutive Blocks"""
        if self.end != b._pos or pos <= self._pos or pos >= b.end:
            raise ValueError("bad argument shifting the border of two Blocks.")
        b._size = b.end - pos
        b._pos = pos
        self._size = pos - self._pos

    def split(self, pos, hardbs):
        if hardbs > 1:
            pos -= pos % hardbs
        if self._pos < pos and self.end > pos:
            b = Block(self._pos, pos - self._pos)
            self._pos = pos
            self._size -= b._size
            return b
        return Block(0, 0)


class Sblock(Block):

    class Status(enum.Enum):
        non_tried = '?'
        non_trimmed = '*'
        non_scraped = '/'
        bad_sector = '-'
        finished = '+'

    status = None

    def __init__(self, *args):
        if len(args) == 2:
            b, st = args
            p, s = b._pos, s._size
        elif len(args) == 3:
            p, s, st = args
        else:
            raise TypeError(args)
        super().__init__(p, s)
        self.status = Sblock.Status(st)

    def __ne__(self, other):
        if not isinstance(other, Sblock):
            return NotImplemented
        return super().__ne__(other) or other.status is not self.status

    def join(self, sb):
        if self.status == sb.status:
            return super().join(sb)
        else:
            return False

    def split(self, pos, hardbs=1):
        return Sblock(super().split(pos, hardbs=hardbs), self.status)

    @staticmethod
    def isstatus(st):
        try:
            Sblock.Status(st)
        except ValueError:
            return False
        else:
            return True

    @staticmethod
    def is_good_status(st):
        return st is not Sblock.Status.bad_sector


class DdrescueMapFileError(ValueError):

    def __init__(self, mapfile, linenum, line=None):
        self.mapfile = mapfile
        self.linenum = linenum
        self.line = line
        super().__init__('error in mapfile')

    def __str__(self):
        s = f'{os.fspath(self.mapfile)}, line {self.linenum}: {super().__str__()}'
        if self.line is not None:
            s += f': {self.line!r}'
        return s


class DdrescueMapFile(TextFile):
    """A GNU ddrescue map file"""

    current_pos = None
    #current_msg = None
    current_status = None
    current_pass = None
    #index = None      # cached index of last find or change
    sblocks = None    # note: blocks are consecutive (list)
    _cached_tot_size = None

    @staticmethod
    def enumerate_lines(fp):
        """Read lines discarding comments, leading whitespace and blank lines."""
        for linenum, line in enumerate(fp):
            line = line.lstrip().rstrip('\n')
            if not line or line.startswith('#'):
                continue
            yield linenum, line

    def load(self, file=None, default_sblock_status=None):
        """Returns true if mapfile exists and is readable.
        Fills the gaps if 'default_sblock_status' is a valid status character.
        NOTE: Shamelessly ported from GNU ddrescue 1.23 (GPLv2) to Python by Jean-Sebastien Trottier.
        """
        if file is None:
            file = self.fp
        if file is None:
            with self.open('r') as file:
                return self.load(file=file, default_sblock_status=default_sblock_status)
        loose = Sblock.isstatus(default_sblock_status)
        self.sblocks = []
        self._cached_tot_size = None
        iter_lines = self.enumerate_lines(file)
        try:
            linenum, line = next(iter_lines)
        except StopIteration:
            return  # Empty
        # status line
        self.current_pass = 1  # default value
        m = re.match(r'^(?P<pos>\d+|0[xX][A-Fa-f0-9]+)\s+(?P<ch>\S+)(?:\s+(?P<pass>\d+))?', line)  # "%lli %c %d\n"
        if m:
            self.current_pos = int(m.group('pos'), 0)
            ch = m.group('ch')
            try:
                self.current_pass = int(m.group('pass'))
            except KeyError:
                pass
        if m and self.current_pos >= 0 and Sblock.isstatus(ch) and self.current_pass >= 1:
            self.current_status = Sblock.Status(ch)
        else:
            raise DdrescueMapFileError(self, linenum, line=line)
        re_sblock = re.compile(r'^(?P<pos>\d+|0[xX][A-Fa-f0-9]+)\s+(?P<size>\d+|0[xX][A-Fa-f0-9]+)\s+(?P<ch>\S)$')  # "%lli %lli %c\n"
        for linenum, line in iter_lines:
            m = re_sblock.match(line)
            if m:
                pos = int(m.group('pos'), 0)
                size = int(m.group('size'), 0)
                ch = m.group('ch')
            if m and pos >= 0 and Sblock.isstatus(ch) and (size > 0 or (size == 0 and pos == 0)):
                st = Sblock.Status(ch)
                sb = Sblock(pos, size, st)
                try:
                    b = self.sblocks[-1]
                except IndexError:
                    end = 0
                else:
                    end = b.end
                if sb.pos != end:
                    if loose and sb.pos > end:
                        sb2 = Sblock(end, sb.pos - end, default_sblock_status)
                        self.sblocks.append(sb2)
                    elif end > 0:
                        raise DdrescueMapFileError(self, linenum, line=line)
                self.sblocks.append(sb)
            else:
                raise DdrescueMapFileError(self, linenum, line=line)

    def is_finished(self):
        return all(
            sb.status is Sblock.Status.finished
            for sb in self.sblocks)

    def compact_sblocks(self):
        new_vector = []
        l = 0
        while l < len(self.sblocks):
            run = self.sblocks[l]
            r = l + 1
            while r < len(self.sblocks) \
                    and self.sblocks[r].status == run.status:
                r += 1
            if r > l + 1:
                run.size = self.sblocks[r-1].end - run.pos
            new_vector.append(run)
            l = r;
        self.sblocks = new_vector

    def stats(self):
        d = {e: 0 for e in Sblock.Status}
        total_size = 0
        for sb in self.sblocks:
            sb_size = sb.size
            d[sb.status] += sb_size
            total_size += sb_size
        d['total'] = total_size
        return d

    @property
    def tot_size(self):
        if self._cached_tot_size is None:
            self._cached_tot_size = sum(
                sb.size
                for sb in self.sblocks)
        return self._cached_tot_size


class Ddrescue(Executable):

    name = 'ddrescue'
    MapFile = DdrescueMapFile

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt


ddrescue = Ddrescue()

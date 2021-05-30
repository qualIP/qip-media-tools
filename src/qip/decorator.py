# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import functools
import sys
import logging
import traceback
import inspect
import types

_trace_indent = 0


def _try_repr(obj):
    try:
        return repr(obj)
    except:
        pass
    return '<%s object id=%s>' % (
            _try_repr(type(obj)),
            id(obj),
            )


def trace(func=None, log=None, pin=True, pargs=True, pout=True, preturn=True,
        pexcept=True, ptraceback=True, tgenerator=False):
    if log is None:
        log = logging.getLogger(__name__)

    def outer(func):
        func_name = getattr(func, "__qualname__", None)
        if func_name is None:
            func_name = getattr(func, "__name__", None)
            if func_name is None:
                func_name = _try_repr(func)

        @functools.wraps(func)
        def inner(*args, **kwargs):
            global _trace_indent
            indent = " " * _trace_indent
            _trace_indent += 1
            try:
                if pin:
                    if pargs:
                        log.info("%sIN:  %s(%s)",
                                indent, func_name,
                                ", ".join(
                                    [_try_repr(arg) for arg in args] +
                                    ["%s=%s" % (key, _try_repr(arg))
                                        for key, arg in kwargs.items()]))
                    else:
                        log.info("%sIN:  %s",
                                indent, func_name)
                try:
                    ret = func(*args, **kwargs)
                except:
                    exc_type, exc, exc_traceback = sys.exc_info()
                    if pexcept:
                        log.info("%sEXC: %s, raised %s: %s",
                                indent, func_name, exc.__class__.__name__, exc)
                        if ptraceback:
                            traceback_fmt = traceback.format_list(
                                    traceback.extract_tb(exc_traceback)[1:])
                            log.info("%sTB:  %s",
                                    indent,
                                    (indent + "     ").join(traceback_fmt) \
                                            .rstrip("\r\n"))
                    raise
                if pout:
                    if preturn:
                        log.info("%sOUT: %s, returned %s",
                                indent, func_name,
                                repr(ret),
                                )
                    else:
                        log.info("%sOUT: %s",
                                indent, func_name)
                if tgenerator and inspect.isgenerator(ret):
                    ret = trace_generator(ret, log=log, pyield=pout, pexcept=pexcept, ptraceback=ptraceback)
                    #ret = vgenerator(ret, log=log, pyield=pout, pexcept=pexcept, ptraceback=ptraceback)
                return ret
            finally:
                _trace_indent -= 1

        return inner

    if func is None:
        return outer
    else:
        return outer(func)


def trace_generator(gen, gen_name=None, log=None, pyield=True, pexcept=True, ptraceback=True):
    global _trace_indent

    if log is None:
        log = logging.getLogger(__name__)

    #if gen_name is None:
    #    gen_name = getattr(gen, "__qualname__", None)
    #if gen_name is None:
    #    gen_name = getattr(gen, "__name__", None)
    if gen_name is None:
        gen_name = _try_repr(gen)

    while True:
        try:
            item = next(gen)
        except StopIteration:
            if pyield:
                indent = " " * _trace_indent
                log.info("%sSTOP: %s",
                        indent, gen_name,
                        )
            raise
        except:
            exc_type, exc, exc_traceback = sys.exc_info()
            if pexcept:
                indent = " " * _trace_indent
                log.info("%sTHROW: %s, raised %s: %s",
                        indent, gen_name, exc.__class__.__name__, exc)
                if ptraceback:
                    traceback_fmt = traceback.format_list(
                            traceback.extract_tb(exc_traceback)[1:])
                    log.info("%sTB:  %s",
                            indent,
                            (indent + "     ").join(traceback_fmt) \
                                    .rstrip("\r\n"))
            try:
                item = gen.throw(exc_type, exc, exc_traceback)
            except:
                exc_type2, exc2, exc_traceback2 = sys.exc_info()
                if pexcept:
                    indent = " " * _trace_indent
                    if exc is None:
                        # Need to force instantiation so we can reliably
                        # tell if we get the same exception back
                        exc = exc_type()
                    if exc2 is exc:
                        log.info("%sTHROW: %s, re-raised",
                                indent, gen_name)
                    else:
                        log.info("%sEXC: %s, raised %s: %s",
                                indent, gen_name, exc2.__class__.__name__, exc2)
                        if ptraceback:
                            traceback_fmt = traceback.format_list(
                                    traceback.extract_tb(exc_traceback2)[1:])
                            log.info("%sTB:  %s",
                                    indent,
                                    (indent + "     ").join(traceback_fmt) \
                                            .rstrip("\r\n"))
                raise
        if pyield:
            indent = " " * _trace_indent
            if item is None:
                log.info("%sYIELD: %s, yielded",
                        indent, gen_name,
                        )
            else:
                log.info("%sYIELD: %s, yielded %s",
                        indent, gen_name,
                        repr(item),
                        )
        try:
            yield item
        except:
            exc_type, exc, exc_traceback = sys.exc_info()
            if pexcept:
                indent = " " * _trace_indent
                log.info("%sEXC: %s, caught %s: %s",
                        indent, gen_name, exc.__class__.__name__, exc)
                if ptraceback:
                    traceback_fmt = traceback.format_list(
                            traceback.extract_tb(exc_traceback)[1:])
                    log.info("%sTB:  %s",
                            indent,
                            (indent + "     ").join(traceback_fmt) \
                                    .rstrip("\r\n"))
            try:
                return gen.throw(exc_type, exc, exc_traceback)
            except:
                exc_type, exc, exc_traceback = sys.exc_info()
                if pexcept:
                    indent = " " * _trace_indent
                    log.info("%sEXC: %s, re-threw %s: %s",
                            indent, gen_name, exc.__class__.__name__, exc)
                    if ptraceback:
                        traceback_fmt = traceback.format_list(
                                traceback.extract_tb(exc_traceback)[1:])
                        log.info("%sTB:  %s",
                                indent,
                                (indent + "     ").join(traceback_fmt) \
                                        .rstrip("\r\n"))
                raise

def func_once(func):
    """A decorator that runs a function only once.
	From http://code.activestate.com/recipes/425445-once-decorator/
    """
    def decorated(*args, **kwargs):
        try:
            return decorated._once_result
        except AttributeError:
            decorated._once_result = func(*args, **kwargs)
            return decorated._once_result
    return decorated

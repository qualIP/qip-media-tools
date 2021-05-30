# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

def _PyType_Lookup(cls, name, default=None):
    '''Internal API to look for a name through the MRO.

    This is basically the same as Python's _PyType_Lookup, except no caching is
    provided.
    '''

    # keep a strong reference to mro because cls->tp_mro can be replaced during
    # PyDict_GetItem(dict, name)
    try:
        mro = cls.__mro__
    except AttributeError:
        # (Hopefully never reached)
        # If mro is NULL, the cls is either not yet initialized by PyType_Ready(),
        # or already cleared by type_clear(). Either way the safest thing to do is
        # to return NULL.
        return default

    # Lookup the attribute in each base of the mro and return the first
    # occurence, or None.
    res = default
    for base in mro:
        basedict = base.__dict__
        try:
            res = basedict[name]
        except KeyError:
            pass
        else:
            break

    return res

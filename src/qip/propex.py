# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'is_descriptor',
    'dynamicmethod',
    'propex',
)

import enum
import weakref


def is_descriptor(obj):
	"""
	Returns True if obj is a descriptor, False otherwise.
	"""
	return any(
		hasattr(obj, attr)
		for attr in (
				'__get__',
				'__set__',
				'__delete__',
		))


class dynamicmethod(object):

    def __init__(self, method, *args, **kwargs):
        self.__method = method
        self.__cmethod = classmethod(method)
        super().__init__(*args, **kwargs)

    def __get__(self, inst, ownerclass=None):
        if inst is None:
            r = self.__cmethod
        else:
            r = self.__method
        if is_descriptor(r):
            r = r.__get__(inst, ownerclass)
        return r


class propex(object):

    class Constants(enum.Enum):
        # not_specified: Easily detect unspecified arguments in function calls
        not_specified = 1

    # Copy all the Constants enum values as members of the propex
    # class
    locals().update(Constants.__members__)

    class DefaultActions(enum.Enum):
        function_return_default = 'fdef'
        function_set_init = 'finit'
        method_return_default = 'fdef_method'
        method_set_init = 'finit_method'
        value_return_default = 'default'
        value_set_init = 'init'

    @staticmethod
    def test_is(other):

        msg = 'Not %r.' % (other,)

        def f(value):
            if value is not other:
                raise ValueError(msg)
            return value

        return f

    @staticmethod
    def test_isinstance(classinfo):

        if not classinfo:
            raise ValueError(classinfo)
        isinstance(None, classinfo)  # Just make sure Python likes it
        msg = 'Not an instance of '
        if type(classinfo) is tuple:
            if len(classinfo) > 1:
                msg += ', '.join([c.__name__ for c in classinfo[0:-1]])
                msg += ' or '
            msg += classinfo[-1].__name__
        else:
            msg += classinfo.__name__
        msg += '.'

        def f(value):
            if not isinstance(value, classinfo):
                raise ValueError(msg)
            return value

        return f

    @staticmethod
    def test_istype(classinfo):

        if not classinfo:
            raise ValueError(classinfo)
        isinstance(None, classinfo)  # Just make sure Python likes it
        msg = 'Not of type '
        if type(classinfo) is tuple:
            if len(classinfo) > 1:
                msg += ', '.join([c.__name__ for c in classinfo[0:-1]])
                msg += ' or '
            msg += classinfo[-1].__name__
        else:
            msg += classinfo.__name__
        msg += '.'

        if type(classinfo) is tuple:

            def f(value):
                if type(value) not in classinfo:
                    raise ValueError(msg)
                return value

        else:

            def f(value):
                if type(value) is not classinfo:
                    raise ValueError(msg)
                return value

        return f

    @staticmethod
    def test_in(container):

        msg = 'Not in %r.' % (container,)

        def f(value):
            if value not in container:
                raise ValueError(msg)
            return value

        return f

    @staticmethod
    def test_type_in(type_, container):

        msg = 'Not in %r.' % (container,)

        def f(value):
            value = type_(value)
            if value not in container:
                raise ValueError(msg)
            return value

        return f

    @staticmethod
    def test_set_of(transforms):

        if type(transforms) is not tuple:
            transforms = (transforms,)
        if not transforms:
            raise ValueError('Empty tuple of transformations.')

        def f(value):
            value = iter(value)  # test iterable
            try:
                value = {
                    propex._transform(e, transforms)
                    for e in value}
            except ValueError as e:
                raise ValueError('Not cast to set (%s).' % (e,))
            return value

        return f

    @staticmethod
    def test_list_of(transforms):

        if type(transforms) is not tuple:
            transforms = (transforms,)
        if not transforms:
            raise ValueError('Empty tuple of transformations.')

        def f(value):
            value = iter(value)  # test iterable
            try:
                value = [
                    propex._transform(e, transforms)
                    for e in value]
            except ValueError as e:
                raise ValueError('Not cast to list (%s).' % (e,))
            return value

        return f

    @staticmethod
    def test_tuple_of(transforms):

        if type(transforms) is not tuple:
            transforms = (transforms,)
        if not transforms:
            raise ValueError('Empty tuple of transformations.')

        def f(value):
            value = iter(value)  # test iterable
            try:
                value = tuple(
                    propex._transform(e, transforms)
                    for e in value)
            except ValueError as e:
                raise ValueError('Not cast to tuple (%s).' % (e,))
            return value

        return f

    @staticmethod
    def test_auto_ref(transforms):

        if transforms is not None:
            if type(transforms) is not tuple:
                transforms = (transforms,)
            if not transforms:
                raise ValueError('Empty tuple of transformations.')

            def f(value):
                value = propex._transform(value, transforms)
                return propex.auto_ref(value)

            return f
        else:
            return propex.auto_ref

    @staticmethod
    def auto_ref(value):

        try:
            value = weakref.ref(value)
        except TypeError:
            pass
        return value

    @staticmethod
    def auto_unref(value):
        if isinstance(value, weakref.ReferenceType):
            value = value()
        return value

    @staticmethod
    def _transform(value, transforms):
        if transforms is not None:
            if not transforms:
                raise AttributeError('can\'t set attribute')
            # Find a valid transformation
            exceptions = []
            for transform in transforms:
                try:
                    if transform is None:
                        if value is not None:
                            raise ValueError('Not None')
                    else:
                        value = transform(value)
                    break
                except (ValueError, TypeError) as e:
                    exceptions.append(e)
                    pass
            else:
                # None found!
                exceptions = [str(e) for e in exceptions]
                exceptions = [e if e.endswith('.') else e + '.'
                              for e in exceptions]
                raise ValueError('{}: {}'.format(value, ' '.join(exceptions)))
        return value

    def _default_getter(self, inst):

        attr = self.__attr or '_' + self.__name__
        try:
            # Get the value using the internal attribute name.
            value = getattr(inst, attr)
        except AttributeError:
            # No value; Consult the default (__def) and perform the appropriate
            # action (__def_action.)
            fdef = self.__def
            def_action = self.__def_action
            if def_action is None:
                # No default; Attribute is undefined.
                raise AttributeError
            elif def_action is propex.DefaultActions.value_return_default:
                # Return the requested default value. Since it was supplied, do
                # not transform it.
                return fdef  # no transform
            elif def_action is propex.DefaultActions.method_return_default:
                # Call the specified method; Since the method supplies the
                # value, do not transform it.
                return fdef(inst)  # no transform
            elif def_action is propex.DefaultActions.function_return_default:
                # Call the specified function; Since the method supplies the
                # value, do not transform it.
                return fdef()  # no transform
            elif def_action is propex.DefaultActions.value_set_init:
                # Initialize the attribute with the requested default value.
                # Since it is stored and further access will transform it,
                # allow transformations here too.
                value = fdef
            elif def_action is propex.DefaultActions.method_set_init:
                # Call the specified method and initialize the attribute with
                # the requested default value. Since it is stored and further
                # access will transform it, allow transformations here too.
                value = fdef(inst)
            elif def_action is propex.DefaultActions.function_set_init:
                # Call the specified function and initialize the attribute with
                # the requested default value. Since it is stored and further
                # access will transform it, allow transformations here too.
                value = fdef()
            else:
                raise ValueError(def_action)
            # Reached this point due to a new "init" value; Set, transform &
            # return.
            setattr(inst, attr, value)
        try:
            # Reached this point due to an existing value or a new "init"
            # value; Transform & return.
            # Apply transformations (__gettype)
            value = self._transform(value, self.__gettype)
        except ValueError as e:
            # Transformation failed, convert to AttributeError which is
            # appropriate for a getter.
            raise AttributeError('%s: %s' % (attr, e))
        # Reached this point with a transformed value; Return.
        return value

    def _default_cgetter(self, cls):

        attr = self.__attr or '_' + self.__name__
        try:
            # Get the value using the internal attribute name.
            value = getattr(cls, attr)
        except AttributeError:
            # No value; Consult the default (__cdef) and perform the appropriate
            # action (__cdef_action.)
            cfdef = self.__cdef
            cdef_action = self.__cdef_action
            if cdef_action is None:
                # No cdefault; Return the descriptor itself
                return self
            elif cdef_action is propex.DefaultActions.value_return_default:
                # Return the requested cdefault value. Since it was supplied, do
                # not transform it.
                return cfdef  # no transform
            elif cdef_action is propex.DefaultActions.method_return_default:
                # Call the specified method; Since the method supplies the
                # value, do not transform it.
                return cfdef(cls)  # no transform
            elif cdef_action is propex.DefaultActions.function_return_default:
                # Call the specified function; Since the method supplies the
                # value, do not transform it.
                return cfdef()  # no transform
            elif cdef_action is propex.DefaultActions.value_set_init:
                # Initialize the attribute with the requested default value.
                # Since it is stored and further access will transform it,
                # allow transformations here too.
                value = cfdef
            elif cdef_action is propex.DefaultActions.method_set_init:
                # Call the specified method and initialize the attribute with
                # the requested default value. Since it is stored and further
                # access will transform it, allow transformations here too.
                value = cfdef(cls)
            elif cdef_action is propex.DefaultActions.function_set_init:
                # Call the specified function and initialize the attribute with
                # the requested default value. Since it is stored and further
                # access will transform it, allow transformations here too.
                value = cfdef()
            else:
                raise ValueError(cdef_action)
            # Reached this point due to a new "init" value; Set, transform &
            # return.
            setattr(cls, attr, value)
        try:
            # Reached this point due to an existing value or a new "init"
            # value; Transform & return.
            # Apply transformations (__gettype)
            value = self._transform(value, self.__gettype)
        except ValueError as e:
            # Transformation failed, convert to AttributeError which is
            # appropriate for a getter.
            raise AttributeError('%s: %s' % (attr, e))
        # Reached this point with a transformed value; Return.
        return value

    def _default_setter(self, inst, value):
        try:
            # Set the value using the internal attribute name.
            attr = self.__attr or '_' + self.__name__
            setattr(inst, attr, value)
        except AttributeError:
            # Convert AttributeError about _name into unspecified one
            raise AttributeError

    def _default_deleter(self, inst):
        try:
            # Delete the value using the internal attribute name.
            attr = self.__attr or '_' + self.__name__
            delattr(inst, attr)
        except AttributeError:
            # Convert AttributeError about _name into unspecified one
            raise AttributeError

    def __init__(self,
                 # Instance
                 fget=not_specified,
                 fset=not_specified,
                 fdel=not_specified,
                 fdef=not_specified,
                 fdef_method=not_specified,
                 default=not_specified,
                 finit=not_specified,
                 finit_method=not_specified,
                 init=not_specified,
                 # Class
                 cfget=not_specified,
                 cfdef=not_specified,
                 cfdef_method=not_specified,
                 cdefault=not_specified,
                 cfinit=not_specified,
                 cfinit_method=not_specified,
                 cinit=not_specified,
                 # Meta
                 name=None, attr=None,
                 type=None, gettype=None,
                 read_only=False,
                 doc=None):
        type_ = type
        type = __builtins__['type']
        getter_doc = False  # doc doesn't come from the getter

        if fget is not propex.not_specified:
            # A getter is specified.
            if name is None:
                # Default the name to the getter's name:
                #     @propex
                #     def attr_name(self):
                #         ...
                name = fget.__name__
            if doc is None:
                # Default the docimentation to the getter's doc:
                #     @propex
                #     def attr_name(self):
                #         '''getter's doc'''
                #         ...
                doc = getattr(fget, '__doc__', None)
                if doc is not None:
                    getter_doc = True  # doc comes from the getter

        if read_only:
            # read-only attributes can't be set (and type-transformed) or
            # deleted
            if fset not in (None, propex.not_specified):
                raise TypeError('read-only attributes cannot have a setter')
            if fdel not in (None, propex.not_specified):
                raise TypeError('read-only attributes cannot have a deleter')
            if type_ is not None:
                raise TypeError('read-only attributes cannot have a type')
            fset = None
            fdel = None
            type_ = None

        if fget not in (None, propex.not_specified) \
                and not callable(fget):
            raise TypeError('fget argument not callable')
        if cfget not in (None, propex.not_specified) \
                and not callable(cfget):
            raise TypeError('cfget argument not callable')
        if fset not in (None, propex.not_specified) \
                and not callable(fset):
            raise TypeError('fset argument not callable')
        if fdel not in (None, propex.not_specified) \
                and not callable(fdel):
            raise TypeError('fdel argument not callable')

        if sum([
                fdef is not propex.not_specified,
                fdef_method is not propex.not_specified,
                default is not propex.not_specified,
                finit is not propex.not_specified,
                finit_method is not propex.not_specified,
                init is not propex.not_specified]) > 1:
            raise TypeError('fdef, fdef_method, default, finit, finit_method'
                            ' and init arguments are all mutually exclusive')
        if fdef is not propex.not_specified:
            if fdef is not None and not callable(fdef):
                raise TypeError('fdef argument not callable')
            fdef = fdef
            def_action = fdef and propex.DefaultActions('fdef')
        elif fdef_method is not propex.not_specified:
            if fdef_method is not None and not callable(fdef_method):
                raise TypeError('fdef_method argument not callable')
            fdef = fdef_method
            def_action = fdef and propex.DefaultActions('fdef_method')
        elif default is not propex.not_specified:
            fdef = default
            def_action = propex.DefaultActions('default')
        elif finit is not propex.not_specified:
            if finit is not None and not callable(finit):
                raise TypeError('finit argument not callable')
            fdef = finit
            def_action = fdef and propex.DefaultActions('finit')
        elif finit_method is not propex.not_specified:
            if finit_method is not None and not callable(finit_method):
                raise TypeError('finit_method argument not callable')
            fdef = finit_method
            def_action = fdef and propex.DefaultActions('finit_method')
        elif init is not propex.not_specified:
            fdef = init
            def_action = propex.DefaultActions('init')
        else:
            fdef = None
            def_action = None

        if sum([
                cfdef is not propex.not_specified,
                cfdef_method is not propex.not_specified,
                cdefault is not propex.not_specified,
                cfinit is not propex.not_specified,
                cfinit_method is not propex.not_specified,
                cinit is not propex.not_specified]) > 1:
            raise TypeError('cfdef, cfdef_method, cdefault, cfinit, cfinit_method'
                            ' and cinit arguments are all mutually exclusive')
        if cfdef is not propex.not_specified:
            if cfdef is not None and not callable(cfdef):
                raise TypeError('cfdef argument not callable')
            cfdef = cfdef
            cdef_action = cfdef and propex.DefaultActions('fdef')
        elif cfdef_method is not propex.not_specified:
            if cfdef_method is not None and not callable(cfdef_method):
                raise TypeError('cfdef_method argument not callable')
            cfdef = cfdef_method
            cdef_action = cfdef and propex.DefaultActions('fdef_method')
        elif cdefault is not propex.not_specified:
            cfdef = cdefault
            cdef_action = propex.DefaultActions('default')
        elif cfinit is not propex.not_specified:
            if cfinit is not None and not callable(cfinit):
                raise TypeError('cfinit argument not callable')
            cfdef = cfinit
            cdef_action = cfdef and propex.DefaultActions('finit')
        elif cfinit_method is not propex.not_specified:
            if cfinit_method is not None and not callable(cfinit_method):
                raise TypeError('cfinit_method argument not callable')
            cfdef = cfinit_method
            cdef_action = cfdef and propex.DefaultActions('finit_method')
        elif init is not propex.not_specified:
            cfdef = init
            cdef_action = propex.DefaultActions('init')
        else:
            cfdef = None
            cdef_action = None

        if name is None:
            # name is mandatory as it is used for the default internal
            # attribute name and in raising meaningful AttributeError
            # exceptions.
            raise TypeError('name argument missing')
        if type(name) is not str:
            raise TypeError('name argument not a str')
        if doc is not None and type(doc) is not str:
            raise TypeError('doc argument not a str')
        if type_ is not None:
            if type(type_) is not tuple:
                # Single transformation => singleton
                type_ = (type_,)
            for transform in type_:
                if transform is not None and not callable(transform):
                    raise TypeError('type argument not callable')
        if gettype is not None:
            if type(gettype) is not tuple:
                # Single transformation => singleton
                gettype = (gettype,)
            for transform in gettype:
                if transform is not None and not callable(transform):
                    raise TypeError('gettype argument not callable')

        # Save all settings to private attributes
        self.__get = fget
        self.__cget = cfget
        self.__set = fset
        self.__del = fdel
        self.__def = fdef
        self.__def_action = def_action
        self.__cdef = cfdef
        self.__cdef_action = cdef_action
        self.__name__ = name
        self.__attr = attr
        self.__getter_doc = getter_doc
        self.__doc__ = doc
        self.__type = type_
        self.__gettype = gettype

        super().__init__()

    def copy(self, **kwargs):
        # Initialize a copy using private attributes
        d = {
            'fget': self.__get,
            'fset': self.__set,
            'fdel': self.__del,
            'fdef': propex.not_specified,
            'fdef_method': propex.not_specified,
            'default': propex.not_specified,
            'finit': propex.not_specified,
            'finit_method': propex.not_specified,
            'init': propex.not_specified,
            'cfdef': propex.not_specified,
            'cfdef_method': propex.not_specified,
            'cdefault': propex.not_specified,
            'cfinit': propex.not_specified,
            'cfinit_method': propex.not_specified,
            'name': self.__name__,
            'attr': self.__attr,
            'doc': None if self.__getter_doc else self.__doc__,
            'type': self.__type,
            'gettype': self.__gettype,
        }
        # See if any keyword arguments correspond to default actions...
        if not any(
                (e.value in kwargs)
                for e in propex.DefaultActions.__members__.values()):
            # No default action arguments given
            if self.__def_action:
                # Convert the __def/__def_action private attributes into
                # __init__'s corresponding argument
                d[self.__def_action.value] = self.__def
            else:
                # Degenerate "no default value" case.
                d['fdef'] = None
        # See if any keyword arguments correspond to default actions...
        if not any(
                (f'c{e.value}' in kwargs)
                for e in propex.DefaultActions.__members__.values()):
            # No default action arguments given
            if self.__cdef_action:
                # Convert the __cdef/__cdef_action private attributes into
                # __init__'s corresponding argument
                d[self.__cdef_action.value] = self.__cdef
            else:
                # Degenerate "no default value" case.
                d['cfdef'] = None
        # Update defaults with the caller's overrides.
        # Any invalid keyword will cause __init__ to raise TypeError. Not
        # checking them here allows better subclassing support.
        d.update(kwargs)
        # Create the new propex (or subclass)
        return type(self)(**d)

    def __copy__(self):
        return self.copy()

    def getter(self, fget):
        if fget is not None and not callable(fget):
            raise TypeError('getter argument not callable')
        return self.copy(fget=fget)

    def cgetter(self, cfget):
        if cfget is not None and not callable(cfget):
            raise TypeError('cgetter argument not callable')
        return self.copy(cfget=cfget)

    def setter(self, fset):
        if fset is not None and not callable(fset):
            raise TypeError('setter argument not callable')
        return self.copy(fset=fset)

    def deleter(self, fdel):
        if fdel is not None and not callable(fdel):
            raise TypeError('deleter argument not callable')
        return self.copy(fdel=fdel)

    def defaulter(self, fdef):
        if fdef is not None and not callable(fdef):
            raise TypeError('defaulter argument not callable')
        return self.copy(fdef_method=fdef)

    def cdefaulter(self, cfdef):
        if cfdef is not None and not callable(cfdef):
            raise TypeError('cdefaulter argument not callable')
        return self.copy(cfdef_method=cfdef)

    def initter(self, finit):
        if finit is not None and not callable(finit):
            raise TypeError('initter argument not callable')
        return self.copy(finit_method=finit)

    def __get__(self, inst, cls=None):
        if inst is None:
            # No instance; Invoked from the owner class:
            #    descriptor = MyClass.attr
            cfget = self.__cget
            if cfget is None:
                # No getter; write-only!
                # Same error message as property's
                raise AttributeError('unreadable attribute')
            if cfget is propex.not_specified:
                # No custom getter; Use propex's default cgetter
                # implementation.
                cfget = self._default_cgetter
            try:
                # Call the getter and return the value.
                return cfget(cls)
            except AttributeError as e:
                # In no error message was provided, default it to the attribute
                # name.
                e.args = e.args or (self.__name__,)
                raise
        else:
            # With instance, Invoked from the object instance:
            #     value = inst.attr
            fget = self.__get
            if fget is None:
                # No getter; write-only!
                # Same error message as property's
                raise AttributeError('unreadable attribute')
            if fget is propex.not_specified:
                # No custom getter; Use propex's default getter
                # implementation.
                fget = self._default_getter
            try:
                # Call the getter and return the value.
                return fget(inst)
            except AttributeError as e:
                # In no error message was provided, default it to the attribute
                # name.
                e.args = e.args or (self.__name__,)
                raise

    def __set__(self, inst, value):
        # Invoked from the object instance:
        #     inst.attr = value
        fset = self.__set
        if fset is None:
            # No setter; read-only!
            # Same error message as property's
            raise AttributeError('can\'t set attribute')
        # Apply transformations (__type)
        try:
            value = self._transform(value, self.__type)
        except ValueError as e:
            # Transformation failed, convert to AttributeError which is
            # appropriate for a setter.
            attr = self.__attr or '_' + self.__name__
            raise AttributeError('%s: %s' % (attr, e))
        if fset is propex.not_specified:
            # No custom setter; Use propex's default setter
            # implementation.
            fset = self._default_setter
        try:
            # Call the setter and return the value (typically None.)
            return fset(inst, value)
        except AttributeError as e:
            # In no error message was provided, default it to the attribute
            # name.
            e.args = e.args or (self.__name__,)
            raise

    def __delete__(self, inst):
        # Invoked from the object instance:
        #     del inst.attr
        fdel = self.__del
        if fdel is None:
            # No deleter; read-only!
            # Same error message as property's
            attr = self.__attr or '_' + self.__name__
            raise AttributeError('%s: can\'t delete attribute' % (attr,))
        if fdel is propex.not_specified:
            # No custom deleter; Use propex's default deleter
            # implementation.
            fdel = self._default_deleter
        try:
            # Call the deleter and return the value (typically None.)
            return fdel(inst)
        except AttributeError as e:
            # In no error message was provided, default it to the attribute
            # name.
            e.args = e.args or (self.__name__,)
            raise

    @property
    def __isabstractmethod__(self):
        fget = self.__get
        if fget not in (None, propex.not_specified) \
                and getattr(fget, "__isabstractmethod__", False):
            return True
        fset = self.__set
        if fset not in (None, propex.not_specified) \
                and getattr(fset, "__isabstractmethod__", False):
            return True
        fdel = self.__del
        if fdel not in (None, propex.not_specified) \
                and getattr(fdel, "__isabstractmethod__", False):
            return True
        fdef = self.__def
        if fdef is not None \
                and self.__def_action in (
                    propex.DefaultActions.function_return_default,
                    propex.DefaultActions.function_set_init,
                    propex.DefaultActions.method_return_default,
                    propex.DefaultActions.method_set_init) \
                and getattr(fdef, "__isabstractmethod__", False):
            return True
        return False

    def __repr__(self):
        return '{}(name={!r}, ...)'.format(
            self.__class__.__name__,
            self.__name__)

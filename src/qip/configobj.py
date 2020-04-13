
__all__ = (
        'ConfigObj',
        )

from configobj import ConfigObj as _ConfigObj

class ConfigObj(_ConfigObj):

    quote_value = _ConfigObj._quote

    quote_option = _ConfigObj._quote

    def _write_line(self, indent_string, entry, this_entry, comment):
        """Write an individual line, for the write method"""
        # NOTE: the calls to self._quote here handles non-StringType values.
        if not self.unrepr:
            val = self._decode_element(self.quote_value(this_entry))
        else:
            val = repr(this_entry)
        return '%s%s%s%s%s' % (indent_string,
                               self._decode_element(self.quote_option(entry, multiline=False)),
                               self._a_to_u(' = '),
                               val,
                               self._decode_element(comment))

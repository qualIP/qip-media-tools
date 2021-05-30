# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
        'XdgResource',
        )

from pathlib import Path
import abc
import xdg.BaseDirectory

class XdgResource(metaclass=abc.ABCMeta):

    @property
    @abc.abstractmethod
    def xdg_resource(self):
        raise NotImplementedError

    def save_config_path(self):
        return Path(xdg.BaseDirectory.save_config_path(self.xdg_resource))

    def load_config_paths(self):
        for x in xdg.BaseDirectory.load_config_paths(self.xdg_resource):
            yield Path(x)

    def load_first_config(self):
        for x in self.load_config_paths():
            return x
        return None

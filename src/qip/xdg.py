# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
        'XdgResource',
        )

from pathlib import Path
import abc
import os
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

    def prep_save_config_path(self, target_path=None):
        save_config_path = self.save_config_path()

        if target_path is not None \
                and os.path.commonpath(
                    [save_config_path, target_path]) \
                != save_config_path:
            # target is not under the save_config_path
            return

        if not save_config_path.exists():
            import platform
            if platform.system() == 'Darwin':
                # ~/.config/<app> -> ~/Library/Application Support/<app>
                macos_lib_path = Path.home() / 'Library' / 'Application Support' / self.darwin_resource
                macos_lib_path.mkdir(parents=True, exist_ok=True)
                save_config_path.parent.mkdir(parents=True, exist_ok=True)
                save_config_path.symlink_to(macos_lib_path, target_is_directory=True)
            else:
                # ~/.config/<app>
                save_config_path.mkdir(parents=True, exist_ok=True)

    @property
    def darwin_resource(self):
        try:
            return self.darwin_resource
        except AttributeError:
            return self.xdg_resource

    @darwin_resource.setter
    def darwin_resource(self, value):
        self._darwin_resource = value

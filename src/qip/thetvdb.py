#!/usr/bin/env python3
"""TheTVDB API Access

See: https://api.thetvdb.com/swagger

Attribution: TV information and images are provided by TheTVDB.com, but we are not endorsed or certified by TheTVDB.com or its affiliates.
"""

__all__ = [
]

import qip  # Executable support

from pathlib import Path
import configparser
import io
import os
import tvdb_api

from qip.isolang import isolang
from qip.xdg import XdgResource

class Tvdb(tvdb_api.Tvdb, XdgResource):

    xdg_resource = 'thetvdb'

    def default_config_file(self):
        config_file1 = self.save_config_path() / 'config'
        if config_file1.exists():
            return config_file1
        config_file2 = Path.home() / '.thetvdb.conf'
        if config_file2.exists():
            return config_file2
        return config_file1  # The default that doesn't exist

    config_file_parser = None

    def __init__(self, *,
                 apikey=None,
                 username=None,
                 userkey=None,
                 config_file=None,
                 language=None,
                 **kwargs):

        config_file = config_file or self.default_config_file()
        self.config_file_parser = configparser.ConfigParser(allow_no_value=True)
        if isinstance(config_file, io.IOBase):
            self.config_file_parser.read_file(config_file)
        elif isinstance(config_file, (str, os.PathLike)):
            self.config_file_parser.read([os.fspath(config_file)])
        else:
            raise TypeError(config_file)

        try:
            auth_config = self.config_file_parser['auth']
        except KeyError:
            pass
        else:
            try:
                apikey = apikey or auth_config['apikey']
            except KeyError:
                pass
            try:
                username = username or auth_config['username']
            except KeyError:
                pass
            try:
                userkey = userkey or auth_config['userkey']
            except KeyError:
                pass

        super().__init__(**kwargs)

        # tvdb_api.Tvdb requires all 3 variables to be set so fill them manually instead
        self.config['auth_payload']['apikey'] = apikey
        self.config['auth_payload']['username'] = username
        self.config['auth_payload']['userkey'] = userkey

        self.language = 'en' if language is None else language

    @property
    def language(self):
        return self.config['language']

    @language.setter
    def language(self, value):
        self.config['language'] = 'en' if value is None else isolang(value).iso639_1
        # Fixup since it is forced in
        self.headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Language': self.config['language']}

if __name__ == "__main__":
    import logging
    import re
    from qip.app import app

    @app.main_wrapper
    def main():

        app.init(logging_level=logging.DEBUG)

        tvdb = Tvdb(
            apikey='d38d1a8df34d030f1be077798db952bc',  # mmdemux
            interactive=True)

        tvshow = app.input_dialog(title='TheTVDB',
                                  text='Please provide tvshow [lang]')
        m = re.match(r'^(?P<tvshow>.+) \[(?P<language>\w\w\w)\]', tvshow)
        if m:
            tvdb.language = m.group('language')
            tvshow = m.group('tvshow').strip()

        l_series = tvdb.search(tvshow)
        assert l_series, "No series!"

        for i, d_series in enumerate(l_series):
            print('{seriesName} [{language}], {network}, {firstAired}, {status} (#{id})'.format_map(d_series))

    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker

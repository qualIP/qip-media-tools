#!/usr/bin/env python3
"""Goodreads API Access

See: https://www.goodreads.com/api/keys

"""

__all__ = [
    'GoodreadsClient',
]

import qip  # Executable support

from pathlib import Path
import configparser
import datetime
import goodreads.client
import io
import os

_goodreads = goodreads
del goodreads

from qip.isolang import isolang
from qip.xdg import XdgResource

def goodreads_parse_date(tup):
    """Convert goodreads date to Python date.

    goodreads module uses a tuple of strings for dates:

        tuple(str(month), str(day), str(year))
    """
    if tup == (None, None, None):
        return None
    month, day, year = tup
    return datetime.date(day=int(day or 1), month=int(month or 1), year=int(year))

def goodreads_cite_book(book, cite_api=None):
    """Cite a book."""

    if cite_api is None:
        from qip.cite import default as cite_api

    publication_date = goodreads_parse_date(book.publication_date)
    return cite_api.cite_book(
        authors=[e.name for e in book.authors],
        title=book.title,
        edition=book.edition_information,
        publisher=book.publisher,
        publication_date=publication_date and publication_date.year,
        medium='E-book' if book.is_ebook == 'true' else 'Print',
    )


class GoodreadsClient(_goodreads.client.GoodreadsClient, XdgResource):

    xdg_resource = 'goodreads'

    def default_config_file(self):
        config_file1 = self.save_config_path() / 'config'
        if config_file1.exists():
            return config_file1
        config_file2 = Path.home() / '.goodreads.conf'
        if config_file2.exists():
            return config_file2
        return config_file1  # The default that doesn't exist

    config_file_parser = None

    def __init__(self, *,
                 client_key=None,
                 client_secret=None,
                 access_token=None,
                 access_token_secret=None,
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
                client_key = client_key or auth_config['client_key']
            except KeyError:
                pass
            try:
                client_secret = client_secret or auth_config['client_secret']
            except KeyError:
                pass
            try:
                access_token = access_token or auth_config['access_token']
            except KeyError:
                pass
            try:
                access_token_secret = access_token_secret or auth_config['access_token_secret']
            except KeyError:
                pass

        super().__init__(client_key=client_key,
                         client_secret=client_secret,
                         **kwargs)

        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.language = language

    def oauth_init(self):
        # Overridden here to fix URLs http->https
        """Start outh and return authorization url."""
        service = OAuth1Service(
            consumer_key=self.client_key,
            consumer_secret=self.client_secret,
            name='goodreads',
            request_token_url='https://www.goodreads.com/oauth/request_token',
            authorize_url='https://www.goodreads.com/oauth/authorize',
            access_token_url='https://www.goodreads.com/oauth/access_token',
            base_url='https://www.goodreads.com/'
        )
        request_token, request_token_secret = service.get_request_token(header_auth=True)
        auth_url = service.get_authorize_url(request_token)
        # Store service for finalizing
        self.request_token = request_token
        self.request_token_secret = request_token_secret
        self.service = service
        return auth_url

    def authenticate(self, access_token=None, access_token_secret=None):
        access_token = access_token or self.access_token
        access_token_secret = access_token_secret or self.access_token_secret
        return super().authenticate(access_token=access_token, access_token_secret=access_token_secret)

    @property
    def language(self):
        return self._language

    @language.setter
    def language(self, value):
        self._language = 'en' if value is None else isolang(value).iso639_1

    parse_date = staticmethod(goodreads_parse_date)
    cite_book = staticmethod(goodreads_cite_book)

if __name__ == "__main__":
    import logging
    import re
    from qip.app import app

    @app.main_wrapper
    def main():

        app.init(logging_level=logging.DEBUG)

        gc = GoodreadsClient(
            # taged API key:
            client_key='OtgaaV6YFDY88U0WoW5h3w',
            client_secret='I9b9PDjDpK9rLT8iMy09lE1fKIjjvwXt4Vy1DAPiSxo',
        )

        gc.authenticate()
        print(f'OAuth: access_token={gc.session.access_token}, access_token_secret={gc.session.access_token_secret}')

        title = app.input_dialog(title='Goodreads',
                                 text='Please provide book title [lang]',
                                 initial_text='The Reptile Room (A Series of Unfortunate Events #2)')
        if not title:
            raise Exception('Cancelled by user')
        m = re.match(r'^(?P<title>.+) \[(?P<language>\w\w\w)\]', title)
        if m:
            gc.language = m.group('language')
            title = m.group('title').strip()

        books = gc.search_books(title, search_field='title')
        if not books:
            raise ValueError('No books found')

        book = app.radiolist_dialog(title='Books',
                                    values=[(book, str(book))
                                            for book in books])
        if not book:
            raise Exception('Cancelled by user')

        def authors_str(authors):
            return '; '.join(str(e) for e in authors)

        image_url = book.image_url
        full_image_url = re.sub(r'\._SX\d+_(\.jpg)$', r'\1', image_url or '')

        def filter_author(author):
            role = author._author_dict['role']
            if role in (
                    None,
            ):
                return True
            if role in (
                    'Illustrator',
            ):
                return False
            raise NotImplementedError(f'Author role {role!r}')

        authors = [
            author
            for author in book.authors
            if filter_author(author)
        ]
        non_authors = [
            author
            for author in book.authors
            if not filter_author(author)
        ]

        print(f'''
title={book.title},
authors={authors_str(authors)},
non_authors={authors_str(non_authors)},
country_code={book._book_dict["country_code"]},
work={book.work}'
series_works={book.series_works}'
publication_date={book.publication_date}'
publisher={book.publisher}'
language_code={book.language_code}'
edition_information={book.edition_information}'
image_url={book.image_url}'
full_image_url={full_image_url}'
is_ebook={book.is_ebook}'
format={book.format}'
link={book.link}'
description={book.description}
''')

        # print(f'_book_dict={book._book_dict!r}')

        title = book.title
        if book.series_works:
            series_work = book.series_works['series_work']
            series_position = series_work['user_position']
            series_title = series_work['series']['title']
            title = re.sub(rf' \({re.escape(series_title)}, #{series_position}\)$', '', title)
        else:
            series_position = series_title = None
        base_title = title
        if series_title:
            title = f'{base_title} ({series_title} #{series_position})'
            sorttitle = '{series_title} #{series_position:02d} - {base_title}'
        else:
            sorttitle = None

        from qip.mm import AlbumTags
        tags = AlbumTags()

        tags.title = title
        if sorttitle:
            tags.sorttitle = sorttitle
        tags.artist = [str(e) for e in authors]
        from datetime import datetime
        m, d, y = book.publication_date
        tags.date = datetime(year=int(y), month=int(m), day=int(d))
        tags.language = book.language_code
        tags.picture = image_url
        tags.longdescription = book.description
        tags.country = book._book_dict["country_code"]

        tags.pprint()

    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et

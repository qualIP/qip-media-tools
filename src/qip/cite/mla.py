
""" MLA Citation Support

See: https://www.bibme.org/citation-guide/mla/
"""

__all__ = (
    'cite_book',
    'cite_movie',
    'cite_tvshow',
)

import datetime
import collections


def oxford_list_join(words):
    if not words:
        return None
    if len(words) == 2 and words[-1] != 'et al':
        return ' and '.join(str(e) for e in words)
    if len(words) > 2 and words[-1] != 'et al':
        return ', '.join(str(e) for e in words[:-1]) + ', and ' + str(words[-1])
    return ', '.join(str(e) for e in words)


def scan_date(date):
    if not date:
        return None
    if isinstance(date, (datetime.date, datetime.datetime)):
        return date
    if isinstance(date, int):
        return datetime.date(year=date, month=1, day=1)
    try:
        return datetime.date(date)
    except:
        pass
    try:
        return datetime.datetime.strptime(date, '%Y-%m-%d').date()
    except:
        pass
    return date


def format_international_date(date):
    date = scan_date(date)
    if not isinstance(date, (datetime.date, datetime.datetime)):
        return date
    day = date.day
    month = date.strftime('%B')
    year = date.year
    month = {
        'January': 'Jan.',
        'February': 'Feb.',
        'March': 'Mar.',
        'April': 'Apr.',
        'May': 'May',
        'June': 'June',
        'July': 'July',
        'August': 'Aug.',
        'September': 'Sept.',
        'October': 'Oct.',
        'November': 'Nov.',
        'December': 'Dec.',
    }.get(month, month)
    return f'{day} {month} {year}'


def format_personnel(*,
                     # parts
                     narrator=None,
                     narrators=None,
                     screenplay_writer=None,
                     screenplay_writers=None,
                     director=None,
                     directors=None,
                     writer=None,
                     writers=None,
                     performers=None,
                     producer=None,
                     producers=None,
                     # options
                     **kwargs,
                     ):
    cite = ''

    for (prefix, one_value, list_value) in (
            ('Screenplay by', screenplay_writer, screenplay_writers),
            ('Writ.', writer, writers),
            ('Dir.', director, directors),
            ('Prod.', producer, producers),
            ('Narr.', narrator, narrators),
            ('Perf.', None, performers),
    ):
        if one_value:
            list_value = [one_value]
        if list_value:
            if cite:
                cite += ' '
            cite += f'{prefix} {oxford_list_join(list_value)}.'

    return cite or None


def cite_book(*,
              # parts
              authors=None,
              name=None,
              last_name=None, first_name=None,
              chapter=None,
              title,
              subtitle=None,
              edition=None,
              original_year=None,
              is_reprint=False,
              publisher_city=None,
              publisher=None,
              published_year=None,
              page_range=None,
              medium=None,
              # options
              abbreviate_authors=False,
              curly_quotes=False,
              # aliases
              date=None,
              publication_date=None,
              mediatype=None,
              **kwargs):
    """https://www.bibme.org/citation-guide/mla/book/

    Format:
        Last Name, First Name. Book Title. Publisher City: Publisher Name, Year Published. Medium.
    """
    print(f'{name!r}, {published_year!r}, {original_year!r}, {kwargs!r}')

    ldquo, rdquo = '“”' if curly_quotes else '""'
    cite = ''

    if published_year is None:
        if date is None:
            date = publication_date
        date = scan_date(date)
        if date:
            published_year = date.year

    if medium is None:
        medium = mediatype

    # How to cite a book in a bibliography using MLA

    # The most basic entry for a book consists of the author’s name, the book
    # title, publisher city, publisher name, year of publication, and medium.
    #
    # Last Name, First Name. Book Title. Publisher City: Publisher Name, Year Published. Medium.
    #
    # Smith, John. The Sample Book. Pittsburgh: BibMe, 2008. Print.
    #
    # The first author’s name should be reversed, with a comma being placed
    # after the last name and a period after the first name (or any middle
    # name). The name should not be abbreviated and should be written exactly
    # as it appears on the title page. Titles and affiliations associated with
    # the author should generally be omitted. A suffix, such as a roman numeral
    # or Jr./Sr. should appear after the author’s given name, preceded by a
    # comma.

    if authors:
        authors = list(authors)
        name = authors.pop(0)
    else:
        authors = []

    if name:
        try:
            if ',' in name:
                raise ValueError
            first_name, last_name = name.split(' ')
        except ValueError:
            first_name, last_name = name, ''
    name = ''
    if last_name:
        if name:
            name += ' '
        name += last_name
    if first_name:
        if last_name:
            name += ', '
        elif name:
            name += ' '
        name += first_name
    if name:
        authors.insert(0, name)

    # For books with three or more authors, you may either include each author
    # in the citation or only include the first author, followed by the
    # abbreviation “et al.”
    #
    # Smith, John, Jane Doe, and Bob Anderson. The Sample Book. Pittsburgh: BibMe, 2008. Print.
    #
    # Smith, John, et al. The Sample Book. Pittsburgh: BibMe, 2008. Print.

    if abbreviate_authors and len(authors) >= 3:
        authors[1:] = ['et al']

    # For a book written by two or more authors, list them in order as they
    # appear on the title page. Only the first author’s name should be
    # reversed, while the others are written in normal order. Separate author
    # names by a comma, and place the word “and” before the last author’s name.

    authors = oxford_list_join(authors)

    if authors:
        if cite:
            cite += ' '
        cite += f'{authors}.'

    # If you are citing a specific chapter from the book, include the chapter
    # name and a period in quotations before the book title.

    if chapter:
        if cite:
            cite += ' '
        cite += f'{ldquo}{chapter}.{rdquo}'

    # The full title of the book, including any subtitles, should be italicized
    # and followed by a period.

    assert title
    # TODO <i>
    if title:
        if cite:
            cite += ' '
        cite += title

    #
    # If the book has a subtitle, the main title
    # should be followed by a colon (unless the main title ends with a question
    # mark or exclamation point).

    if subtitle:
        if cite[-1] in '?!':
            cite += ' '
        else:
            cite += ': '
        cite += subtitle

    # TODO </i>
    cite += '.'

    # When a book has no edition number/name present, it is generally a first
    # edition. If you have to cite a specific edition of a book later than the
    # first, you should indicate the new edition in your citation. If the book
    # is a revised edition or an edition that includes substantial new content,
    # include the number, name, or year of the edition and the abbreviation
    # “ed.” in parentheses between the book title and the period that follows
    # it. “Revised edition” should be abbreviated as “Rev. ed.” and “Abridged
    # edition” should be abbreviated as “Abr. ed.” The edition can usually be
    # found on the title page, as well as on the copyright page, along with the
    # edition’s date.
    #
    # Smith, John. The Sample Book. 2nd ed. Pittsburgh: BibMe, 2008. Print.
    #
    # Smith, John. The Sample Book. Rev. ed. Pittsburgh: BibMe, 2008. Print.

    if edition:
        edition = {
            'Revised': 'Rev.',
            'Abridged': 'Abr.',
        }.get(edition, edition)
        if cite:
            cite += ' '
        cite += f'{edition} ed.'

    # If the book is a reprint edition and is a newly republished version of an
    # older book, include the following information after the period that
    # follows the book title: the original year of publication and the word
    # “Reprint”, both followed by periods. The publication year at the end of
    # the citation should be the year of the book’s reprinting.
    #
    # Smith, John. The Sample Book. 1920. Reprint. Pittsburgh: BibMe, 2008. Print.

    if is_reprint:
        if original_year:
            if cite:
                cite += ' '
            cite += f'{original_year}.'
        if cite:
            cite += ' '
        cite += 'Reprint.'

    # The publication information can generally be found on the title page of
    # the book. If it is not available there, it may also be found on the
    # copyright page. State the publication city and then a colon. If there are
    # multiple cities listed, include only the first city.

    if publisher_city:
        if cite:
            cite += ' '
        cite += publisher_city

    # Next state the publisher name, which should be abbreviated where
    # appropriate; articles (e.g. A, An), business titles (e.g. Co., Corp.,
    # Inc., Ltd.), and descriptive words (e.g. Books, House, Press, Publishers)
    # should be omitted. If the publisher is a university press, though, you
    # should include the abbreviation “P” in the publisher name to distinguish
    # it from the university, which may publish independently of the publisher
    # in question. A publisher name consisting of the name(s) of person(s)
    # should be abbreviated to only include the last name of the first person
    # listed. Standard abbreviations should be used for other words (e.g.
    # Acad., Assn., Soc., UP). The publisher name is followed by a comma, the
    # year of publication, a period, the medium in which the book was published
    # (e.g. Print, Web), and a period.

    if publisher:
        if publisher_city:
            cite += ': '
        elif cite:
            cite += ' '
        cite += publisher

    if published_year:
        if publisher_city or publisher:
            cite += ', '
        elif cite:
            cite += ' '
        cite += str(published_year)

    if publisher_city or publisher or published_year:
        cite += '.'

    # [If you are citing a specific chapter from the book...] Also include the
    # range of page numbers for the chapter, along with a period, in between
    # the publication year and the medium.
    #
    # Smith, John. “The First Chapter.” The Sample Book. Pittsburgh: BibMe, 2008. 12-20. Print.

    if page_range:
        if cite:
            cite += ' '
        if len(page_range) > 1:
            cite += f'{page_range[0]}-{page_range[-1]}'
        else:
            cite += f'page_range[0]'
        cite += '.'

    if medium:
        if cite:
            cite += ' '
        cite += f'{medium}.'

    return cite


def cite_movie(*,
               # parts
               title,
               original_title=None,
               # [personnel...]
               original_year=None,
               distributor=None,
               distribution_year=None,
               medium=None,
               # options
               # aliases
               date=None,
               mediatype=None,
               **kwargs):
    """https://www.bibme.org/citation-guide/mla/film/

    Format:
        Film title. Dir. First Name Last Name. Distributor, Year of Release. Medium.
    """

    cite = ''

    if distribution_year is None:
        date = scan_date(date)
        if date:
            distribution_year = date.year

    if medium is None:
        medium = mediatype

    # How to cite a film in a bibliography using MLA

    # The most basic entry for a film consists of the title, director,
    # distributor, year of release, and medium. You may also choose to include
    # the names of the writer(s), performer(s), and the producer(s), as well as
    # the film’s original release date.
    #
    # Film title. Dir. First Name Last Name. Distributor, Year of Release. Medium.
    #
    # BibMe: The Movie. Dir. John Smith. Columbia, 2009. Film.

    # The citation should begin with the film title italicized, followed by a
    # period. If the film is dubbed in English or does not have an English
    # title, you may begin by including the title as translated in English,
    # followed by the original title in square brackets.
    #
    # [Yes, the example is flawed! - qualIP]
    # BibMe: La Película [BibMe: The Movie]. Dir. John Smith. Columbia, 2009. Film.

    assert title
    if title:
        if cite:
            cite += ' '
        # TODO <i>
        cite += title
        # TODO </i>

    if original_title:
        if cite:
            cite += ' '
        cite += f'[{original_title}]'

    if title or original_title:
        cite += '.'

    # The director’s name should be cited, preceded by the abbreviation “Dir.”
    # If relevant, you may also choose to include the names of the writer(s),
    # performer(s) (preceded by the abbreviation “Perf.”), and/or producer(s)
    # (preceded by the abbreviation “Prod.”). Group different types of
    # personnel together and separate each personnel group by a period. Write
    # these personnel names in normal order – do not reverse the first and last
    # names.
    #
    # BibMe: The Movie. Screenplay by Jane Doe. Dir. John Smith. Prod. Bob Johnson. Perf. Mike Jones and Jim Jones. Columbia, 2009. Film.

    personnel = format_personnel(**kwargs)
    if personnel:
        if cite:
            cite += ' '
        cite += personnel

    # If you would like to emphasize the contributions of a specific person in
    # your citation, start the citation with that person’s name, followed by a
    # comma, an abbreviation for their position, and a period. The person’s
    # name should be reversed, with a comma being placed after the last name. A
    # suffix, such as a roman numeral or Jr./Sr. should appear after the
    # author’s given name, preceded by a comma.
    #
    # Johnson, Bob, prod. BibMe: The Movie. Screenplay by Jane Doe. Dir. John Smith. Perf. Mike Jones and Jim Jones. Columbia, 2009. Film.
    # TODO

    # List the distributor of the film, followed by a comma, the year released,
    # and a period. If the film’s original year of release differs from the
    # year of release for the copy of the film you viewed, include the original
    # year of release after the personnel, and place the year of release for
    # the copy of the film you viewed after the distributor.
    #
    # BibMe: The Movie. Dir. John Smith. 2007. Columbia, 2009. Film.

    if original_year and original_year != distribution_year:
        if cite:
            cite += ' '
        cite += f'{original_year}.'

    if distributor:
        if cite:
            cite += ' '
        cite += distributor

    if distribution_year:
        if distributor:
            cite += ', '
        elif cite:
            cite += ' '
        cite += str(distribution_year)

    if distributor or distribution_year:
        cite += '.'

    # Conclude the citation with the medium on which you viewed the film, which
    # may be videocassette, DVD, laser disc, etc., followed by a period. If you
    # are citing a theater viewing of the film or you are citing the film
    # without reference to a particular copy of it, use the word “Film”. Slide
    # programs or filmstrips should be cited as films.
    #
    # BibMe: The Slide Program. Dir. John Smith. Columbia, 2009. Slide program.
    #
    # BibMe: The Movie. Dir. John Smith. Columbia, 2009. DVD.

    if medium:
        if cite:
            cite += ' '
        cite += f'{medium}.'

    return cite


def cite_tvshow(*,
                # parts
                title=None,  # Episode title
                tvshow=None,
                season=None,
                episode=None,
                is_series=True,
                network=None,
                station_call_letters=None,
                station_city=None,
                date=None,
                medium=None,
                is_transcript=False,
                # [personnel...]
                # options
                curly_quotes=False,
                mediatype=None,
                **kwargs):

    ldquo, rdquo = '“”' if curly_quotes else '""'
    cite = ''

    if medium is None:
        medium = mediatype

    # How to cite a TV / Radio program in a bibliography using MLA
    #
    # The most basic citation for a radio/TV program consists of the episode
    # title, program/series name, broadcasting network, the original broadcast
    # date, and the medium.
    #
    # “Episode Title.” Program/Series Name. Network. Original Broadcast Date. Medium.
    #
    # “The Highlights of 100.” Seinfeld. Fox. 17 Feb. 2009. Television.
    #
    # Begin the citation with the episode name or number, along with a period,
    # inside quotation marks. Follow it with the name of the program or series,
    # which is italicized, followed by a period.

    personnel = format_personnel(**kwargs)

    if title:
        if cite:
            cite += ' '
        cite += f'{ldquo}{title}.{rdquo}'

    # If relevant, you may also choose to include the names of personnel
    # involved with the program. Depending on if the personnel are relevant to
    # the specific episode or the series as a whole, place the personnel names
    # either after the episode title or the program/series name. You may cite
    # narrator(s) (preceded by the abbreviation “Narr.”), writer(s) (preceded
    # by the abbreviation “Writ.”), director (preceded by the abbreviation
    # “Dir.”), performer(s) (preceded by the abbreviation “Perf.”), and/or
    # producer(s) (preceded by the abbreviation “Prod.”). Group different types
    # of personnel together and separate each personnel group by a period.
    # Write these personnel names in normal order – do not reverse the first
    # and last names.
    #
    # “The Highlights of 100.” Narr. Jerry Seinfeld. Writ. Peter Mehlman. Dir. Andy Ackerman. Perf. Jerry Seinfeld, Jason Alexander, Julia Louis-Dreyfus, and Michael Richards. Prod. Larry David. Seinfeld. Fox. WNYW, New York City. 17 Feb. 2009. Television.

    if title and personnel:
        if cite:
            cite += ' '
        cite += personnel

    if tvshow:
        if cite:
            cite += ' '
        # TODO <i>
        cite += f'{tvshow}'
        # TODO </i>
        if season is not None:
            if cite:
                cite += ', '
            if season == 0:
                cite += f'specials'
            else:
                cite += f'season {season}'
        if episode is not None:
            if not isinstance(episode, collections.abc.Iterable) or isinstance(episode, str):
                episode = (episode,)
            episode = list(str(e) for e in episode)
            if episode and episode != ['0']:
                if cite:
                    cite += ', '
                cite += 'episode{s} {episode}'.format(
                    s='s' if len(episode) > 1 else '',
                    episode=oxford_list_join(episode))
        cite += f'.'

    if not title and personnel:
        if cite:
            cite += ' '
        cite += personnel

    # Also include the name of the network on which the program was broadcast,
    # followed by a period.

    if network:
        if cite:
            cite += ' '
        cite += f'{network}.'

    # If the program was broadcast on a local affiliate of a national network,
    # include the call letters and city of the local station, separated by a
    # comma, after the name of the network. Follow the city with a period.
    #
    # “The Highlights of 100.” Seinfeld. Fox. WNYW, New York City. 17 Feb. 2009. Television.

    if station_call_letters:
        if cite:
            cite += ' '
        cite += station_call_letters

    if station_city:
        if station_call_letters:
            cite += ', '
        elif cite:
            cite += ' '
        cite += station_city

    if station_call_letters or station_city:
        cite += '.'

    # State the date on which your program was originally broadcast, along with
    # a period. The complete date should be written in the international format
    # (e.g. “day month year”). With the exception of May, June, and July, month
    # names should be abbreviated (four letters for September, three letters
    # for all other months) and followed with a period.

    # If you need to cite just a program/series, begin the citation with the
    # program/series name, followed by the relevant personnel. For a series,
    # cite the first year of airing in place of a specific broadcast date.
    #
    # Seinfeld. Prod. Larry David. Fox. WNYW, New York City. 1989. Television.
    #
    # Breaking the Magicians’ Code: Magic’s Biggest Secrets Finally Revealed. Narr. Mitch Pileggi. Fox. WNYW, New York City. 24 Nov. 1997. Television.

    date = scan_date(date)
    if date:
        if cite:
            cite += ' '
        if title or not is_series:
            cite += f"{format_international_date(date)}."
        elif isinstance(date, (datetime.date, datetime.datetime)):
            cite += f"{date.year}."
        else:
            cite += f"{date}."

    # End the citation with the medium in which your program was broadcast
    # (e.g. Television, Radio) and a period.

    if medium:
        if cite:
            cite += ' '
        cite += f'{medium}.'

    # If you are citing a transcript of the program, the medium within the
    # citation should be the medium in which the transcript was published (e.g.
    # Print, Web), not the medium in which the program was broadcast. End the
    # citation with the word “Transcript” and a period.
    #
    # “The Highlights of 100.” Seinfeld. Fox. WNYW, New York City. 17 Feb. 2009. Print. Transcript.

    if is_transcript:
        if cite:
            cite += ' '
        cite += 'Transcript.'

    return cite

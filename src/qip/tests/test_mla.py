#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import unittest

from pathlib import Path
import os
import sys

import qip.cite.mla as mla

import logging
#logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

import reprlib
reprlib.aRepr.maxdict = 100

test_dir = Path(__file__).parent.absolute()


class test_mla(unittest.TestCase):

    @property
    def tmp_dir(self):
        return test_dir / f'tmp{Path(self.id()).suffix}'

    def test_cite_book(self):

        self.assertEqual(
            mla.cite_book(
                last_name="Last Name",
                first_name="First Name",
                title="Book Title",
                publisher_city="Publisher City",
                publisher="Publisher Name",
                published_year="Year Published",
                medium="Medium",
            ),
            "Last Name, First Name. Book Title. Publisher City: Publisher Name, Year Published. Medium.")

        self.assertEqual(
            mla.cite_book(
                last_name="Smith",
                first_name="John",
                title="The Sample Book",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John. The Sample Book. Pittsburgh: BibMe, 2008. Print.")
        self.assertEqual(
            mla.cite_book(
                name="Smith, John",
                title="The Sample Book",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John. The Sample Book. Pittsburgh: BibMe, 2008. Print.")
        self.assertEqual(
            mla.cite_book(
                name="John Smith",
                title="The Sample Book",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John. The Sample Book. Pittsburgh: BibMe, 2008. Print.")
        self.assertEqual(
            mla.cite_book(
                authors=["John Smith",],
                title="The Sample Book",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John. The Sample Book. Pittsburgh: BibMe, 2008. Print.")

        self.assertEqual(
            mla.cite_book(
                authors=["John Smith", "Jane Doe", "Bob Anderson"],
                title="The Sample Book",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John, Jane Doe, and Bob Anderson. The Sample Book. Pittsburgh: BibMe, 2008. Print.")
        self.assertEqual(
            mla.cite_book(
                authors=["John Smith", "Jane Doe", "Bob Anderson"],
                title="The Sample Book",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
                abbreviate_authors=True,
            ),
            "Smith, John, et al. The Sample Book. Pittsburgh: BibMe, 2008. Print.")

        self.assertEqual(
            mla.cite_book(
                last_name="Smith",
                first_name="John",
                title="The Sample Book",
                edition="2nd",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John. The Sample Book. 2nd ed. Pittsburgh: BibMe, 2008. Print.")

        self.assertEqual(
            mla.cite_book(
                last_name="Smith",
                first_name="John",
                title="The Sample Book",
                edition="Revised",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John. The Sample Book. Rev. ed. Pittsburgh: BibMe, 2008. Print.")

        self.assertEqual(
            mla.cite_book(
                last_name="Smith",
                first_name="John",
                title="The Sample Book",
                original_year=1920,
                is_reprint=True,
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
            ),
            "Smith, John. The Sample Book. 1920. Reprint. Pittsburgh: BibMe, 2008. Print.")

        self.assertEqual(
            mla.cite_book(
                last_name="Smith",
                first_name="John",
                chapter="The First Chapter",
                page_range=range(12, 21),
                title="The Sample Book",
                publisher_city="Pittsburgh",
                publisher="BibMe",
                published_year=2008,
                medium="Print",
                curly_quotes=True,
            ),
            "Smith, John. “The First Chapter.” The Sample Book. Pittsburgh: BibMe, 2008. 12-20. Print.")

    def test_cite_movie(self):

        self.assertEqual(
            mla.cite_movie(
                title="Film title",
                director="First Name Last Name",
                distributor="Distributor",
                distribution_year="Year of Release",
                medium="Medium",
            ),
            "Film title. Dir. First Name Last Name. Distributor, Year of Release. Medium.")
        self.assertEqual(
            mla.cite_movie(
                title="Film title",
                directors=["First Name Last Name"],
                distributor="Distributor",
                distribution_year="Year of Release",
                medium="Medium",
            ),
            "Film title. Dir. First Name Last Name. Distributor, Year of Release. Medium.")

        self.assertEqual(
            mla.cite_movie(
                title="BibMe: The Movie",
                director="John Smith",
                distributor="Columbia",
                distribution_year=2009,
                medium="Film",
            ),
            "BibMe: The Movie. Dir. John Smith. Columbia, 2009. Film.")

        self.assertEqual(
            mla.cite_movie(
                title="BibMe: La Película",
                original_title="BibMe: The Movie",
                director="John Smith",
                distributor="Columbia",
                distribution_year=2009,
                medium="Film",
            ),
            # [Yes, the example is flawed! - qualIP]
            "BibMe: La Película [BibMe: The Movie]. Dir. John Smith. Columbia, 2009. Film.")

        self.assertEqual(
            mla.cite_movie(
                title="BibMe: The Movie",
                screenplay_writer="Jane Doe",
                director="John Smith",
                producer="Bob Johnson",
                performers=["Mike Jones", "Jim Jones"],
                distributor="Columbia",
                distribution_year=2009,
                medium="Film",
            ),
            "BibMe: The Movie. Screenplay by Jane Doe. Dir. John Smith. Prod. Bob Johnson. Perf. Mike Jones and Jim Jones. Columbia, 2009. Film.")

        self.assertEqual(
            mla.cite_movie(
                title="BibMe: The Movie",
                director="John Smith",
                original_year=2007,
                distributor="Columbia",
                distribution_year=2009,
                medium="Film",
            ),
            "BibMe: The Movie. Dir. John Smith. 2007. Columbia, 2009. Film.")

        self.assertEqual(
            mla.cite_movie(
                title="BibMe: The Slide Program",
                director="John Smith",
                distributor="Columbia",
                distribution_year=2009,
                medium="Slide program",
            ),
            "BibMe: The Slide Program. Dir. John Smith. Columbia, 2009. Slide program.")

        self.assertEqual(
            mla.cite_movie(
                title="BibMe: The Movie",
                director="John Smith",
                distributor="Columbia",
                distribution_year=2009,
                medium="DVD",
            ),
            "BibMe: The Movie. Dir. John Smith. Columbia, 2009. DVD.")

    def test_cite_tvshow(self):

        self.assertEqual(
            mla.cite_tvshow(
                title="Episode Title",
                tvshow="Program/Series Name",
                network="Network",
                date="Original Broadcast Date",
                medium="Medium",
                curly_quotes=True,
            ),
            "“Episode Title.” Program/Series Name. Network. Original Broadcast Date. Medium.")

        self.assertEqual(
            mla.cite_tvshow(
                title="The Highlights of 100",
                tvshow="Seinfeld",
                network="Fox",
                date="2009-02-17",
                medium="Television",
                curly_quotes=True,
            ),
            "“The Highlights of 100.” Seinfeld. Fox. 17 Feb. 2009. Television.")

        self.assertEqual(
            mla.cite_tvshow(
                title="The Highlights of 100",
                tvshow="Seinfeld",
                network="Fox",
                station_call_letters="WNYW",
                station_city="New York City",
                date="2009-02-17",
                medium="Television",
                curly_quotes=True,
            ),
            "“The Highlights of 100.” Seinfeld. Fox. WNYW, New York City. 17 Feb. 2009. Television.")

        self.assertEqual(
            mla.cite_tvshow(
                title="The Highlights of 100",
                narrator="Jerry Seinfeld",
                writer="Peter Mehlman",
                director="Andy Ackerman",
                performers=["Jerry Seinfeld", "Jason Alexander", "Julia Louis-Dreyfus", "Michael Richards"],
                producer="Larry David",
                tvshow="Seinfeld",
                network="Fox",
                station_call_letters="WNYW",
                station_city="New York City",
                date="2009-02-17",
                medium="Television",
                curly_quotes=True,
            ),
            #"“The Highlights of 100.” Narr. Jerry Seinfeld. Writ. Peter Mehlman. Dir. Andy Ackerman. Perf. Jerry Seinfeld, Jason Alexander, Julia Louis-Dreyfus, and Michael Richards. Prod. Larry David. Seinfeld. Fox. WNYW, New York City. 17 Feb. 2009. Television.")
            "“The Highlights of 100.” Writ. Peter Mehlman. Dir. Andy Ackerman. Prod. Larry David. Narr. Jerry Seinfeld. Perf. Jerry Seinfeld, Jason Alexander, Julia Louis-Dreyfus, and Michael Richards. Seinfeld. Fox. WNYW, New York City. 17 Feb. 2009. Television.")

        self.assertEqual(
            mla.cite_tvshow(
                tvshow="Seinfeld",
                producer="Larry David",
                network="Fox",
                station_call_letters="WNYW",
                station_city="New York City",
                date="1989-01-01",
                medium="Television",
                curly_quotes=True,
            ),
            "Seinfeld. Prod. Larry David. Fox. WNYW, New York City. 1989. Television.")

        self.assertEqual(
            mla.cite_tvshow(
                tvshow="Breaking the Magicians’ Code: Magic’s Biggest Secrets Finally Revealed",
                is_series=False,
                narrator="Mitch Pileggi",
                network="Fox",
                station_call_letters="WNYW",
                station_city="New York City",
                date="1997-11-24",
                medium="Television",
                curly_quotes=True,
            ),
            "Breaking the Magicians’ Code: Magic’s Biggest Secrets Finally Revealed. Narr. Mitch Pileggi. Fox. WNYW, New York City. 24 Nov. 1997. Television.")

        self.assertEqual(
            mla.cite_tvshow(
                title="The Highlights of 100",
                tvshow="Seinfeld",
                network="Fox",
                station_call_letters="WNYW",
                station_city="New York City",
                date="2009-02-17",
                medium="Print",
                is_transcript=True,
                curly_quotes=True,
            ),
            "“The Highlights of 100.” Seinfeld. Fox. WNYW, New York City. 17 Feb. 2009. Print. Transcript.")

if __name__ == '__main__':
    unittest.main()

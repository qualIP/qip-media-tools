#!/usr/bin/env python3

import unittest
import operator

import qip.mm
from qip.mm import MediaTagEnum, AlbumTags, FrameRate

class test_snd(unittest.TestCase):

    def test_AlbumTags(self):

        album_tags = AlbumTags()
        album_tags.title = '-title-'
        album_tags.year = 2019
        self.assertEqual(album_tags.title, '-title-')
        self.assertEqual(album_tags.year, 2019)
        self.assertEqual(operator.attrgetter('year', 'month', 'day')(album_tags.date), (2019, None, None))
        self.assertEqual(str(album_tags.date), '2019')
        self.assertIs(album_tags.artist, None)
        self.assertIn(MediaTagEnum.albumtitle, album_tags)
        self.assertIn(MediaTagEnum.title, album_tags)
        self.assertIn(MediaTagEnum.date, album_tags)
        self.assertIn(MediaTagEnum.year, album_tags)
        self.assertTrue(album_tags.contains('year'))
        self.assertTrue(album_tags.contains(MediaTagEnum.year))
        self.assertFalse(album_tags.contains(MediaTagEnum.year, strict=True))  # even with year->date
        self.assertIn(MediaTagEnum.composer, album_tags)
        self.assertTrue(album_tags.contains('composer'))
        self.assertTrue(album_tags.contains(MediaTagEnum.composer))
        self.assertFalse(album_tags.contains(MediaTagEnum.composer, strict=True))
        self.assertEqual(dict(album_tags),
                         {
                             #MediaTagEnum.albumtitle: '-title-',
                             MediaTagEnum.title: '-title-',
                             MediaTagEnum.date: qip.mm.MediaTagDate('2019'),
                         })

    def test_FrameRate_round_common(self):

        FrameRate(24000, 1000).round_common == FrameRate(24000, 1000)
        FrameRate(24000, 1001).round_common == FrameRate(24000, 1001)
        FrameRate(30000, 1000).round_common == FrameRate(30000, 1000)
        FrameRate(30000, 1001).round_common == FrameRate(30000, 1001)
        FrameRate(1/0.033367, 1).round_common == FrameRate(24000, 1001)

if __name__ == '__main__':
    unittest.main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker

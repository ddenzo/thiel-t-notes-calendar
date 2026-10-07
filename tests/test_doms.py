import datetime as dt
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from calendar_builder import parse_doms

class DomsTests(unittest.TestCase):
    def test_captured_page(self):
        soup = BeautifulSoup((Path(__file__).parent / 'doms.html').read_text(), 'html.parser')
        events = parse_doms(soup, dt.date(2026, 10, 7))
        self.assertEqual(len(events), len(soup.select('hr')))
        self.assertEqual(events[0]['description'], 'Thiel hosts Grove City in women’s tennis.')
        self.assertEqual(events[1]['location'], 'Stoeber Field at Alumni Stadium')
        self.assertIn('Biweekly', events[2]['description'])
        self.assertTrue(any(e['links'] for e in events))
    def test_new_year(self):
        soup = BeautifulSoup('<p><strong>Event</strong><br>Jan. 2 at noon<br><em>Stamm Hall</em></p><p>A workshop.</p><hr>', 'html.parser')
        self.assertEqual(parse_doms(soup, dt.date(2026, 12, 30))[0]['date'], '2027-01-02')
    def test_invalid_page(self):
        with self.assertRaises(ValueError):
            parse_doms(BeautifulSoup('error', 'html.parser'), dt.date(2026,10,7))

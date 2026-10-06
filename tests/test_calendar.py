import unittest
import datetime as dt
from pathlib import Path
from bs4 import BeautifulSoup
from calendar_builder import ap_time, location, detail, render

class CalendarTests(unittest.TestCase):
    def test_times(self):
        for raw, expected in [('12:00pm', 'noon'), ('11:00am', '11 a.m.'), ('12:01am', '12:01 a.m.'), ('7:30pm', '7:30 p.m.')]:
            self.assertEqual(ap_time(raw)[0], expected)
        self.assertIsNone(ap_time('TBA')[0])
    def test_locations(self):
        self.assertEqual(location('Stamm Hall', None), 'Stamm Hall, James Pedas Communication Center')
        self.assertEqual(location('Lutheran Heritage Room - HMSC', None), 'Lutheran Heritage Room, Howard Miller Student Center')
        self.assertEqual(location('Alumni Stadium', 'football'), 'Stoeber Field at Alumni Stadium')
    def test_live_fixtures(self):
        for name in ['tennis', 'stress']:
            soup = BeautifulSoup((Path(__file__).parent / (name + '.html')).read_text(), 'html.parser')
            event = detail(soup, '', dt.date(2026, 10, 7), 'https://www.thiel.edu/calendar/')
            self.assertIsNotNone(event['time'])
            self.assertEqual(render(event).count('\n'), 3)
            if name == 'tennis':
                self.assertEqual(event['description'], 'Thiel hosts Grove City in women’s tennis.')
            else:
                self.assertIn('editorial review', ' '.join(event['warnings']))
    def test_links(self):
        soup = BeautifulSoup('<h5 class="modal-title">Workshop</h5><div class="modal-body"><p class="eventpagedt">11:00am</p><p class="eventpagelocation">Bly Hall</p><p>The workshop covers writing. <a href="https://example.org/register">Register here</a></p><hr><p>Contact</p></div>', 'html.parser')
        e = detail(soup, '', dt.date(2026, 10, 7), 'https://www.thiel.edu/calendar/')
        self.assertEqual(e['links'][0]['url'], 'https://example.org/register')
        self.assertIn('Register here.', e['description'])
        self.assertNotIn('Contact', e['source_description'])

from datetime import date,timedelta
from unittest import TestCase
from neurofocus.pages import periods


class PeriodTests(TestCase):
    def test_week_starts_monday_across_new_year(self):
        groups=periods(1,date(2027,1,1))
        self.assertEqual(groups[-1][:2],(date(2026,12,28),date(2027,1,3)))

    def test_months_contiguous_and_include_leap_day(self):
        groups=periods(2,date(2028,3,1))
        self.assertEqual(groups[-2][1],date(2028,2,29))
        for prior,following in zip(groups,groups[1:]):
            self.assertEqual(prior[1]+timedelta(days=1),following[0])

    def test_last_seven_days(self):
        groups=periods(0,date(2026,1,3))
        self.assertEqual((groups[0][0],groups[-1][1]),(date(2025,12,28),date(2026,1,3)))

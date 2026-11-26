import random
import unittest
from dataclasses import replace
from neurofocus.config import Settings
from neurofocus.engine import Engine


class TimerTests(unittest.TestCase):
    def begin(self, **kwargs):
        self.engine=Engine(lambda a,b:a)
        self.engine.start(replace(Settings(),**kwargs),0)
        return self.engine

    def test_default_contract(self):
        s=Settings()
        self.assertEqual((s.focus,s.long,s.low,s.high,s.micro),(90,20,3,5,10))
        self.assertTrue(s.micro_on and s.inclusive and s.auto_long)

    def test_random_redrawn_within_bounds(self):
        rng=random.Random(42)
        seen=[]
        def draw(a,b):
            value=rng.randint(a,b)
            seen.append(value)
            return value
        e=Engine(draw)
        e.start(Settings(focus=720),0)
        e.tick(720*60000,720*60000)
        self.assertGreater(len(set(seen)),130)
        self.assertTrue(all(180000<=x<=300000 for x in seen))

    def test_pause_resume_fractional_second(self):
        e=self.begin()
        e.pause(1234,1234)
        e.tick(1000000,1000000)
        self.assertEqual(e.used,1234)
        e.resume(1000200)
        e.tick(1000767,1000767)
        self.assertEqual(e.used,1801)

    def test_micro_pause_and_resample(self):
        e=self.begin(low=1,high=1)
        events=e.tick(60000,60000)
        self.assertEqual(events[-1].kind,"micro_start")
        e.pause(61100,61100)
        self.assertEqual(e.remaining(),8900)
        e.resume(100000)
        self.assertEqual(e.tick(108900,108900)[-1].kind,"resume_focus")
        self.assertEqual(e.left,60000)

    def test_focus_end_wins_tie(self):
        e=self.begin(focus=1,low=1,high=1)
        entries=e.tick(60000,60000)
        self.assertEqual([v.kind for v in entries],["focus","complete","long_start"])

    def test_inclusive_truncates_micro_at_end(self):
        e=self.begin(focus=2,low=1,high=1,micro=90)
        e.tick(60000,60000)
        self.assertEqual(e.remaining(),60000)
        rows=e.tick(120500,120500)
        self.assertEqual([(v.kind,v.duration) for v in rows],
                         [("micro",60000),("complete",0),("long_start",0),("long",500)])

    def test_exclusive_micro_delays_completion(self):
        e=self.begin(focus=2,low=1,high=1,micro=10,inclusive=False)
        entries=e.tick(130000,130000)
        self.assertEqual(sum(v.duration for v in entries if v.kind=="focus"),120000)
        self.assertEqual(sum(v.duration for v in entries if v.kind=="micro"),10000)
        self.assertEqual(e.phase,"long")

    def test_long_end_waits_for_user(self):
        e=self.begin(focus=1,long=1,micro_on=False)
        rows=e.tick(86400000,86400000)
        self.assertEqual(e.phase,"idle")
        self.assertEqual(sum(v.duration for v in rows),120000)
        self.assertEqual(rows[-1].at,120000)
        self.assertEqual(e.tick(90000000,90000000),[])

    def test_auto_long_off(self):
        e=self.begin(focus=1,auto_long=False)
        self.assertEqual(e.tick(60001,60001)[-1].kind,"complete")
        self.assertEqual(e.phase,"idle")

    def test_12_hour_irregular_updates_no_drift(self):
        e=self.begin(focus=720,inclusive=False)
        now=0
        totals={"focus":0,"micro":0,"long":0}
        rng=random.Random(17)
        while e.phase!="idle":
            now+=rng.randrange(1,15000)
            for row in e.tick(now,now):
                if row.duration: totals[row.kind]+=row.duration
        self.assertEqual(totals["focus"],43200000)
        self.assertEqual(totals["long"],1200000)
        self.assertEqual(totals["micro"],2390000)

    def test_wallclock_changes_do_not_change_elapsed(self):
        e=self.begin()
        e.tick(1000,9000000)
        e.tick(5000,4000000)
        self.assertEqual(e.used,5000)

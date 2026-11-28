from dataclasses import replace
from datetime import datetime,date
from pathlib import Path
import json,sqlite3,tempfile,unittest
from neurofocus.calendar_data import CalendarData
from neurofocus.config import Settings
from neurofocus.controller import Controller
from neurofocus.engine import Engine
from neurofocus.history import activities,session_detail
from neurofocus.modes import Profile,default
from neurofocus.mode_stats import mode_totals
from neurofocus.storage import Store
from neurofocus.visual import stamp
from test_storage import FakeClock

class FocusPolicies(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.store=Store(self.root/"study.sqlite3")
        self.addCleanup(self.store.db.close)
        self.clock=FakeClock()
        self.c=Controller(self.store,self.root/"settings.json",Settings(),self.clock,Engine(lambda a,b:a))
        self.db=self.store.db
        self.e=self.c.engine

    def use(self,key,**cfg):
        p=replace(default(key),**cfg)
        self.c.save_profile(p)
        self.c.profiles.select(key)
        return p

    def tick(self,ms,action=None,**options):
        self.clock.step(ms)
        return self.c.update(action,**options)

    def test_four_pomodoros_and_partial_do_not_advance(self):
        self.use("pomo",focus=1,short=1,long=2)
        for i,phase in enumerate(("short","short","short","long"),1):
            self.c.start()
            self.assertEqual(self.e.round_index,i)
            self.assertEqual(self.tick(60000),["complete",phase+"_start"])
            self.assertEqual(self.e.phase,phase)
            self.assertEqual(self.tick(120000 if i==4 else 60000),[phase+"_end"])
            self.assertIsNone(self.c.sid)
        self.c.start()
        self.tick(12500,"ended")
        self.c.start()
        self.assertEqual(self.e.round_index,1)
        self.assertEqual(self.db.execute("SELECT sum(completed),sum(focus) FROM days").fetchone(),(4,252500))

    def test_ready_manual_start_skip_and_pause_on_break(self):
        self.use("pomo",focus=1,rounds=2,auto_long=False)
        self.c.start()
        self.tick(60100)
        self.assertEqual(self.e.phase,"ready")
        self.tick(90000,"begin_rest")
        self.assertEqual(self.e.phase,"short")
        self.tick(1234,"pause")
        self.tick(9000,"resume")
        self.tick(566,"skip_rest")
        self.assertEqual(self.db.execute("SELECT ms FROM rest_days").fetchone(),(1800,))
        self.assertEqual(self.db.execute("SELECT paused_ms FROM session_protocol").fetchone(),(9000,))
        self.c.start()
        self.tick(60000)
        self.c.update("begin_rest")
        self.assertEqual(self.e.phase,"long")

    def test_delayed_callback_stops_at_manual_rest_prompt(self):
        self.use("pomo",focus=1,short=1,auto_long=False)
        self.c.start()
        self.assertEqual(self.tick(500000),["complete"])
        self.assertEqual(self.e.phase,"ready")
        self.assertEqual(self.e.remaining(),60000)
        self.c.update("begin_rest")
        self.assertEqual(self.e.remaining(),60000)
        self.assertEqual(self.db.execute("SELECT sum(focus) FROM days").fetchone(),(60000,))

    def test_auto_next_uses_queued_mode_and_exact_boundary(self):
        self.use("pomo",focus=1,short=1,auto_next=True)
        self.c.start()
        old=self.c.sid
        self.use("deep",focus=45)
        events=self.tick(120235)
        self.assertIn("auto_start",events)
        self.assertEqual(self.e.actual,235)
        self.assertNotEqual(self.c.sid,old)
        self.assertEqual(self.e.config.id,"deep")
        self.assertEqual(self.e.target,45*60000)
        self.c.update("flush")
        self.assertEqual(self.db.execute("SELECT sum(ms) FROM focus_spans").fetchone(),(60235,))
        first_end,second_start=self.db.execute("SELECT a.updated,b.started FROM sessions a,sessions b WHERE a.id=? AND b.id=?",(old,self.c.sid)).fetchone()
        self.assertEqual(first_end,second_start)

    def test_auto_next_delayed_wakeup_does_not_invent_focus(self):
        self.use("deep",focus=1,long=1,auto_next=True)
        self.c.start()
        self.tick(720000)
        self.assertIsNone(self.c.sid)
        self.assertEqual(self.store.history()[0][2:5],(60000,0,60000))

    def test_flow_pause_hint_boundaries_manual_duration_and_hours(self):
        p=self.use("flow",reminder=60)
        self.assertEqual([p.suggested_minutes(ms) for ms in [0,1499999,1500000,2999999,3000000,5399999,5400000]],[5,5,8,8,15,15,20])
        self.assertEqual(replace(p,break_steps=(3,6,9,12)).suggested_minutes(5400000),12)
        self.assertEqual(replace(p,suggest=False,long=7).suggested_minutes(5400000),7)
        self.c.start()
        self.tick(1234,"pause")
        self.tick(90000,"resume")
        self.assertEqual(self.tick(3660000),["rest_hint"])
        self.assertEqual(stamp(self.e.remaining(),True),"1:01:01")
        self.c.update("rest",minutes=7)
        self.c.update("rest",minutes=3)
        self.assertEqual(self.e.remaining(),420000)
        self.tick(11111,"skip_rest")
        self.assertEqual(self.db.execute("SELECT kind,ms FROM rest_days").fetchone(),("manual",11111))
        self.assertEqual(self.db.execute("SELECT minutes FROM manual_rest_plan").fetchone(),(7,))
        self.assertEqual(self.store.history()[0][2],3661234)
        self.assertEqual(self.store.history()[0][-1],0)

    def test_custom_snapshot_rename_delete_and_persistence(self):
        p=replace(self.c.profiles.create(),name="读原典",count_up=True,micro_on=True,low=1,high=1,short_on=True,grouped=True)
        self.c.save_profile(p)
        self.c.profiles.select(p.id)
        self.c.start()
        self.tick(70000)
        self.assertEqual(self.e.actual,60000)
        self.c.save_profile(replace(p,name="读书"))
        reopened=Controller(self.store,self.c.path,Settings(),self.clock)
        self.assertEqual(reopened.selected_profile.name,"读书")
        self.assertEqual(self.e.config.name,"读原典")
        self.c.profiles.delete(p.id)
        self.tick(1300,"ended")
        self.assertEqual(self.c.selected_profile.id,"neuro")
        a=activities(self.db)[0]
        self.assertEqual((a.mode_name,a.ms),("读原典",61300))
        self.assertIn("读原典",session_detail(self.db,a))
        raw=json.loads(self.db.execute("SELECT config FROM session_protocol").fetchone()[0])
        self.assertEqual((raw["id"],raw["count_up"],raw["round_index"]),(p.id,True,1))

    def test_deep_early_break_and_next_run_reset(self):
        self.use("deep",focus=60)
        self.c.start()
        self.tick(172345,"rest",minutes=1)
        self.assertEqual(self.e.phase,"manual")
        self.tick(60000)
        self.assertEqual(self.store.history()[0][1:4],("ended",172345,0))
        self.c.start()
        self.tick(3600000)
        self.assertEqual(self.e.phase,"long")
        self.assertEqual(self.store.history()[0][-1],1)

    def test_same_activity_semantics_and_cross_midnight_stats(self):
        self.use("flow")
        tag=self.store.tags.save("数学","#118844")
        self.clock.wall=round(datetime(2026,12,31,23,59,58).timestamp()*1000)
        self.c.start()
        self.tick(1000)
        self.c.select_tag(tag)
        self.tick(3000,"rest",minutes=3)
        self.tick(3005,"skip_rest")
        period=mode_totals(self.db,date(2026,12,31),date(2027,1,1))
        self.assertEqual(period,[("flow","Flowtime",4000,3,1)])
        self.assertEqual(len(activities(self.db)),3)
        cal=CalendarData(self.db,date(2026,12,31),date(2027,1,1),date(2027,1,1))
        self.assertEqual(cal.ms,4000)
        self.assertEqual(cal.days[date(2027,1,1)].manual_rest,3005)
        self.assertEqual(mode_totals(self.db,"2027-01-01","2027-01-01")[0][2],2000)
        self.store.export(self.root/"out.json")
        data=json.loads((self.root/"out.json").read_text(encoding="utf8"))
        self.assertEqual(sum(r["自主休息秒"] for r in data["records"]),3.005)
        self.assertEqual(data["protocols"][0]["config"]["id"],"flow")

    def test_retry_cycle_commit_and_suspend(self):
        self.use("pomo",focus=1)
        self.c.start()
        self.db.execute("CREATE TRIGGER fail BEFORE UPDATE ON sessions BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.tick(60000)
        self.db.execute("DROP TRIGGER fail")
        self.tick(5000,"suspend")
        self.assertEqual(self.db.execute("SELECT next_round FROM cycle_cursor").fetchone(),(2,))
        self.clock.wall+=3600000
        self.clock.woke=True
        self.tick(0)
        self.assertTrue(self.e.paused)
        self.assertEqual(self.db.execute("SELECT sum(ms) FROM rest_days").fetchone(),(5000,))
        self.assertEqual(self.db.execute("SELECT sum(completed) FROM days").fetchone(),(1,))

    def test_schema_backup_once_and_legacy_unknown(self):
        sid=self.store.start(self.clock.wall)
        from neurofocus.engine import Entry
        self.store.checkpoint(sid,[Entry("focus",self.clock.wall,2000)],self.clock.wall+2000,"done")
        self.db.execute("DROP TABLE rest_days")
        for _ in range(2): Store(self.root/"study.sqlite3").db.close()
        self.assertEqual(len(list(self.root.glob("study-before-focus-engine-*.sqlite3"))),1)
        self.assertEqual(mode_totals(self.db,date.min,date.max),[("legacy","旧版记录",2000,1,1)])

    def test_invalid_configs_and_stable_identity(self):
        for params in ({"name":" "},{"rounds":0},{"low":5,"high":3},{"break_steps":(0,1,2,3)},{"count_up":1}):
            with self.subTest(params=params),self.assertRaises(ValueError): Profile(**params)
        self.assertNotEqual(self.c.profiles.create().id,self.c.profiles.create().id)
        self.use("deep",focus=45)
        self.assertEqual(self.c.profiles.items["neuro"].focus,90)

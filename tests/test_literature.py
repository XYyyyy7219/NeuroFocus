import json
import os
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from neurofocus.literature import CATALOG, Entry, Library, Source, excerpt_lines, parse_bundle, read_json


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.file = Path(temp.name)/"local.json"
        self.lib = Library(self.file)
        self.now = datetime(2026,3,12,9)

    def test_public_assets_and_all_reviewed_coordinates(self):
        rows = list(parse_bundle(read_json(CATALOG)).values())
        expected = [(1,322,328),(2,984,984),(5,6827,6831),(5,6839,6841),(2,1046,1046),
                    (3,3765,3765),(4,5263,5263),(5,6793,6793),(2,384,384),(2,842,842),
                    (2,868,868),(2,1026,1038),(2,2466,2466),(1,258,260),(2,816,816),
                    (2,1318,1318),(3,3343,3351),(3,3273,3273),(3,3283,3283),(5,6139,6139),
                    (5,6791,6791),(1,60,60),(2,1132,1132),(2,2483,2483),(3,2719,2719),
                    (4,4853,4853),(4,4859,4859),(4,4863,4863)]
        names = "乱世的序幕 草原下的历史 少年南行 英雄的相遇 承担命运 挣脱束缚 天下和睦的理想 选择自己的道路 独自仰望星空 夕阳与北辰 对命星的质疑 古风尘的星辰演算 鹰的视野与星空 对弱小生命的悲悯 一生的承诺 读书与宽仁 与众不同的世子 得失与本心 内心的选择 人生不止于功业 成就与孤独 落日与流云 草原上的日出 雨后的星空 春日午后的梦 延伸至地平线的彩虹 北陆的简单之美 云雾中的彤云大山".split()
        sections = "历史 三 四 历史 四 八 九 四 一 三 三 四 十三 二 历史 五 六 五 五 一 四 一 五 十四 二 六 六 六".split()
        self.assertEqual(len(rows),36)
        for i, (chapter,first,last) in enumerate(expected):
            row = rows[i]
            self.assertEqual((row.id,row.title), (f"NF-V01-{i+1:03}",names[i]))
            self.assertTrue(row.reviewed)
            self.assertFalse(row.enabled)
            self.assertIsNone(row.text)
            self.assertEqual((row.source.author,row.source.book,row.source.volume,row.source.volumeTitle),
                             ("江南","九州缥缈录",1,"蛮荒"))
            self.assertTrue(row.source.chapter.startswith("第"+"一二三四五"[chapter-1]+"章"))
            self.assertEqual((row.source.section,row.source.lineStart,row.source.lineEnd),(sections[i],first,last))
            self.assertGreaterEqual(len(row.tags),2)
        self.assertEqual(rows[7].categories,("少年与理想","温柔与悲悯"))
        # Allowlist the exact eight approved public originals separately from private imports.
        originals = rows[28:]
        self.assertTrue(all(e.source==Source("NeuroFocus","原创示例") and e.enabled for e in originals))
        digest = sha256("\n".join(e.id+":"+e.text for e in originals).encode()).hexdigest()
        self.assertEqual(digest,"be5c48aa82a61410fc59e2b30fc8388eccb02c9fc6b2fec14110a40770124123")

    def test_daily_scenes_rotation_restart_and_manual(self):
        morning = self.lib.choose("home",self.now)
        self.assertTrue({"少年与理想","宁静与自然"}.intersection(morning.categories))
        self.assertEqual(Library(self.file).choose("home",self.now.replace(hour=23)),morning)
        sky = self.lib.choose("starMap",self.now)
        self.assertIn("starMap",sky.scenes)
        self.assertNotEqual(self.lib.choose("home",self.now,another=True),morning)
        tomorrow = self.now+timedelta(days=1)
        pinned = self.lib.choose("home",tomorrow,period="manual")
        self.assertEqual(self.lib.choose("home",tomorrow+timedelta(days=40),period="manual"),pinned)
        sequence = [self.lib.choose("home",tomorrow+timedelta(days=i)).id for i in range(9)]
        self.assertTrue(all(a!=b for a,b in zip(sequence,sequence[1:])))
        self.assertGreaterEqual(len(set(sequence)),7)

    def test_private_excerpt_and_local_export(self):
        key="NF-V01-010"
        base=CATALOG.read_bytes()
        self.lib.edit(key,text="仅用于本测试的授权占位文本",enabled=True,favorite=True)
        self.assertTrue(Library(self.file).entries[key].favorite)
        self.assertEqual(CATALOG.read_bytes(),base)
        out=self.file.with_name("backup.nfquotes.json")
        self.lib.export(out)
        fresh=Library(self.file.with_name("restore.json"))
        fresh.import_bundle(read_json(out))
        self.assertEqual(fresh.entries,self.lib.entries)
        self.lib.edit(key,enabled=False)
        self.assertFalse(Library(self.file).entries[key].enabled)
        self.assertTrue(Library(self.file).entries[key].text)

    def test_cross_volume_duplicates_bad_import_roll_back(self):
        template=asdict(self.lib.entries["NF-V01-010"])
        row={**template,"id":"NF-V02-001","source":{**template["source"],"volume":2},
             "text":"One 测试","enabled":True}
        self.lib.import_bundle({"version":1,"entries":[row]})
        previous=self.file.read_bytes()
        for bad in ([row,row], [{**row,"id":"OTHER","text":"ＯＮＥ测 试"}],
                    [{**row,"source":{**row["source"],"volume":3}}],
                    [{**row,"text":" ","enabled":True}], [{**row,"scenes":["void"]}],
                    [{**row,"source":{**row["source"],"lineEnd":0}}],
                    [{**template,"title":"错误的覆盖"}]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.lib.import_bundle({"version":1,"entries":bad})
            self.assertEqual(previous,self.file.read_bytes())

    def test_failures_leave_content_and_daily_choice_intact(self):
        selected=self.lib.choose("home",self.now)
        before=self.file.read_bytes()
        with patch("neurofocus.literature.os.replace",side_effect=OSError), self.assertRaises(OSError):
            self.lib.edit(selected.id,favorite=True)
        self.assertEqual(before,self.file.read_bytes())
        self.assertFalse(self.lib.entries[selected.id].favorite)
        self.file.write_bytes(b"{")
        lib=Library(self.file)
        self.assertTrue(lib.problem)
        self.assertIsNotNone(lib.choose("home",self.now))
        self.assertEqual(self.file.read_bytes(),b"{")

    def test_empty_and_scene_specific_pool(self):
        self.lib.import_bundle({"version":1,"entries":[asdict(replace(e,enabled=False)) for e in self.lib.entries.values()]})
        self.assertIsNone(self.lib.choose("starMap",self.now))
        row={"id":"mine","title":"测试","source":{"author":"测试作者","book":"本地手记"},
             "category":"星辰与求知","text":"独立的测试正文","scenes":["home"]}
        self.lib.import_bundle({"version":1,"entries":[row]})
        self.assertEqual(self.lib.choose("home",self.now).id,"mine")
        self.lib.import_bundle({"version":1,"entries":[{**row,"scenes":["starMap"]}]})
        self.assertIsNone(self.lib.choose("home",self.now))
        self.assertEqual(self.lib.choose("starMap",self.now).id,"mine")

    def test_read_only_txt_range_encoding_and_version(self):
        path=self.file.with_suffix(".txt")
        source=Source("作者","作品",lineStart=2,lineEnd=3)
        for enc in ("utf-8-sig","utf-16","gb18030"):
            raw="开始\r\n本地段落\r\n另一行\r\n结束".encode(enc)
            path.write_bytes(raw)
            self.assertEqual(excerpt_lines(path,source),"本地段落\n另一行")
            self.assertEqual(path.read_bytes(),raw)
        with self.assertRaises(ValueError):
            excerpt_lines(path,replace(source,lineEnd=99))

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import curate  # noqa: E402

NOW = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Claude Code &amp; CLAUDE.md 運用</title>
<link>https://www.google.com/url?rct=j&amp;sa=t&amp;url=https%3A%2F%2Fexample.com%2Fa%2F%3Futm_source%3Dx%26id%3D1&amp;ct=ga</link>
<description>&lt;b&gt;要約&lt;/b&gt;です</description><pubDate>Sat, 31 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Claude Code &amp; CLAUDE.md 運用!</title><link>https://example.com/b</link>
<description>dup title</description><pubDate>Sat, 31 Oct 2026 11:00:00 GMT</pubDate></item>
<item><title>古い記事</title><link>https://example.com/old</link>
<description>x</description><pubDate>Mon, 01 Sep 2026 11:00:00 GMT</pubDate></item>
<item><title>別の記事</title><link>https://example.com/a?id=1</link>
<description>same url</description><pubDate>Sat, 31 Oct 2026 12:00:00 GMT</pubDate></item>
<item><title>処理済み</title><link>https://example.com/seen</link>
<description>x</description><pubDate>Sat, 31 Oct 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title>
<link rel="alternate" href="https://example.org/x/"/><summary>S</summary>
<updated>2026-10-31T10:00:00Z</updated></entry></feed>"""


class T(unittest.TestCase):
    def test_google_redirect(self):
        u = "https://www.google.com/url?rct=j&url=https%3A%2F%2Fexample.com%2Fa&ct=ga"
        self.assertEqual(curate.resolve_google_redirect(u), "https://example.com/a")
        self.assertEqual(curate.resolve_google_redirect("https://example.com/z"), "https://example.com/z")

    def test_normalize(self):
        self.assertEqual(curate.normalize_url("HTTPS://Example.com/a/?utm_source=x&id=1#top"),
                         "https://example.com/a?id=1")

    def test_parse_rss_and_atom(self):
        arts = curate.parse_feed(RSS.encode())
        self.assertEqual(len(arts), 5)
        self.assertEqual(arts[0].url, "https://example.com/a?id=1")
        self.assertEqual(arts[0].summary, "要約 です")
        self.assertEqual(curate.parse_feed(ATOM.encode())[0].url, "https://example.org/x")

    def test_filter_first_run(self):
        seen = {"initialized": False, "items": {}, "titles": {}}
        seen["items"]["https://example.com/seen"] = "2026-10-30"
        arts = curate.parse_feed(RSS.encode())
        out, st = curate.filter_new(arts, seen, NOW, 3)
        self.assertEqual([a.url for a in out], ["https://example.com/a?id=1"])
        self.assertEqual(st, {"seen": 1, "duplicate": 2, "too_old": 1})
        self.assertIn("https://example.com/old", seen["items"])

    def test_filter_later_run_keeps_old(self):
        seen = {"initialized": True, "items": {}, "titles": {}}
        out, st = curate.filter_new(curate.parse_feed(RSS.encode()), seen, NOW, 3)
        self.assertEqual(st["too_old"], 0)

    def test_feed_roundtrip_and_retention(self):
        a = curate.Article("タイトル <x>", "https://example.com/n", "sum", NOW, "example.com")
        a.areas, a.score, a.comment = ["md", "dx"], 4, "参考になる"
        old = curate.article_to_item(a, NOW - timedelta(days=61))
        old["guid"] = "https://example.com/old"
        items = curate.merge_items([old], [curate.article_to_item(a, NOW)], NOW, 60)
        self.assertEqual([i["guid"] for i in items], ["https://example.com/n"])
        import tempfile
        p = Path(tempfile.mkdtemp()) / "feed.xml"
        p.write_bytes(curate.build_feed(items, {"feed_title": "t", "feed_link": "l", "feed_description": "d"}, NOW))
        back = curate.load_feed_items(p)
        self.assertEqual(back[0]["guid"], "https://example.com/n")
        self.assertTrue(back[0]["title"].startswith(curate.AREAS["md"] + curate.AREAS["dx"]))
        self.assertIn("参考になる", back[0]["description"])

    def test_stage1_unjudged_not_marked_seen(self):
        class G:
            def generate_json(self, prompt):
                return [{"id": 0, "relevant": True, "practical": True, "areas": ["app", "xx", "app"], "score": 4},
                        {"id": 1, "relevant": False, "practical": False, "areas": [], "score": 1}]
        arts = [curate.Article(f"t{i}", f"https://e.com/{i}", "", NOW, "e.com") for i in range(3)]
        seen = {"initialized": True, "items": {}, "titles": {}}
        s = {"stage1_batch_size": 25, "stage1_threshold": 3}
        passed, scores = curate.run_stage1(G(), "c", arts, s, seen, NOW)
        self.assertEqual((len(passed), scores), (1, [4, 1]))
        self.assertEqual(passed[0].areas, ["app"])
        self.assertEqual(list(seen["items"]), ["https://e.com/1"])

    def test_score_summary(self):
        self.assertEqual(curate.score_summary([5, 4, 4, 3, 1]), "5点1 / 4点2 / 3点以下2")

    def test_stage2_threshold(self):
        class G:
            def __init__(self):
                self.n = 0

            def generate_json(self, prompt):
                self.n += 1
                return {"keep": True, "areas": ["md"], "score": 3 if self.n == 1 else 4, "comment": "c"}
        import unittest.mock as m
        arts = [curate.Article(f"t{i}", f"https://e.com/{i}", "", NOW, "e.com") for i in range(2)]
        for a in arts:
            a.areas = ["md"]
        seen = {"initialized": True, "items": {}, "titles": {}}
        with m.patch.object(curate, "fetch_body", return_value=None):
            acc, scores, ok, ng = curate.run_stage2(G(), "c", arts, {"final_threshold": 4}, seen, NOW)
        self.assertEqual((len(acc), scores, ng), (1, [3, 4], 2))


if __name__ == "__main__":
    unittest.main()

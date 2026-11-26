"""Tests for review_page.py revision binding and feedback handling."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "skills", "video-explainer", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import review_page


def make_solid_video(path, color, w=320, h=180, dur=2.0, fps=24):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:r={fps}:d={dur}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
        ],
        check=True,
    )


def average_rgb(image_path):
    raw = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", image_path,
            "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return tuple(raw[:3])


def post_json(url, payload):
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


class ReviewPageRevisionTests(unittest.TestCase):
    def _start_server(self, root, page, feedback, scenes, video, words):
        review_page.write_page(root, page, video, scenes)
        work = os.path.dirname(os.path.abspath(feedback))

        def run_serve():
            review_page.serve(root, page, feedback, scenes, video, 0, False, 30, words)

        thread = threading.Thread(target=run_serve, daemon=True)
        thread.start()
        info_path = os.path.join(work, "review-server.json")
        deadline = time.monotonic() + 5.0
        base_url = None
        while time.monotonic() < deadline:
            info = review_page.read_json(info_path, {})
            url = info.get("url", "")
            if url:
                base_url = url.split("/work/")[0]
                try:
                    with urlopen(base_url + "/api/health", timeout=1) as resp:
                        if resp.status == 200:
                            break
                except OSError:
                    pass
            time.sleep(0.05)
        self.assertIsNotNone(base_url, "Review server did not start in time")
        return base_url

    def test_note_sent_after_draft2_publishes_keeps_draft1_frame_scene_and_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tmp
            page = os.path.join(root, "work", "review", "index.html")
            feedback = os.path.join(root, "work", "feedback.md")
            v1 = os.path.join(root, "renders", "demo-v1.mp4")
            v2 = os.path.join(root, "renders", "demo-v2.mp4")
            make_solid_video(v1, "0xE11D48")  # red
            make_solid_video(v2, "0x2563EB")  # blue

            scenes_v1 = [{
                "id": "s01", "start": 0.0, "end": 2.0,
                "layout": "title", "visual": "title: Draft One Headline",
                "spoken": "Draft one narration.",
            }]
            words_v1 = [
                {"text": "Draft", "start": 0.1, "end": 0.4},
                {"text": "one", "start": 0.45, "end": 0.8},
                {"text": "narration.", "start": 0.85, "end": 1.3},
            ]
            scenes_v2 = [{
                "id": "s01", "start": 0.0, "end": 2.0,
                "layout": "code", "visual": "code: Draft Two Snippet",
                "spoken": "Draft two replacement.",
            }]
            words_v2 = [
                {"text": "Draft", "start": 0.1, "end": 0.4},
                {"text": "two", "start": 0.45, "end": 0.8},
                {"text": "replacement.", "start": 0.85, "end": 1.3},
            ]

            base_url = self._start_server(root, page, feedback, scenes_v1, v1, words_v1)

            # Publish draft 2 while the reviewer's browser tab is still on draft 1.
            review_page.write_page(root, page, v2, scenes_v2)
            review_page.serve(root, page, feedback, scenes_v2, v2, 0, False, 0.1, words_v2)

            # Reviewer submits the note written on draft 1.
            status, reply = post_json(
                base_url + "/api/feedback",
                {
                    "video": "/renders/demo-v1.mp4",
                    "comments": [{"t": 0.5, "scene": "s01", "scene_start": 0.0, "scene_end": 2.0, "note": "Keep the red title"}],
                    "overall": "",
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(reply["ok"])

            batch_md_path = os.path.join(root, "work", "feedback-batches", reply["batch_id"] + ".md")
            with open(batch_md_path, encoding="utf-8") as fh:
                md_v1 = fh.read()

            self.assertIn("# Review notes: demo-v1.mp4", md_v1)
            self.assertIn("(title, title: Draft One Headline)", md_v1)
            self.assertIn("Draft one narration.", md_v1)
            self.assertNotIn("demo-v2.mp4", md_v1)
            self.assertNotIn("Draft Two Snippet", md_v1)
            self.assertNotIn("Draft two replacement.", md_v1)

            m = re.search(r"^Frame: (.+)$", md_v1, re.MULTILINE)
            self.assertIsNotNone(m, f"Expected Frame line in:\n{md_v1}")
            r, g, b = average_rgb(m.group(1).strip())
            self.assertGreater(r, 180, f"Expected red draft-1 frame, got RGB={(r, g, b)}")
            self.assertGreater(r, b + 100, f"Expected red draft-1 frame, got RGB={(r, g, b)}")

            # Reviewer on draft 2 still gets draft 2's frame, scene, and transcript.
            status2, reply2 = post_json(
                base_url + "/api/feedback",
                {
                    "video": "/renders/demo-v2.mp4",
                    "comments": [{"t": 0.5, "scene": "s01", "scene_start": 0.0, "scene_end": 2.0, "note": "Blue code looks crisp"}],
                    "overall": "",
                },
            )
            self.assertEqual(status2, 200)
            batch2_md_path = os.path.join(root, "work", "feedback-batches", reply2["batch_id"] + ".md")
            with open(batch2_md_path, encoding="utf-8") as fh:
                md_v2 = fh.read()
            self.assertIn("# Review notes: demo-v2.mp4", md_v2)
            self.assertIn("(code, code: Draft Two Snippet)", md_v2)
            self.assertIn("Draft two replacement.", md_v2)
            m2 = re.search(r"^Frame: (.+)$", md_v2, re.MULTILINE)
            self.assertIsNotNone(m2)
            r2, g2, b2 = average_rgb(m2.group(1).strip())
            self.assertGreater(b2, 180, f"Expected blue draft-2 frame, got RGB={(r2, g2, b2)}")
            self.assertGreater(b2, r2 + 100, f"Expected blue draft-2 frame, got RGB={(r2, g2, b2)}")

    def test_feedback_without_video_falls_back_to_current_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tmp
            page = os.path.join(root, "work", "review", "index.html")
            feedback = os.path.join(root, "work", "feedback.md")
            v1 = os.path.join(root, "renders", "demo-v1.mp4")
            make_solid_video(v1, "0x2563EB")
            scenes_v1 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "title", "visual": "title: Current", "spoken": "Hello."}]

            base_url = self._start_server(root, page, feedback, scenes_v1, v1, [])
            status, reply = post_json(
                base_url + "/api/feedback",
                {"comments": [{"t": 0.4, "scene": "s01", "note": "Fallback check"}], "overall": ""},
            )
            self.assertEqual(status, 200)
            batch_md_path = os.path.join(root, "work", "feedback-batches", reply["batch_id"] + ".md")
            with open(batch_md_path, encoding="utf-8") as fh:
                md = fh.read()
            self.assertIn("# Review notes: demo-v1.mp4", md)
            self.assertIn("(title, title: Current)", md)

    def test_feedback_rejects_path_traversal_and_unknown_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tmp
            page = os.path.join(root, "work", "review", "index.html")
            feedback = os.path.join(root, "work", "feedback.md")
            v1 = os.path.join(root, "renders", "demo-v1.mp4")
            make_solid_video(v1, "0xE11D48")
            scenes_v1 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "title", "visual": "title: One", "spoken": "One."}]

            base_url = self._start_server(root, page, feedback, scenes_v1, v1, [])
            with open(os.path.join(root, "script.md"), "w", encoding="utf-8") as fh:
                fh.write("# secret script\n")
            for bad_video in ("/../../etc/passwd", "/renders/does-not-exist.mp4", "/script.md", 123):
                with self.assertRaises(HTTPError) as cm:
                    post_json(base_url + "/api/feedback", {"video": bad_video, "comments": [], "overall": "hi"})
                self.assertEqual(cm.exception.code, 400)

    def test_pruned_draft_keeps_metadata_without_attaching_newer_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tmp
            page = os.path.join(root, "work", "review", "index.html")
            feedback = os.path.join(root, "work", "feedback.md")
            v1 = os.path.join(root, "renders", "demo-v1.mp4")
            v2 = os.path.join(root, "renders", "demo-v2.mp4")
            make_solid_video(v1, "0xE11D48")
            make_solid_video(v2, "0x2563EB")
            scenes_v1 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "title", "visual": "title: Pruned Draft", "spoken": "Original line."}]
            scenes_v2 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "code", "visual": "code: Newer Draft", "spoken": "Newer line."}]

            base_url = self._start_server(root, page, feedback, scenes_v1, v1, [])
            review_page.write_page(root, page, v2, scenes_v2)
            review_page.serve(root, page, feedback, scenes_v2, v2, 0, False, 0.1, [])
            os.remove(v1)

            status, reply = post_json(
                base_url + "/api/feedback",
                {
                    "video": "/renders/demo-v1.mp4",
                    "comments": [{"t": 0.5, "scene": "s01", "note": "Note on pruned draft"}],
                    "overall": "",
                },
            )
            self.assertEqual(status, 200)
            batch_md_path = os.path.join(root, "work", "feedback-batches", reply["batch_id"] + ".md")
            with open(batch_md_path, encoding="utf-8") as fh:
                md = fh.read()
            self.assertIn("# Review notes: demo-v1.mp4", md)
            self.assertIn("(title, title: Pruned Draft)", md)
            self.assertIn("Original line.", md)
            self.assertNotIn("Frame:", md)
            self.assertNotIn("demo-v2.mp4", md)

    def test_write_page_binds_comments_and_submission_to_video_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tmp
            page = os.path.join(root, "work", "review", "index.html")
            v1 = os.path.join(root, "renders", "demo-v1.mp4")
            make_solid_video(v1, "0xE11D48")
            scenes_v1 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "title", "visual": "title: One", "spoken": "One."}]
            review_page.write_page(root, page, v1, scenes_v1)
            with open(page, encoding="utf-8") as fh:
                html_doc = fh.read()
            self.assertIn('const VIDEO = v.getAttribute("src").split("?")[0];', html_doc)
            self.assertIn('video: VIDEO });', html_doc)
            self.assertIn('body: JSON.stringify({ video: VIDEO,', html_doc)

    def test_mixed_draft_comments_in_one_batch_keep_per_comment_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tmp
            page = os.path.join(root, "work", "review", "index.html")
            feedback = os.path.join(root, "work", "feedback.md")
            v1 = os.path.join(root, "renders", "demo-v1.mp4")
            v2 = os.path.join(root, "renders", "demo-v2.mp4")
            make_solid_video(v1, "0xE11D48")  # red
            make_solid_video(v2, "0x2563EB")  # blue

            scenes_v1 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "title", "visual": "title: Draft One", "spoken": "One."}]
            words_v1 = [{"text": "Alpha", "start": 0.1, "end": 0.6}]
            scenes_v2 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "code", "visual": "code: Draft Two", "spoken": "Two."}]
            words_v2 = [{"text": "Beta", "start": 0.1, "end": 0.6}]

            base_url = self._start_server(root, page, feedback, scenes_v1, v1, words_v1)
            review_page.write_page(root, page, v2, scenes_v2)
            review_page.serve(root, page, feedback, scenes_v2, v2, 0, False, 0.1, words_v2)

            status, reply = post_json(
                base_url + "/api/feedback",
                {
                    "video": "/renders/demo-v1.mp4",
                    "comments": [
                        {"t": 0.3, "scene": "s01", "note": "From draft 1", "video": "/renders/demo-v1.mp4"},
                        {"t": 0.4, "scene": "s01", "note": "Added after reload on draft 2", "video": "/renders/demo-v2.mp4"},
                    ],
                    "overall": "",
                },
            )
            self.assertEqual(status, 200)
            batch_md_path = os.path.join(root, "work", "feedback-batches", reply["batch_id"] + ".md")
            with open(batch_md_path, encoding="utf-8") as fh:
                md = fh.read()

            self.assertIn("(title, title: Draft One)", md)
            self.assertIn("Says: “Alpha”", md)
            self.assertIn("(code, code: Draft Two) · demo-v2.mp4", md)
            self.assertIn("Says: “Beta”", md)

            frame_paths = re.findall(r"^Frame: (.+)$", md, re.MULTILINE)
            self.assertEqual(len(frame_paths), 2)
            r1, _, b1 = average_rgb(frame_paths[0].strip())
            r2, _, b2 = average_rgb(frame_paths[1].strip())
            self.assertGreater(r1, b1 + 100)
            self.assertGreater(b2, r2 + 100)

    def test_symlinked_draft_video_resolves_its_revision(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            root = tmp
            page = os.path.join(root, "work", "review", "index.html")
            feedback = os.path.join(root, "work", "feedback.md")
            target_v1 = os.path.join(external, "raw-v1.mp4")
            make_solid_video(target_v1, "0xE11D48")
            os.makedirs(os.path.join(root, "renders"), exist_ok=True)
            link_v1 = os.path.join(root, "renders", "demo-v1.mp4")
            os.symlink(target_v1, link_v1)

            scenes_v1 = [{"id": "s01", "start": 0.0, "end": 2.0, "layout": "title", "visual": "title: Symlinked", "spoken": "Linked line."}]
            base_url = self._start_server(root, page, feedback, scenes_v1, link_v1, [])

            status, reply = post_json(
                base_url + "/api/feedback",
                {
                    "video": "/renders/demo-v1.mp4",
                    "comments": [{"t": 0.5, "scene": "s01", "note": "Check symlinked draft"}],
                    "overall": "",
                },
            )
            self.assertEqual(status, 200)
            batch_md_path = os.path.join(root, "work", "feedback-batches", reply["batch_id"] + ".md")
            with open(batch_md_path, encoding="utf-8") as fh:
                md = fh.read()
            self.assertIn("# Review notes: demo-v1.mp4", md)
            self.assertIn("(title, title: Symlinked)", md)
            self.assertIn("Linked line.", md)
            m = re.search(r"^Frame: (.+)$", md, re.MULTILINE)
            self.assertIsNotNone(m)
            r, g, b = average_rgb(m.group(1).strip())
            self.assertGreater(r, 180)
            self.assertGreater(r, b + 100)


if __name__ == "__main__":
    unittest.main()

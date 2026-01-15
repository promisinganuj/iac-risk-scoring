import sys
import unittest
from pathlib import Path

# Ensure approach2-using-existing-graph is on sys.path so we can import risk_scoring.
THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.diff_capture import capture_normalized_diff  # noqa: E402


class FakeGit:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def run(self, args, *, cwd: str) -> str:
        self.calls.append({"args": list(args), "cwd": cwd})
        key = " ".join(args)
        return self.outputs.get(key, "")


class TestDiffCapture(unittest.TestCase):
    def test_normalized_diff_sorts_files(self) -> None:
        patch = """diff --git a/b.txt b/b.txt
index 111..222 100644
--- a/b.txt
+++ b/b.txt
@@ -1,1 +1,1 @@
-old
+new

diff --git a/a.txt b/a.txt
index 333..444 100644
--- a/a.txt
+++ b/a.txt
@@ -1,1 +1,1 @@
-old
+new
"""
        g = FakeGit(
            {
                "git config --get remote.origin.url": "https://example.com/repo\n",
                "git rev-parse HEAD": "abc123\n",
                "git diff --patch --no-color --no-ext-diff --unified=3 HEAD": patch,
            }
        )

        nd = capture_normalized_diff(repo_dir="/repo", base_ref="HEAD", git=g)
        self.assertEqual([f.path for f in nd.files], ["a.txt", "b.txt"])

    def test_change_id_is_stable_for_same_normalized_output(self) -> None:
        patch_crlf = "diff --git a/a.txt b/a.txt\r\nindex 1..2 100644\r\n--- a/a.txt\r\n+++ b/a.txt\r\n@@ -1,1 +1,1 @@\r\n-old\r\n+new\r\n"
        patch_lf = "diff --git a/a.txt b/a.txt\nindex 1..2 100644\n--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n-old\n+new\n"

        g1 = FakeGit(
            {
                "git config --get remote.origin.url": "https://example.com/repo\n",
                "git rev-parse HEAD": "abc123\n",
                "git diff --patch --no-color --no-ext-diff --unified=3 HEAD": patch_crlf,
            }
        )
        g2 = FakeGit(
            {
                "git config --get remote.origin.url": "https://example.com/repo\n",
                "git rev-parse HEAD": "abc123\n",
                "git diff --patch --no-color --no-ext-diff --unified=3 HEAD": patch_lf,
            }
        )

        nd1 = capture_normalized_diff(repo_dir="/repo", base_ref="HEAD", git=g1)
        nd2 = capture_normalized_diff(repo_dir="/repo", base_ref="HEAD", git=g2)
        self.assertEqual(nd1.change_id, nd2.change_id)


if __name__ == "__main__":
    unittest.main()

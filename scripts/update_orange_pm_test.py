#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_orange_pm.py 테스트 — .vscode 부트스트랩(ensure_vscode_settings) 멱등성."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from update_orange_pm import ensure_vscode_settings  # type: ignore


def _mk_workspace(tmp: Path, projects: list[str], hub_sub: bool = True) -> Path:
    root = tmp / "ws"
    base = root / "Planning-Agent-Hub" if hub_sub else root
    for p in projects:
        (base / "PROJECTS" / p).mkdir(parents=True)
    return root


class TestEnsureVscodeSettings(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_settings_with_first_project(self):
        root = _mk_workspace(self.tmp, ["dbaas", "pm-viz"])
        self.assertTrue(ensure_vscode_settings(root, quiet=True))
        data = json.loads((root / ".vscode" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(data["orangePmViz.product"], "dbaas")  # 정렬 첫 항목

    def test_hub_at_workspace_root(self):
        root = _mk_workspace(self.tmp, ["alpha"], hub_sub=False)
        self.assertTrue(ensure_vscode_settings(root, quiet=True))
        data = json.loads((root / ".vscode" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(data["orangePmViz.product"], "alpha")

    def test_merges_without_touching_other_keys(self):
        root = _mk_workspace(self.tmp, ["alpha"])
        vsdir = root / ".vscode"
        vsdir.mkdir(parents=True)
        (vsdir / "settings.json").write_text(
            json.dumps({"editor.fontSize": 13}), encoding="utf-8"
        )
        self.assertTrue(ensure_vscode_settings(root, quiet=True))
        data = json.loads((vsdir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(data["editor.fontSize"], 13)          # 타 설정 불가침
        self.assertEqual(data["orangePmViz.product"], "alpha")

    def test_idempotent_when_product_already_set(self):
        root = _mk_workspace(self.tmp, ["alpha"])
        vsdir = root / ".vscode"
        vsdir.mkdir(parents=True)
        (vsdir / "settings.json").write_text(
            json.dumps({"orangePmViz.product": "custom"}), encoding="utf-8"
        )
        self.assertFalse(ensure_vscode_settings(root, quiet=True))
        data = json.loads((vsdir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(data["orangePmViz.product"], "custom")  # 기존 값 보존

    def test_leaves_jsonc_untouched(self):
        root = _mk_workspace(self.tmp, ["alpha"])
        vsdir = root / ".vscode"
        vsdir.mkdir(parents=True)
        original = "// comment\n{ \"a\": 1 }\n"
        (vsdir / "settings.json").write_text(original, encoding="utf-8")
        self.assertFalse(ensure_vscode_settings(root, quiet=True))
        self.assertEqual((vsdir / "settings.json").read_text(encoding="utf-8"), original)

    def test_no_projects_no_write(self):
        root = self.tmp / "ws"
        (root / "Planning-Agent-Hub" / "PROJECTS").mkdir(parents=True)  # 빈 PROJECTS
        self.assertFalse(ensure_vscode_settings(root, quiet=True))
        self.assertFalse((root / ".vscode" / "settings.json").exists())

    def test_no_hub_no_write(self):
        root = self.tmp / "ws"
        root.mkdir()
        self.assertFalse(ensure_vscode_settings(root, quiet=True))


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


MODULE = Path(__file__).parents[1] / "pr_pipeline_inspector.py"
SPEC = importlib.util.spec_from_file_location("inspector", MODULE)
inspector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inspector
SPEC.loader.exec_module(inspector)


class PipelineInspectorTests(unittest.TestCase):
    def test_discovers_visual_studio_project_from_check_url(self):
        payload = {"statusCheckRollup": [{"name": "Azure CI", "conclusion": "SUCCESS", "detailsUrl": "https://org.visualstudio.com/project-id/_build/results?buildId=10"}]}
        with patch.object(inspector, "run_json", return_value=payload):
            projects = inspector.discover_azure_projects(42, "owner/repo")
        self.assertEqual(projects[0]["organization"], "org")
        self.assertEqual(projects[0]["project"], "project-id")
        self.assertEqual(projects[0]["checks"][0]["build_id"], "10")

    def test_github_run_reports_log_and_artifacts(self):
        responses = iter([
            {"headRefOid": "sha"},
            [{"databaseId": 9, "workflowName": "CI", "status": "completed", "conclusion": "success", "number": 8}],
            {"jobs": [{"name": "test", "status": "completed", "conclusion": "success"}]},
            {"run_attempt": 2},
            {"artifacts": [{"name": "allure-report"}]},
        ])
        with patch.object(inspector, "run_json", side_effect=lambda _: next(responses)):
            run = inspector.github_run(42, "owner/repo")
        self.assertEqual(run.build_id, "9")
        self.assertEqual(run.attempt, "2")
        self.assertIn("gh run view 9 --repo owner/repo --log", run.log_command)
        self.assertEqual(run.artifacts, [("allure-report", "gh run download 9 --repo owner/repo --name allure-report")])

    def test_azure_run_summarizes_stage_and_artifact(self):
        responses = iter([
            [{"id": 12, "buildNumber": "20260805.1", "status": "completed", "result": "succeeded", "definition": {"name": "CI"}}],
            {"records": [{"type": "Stage", "name": "Build", "state": "completed", "result": "succeeded", "attempt": 2}]},
            [{"name": "aqua-scan"}],
            [{"id": 3}],
        ])
        with patch.object(inspector, "run_json", side_effect=lambda _: next(responses)):
            run = inspector.azure_run(42, "Project", "az")
        self.assertEqual(run.build_id, "12")
        self.assertEqual(run.build_number, "20260805.1")
        self.assertEqual(run.attempt, "unavailable")
        self.assertEqual(run.stages, [("Build", "completed", "succeeded", "2")])
        self.assertIn("--resource artifacts", run.artifacts[0][1])
        self.assertIn("logId=3", run.log_command)

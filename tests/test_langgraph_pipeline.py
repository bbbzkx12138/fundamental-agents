from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from fundamental_agent.langgraph_pipeline import build_langgraph


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json"


class LangGraphPipelineTest(unittest.TestCase):
    def test_pipeline_pauses_and_resumes_after_approval(self) -> None:
        graph = build_langgraph(
            CACHE_PATH,
            ["AAPL", "MSFT", "NVDA"],
            checkpointer=MemorySaver(),
            llm_mode="template",
            progress=False,
            trace_enabled=False,
        )
        config = {"configurable": {"thread_id": "test-approval"}}

        first = graph.invoke({}, config=config)
        self.assertTrue(first.get("__interrupt__"))
        self.assertTrue(first.get("markdown"))
        self.assertIn("摘要与解释", first["markdown"])
        self.assertIn("合规检查", first["markdown"])
        self.assertEqual(first["summary_source"], "template")
        self.assertTrue(first["compliance"]["passed"])
        self.assertIn("budget_snapshot", first)
        self.assertNotIn("人工审批已通过", first["markdown"])

        second = graph.invoke(
            Command(resume={"approved": True, "comment": "测试审批"}),
            config=config,
        )
        self.assertTrue(second["approved"])
        self.assertIn("人工审批已通过", second["markdown"])
        self.assertIn("报告正文未检测到交易建议表述", second["markdown"])
        self.assertIn("SEC EDGAR companyfacts", second["json"])

    def test_pipeline_rejects_without_final_report(self) -> None:
        graph = build_langgraph(
            CACHE_PATH,
            ["AAPL", "MSFT", "NVDA"],
            checkpointer=MemorySaver(),
            llm_mode="template",
            progress=False,
            trace_enabled=False,
        )
        config = {"configurable": {"thread_id": "test-reject"}}

        graph.invoke({}, config=config)
        second = graph.invoke(
            Command(resume={"approved": False, "comment": "测试拒绝"}),
            config=config,
        )

        self.assertFalse(second["approved"])
        self.assertNotIn("人工审批已通过", second["markdown"])

    def test_pipeline_writes_node_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph = build_langgraph(
                CACHE_PATH,
                ["AAPL", "MSFT", "NVDA"],
                checkpointer=MemorySaver(),
                llm_mode="template",
                progress=False,
                trace_enabled=True,
                trace_dir=Path(temp_dir),
                run_id="trace-test",
            )
            graph.invoke(
                {},
                config={"configurable": {"thread_id": "trace-test-thread"}},
            )
            trace_path = Path(temp_dir) / "trace-test.jsonl"
            self.assertTrue(trace_path.exists())
            records = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(
                any(
                    record["event"] == "node_end"
                    and record["node"] == "human_approval"
                    and record["status"] == "interrupted"
                    for record in records
                )
            )


if __name__ == "__main__":
    unittest.main()

"""Eval harness for the paper-search agent.

Run: cd eval && uv run --with-requirements ../app/requirements.txt \
       --with pytest,pytest-asyncio,rouge-score --with "google-adk[gcp,eval]>=2.4" python -m pytest run_eval.py -s

Judges with an LLM (final_response_match_v2), so results carry model
nondeterminism; num_runs smooths it. The candidate is the app's agent
(self-hosted Gemma; MODEL_API_BASE required). The judge model is separate
test infrastructure, not part of the product. Do not gate on `adk eval` (its
CLI exits 0 even on failure in ADK 2.4); this pytest asserts.
"""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.local_eval_sets_manager import load_eval_set_from_file

HERE = pathlib.Path(__file__).parent
EVALSET = HERE / "paper_search.evalset.json"

# Tool-name trajectories are asserted per case in the evalset; exact-args
# matching is deliberately not used (free-text query args are brittle across
# models). The LLM judge gates whether answers are grounded and appropriate.
CONFIG = EvalConfig(
    criteria={
        "final_response_match_v2": {
            "threshold": float(os.environ.get("EVAL_THRESHOLD", "0.7")),
            "judge_model_options": {
                "judge_model": os.environ.get("EVAL_JUDGE_MODEL", "gemini-2.5-flash"),
                "num_samples": 3,
            },
        },
    }
)


@pytest.mark.asyncio
async def test_paper_agent_eval():
    eval_set = load_eval_set_from_file(str(EVALSET), EVALSET.stem)
    await AgentEvaluator.evaluate_eval_set(
        agent_module="paper_agent_eval",
        eval_set=eval_set,
        eval_config=CONFIG,
        num_runs=int(os.environ.get("EVAL_NUM_RUNS", "1")),
    )

import os
import json
import yaml
from pathlib import Path
from typing import Optional
import openai
from dotenv import load_dotenv

from core.config_model import ApplianceConfig
from core.session_store import SessionStore
from core.calibration import CalibrationEngine

load_dotenv()


class AdvisoryEngine:

    PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
    BASELINES_PATH = Path(__file__).parent.parent / "data" / "hardware_baselines.json"

    def __init__(self):
        api_key = os.environ["OPENAI_API_KEY"]
        self.client = openai.OpenAI(api_key=api_key)
        self.async_client = openai.AsyncOpenAI(api_key=api_key)
        self.model = os.environ.get("ADVISORY_MODEL", "gpt-4o")
        self.max_tokens = int(os.environ.get("ADVISORY_MAX_TOKENS", "2048"))
        self.calibration = CalibrationEngine()
        self.session = SessionStore.get()

        with open(self.BASELINES_PATH) as f:
            self.baselines = json.load(f)

        with open(self.PROMPTS_DIR / "system_base.txt") as f:
            self.system_base = f.read()

    def ask_preselected(self, question_id: int) -> dict:
        """Answer one of the 16 pre-selected questions using the current config."""
        matches = list(self.PROMPTS_DIR.glob(f"q{question_id:02d}_*.yaml"))
        if not matches:
            return {"error": f"No prompt template found for question ID {question_id}"}

        with open(matches[0]) as f:
            template = yaml.safe_load(f)

        return self._run_query(
            question_text=template["question_text"],
            prompt_additions=template.get("prompt_additions", ""),
            category="A",
            question_id=question_id
        )

    def ask_custom(self, question: str) -> dict:
        """Answer a custom question using the current config."""
        return self._run_query(
            question_text=question,
            prompt_additions="",
            category="B",
            question_id=None
        )

    def _build_context(self):
        """Build config JSON and calibration context from current session."""
        config = self.session.get_config()
        config_json = config.model_dump(exclude_none=True) if config else {}
        calibration_ctx = self.calibration.build_calibration_context(config) if config else {}
        return config_json, calibration_ctx

    def _build_user_prompt(self, config_json: dict, calibration_ctx: dict,
                           question_text: str, prompt_additions: str) -> str:
        return f"""
## APPLIANCE CONFIGURATION
```json
{json.dumps(config_json, indent=2)}
```

## HARDWARE PERFORMANCE BASELINES
```json
{json.dumps(self.baselines, indent=2)}
```

## REAL-WORLD CALIBRATION CONTEXT
```json
{json.dumps(calibration_ctx, indent=2)}
```

## QUESTION
{question_text}

## ADDITIONAL CONTEXT FOR THIS QUESTION
{prompt_additions}

---

Provide a complete advisory response following the structure defined in your system prompt.
"""

    def _run_query(self, question_text: str, prompt_additions: str,
                   category: str, question_id: Optional[int]) -> dict:

        config_json, calibration_ctx = self._build_context()
        user_prompt = self._build_user_prompt(config_json, calibration_ctx,
                                              question_text, prompt_additions)

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": self.system_base},
                {"role": "user", "content": user_prompt}
            ]
        )

        return {
            "question_id": question_id,
            "category": category,
            "question": question_text,
            "response": response.choices[0].message.content,
            "config_provided": bool(config_json),
            "calibration_warnings": calibration_ctx.get("warnings", [])
        }

    # ─── Streaming Methods ────────────────────────────────────────────────────

    async def ask_preselected_stream(self, question_id: int):
        matches = list(self.PROMPTS_DIR.glob(f"q{question_id:02d}_*.yaml"))
        if not matches:
            yield {"type": "error", "message": f"No prompt template found for question {question_id}"}
            return
        with open(matches[0]) as f:
            template = yaml.safe_load(f)
        async for event in self._run_query_stream(
            template["question_text"], template.get("prompt_additions", ""), is_preset=True
        ):
            yield event

    async def ask_custom_stream(self, question: str):
        async for event in self._run_query_stream(question, "", is_preset=False):
            yield event

    TECHNICAL_KEYWORDS = {
        'iops', 'throughput', 'mb/s', 'gb/s', 'bandwidth', 'raid', 'backup',
        'restore', 'replication', 'performance', 'speed', 'latency', 'network',
        'veeam', 'iscsi', 'nas', 'nfs', 's3', 'dedup', 'cache', 'power', 'ups',
        'watt', 'rack', 'drive', 'ssd', 'nvme', 'hdd', 'storage', 'read', 'write',
        'sizing', 'capacity', 'estimate', 'calculate', 'how much', 'how many',
        'bonding', 'lacp', 'rebuild', 'parity', 'stripe', 'volume', 'pool'
    }

    async def _run_query_stream(self, question_text: str, prompt_additions: str,
                                is_preset: bool = True):
        q_lower = question_text.lower()
        is_technical = is_preset or any(kw in q_lower for kw in self.TECHNICAL_KEYWORDS)

        config_json, calibration_ctx = self._build_context()
        warnings = calibration_ctx.get("warnings", []) if is_technical else []

        if is_technical:
            user_prompt = self._build_user_prompt(config_json, calibration_ctx,
                                                  question_text, prompt_additions)
        else:
            # Conversational question — do NOT include hardware data or calibration.
            # Giving the model numbers to work with causes it to produce unsolicited estimates.
            user_prompt = f"The user asked: {question_text}\n\nAnswer naturally and conversationally. Do not produce performance calculations or estimates."

        yield {"type": "start", "question": question_text.strip(), "warnings": warnings}

        stream = await self.async_client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": self.system_base},
                {"role": "user", "content": user_prompt}
            ],
            stream=True
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield {"type": "token", "text": delta}

        yield {"type": "done"}

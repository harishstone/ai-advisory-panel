import os
import json
import yaml
from pathlib import Path
from typing import Optional
import anthropic
from dotenv import load_dotenv

from core.config_model import ApplianceConfig
from core.session_store import SessionStore
from core.calibration import CalibrationEngine

load_dotenv()


class AdvisoryEngine:

    PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
    BASELINES_PATH = Path(__file__).parent.parent / "data" / "hardware_baselines.json"

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = os.environ.get("ADVISORY_MODEL", "claude-sonnet-4-6")
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

    def _run_query(self, question_text: str, prompt_additions: str,
                   category: str, question_id: Optional[int]) -> dict:

        config = self.session.get_config()
        config_json = config.model_dump(exclude_none=True) if config else {}

        calibration_ctx: dict = {}
        if config:
            calibration_ctx = self.calibration.build_calibration_context(config)

        category_note = (
            "NOTE: This is a Category A (pre-selected) question. Apply fine-tuned analysis."
            if category == "A"
            else "NOTE: This is a Category B (custom) question. Mark confidence as Medium at most."
        )

        user_prompt = f"""
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

## QUESTION (Category {category})
{question_text}

## ADDITIONAL CONTEXT FOR THIS QUESTION
{prompt_additions}

---

Provide a complete advisory response following the structure defined in your system prompt.
{category_note}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_base,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return {
            "question_id": question_id,
            "category": category,
            "question": question_text,
            "response": response.content[0].text,
            "config_provided": bool(config_json),
            "calibration_warnings": calibration_ctx.get("warnings", [])
        }

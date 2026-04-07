"""
Tests for core/advisory_engine.py

Mocks the Anthropic client so no real API calls are made.
Verifies prompt assembly, YAML template loading, category tagging,
and correct integration with SessionStore + CalibrationEngine.
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.advisory_engine import AdvisoryEngine
from core.session_store import SessionStore
from core.config_model import (
    ApplianceConfig,
    StorageMediaConfig,
    StorageConfig,
    NetworkConfig,
    DiskType,
    RaidLevel,
    NicSpeed,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_session():
    """Reset SessionStore before every test."""
    SessionStore.get().clear()
    yield
    SessionStore.get().clear()


@pytest.fixture
def mock_anthropic_response():
    """A minimal fake Anthropic API response object."""
    msg = MagicMock()
    msg.content = [MagicMock(text="ESTIMATE\n12,000 IOPS\n\nCONFIDENCE LEVEL: High")]
    return msg


@pytest.fixture
def engine_with_mock(mock_anthropic_response):
    """AdvisoryEngine with Anthropic client mocked out."""
    with patch("core.advisory_engine.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        MockAnthropic.return_value = mock_client
        eng = AdvisoryEngine()
        eng.client = mock_client
        yield eng, mock_client


# ─── Pre-selected Questions ────────────────────────────────────────────────────

def test_ask_preselected_q1_loads_correct_template(engine_with_mock):
    """ask_preselected(1) must find and use q01_iops_throughput.yaml."""
    eng, mock_client = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig(
        storage_media=StorageMediaConfig(
            primary_disk_type=DiskType.SAS_HDD,
            primary_disk_count=12
        )
    ))

    result = eng.ask_preselected(1)

    assert result["category"] == "A"
    assert result["question_id"] == 1
    assert "response" in result
    # Claude API was called once
    mock_client.messages.create.assert_called_once()


def test_ask_preselected_returns_category_a(engine_with_mock):
    eng, _ = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig())
    result = eng.ask_preselected(5)
    assert result["category"] == "A"


def test_ask_preselected_invalid_id_returns_error(engine_with_mock):
    """A question ID with no matching YAML file must return an error dict."""
    eng, mock_client = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig())
    result = eng.ask_preselected(99)
    assert "error" in result
    # No API call made
    mock_client.messages.create.assert_not_called()


def test_all_16_templates_exist():
    """All q01 through q16 YAML files must exist on disk."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    for i in range(1, 17):
        matches = list(prompts_dir.glob(f"q{i:02d}_*.yaml"))
        assert len(matches) == 1, f"Expected exactly one YAML for Q{i}, found: {matches}"


# ─── Custom Questions ──────────────────────────────────────────────────────────

def test_ask_custom_returns_category_b(engine_with_mock):
    eng, _ = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig())
    result = eng.ask_custom("How many VMs can this appliance run?")
    assert result["category"] == "B"
    assert result["question"] == "How many VMs can this appliance run?"


def test_ask_custom_api_called_once(engine_with_mock):
    eng, mock_client = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig())
    eng.ask_custom("What is the best RAID level?")
    mock_client.messages.create.assert_called_once()


# ─── Prompt Content Verification ──────────────────────────────────────────────

def test_prompt_includes_config_json(engine_with_mock):
    """The user prompt sent to Claude must contain the config as JSON."""
    eng, mock_client = engine_with_mock
    config = ApplianceConfig(
        network=NetworkConfig(
            nic_speed=NicSpeed.GBE_25,
            active_data_ports=4
        )
    )
    SessionStore.get().set_config(config)

    eng.ask_preselected(4)  # Q4: network throughput

    call_args = mock_client.messages.create.call_args
    user_message = call_args.kwargs["messages"][0]["content"]
    assert "25gbe" in user_message
    assert "active_data_ports" in user_message


def test_prompt_includes_hardware_baselines(engine_with_mock):
    """The user prompt must include hardware baseline data."""
    eng, mock_client = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig())

    eng.ask_preselected(1)

    call_args = mock_client.messages.create.call_args
    user_message = call_args.kwargs["messages"][0]["content"]
    assert "disk_baselines" in user_message or "sas_hdd" in user_message


def test_prompt_includes_calibration_context(engine_with_mock):
    """The user prompt must include the calibration context block."""
    eng, mock_client = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig(
        storage_config=StorageConfig(write_back_policy="write_through")
    ))

    eng.ask_preselected(1)

    call_args = mock_client.messages.create.call_args
    user_message = call_args.kwargs["messages"][0]["content"]
    assert "CALIBRATION" in user_message or "calibration" in user_message.lower()


def test_category_b_note_in_prompt(engine_with_mock):
    """Custom (Category B) questions must include the Category B note in the prompt."""
    eng, mock_client = engine_with_mock
    SessionStore.get().set_config(ApplianceConfig())

    eng.ask_custom("What is the power draw?")

    call_args = mock_client.messages.create.call_args
    user_message = call_args.kwargs["messages"][0]["content"]
    assert "Category B" in user_message


# ─── Calibration Warnings in Result ──────────────────────────────────────────

def test_calibration_warnings_returned_in_result(engine_with_mock):
    """Result dict must include calibration_warnings from the engine."""
    eng, _ = engine_with_mock
    config = ApplianceConfig(
        network=NetworkConfig(
            dedicated_storage_network=False,  # triggers shared_network warning
            jumbo_frames_mtu9000=True,
        )
    )
    SessionStore.get().set_config(config)
    result = eng.ask_preselected(4)
    assert "calibration_warnings" in result
    assert isinstance(result["calibration_warnings"], list)
    assert len(result["calibration_warnings"]) > 0


def test_no_config_returns_empty_calibration_warnings(engine_with_mock):
    """With no config loaded, calibration_warnings must be an empty list."""
    eng, _ = engine_with_mock
    # No config set in session
    result = eng.ask_preselected(1)
    assert result["calibration_warnings"] == []

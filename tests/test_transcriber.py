"""Tests for transcription post-processing (no model loading involved)."""

import json

import numpy as np
import pytest

import transcriber as transcriber_module  # noqa: E402
from transcriber import BASE_PROMPT, MAX_PROMPT_CHARS, WhisperTranscriber  # noqa: E402


@pytest.fixture
def tr():
    """A WhisperTranscriber shell with no model loaded."""
    obj = object.__new__(WhisperTranscriber)
    obj._prompt_cache = (None, BASE_PROMPT)
    return obj


# --- process_cancellation -------------------------------------------------


def test_cancel_that_trims_back_to_last_sentence(tr):
    assert tr.process_cancellation("First one. Second one cancel that") == "First one."


def test_cancel_that_alone_clears_everything(tr):
    assert tr.process_cancellation("cancel that") == ""
    assert tr.process_cancellation("Cancel that.") == ""


def test_cancel_that_only_triggers_at_end(tr):
    text = "cancel that order and continue"
    assert tr.process_cancellation(text) == text


def test_scratch_that_is_not_a_cancellation(tr):
    # 'scratch that' is a delete-last-word command handled by NLPProcessor;
    # swallowing it here would break that command.
    text = "hello world scratch that"
    assert tr.process_cancellation(text) == text


def test_cancellation_keeps_question_and_exclamation_boundaries(tr):
    assert tr.process_cancellation("Really? Yes cancel that") == "Really?"
    assert tr.process_cancellation("Stop! Go on cancel that") == "Stop!"


# --- dynamic prompt -------------------------------------------------------


def test_prompt_without_dictionary_is_base(tr, tmp_path, monkeypatch):
    monkeypatch.setattr(transcriber_module, "DICTIONARY_FILE", str(tmp_path / "missing.json"))
    assert tr._get_dynamic_prompt() == BASE_PROMPT


def test_prompt_includes_dictionary_terms(tr, tmp_path, monkeypatch):
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps(["Kubernetes", "gRPC"]))
    monkeypatch.setattr(transcriber_module, "DICTIONARY_FILE", str(path))

    prompt = tr._get_dynamic_prompt()
    assert "Kubernetes" in prompt and "gRPC" in prompt


def test_prompt_is_capped_for_huge_dictionaries(tr, tmp_path, monkeypatch):
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps([f"term{i:04d}" for i in range(2000)]))
    monkeypatch.setattr(transcriber_module, "DICTIONARY_FILE", str(path))

    prompt = tr._get_dynamic_prompt()
    assert len(prompt) <= MAX_PROMPT_CHARS
    assert "term0000" in prompt  # earliest terms survive


def test_prompt_is_cached_until_file_changes(tr, tmp_path, monkeypatch):
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps(["Alpha"]))
    monkeypatch.setattr(transcriber_module, "DICTIONARY_FILE", str(path))

    first = tr._get_dynamic_prompt()
    reads = {"n": 0}
    real_open = open

    def counting_open(*args, **kwargs):
        reads["n"] += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", counting_open)
    assert tr._get_dynamic_prompt() == first
    assert reads["n"] == 0  # served from cache, no disk read


def test_prompt_survives_corrupt_dictionary(tr, tmp_path, monkeypatch):
    path = tmp_path / "dictionary.json"
    path.write_text("{ broken")
    monkeypatch.setattr(transcriber_module, "DICTIONARY_FILE", str(path))
    assert tr._get_dynamic_prompt() == BASE_PROMPT


# --- transcribe guards ----------------------------------------------------


def test_transcribe_returns_empty_for_no_audio(tr):
    assert tr.transcribe(None) == ""
    assert tr.transcribe(np.array([], dtype=np.float32)) == ""


def test_transcribe_accepts_non_contiguous_float64(tr, tmp_path, monkeypatch):
    """A sliced/strided float64 array must be converted, not rejected."""
    monkeypatch.setattr(transcriber_module, "DICTIONARY_FILE", str(tmp_path / "none.json"))

    captured = {}

    class FakeSegment:
        text = " hello there "

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            captured["dtype"] = audio.dtype
            captured["contiguous"] = audio.flags["C_CONTIGUOUS"]
            return [FakeSegment()], None

    tr.model = FakeModel()
    tr.actual_engine = "faster-whisper"
    tr.vad_filter = True
    tr.language = None

    audio = np.linspace(-1, 1, 200, dtype=np.float64)[::2]
    assert tr.transcribe(audio) == "hello there"
    assert captured["dtype"] == np.float32
    assert captured["contiguous"] is True


def test_transcribe_swallows_engine_errors(tr, tmp_path, monkeypatch):
    monkeypatch.setattr(transcriber_module, "DICTIONARY_FILE", str(tmp_path / "none.json"))

    class ExplodingModel:
        def transcribe(self, audio, **kwargs):
            raise RuntimeError("engine exploded")

    tr.model = ExplodingModel()
    tr.actual_engine = "faster-whisper"
    tr.vad_filter = True
    tr.language = None

    assert tr.transcribe(np.zeros(1000, dtype=np.float32)) == ""

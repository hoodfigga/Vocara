"""Tests for VAD/audio chunk buffering without touching audio hardware.

The VAD state machine is exercised directly by feeding synthetic chunks into
its buffer helpers; no InputStream is ever opened.
"""

import numpy as np
import pytest

pytest.importorskip("sounddevice", reason="sounddevice is required by audio_handler")
pytest.importorskip("PySide6", reason="PySide6 is required by audio_handler")

from audio_handler import VADThread  # noqa: E402


@pytest.fixture
def vad():
    t = VADThread(sample_rate=16000, silence_timeout=2.0, energy_threshold=0.015)
    yield t
    t.stop()


def _chunk(seconds, sample_rate=16000, loud=True):
    n = int(sample_rate * seconds)
    if loud:
        return np.full((n, 1), 0.1, dtype=np.float32)  # rms 0.1 > 0.015
    return np.zeros((n, 1), dtype=np.float32)  # silent


def test_phrase_flush_emits_when_long_enough(vad):
    emitted = []
    vad.phrase_detected.connect(lambda a: emitted.append(a))

    vad._append(_chunk(1.0))  # speech
    vad._flush_phrase()

    assert len(emitted) == 1
    assert len(emitted[0]) == 16000
    assert emitted[0].dtype == np.float32
    assert emitted[0].ndim == 1  # flattened mono


def test_short_burst_is_discarded_as_noise(vad):
    emitted = []
    vad.phrase_detected.connect(lambda a: emitted.append(a))

    vad._append(_chunk(0.2))  # under the 0.4s minimum
    vad._flush_phrase()

    assert emitted == []


def test_phrases_reset_buffer_after_flush(vad):
    vad._append(_chunk(1.0))
    vad._flush_phrase()
    vad._append(_chunk(1.0))
    vad._flush_phrase()
    # Buffer state fully reset between phrases
    assert vad._buffered_samples == 0
    assert vad._chunks == []
    assert vad.is_speaking is False


def test_max_phrase_cap_flushes_early(vad):
    emitted = []
    vad.phrase_detected.connect(lambda a: emitted.append(a))

    # Appending past the 60 s cap in one stretch must flush instead of growing
    total = int(vad.sample_rate * (VADThread.MAX_PHRASE_SECONDS + 2))
    chunk = np.full((total, 1), 0.1, dtype=np.float32)
    vad._append(chunk)

    assert emitted  # the overflow was flushed as a phrase
    assert vad._buffered_samples == 0  # buffer reset after the forced flush


def test_silence_appends_then_flushes(vad):
    """A quiet chunk after speech is part of the phrase; prolonged silence ends it."""
    emitted = []
    vad.phrase_detected.connect(lambda a: emitted.append(a))

    vad.is_speaking = True
    vad._append(_chunk(1.0, loud=True))
    vad._append(_chunk(0.5, loud=False))  # trailing silence still buffered
    vad._flush_phrase()

    assert len(emitted) == 1
    assert len(emitted[0]) == int(1.5 * 16000)

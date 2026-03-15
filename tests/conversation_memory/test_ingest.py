"""Unit tests for transcript ingestion: message order and parsing."""
import json
from pathlib import Path

import pytest

from services.conversation_memory.ingest import (
    TranscriptInput,
    _message_id,
    _parse_transcript,
    ingest_transcript,
)


def test_message_id_deterministic():
    """Message IDs are deterministic from conversation_id and position."""
    assert _message_id("conv_001", 0) == "conv_001_msg_0"
    assert _message_id("conv_001", 11) == "conv_001_msg_11"


def test_parse_transcript_preserves_message_order():
    """Transcript parsing preserves message order by position."""
    raw = {
        "conversation_id": "conv_001",
        "messages": [
            {"role": "user", "text": "First"},
            {"role": "assistant", "text": "Second"},
            {"role": "user", "text": "Third"},
        ],
    }
    conversation, messages = _parse_transcript(raw)
    assert conversation.id == "conv_001"
    assert len(messages) == 3
    assert messages[0].position == 0 and messages[0].text == "First"
    assert messages[1].position == 1 and messages[1].text == "Second"
    assert messages[2].position == 2 and messages[2].text == "Third"
    assert messages[0].id == "conv_001_msg_0"
    assert messages[1].id == "conv_001_msg_1"
    assert messages[2].id == "conv_001_msg_2"


def test_parse_transcript_from_dict():
    """from_dict builds TranscriptInput and parse preserves order."""
    inp = TranscriptInput.from_dict({
        "conversation_id": "c1",
        "messages": [{"role": "user", "text": "A"}, {"role": "user", "text": "B"}],
    })
    conv, msgs = _parse_transcript(inp)
    assert [m.text for m in msgs] == ["A", "B"]
    assert [m.position for m in msgs] == [0, 1]


def test_parse_transcript_empty_messages():
    """Empty messages list yields no messages but valid conversation."""
    raw = {"conversation_id": "empty_conv", "messages": []}
    conversation, messages = _parse_transcript(raw)
    assert conversation.id == "empty_conv"
    assert messages == []


def test_ingest_transcript_empty_messages_no_write():
    """Ingest with no messages returns without failing (no session write for messages)."""
    raw = {"conversation_id": "empty", "messages": []}
    conv, msgs = ingest_transcript(raw)
    assert conv.id == "empty"
    assert msgs == []

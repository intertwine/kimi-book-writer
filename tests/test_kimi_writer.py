import json
import pytest
from pathlib import Path
from kimi_writer import load_or_init_state, build_book_markdown, save_state

def test_load_or_init_state_new(tmp_path):
    state_file = tmp_path / "novel_state.json"
    state = load_or_init_state(state_file)
    assert state["title"] is None
    assert state["current_idx"] == 0
    assert state["chapters"] == []

def test_load_or_init_state_existing(tmp_path):
    state_file = tmp_path / "novel_state.json"
    existing_data = {
        "title": "Test Novel",
        "concept": "A test concept",
        "model": "kimi-k2-test",
        "temperature": 0.7,
        "max_output_tokens": 1000,
        "outline_text": "1. Test",
        "chapters": [{"title": "Test", "content": "## Test"}],
        "outline_items": ["Test"],
        "current_idx": 1
    }
    state_file.write_text(json.dumps(existing_data))
    
    state = load_or_init_state(state_file)
    assert state["title"] == "Test Novel"
    assert state["model"] == "kimi-k2-test"
    assert len(state["chapters"]) == 1

def test_save_state(tmp_path):
    state_file = tmp_path / "novel_state.json"
    state = {"title": "Saved State"}
    save_state(state_file, state)
    
    assert state_file.exists()
    assert json.loads(state_file.read_text())["title"] == "Saved State"

def test_build_book_markdown():
    state = {
        "title": "My Book",
        "concept": "A great story",
        "outline_text": "1. Chapter 1",
        "chapters": [
            {"title": "Chapter 1", "content": "## Chapter 1\n\nOnce upon a time..."}
        ]
    }
    md = build_book_markdown(state)
    assert "# My Book" in md
    assert "*Generated from concept:* A great story" in md
    assert "## Outline" in md
    assert "1. Chapter 1" in md
    assert "Once upon a time..." in md

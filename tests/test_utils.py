from utils import extract_outline_items

def test_extract_numbered_list():
    text = """
1. Chapter One
2. Chapter Two: The Middle
3. Chapter Three -- The End
    """
    items = extract_outline_items(text)
    # The current implementation splits on '--' but not '-' in the body
    # It does handle 'Chapter Two: The Middle' by removing 'Chapter Two: ' prefix if regex matches
    # Wait, line 16 remove 'Chapter \d+ [:-–]' prefix.
    # '2. Chapter Two: The Middle' -> removes '2. '. 'Chapter Two: The Middle'.
    # Does 'Chapter Two: ' match 'Chapter \d+'? No, 'Two' is not \d+.
    # So 'Chapter Two: The Middle' remains 'Chapter Two: The Middle'.
    assert items == ["Chapter One", "Chapter Two: The Middle", "Chapter Three"]

def test_extract_markdown_headers():
    text = """
## Chapter 1: Startup
## Chapter 2: Growth
## Chapter 3: IPO
    """
    items = extract_outline_items(text)
    # utils.py logic:
    # '## Chapter 1: Startup' -> removes '## ' -> 'Chapter 1: Startup'
    # Then removes 'Chapter 1: ' (matches Chapter \d+ :) -> 'Startup'
    assert items == ["Startup", "Growth", "IPO"]

def test_extract_mixed_format():
    text = """
1. Prologue
- Chapter 1: The Incident
* Chapter 2 - The Reaction
    """
    items = extract_outline_items(text)
    # '1. Prologue' -> 'Prologue'
    # '- Chapter 1: The Incident' -> 'Chapter 1: The Incident' -> 'The Incident'
    # '* Chapter 2 - The Reaction' -> 'Chapter 2 - The Reaction'. 'Chapter 2 - ' matches 'Chapter \d+ -'. -> 'The Reaction'
    assert items == ["Prologue", "The Incident", "The Reaction"]

def test_extract_with_summaries():
    text = """
1. The Setup — In which our hero is introduced and things go wrong.
2. The Conflict -- The hero fights back.
    """
    items = extract_outline_items(text)
    assert items == ["The Setup", "The Conflict"]

def test_extract_simple_list():
    # Fallback uses split('\n\n')
    text = """
Chapter One

Chapter Two

Chapter Three
    """
    items = extract_outline_items(text)
    assert items == ["Chapter One", "Chapter Two", "Chapter Three"]

def test_empty_input():
    assert extract_outline_items("") == []

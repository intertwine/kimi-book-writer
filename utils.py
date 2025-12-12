from __future__ import annotations
import re

def extract_outline_items(text: str):
    """
    Extract chapter titles from a model-generated outline.
    Accepts numbered lists, markdown headings, or bullet lists.
    """
    items = []
    for line in text.splitlines():
        line=line.strip()
        if not line:
            continue
        if re.match(r'^(\d+\.\s+|\-\s+|\*\s+|#{1,6}\s+|Chapter\s+\d+)', line, flags=re.I):
            core = re.sub(r'^(\d+\.\s+|\-\s+|\*\s+|#{1,6}\s+|Chapter\s+\d+\s+)', '', line, flags=re.I).strip()
            core = re.sub(r'^(?:Chapter\s*\d+\s*[:\-–]\s*)', '', core, flags=re.I).strip()
            # Remove any leftover leading punctuation (colon, dash, etc.) after removing Chapter prefix
            core = re.sub(r'^[:\-–]\s*', '', core).strip()
            # Remove long dashes and summaries after an em dash
            core = core.split('—')[0].split('--')[0].strip()
            if core:
                items.append(core)
    if not items:
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        items = paras
    seen=set()
    uniq=[]
    for it in items:
        key=it.lower()
        if key not in seen:
            uniq.append(it)
            seen.add(key)
    return uniq[:100]

"""Extractive call summaries and action items from finalized transcript lines."""

import re


_STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are", "was",
    "were", "be", "it", "this", "that", "we", "i", "you", "they", "our", "your", "at", "as", "by",
}
_ACTION = re.compile(
    r"\b(will|need to|needs to|should|please|action|follow up|send|schedule|todo|let's|lets|remember to|make sure|i'll|i will)\b",
    re.IGNORECASE,
)


def _sentences(lines):
    prepared = []
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        speaker = str(line.get("speaker") or line.get("speakerName") or "Participant").strip()[:120] or "Participant"
        text = re.sub(r"\s+", " ", str(line.get("text") or "")).strip()
        if not text:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            sentence = sentence.strip()
            if sentence:
                prepared.append((speaker, sentence[:500]))
    return prepared[:200]


def summarize_lines(lines):
    sentences = _sentences(lines)
    if not sentences:
        return {"text": "", "points": [], "actions": []}
    frequencies = {}
    for _, sentence in sentences:
        for word in re.findall(r"[^\W\d_]{3,}", sentence.casefold(), re.UNICODE):
            if word not in _STOPWORDS:
                frequencies[word] = frequencies.get(word, 0) + 1
    ranked = sorted(
        sentences,
        key=lambda item: sum(frequencies.get(word, 0) for word in re.findall(r"[^\W\d_]{3,}", item[1].casefold(), re.UNICODE)),
        reverse=True,
    )
    chosen = []
    seen = set()
    for speaker, sentence in ranked:
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(f"{speaker}: {sentence}")
        if len(chosen) == 4:
            break
    actions = []
    for speaker, sentence in sentences:
        if _ACTION.search(sentence):
            item = f"{speaker}: {sentence}"
            if item not in actions:
                actions.append(item)
        if len(actions) == 6:
            break
    return {
        "text": " ".join(point.split(": ", 1)[-1] for point in chosen),
        "points": chosen,
        "actions": actions,
    }

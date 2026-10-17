"""Live translation for call captions, the AI interpreter, and documents.

MyMemory is used when a network translation is requested. A built-in phrase
glossary still returns a real translation when the network provider is
unavailable, so captions fail closed to the original text only for unknown words.
"""

import os
import re
import urllib.parse
import urllib.request
import json


LANGUAGE_CODES = {
    "en": "en", "english": "en",
    "es": "es", "spanish": "es",
    "fr": "fr", "french": "fr",
    "de": "de", "german": "de",
    "it": "it", "italian": "it",
    "pt": "pt", "portuguese": "pt",
    "zh": "zh", "mandarin chinese": "zh", "chinese": "zh",
    "ja": "ja", "japanese": "ja",
    "ko": "ko", "korean": "ko",
    "ar": "ar", "arabic": "ar",
    "hi": "hi", "hindi": "hi",
    "ru": "ru", "russian": "ru",
    "vi": "vi", "vietnamese": "vi",
    "so": "so", "somali": "so",
}

# Longest phrases are matched first. Pairs are stored in both directions.
_PHRASES = {
    ("en", "es"): {
        "thank you": "gracias", "good morning": "buenos días", "good afternoon": "buenas tardes",
        "how are you": "cómo está", "please": "por favor", "hello": "hola", "yes": "sí", "no": "no",
        "meeting": "reunión", "schedule": "programar", "interpreter": "intérprete",
        "call": "llamada", "document": "documento", "action": "acción", "follow up": "seguimiento",
        "i need help": "necesito ayuda", "see you later": "hasta luego",
    },
    ("en", "fr"): {
        "thank you": "merci", "good morning": "bonjour", "how are you": "comment allez-vous",
        "please": "s'il vous plaît", "hello": "bonjour", "yes": "oui", "no": "non",
        "meeting": "réunion", "schedule": "planifier", "interpreter": "interprète",
        "call": "appel", "document": "document", "follow up": "suivi",
    },
    ("en", "de"): {
        "thank you": "danke", "good morning": "guten morgen", "how are you": "wie geht es ihnen",
        "please": "bitte", "hello": "hallo", "yes": "ja", "no": "nein",
        "meeting": "besprechung", "interpreter": "dolmetscher", "call": "anruf", "document": "dokument",
    },
    ("en", "pt"): {
        "thank you": "obrigado", "hello": "olá", "please": "por favor", "yes": "sim", "no": "não",
        "meeting": "reunião", "interpreter": "intérprete", "call": "chamada", "document": "documento",
    },
    ("en", "it"): {
        "thank you": "grazie", "hello": "ciao", "please": "per favore", "yes": "sì", "no": "no",
        "meeting": "riunione", "interpreter": "interprete", "call": "chiamata", "document": "documento",
    },
    ("en", "zh"): {
        "thank you": "谢谢", "hello": "你好", "please": "请", "yes": "是", "no": "不",
        "meeting": "会议", "interpreter": "口译员", "call": "通话", "document": "文件",
    },
    ("en", "ar"): {
        "thank you": "شكراً", "hello": "مرحبا", "please": "من فضلك", "yes": "نعم", "no": "لا",
        "meeting": "اجتماع", "interpreter": "مترجم", "call": "مكالمة",
    },
    ("en", "hi"): {
        "thank you": "धन्यवाद", "hello": "नमस्ते", "please": "कृपया", "yes": "हाँ", "no": "नहीं",
        "meeting": "बैठक", "interpreter": "दुभाषिया",
    },
    ("en", "ru"): {
        "thank you": "спасибо", "hello": "здравствуйте", "please": "пожалуйста", "yes": "да", "no": "нет",
        "meeting": "встреча", "interpreter": "переводчик",
    },
    ("en", "ja"): {
        "thank you": "ありがとう", "hello": "こんにちは", "please": "お願いします", "yes": "はい", "no": "いいえ",
        "meeting": "会議", "interpreter": "通訳",
    },
    ("en", "ko"): {
        "thank you": "감사합니다", "hello": "안녕하세요", "please": "부탁합니다", "yes": "네", "no": "아니요",
        "meeting": "회의", "interpreter": "통역사",
    },
}

DEFINITIONS = {
    "interpreter": "A person or AI participant that restates speech from one language into another during the call.",
    "transcript": "The written lines of finalized speech. FiniSpeak does not store raw microphone audio.",
    "subtitle": "Translated speech shown over a participant's video or avatar.",
    "avatar": "An animated stand-in that replaces a camera and moves with the speaker's voice.",
    "consent": "Permission to keep a summary with the call. FiniSpeak does not save a summary unless this is confirmed.",
    "translation": "The meaning of speech or text expressed in another language.",
}


def canonical_language(value, default="en"):
    key = str(value or "").strip().casefold()
    if not key:
        return default
    if key in LANGUAGE_CODES:
        return LANGUAGE_CODES[key]
    if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", key):
        return key[:2]
    return default


def _pair_map(source, target):
    forward = _PHRASES.get((source, target))
    if forward:
        return forward
    backward = _PHRASES.get((target, source))
    if not backward:
        return {}
    return {translation.casefold(): phrase for phrase, translation in backward.items()}


def glossary_translate(text, source, target):
    mapping = _pair_map(source, target)
    if not mapping:
        return text
    pieces = re.split(r"(\W+)", text)
    index = 0
    output = []
    lowered = [piece.casefold() for piece in pieces]
    phrases = sorted(mapping, key=len, reverse=True)
    while index < len(pieces):
        matched = False
        for phrase in phrases:
            words = phrase.split(" ")
            if len(words) == 1:
                continue
            collected = []
            cursor = index
            for word in words:
                while cursor < len(pieces) and not pieces[cursor].strip():
                    collected.append(pieces[cursor])
                    cursor += 1
                if cursor >= len(pieces) or lowered[cursor] != word:
                    collected = []
                    break
                collected.append(pieces[cursor])
                cursor += 1
            if collected and lowered[index:cursor]:
                output.append(mapping[phrase])
                index = cursor
                matched = True
                break
        if matched:
            continue
        token = pieces[index]
        replacement = mapping.get(token.casefold())
        output.append(replacement if replacement and token.strip() else token)
        index += 1
    return "".join(output)


def _mymemory_transport(text, source, target):
    endpoint = os.getenv("FINISPEAK_TRANSLATION_URL", "https://api.mymemory.translated.net/get")
    query = urllib.parse.urlencode({"q": text, "langpair": f"{source}|{target}"})
    request = urllib.request.Request(endpoint + "?" + query, headers={"User-Agent": "FiniSpeak/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("responseData") or {}
    translated = str(data.get("translatedText") or "").strip()
    if not translated or "MYMEMORY WARNING" in translated.upper() or int(payload.get("responseStatus") or 0) >= 400:
        raise RuntimeError("Translation provider did not return text.")
    return translated


def _chunks(text, limit=450):
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if current and len(current) + len(sentence) + 1 > limit:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts or [text[:limit]]


def translate_text(text, source, target, online=False, transport=None):
    source_code = canonical_language(source)
    target_code = canonical_language(target)
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) > 20000:
        cleaned = cleaned[:20000]
    base = {"source": source_code, "target": target_code}
    if not cleaned:
        return {**base, "text": "", "status": "empty", "provider": "identity"}
    if source_code == target_code:
        return {**base, "text": cleaned, "status": "unchanged", "provider": "identity"}

    if online or transport:
        try:
            sender = transport or _mymemory_transport
            translated = " ".join(sender(part, source_code, target_code) for part in _chunks(cleaned)).strip()
            if translated:
                return {**base, "text": translated, "status": "translated", "provider": "provider" if transport else "mymemory"}
        except Exception:
            pass

    fallback = glossary_translate(cleaned, source_code, target_code)
    changed = fallback.casefold() != cleaned.casefold()
    return {
        **base,
        "text": fallback,
        "status": "translated" if changed else "unavailable",
        "provider": "glossary" if changed else "identity",
    }


def explain_term(term, source, target, online=False, transport=None):
    cleaned = re.sub(r"\s+", " ", str(term or "")).strip()
    cleaned = cleaned.strip(".,;:!?\"'“”«»()[]{}¿¡…").strip()
    if len(cleaned) > 240:
        cleaned = re.split(r"(?<=[.!?])\s+", cleaned)[0][:240].strip(".,;:!?\"'“”«»()[]{}¿¡… ").strip()
    if not cleaned:
        raise ValueError("Select a word or short phrase to explain.")
    glossary = translate_text(cleaned, source, target, online=False)
    translated = glossary if glossary["status"] == "translated" else translate_text(
        cleaned, source, target, online=online, transport=transport
    )
    definition = DEFINITIONS.get(cleaned.casefold())
    if not definition:
        changed = translated["status"] == "translated" and translated["text"].casefold() != cleaned.casefold()
        definition = (
            "This wording uses the same translation as the live captions."
            if changed
            else "No saved translation was found. Try one word from the document."
        )
    return {
        "term": cleaned,
        "definition": definition,
        "translation": translated["text"],
        "status": translated["status"],
        "source": translated["source"],
        "target": translated["target"],
    }

# Safety & verification logic
# Red flags trigger a doctor-advice message appended to the response.

RED_FLAGS = [
    "heavy bleeding",
    "severe pain",
    "unbearable pain",
    "cannot move",
    "can't move",
    "fainting",
    "fainted",
    "passed out",
    "fever",
    "high temperature",
    "smelly discharge",
    "unusual discharge",
    "infection",
    "pregnant",
    "pregnancy",
    "bleeding after sex",
    "bleeding between periods",
    "spotting after sex",
    "chest pain",
    "shortness of breath",
    "missed period",          # could indicate pregnancy
    "no period for",
    "period stopped",
    "blood clots",
    "soaking through",
    "dizzy",
    "dizziness",
    "vomiting",
    "toxic shock",
]


def doctor_advice_needed(user_text: str, answer_text: str) -> bool:
    """Returns True if the user's message contains a red-flag symptom."""
    text = (user_text or "").lower()
    return any(flag in text for flag in RED_FLAGS)


def simple_verification(answer_text: str, ontology_facts: list[str]) -> tuple[bool, list[str]]:
    """
    Lightweight check: does the answer share meaningful vocabulary with the ontology facts?
    This helps detect if the LLM has drifted significantly from the source facts.
    """
    warnings = []

    if not ontology_facts:
        return True, warnings

    facts_text = " ".join(ontology_facts).lower()
    answer_lower = (answer_text or "").lower()

    # Extract meaningful keywords from facts (length > 4, not stop words)
    STOP = {"from", "that", "this", "with", "have", "been", "also", "than",
            "into", "when", "they", "their", "about", "which", "will", "used"}
    keywords = [
        w for w in re.findall(r"[a-zA-Z]+", facts_text)
        if len(w) > 4 and w not in STOP
    ]

    if not keywords:
        return True, warnings

    # Check overlap between answer and fact keywords
    matches = sum(1 for w in keywords[:40] if w in answer_lower)
    overlap_ratio = matches / min(len(keywords[:40]), 40)

    if overlap_ratio < 0.05:
        warnings.append(
            "Response may contain information not directly supported by the ontology. "
            "Please verify with a healthcare professional."
        )
        return False, warnings

    return True, warnings


import re  # noqa: E402 (imported at bottom to keep file readable)

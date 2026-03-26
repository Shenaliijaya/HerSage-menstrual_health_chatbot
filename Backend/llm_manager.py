import requests
from config import LLM_PROVIDER, OLLAMA_MODEL, OLLAMA_URL, ENABLE_LLM_POLISH


class LLMManager:
    def __init__(self):
        self.provider = (LLM_PROVIDER or "ollama").lower()

    def is_available(self) -> bool:
        try:
            r = requests.get(OLLAMA_URL.rstrip("/") + "/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def polish(self, ontology_facts: list[str], user_question: str, safety_note: str = "", culture: str = "general") -> str:
        print(f"[LLM] polish() called. ENABLE_LLM_POLISH={ENABLE_LLM_POLISH}")

        if not ENABLE_LLM_POLISH:
            print("[LLM] Skipped - ENABLE_LLM_POLISH is False")
            return ""

        if not ontology_facts:
            print("[LLM] Skipped - no ontology facts provided")
            return ""

        print(f"[LLM] Checking Ollama at {OLLAMA_URL} ...")
        if not self.is_available():
            print("[LLM] Ollama is NOT reachable. Returning empty.")
            return ""

        print(f"[LLM] Sending {len(ontology_facts)} facts to model: {OLLAMA_MODEL}")

        try:
            prompt = self._build_prompt(ontology_facts, user_question, safety_note, culture)
            result = self._ollama(prompt)
            if result:
                # Strip opening/closing quotes the LLM sometimes adds
                result = result.strip().strip('"').strip("'").strip()
                # If response starts with "Answer:" or "Response:" strip that too
                import re
                result = re.sub(r'^(Answer|Response)\s*:\s*', '', result, flags=re.IGNORECASE).strip()
                print(f"[LLM] Got response ({len(result)} chars)")
            else:
                print("[LLM] Got empty response from Ollama")
            return result
        except Exception as e:
            print(f"[LLM] Exception during Ollama call: {e}")
            return ""

    def _build_prompt(self, facts: list[str], question: str, safety_note: str, culture: str = "general") -> str:
        top_facts   = facts[:5]
        facts_block = "\n".join("- " + f for f in top_facts)
        q_lower     = question.lower()

        # Concrete cultural tone instructions — tell Mistral exactly HOW to write differently
        culture_map = {
            "sri_lankan": (
                "You are speaking to someone from Sri Lanka where menstruation is often a private topic. "
                "Start with a warm reassuring sentence. Use gentle, respectful language throughout. "
                "Avoid clinical or blunt phrasing. End with an encouraging note like "
                "'It is always okay to speak to a doctor or trusted adult if you have concerns.'"
            ),
            "south_asian": (
                "You are speaking to someone from South Asia where menstruation may be considered private or taboo. "
                "Use respectful, sensitive language. Begin warmly. Avoid language that could feel shameful. "
                "Gently encourage seeking professional help at the end."
            ),
            "conservative": (
                "You are speaking to someone from a conservative background where this topic is very private. "
                "Use the gentlest possible language. Avoid all clinical terms — say 'monthly cycle' instead of "
                "'menstruation' where possible. Be very encouraging and reassuring throughout. "
                "End with 'It is always okay to speak privately with a healthcare professional.'"
            ),
            "western": (
                "You are speaking to someone from a Western background. "
                "Be direct, practical and factual. Clinical terms are fine. "
                "No need for extra reassurance — focus on clear accurate information."
            ),
            "general": (
                "Use clear, friendly, supportive language suitable for a general audience."
            ),
        }
        culture_note = culture_map.get(culture, culture_map["general"])

        # Myth question format
        is_myth_q = ("myth" in q_lower or "is it true" in q_lower or
                     "cannot exercise" in q_lower or "false" in q_lower or
                     "impure" in q_lower or "unclean" in q_lower)

        if is_myth_q:
            format_instr = (
                "Structure your response exactly as:\n"
                "MYTH: [the false belief in one sentence]\n"
                "FACT: [the truth in 1-2 sentences using only the facts above]"
            )
        else:
            format_instr = ("Write a natural, friendly 2-3 sentence response using ONLY the exact facts listed above. "
                            "Do NOT add any information that is not explicitly stated in the facts above. "
                            "Focus specifically on what the facts say about the topic in the question. "
                            "If the question asks about treatment, focus ONLY on treatment facts. "
                            "Start directly with the topic. Do not start with 'I' or 'As a'.")

        prompt  = "You are a menstrual health education assistant. Use ONLY the facts provided below.\n"
        prompt += "\nTone instruction: " + culture_note
        prompt += "\n\nFacts:\n" + facts_block
        prompt += "\n\nQuestion: " + question
        prompt += "\n\n" + format_instr
        prompt += "\n\nAnswer:"
        return prompt

    def _ollama(self, prompt: str) -> str:
        url = OLLAMA_URL.rstrip("/") + "/api/generate"
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "60m",
            "options": {
                "temperature": 0.2,
                "num_predict": 200,   # enough for cultural tone variation
                "num_ctx": 1024,      # smaller context = faster
                "top_p": 0.9,
            }
        }
        print(f"[LLM] POST {url}")
        r = requests.post(url, json=payload, timeout=300)
        print(f"[LLM] Response status: {r.status_code}")
        if r.status_code != 200:
            raise RuntimeError(f"Ollama error {r.status_code}: {r.text[:300]}")
        data = r.json()
        return (data.get("response") or "").strip()

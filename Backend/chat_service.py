import uuid

from memory_store import append_message, get_last_concept, set_last_concept
from safety import doctor_advice_needed, simple_verification
from ontology_manager import OntologyManager
from llm_manager import LLMManager
from config import EXAMPLE_LIMIT, ENABLE_LLM_POLISH


class ChatService:
    def __init__(self, ontology: OntologyManager, llm: LLMManager):
        self.ontology = ontology
        self.llm = llm

    def _looks_like_ref(self, text: str) -> bool:
        t = (text or "").lower()
        return any(x in t for x in ["for this", "for it", "for that", "this", "it", "that"])

    def _is_treatment_question(self, text: str) -> bool:
        t = (text or "").lower()
        return any(w in t for w in ["treat", "treatment", "medicine", "medication", "help", "relief", "cure"])

    def _title(self, text: str) -> str:
        t = (text or "").strip()
        return t[:1].upper() + t[1:] if t else t

    def _safe_split_value(self, line: str, keyword: str) -> str:
        """Safely extract value after a keyword in a fact string. Never crashes."""
        lower = line.lower()
        marker = f" {keyword.lower()} "
        if marker in lower:
            idx = lower.index(marker)
            return line[idx + len(marker):].strip()
        return ""

    def _fallback_format(self, concept, facts, is_treatment_q, examples):
        """Readable structured fallback when LLM is unavailable."""
        c = self._title(concept.replace("_", " ").strip())
        parts = [f"**{c}**\n"]

        desc_line = edu_line = severity_line = duration_line = None
        treated_lines = []

        for f in facts:
            fl = f.lower()
            if "educationalnote" in fl and not edu_line:
                val = self._safe_split_value(f, "educationalnote")
                if val:
                    edu_line = val
            elif " description " in fl and not desc_line:
                val = self._safe_split_value(f, "description")
                if val:
                    desc_line = val
            elif " severity " in fl and not severity_line:
                val = self._safe_split_value(f, "severity")
                if val:
                    severity_line = val
            elif " duration " in fl and not duration_line:
                val = self._safe_split_value(f, "duration")
                if val:
                    duration_line = val
            elif "treatedby" in fl:
                val = self._safe_split_value(f, "treatedBy") or self._safe_split_value(f, "treatedby")
                if val:
                    treated_lines.append(val.replace("_", " "))

        if edu_line:
            parts.append(edu_line + "\n")
        elif desc_line:
            parts.append(desc_line[:400] + ("..." if len(desc_line) > 400 else "") + "\n")

        if severity_line:
            parts.append(f"**Severity:** {severity_line}")
        if duration_line:
            parts.append(f"**Duration:** {duration_line} days")
        if treated_lines:
            parts.append("**May be helped by:** " + ", ".join(treated_lines[:3]))

        if is_treatment_q and examples:
            parts.append("\n**Treatment options in the knowledge base:**")
            for lbl, d in (examples or [])[:EXAMPLE_LIMIT]:
                parts.append(f"- **{lbl}**: {d}" if d else f"- {lbl}")

        parts.append(
            "\n*Note: Responses are based on verified ontology facts only. "
            "Please consult a healthcare professional for personal medical advice.*"
        )
        return "\n".join(p for p in parts if p)

    def _format_no_facts(self) -> str:
        return (
            "I was not able to find information about that in my knowledge base. "
            "Try asking about topics like Menstruation, PCOS, Endometriosis, "
            "Cramps, Heavy Bleeding, PMS, Fibroids, or Hygiene Products.\n\n"
            "For example:\n"
            "- What is PCOS?\n"
            "- How can I relieve period cramps?\n"
            "- What is the luteal phase?"
        )

    def chat(self, session_id: str, user_text: str, lang: str = "en", culture: str = "general") -> dict:
        if not session_id:
            session_id = str(uuid.uuid4())

        append_message(session_id, "user", user_text)

        # ── Input pre-checks ──────────────────────────────────────────────────

        # 1a. Empty or whitespace input
        if not user_text or not user_text.strip():
            return {
                "session_id":     session_id,
                "answer":         "Please type a question about menstrual health and I will do my best to help.",
                "ontology_facts": [],
                "verified":       True,
                "warnings":       [],
                "doctor_advice":  None,
                "llm_used":       False,
                "is_myth":        False,
                "llm_concepts":   [],
                "llm_claims":     [],
            }
        
        # 1c. Sinhala or Tamil script detection
        def has_sinhala(text):
            return any('\u0D80' <= ch <= '\u0DFF' for ch in text)
        def has_tamil(text):
            return any('\u0B80' <= ch <= '\u0BFF' for ch in text)

        LANG_TMPL = {
            "session_id": session_id, "ontology_facts": [], "verified": True,
            "warnings": [], "doctor_advice": None, "llm_used": False,
            "is_myth": False, "llm_concepts": [], "llm_claims": []
        }

        if has_sinhala(user_text):
            r = dict(LANG_TMPL)
            r["answer"] = (
                "Sinhala language support is planned for a future version. "
                "Please ask your question in English for now."
            )
            return r

        if has_tamil(user_text):
            r = dict(LANG_TMPL)
            r["answer"] = (
                "Tamil language support is planned for a future version. "
                "Please ask your question in English for now.\n\n"
                "(\u0ba4\u0bae\u0bbf\u0bb4\u0bcd \u0bae\u0bca\u0bb4\u0bbf "
                "\u0b86\u0ba4\u0bb0\u0bb5\u0bc1 \u0b8e\u0ba4\u0bbf\u0bb0\u0bcd"
                "\u0b95\u0bbe\u0bb2\u0ba4\u0bcd\u0ba4\u0bbf\u0bb2\u0bcd "
                "\u0b9a\u0bc7\u0bb0\u0bcd\u0b95\u0bcd\u0b95\u0baa\u0bcd\u0baa\u0b9f\u0bc1\u0bae\u0bcd.)"
            )
            return r

        # 1c. Distress signal detection
        DISTRESS_PHRASES = [
            "want to die", "kill myself", "end my life", "cant take it anymore",
            "can't take it anymore", "no point living", "hurt myself",
            "give up", "too much pain", "unbearable"
        ]
        user_lower = user_text.lower()
        if any(phrase in user_lower for phrase in DISTRESS_PHRASES):
            r = dict(LANG_TMPL)
            r["answer"] = (
                "I hear that you are going through a very difficult time right now. "
                "Your feelings are valid and you deserve support.\n\n"
                "If you are in distress or feeling overwhelmed, please reach out to "
                "someone you trust, or contact a healthcare professional or counsellor. "
                "You do not have to face this alone.\n\n"
                "When you are ready, I am here to help with any menstrual health questions."
            )
            r["doctor_advice"] = (
                "If you are experiencing a mental health crisis, please contact a "
                "healthcare professional or counsellor as soon as possible."
            )
            return r

        # 1d. Greeting detection
        GREETINGS = ["hi", "hello", "hey", "help", "hii", "helo", "hai"]
        if user_text.strip().lower() in GREETINGS:
            r = dict(LANG_TMPL)
            r["answer"] = (
                "Hi there! I am a menstrual health education assistant. "
                "I can answer questions about periods, symptoms, conditions, "
                "hygiene, and more.\n\n"
                "Try asking something like:\n"
                "- What is PCOS?\n"
                "- How do I relieve cramps?\n"
                "- What is the luteal phase?\n"
                "- Is it a myth that you cannot exercise during your period?"
            )
            return r


        # 1b. Non-meaningful input check
        import re as _re
        stripped = user_text.strip()
        real_words = _re.findall(r"[a-zA-Z]{2,}", stripped)

        # Vague filler words that aren't health questions
        VAGUE_WORDS = {
            "good", "fine", "yes", "no", "maybe", "sure",
            "cool", "bye", "hmm", "um", "uh", "what", "why", "how",
            "when", "where", "who", "really", "oh", "wow", "lol", "haha",
            "test", "testing"
        }

        THANK_YOU_WORDS = {"thanks", "thank", "thank you", "thankyou"}
        UNDERSTOOD_WORDS = {"okay", "ok", "alright", "got it", "noted", "understood", "great", "nice"}
        ACK_WORDS = THANK_YOU_WORDS | UNDERSTOOD_WORDS

        singleword = len(real_words) == 1 and real_words[0].lower() in VAGUE_WORDS
        user_lower = stripped.lower()
        ack_word = (len(real_words) == 1 and real_words[0].lower() in ACK_WORDS) or (user_lower in ACK_WORDS)
        norealwords = (len(stripped) <= 2 or len(stripped) <= 10) and not real_words

        if ack_word:
            previous = get_last_concept(session_id)
            if previous:
                if real_words[0].lower() in THANK_YOU_WORDS:
                    ack_reply = "You're welcome! Feel free to ask me anything else about menstrual health."
                else:
                    ack_reply = "Glad that helps! Feel free to ask if you have more questions."
                return {
                    "session_id":     session_id,
                    "answer":         ack_reply,
                    "ontology_facts": [], "verified": True, "warnings": [],
                    "doctor_advice":  None, "llm_used": False, "is_myth": False,
                    "llm_concepts":   [], "llm_claims": []
                }

        if norealwords or singleword or ack_word:
            return {
                "session_id":     session_id,
                "answer":         "I am not sure what you are asking. Could you please be more specific?\n\nFor example:\n- What is PCOS?\n- How do I relieve cramps?\n- What are the signs of endometriosis?",
                "ontology_facts": [], "verified": True, "warnings": [],
                "doctor_advice":  None, "llm_used": False, "is_myth": False,
                "llm_concepts":   [], "llm_claims": []
            }


        # 1. Detect concept
        last     = get_last_concept(session_id)
        detected = self.ontology.detect_target_label(user_text)
        if self._looks_like_ref(user_text) and last:
        # Always treat this as a follow‑up to the last concept
            target = last.lower()
        else:
            target = detected

        # 2. Retrieve ontology facts
        facts = self.ontology.get_relevant_facts(user_text, target_label=target)

        if target:
            set_last_concept(session_id, target)
        elif facts and facts[0].lower().startswith("concept:"):
            set_last_concept(session_id, facts[0].split(":", 1)[1].strip())

        # 3. Safety check
        doctor_msg = None
        if doctor_advice_needed(user_text, ""):
            doctor_msg = (
                "If you are experiencing severe pain, heavy bleeding, fainting, "
                "high fever, or have pregnancy-related concerns, please consult a "
                "doctor or qualified healthcare provider as soon as possible."
            )

        # 4. Build response
        llm_answer = ""
        if not facts:
            answer   = self._format_no_facts()
            verified = True
            warnings = []
        else:
            is_treat_q = self._is_treatment_question(user_text)
            examples   = self.ontology.get_treatment_examples(limit=EXAMPLE_LIMIT) if is_treat_q else None
            concept    = target or "this topic"

            # For treatment follow-up questions, enrich facts with concept-specific
            # treatment relations from the ontology (e.g. PCOS treatedBy ...)
            if is_treat_q and target:
                treat_facts = [
                    f for f in self.ontology.get_relevant_facts(target, target_label=target)
                    if "treatedby" in f.lower() or "treatment" in f.lower()
                    or "lifestyle" in f.lower() or "medication" in f.lower()
                ]
                # Merge with existing facts, deduplicate
                for tf in treat_facts:
                    if tf not in facts:
                        facts.append(tf)

            # Try LLM polish
            if ENABLE_LLM_POLISH:
                # Strip bare 'Concept: X' lines — they cause LLM to echo the label
                facts_for_llm = [f for f in facts if not f.lower().startswith("concept:") and len(f.strip()) > 20]
                if is_treat_q and examples:
                    for lbl, desc in examples:
                        facts_for_llm.append(f"{lbl}: {desc}" if desc else lbl)
                try:
                    llm_answer = self.llm.polish(
                        ontology_facts=facts_for_llm,
                        user_question=user_text,
                        safety_note=doctor_msg or "",
                        culture=culture,
                    )
                except Exception as e:
                    print(f"[ChatService] LLM failed: {e}")

            # Strip only leading/trailing quotes the LLM sometimes adds
            if llm_answer:
                llm_answer = llm_answer.strip().strip('"').strip("'").strip()

            answer = llm_answer if llm_answer else self._fallback_format(
                concept=concept,
                facts=facts,
                is_treatment_q=is_treat_q,
                examples=examples,
            )

            verified, warnings = simple_verification(answer, facts)

        append_message(session_id, "assistant", answer)

        # Detect myth response from facts + target label (reliable)
        myth_keywords = ["menstrualmyth", "mythab", "myth about",
                         "false belief", "misconception", "myth: ",
                         "myth_noexercise", "myth_impurity", "myth_pain"]
        facts_lower = " ".join(facts).lower()
        target_lower = (target or "").lower()
        is_myth = (any(kw in facts_lower for kw in myth_keywords) or
                   "myth" in target_lower)

        return {
            "session_id":     session_id,
            "answer":         answer,
            "ontology_facts": facts,
            "verified":       verified,
            "warnings":       warnings,
            "doctor_advice":  doctor_msg,
            "llm_used":       bool(llm_answer),
            "is_myth":        is_myth,
            "llm_concepts":   [],
            "llm_claims":     [],
        }

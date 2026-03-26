from typing import List, Tuple, Optional
import os
import re
from difflib import get_close_matches

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL

from config import OWL_PATH, TOP_K_FACTS


# Properties in the enhanced ontology we want to surface as facts
FACT_PROPERTIES = [
    "description",
    "severity",
    "duration",
    "dayspercycle",
    "durationdays",
    "cycleday",
    "hormones",
    "prevalence",
    "educationalnote",   # new in enhanced ontology — great for natural answers
]

# Relation properties to capture as triples
RELATION_PROPERTIES = [
    "treatedBy",
    "requiresProduct",
    "hasSymptom",
    "associatedWith",    # new
    "occursInPhase",     # new
    "appropriateFor",    # new
    "commonInCulture",   # new
]


class OntologyManager:
    """
    Loads the enhanced OWL ontology and supports:
      - detect_target_label(question)
      - get_relevant_facts(question, top_k, target_label)
      - get_treatment_examples(limit)
      - get_class_comment(label)   ← new: fetches rdfs:comment for a class
    """

    def __init__(self, owl_path: str = OWL_PATH):
        if not os.path.exists(owl_path):
            raise FileNotFoundError(f"OWL file not found at: {owl_path}")

        self.graph = Graph()
        self.graph.parse(owl_path)

        self._facts: List[str] = []
        self._labels: List[str] = []
        self._label_to_uri: dict[str, URIRef] = {}
        self._label_to_class_uri: dict[str, URIRef] = {}

        self._build_indexes()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text)).strip()

    def _uri_to_name(self, uri) -> str:
        uri_str = str(uri)
        if "#" in uri_str:
            return uri_str.split("#")[-1]
        return uri_str.rstrip("/").split("/")[-1]

    def _first_literal(self, subj: URIRef, pred: URIRef) -> Optional[str]:
        for obj in self.graph.objects(subj, pred):
            if isinstance(obj, Literal):
                return str(obj)
        return None

    def _label_of(self, node: URIRef) -> str:
        return (self._first_literal(node, RDFS.label) or self._uri_to_name(node)).strip()

    # ── Index building ────────────────────────────────────────────────────────

    def _build_indexes(self):
        g = self.graph

        # 1. Class labels
        for cls in g.subjects(RDF.type, OWL.Class):
            lbl = self._first_literal(cls, RDFS.label)
            if lbl:
                key = lbl.strip().lower()
                self._label_to_class_uri[key] = cls

        # 2. All labels (classes + instances)
        all_labels = []
        for subj in g.subjects(RDFS.label, None):
            lbl = self._first_literal(subj, RDFS.label)
            if lbl:
                key = lbl.strip().lower()
                all_labels.append(key)
                self._label_to_uri[key] = subj

        for key, uri in self._label_to_class_uri.items():
            if key not in self._label_to_uri:
                self._label_to_uri[key] = uri
            all_labels.append(key)

        all_labels = list(set(all_labels))
        all_labels.sort(key=len, reverse=True)   # longest-first for greedy matching
        self._labels = all_labels

        # 3. Build fact strings
        facts = []

        # (A) Class concept + subclass facts + rdfs:comment (rich descriptions)
        for cls in g.subjects(RDF.type, OWL.Class):
            child_lbl = self._label_of(cls)
            facts.append(f"Concept: {child_lbl}")

            for parent in g.objects(cls, RDFS.subClassOf):
                parent_lbl = self._label_of(parent)
                facts.append(f"{child_lbl} subClassOf {parent_lbl}")

            # Include rdfs:comment — this is where all the rich educational text lives
            comment = self._first_literal(cls, RDFS.comment)
            if comment:
                facts.append(f"{child_lbl} description {comment.strip()}")

        # (B) Instance attribute facts
        for subj in g.subjects(RDFS.label, None):
            subj_lbl = self._label_of(subj)

            for pred, obj in g.predicate_objects(subj):
                pred_name = self._uri_to_name(pred).lower()

                if isinstance(obj, Literal) and pred_name in FACT_PROPERTIES:
                    # Use "educationalnote" as "educationalNote" in the fact string for readability
                    display_pred = pred_name if pred_name != "educationalnote" else "educationalNote"
                    facts.append(f"{subj_lbl} {display_pred} {str(obj).strip()}")

        # (C) Instance relation facts (treatedBy, associatedWith, etc.)
        for s, p, o in g:
            if not isinstance(s, URIRef) or not isinstance(p, URIRef) or not isinstance(o, URIRef):
                continue

            p_name = self._uri_to_name(p)
            if p_name not in RELATION_PROPERTIES:
                continue

            if (s, RDFS.label, None) in g and (o, RDFS.label, None) in g:
                s_lbl = self._label_of(s)
                o_lbl = self._label_of(o)
                facts.append(f"{s_lbl} {p_name} {o_lbl}")

        self._facts = [self._clean(f) for f in facts]

    # ── Detection & retrieval ─────────────────────────────────────────────────

    def detect_target_label(self, user_text: str) -> Optional[str]:
        q = (user_text or "").lower()

        # Explicit mappings for common colloquial phrases
        colloquial = {
            ("cramp", "severe"): "severe cramping",
            ("cramp", "mild"):   "mild cramping",
            ("period", "first"): "first period (menarche)",
            ("first", "period"): "first period (menarche)",
            ("heavy", "period"): "abnormal heavy bleeding",
            ("heavy", "bleed"):  "abnormal heavy bleeding",
            ("pms",):            "premenstrual syndrome",
            ("pre", "menstrual", "syndrome"): "premenstrual syndrome",
            ("pmdd",):           "pmdd",
            # Myth question mappings
            ("myth", "exercise"): "myth: no exercise during period",
            ("myth", "workout"):  "myth: no exercise during period",
            ("myth", "sport"):    "myth: no exercise during period",
            ("myth", "impure"):   "myth: menstruation is impure",
            ("myth", "unclean"):  "myth: menstruation is impure",
            ("myth", "dirty"):    "myth: menstruation is impure",
            ("myth", "pain"):     "myth: severe pain is normal",
            ("myth", "normal"):   "myth: severe pain is normal",
            ("myth", "period"):   "myth: no exercise during period",
            ("is it true", "exercise"): "myth: no exercise during period",
            ("can you", "exercise"): "myth: no exercise during period",
            ("cannot exercise",):  "myth: no exercise during period",
            ("can't exercise",):  "myth: no exercise during period",
        }
        for keywords, label in colloquial.items():
            if all(kw in q for kw in keywords):
                if label in self._label_to_uri:
                    return label

        # Greedy longest-match against all known labels
        for lbl in self._labels:
            if lbl in q:
                return lbl

        # Fuzzy matching — handles typos like "pcso", "cramos", "endometrisos"
        # Extract meaningful words from the question (length > 3)
        q_words = [w for w in re.findall(r"[a-zA-Z]+", q) if len(w) > 3]
        for word in q_words:
            matches = get_close_matches(word, self._labels, n=1, cutoff=0.82)
            if matches:
                return matches[0]

        return None

    def get_relevant_facts(
        self,
        user_question: str,
        top_k: int = TOP_K_FACTS,
        target_label: Optional[str] = None,
    ) -> List[str]:
        q = (user_question or "").lower()
        target = target_label or self.detect_target_label(user_question)

        if target:
            target_l = target.lower()
            out = []
            for f in self._facts:
                fl = f.lower()
                if fl.startswith(f"concept: {target_l}") or fl.startswith(f"{target_l} "):
                    out.append(f)
            if out:
                return out[:top_k]

        # Fallback: keyword overlap scoring
        q_words = set(w for w in re.findall(r"[a-zA-Z]+", q) if len(w) >= 4)
        scored = []
        for f in self._facts:
            fl = f.lower()
            hits = sum(1 for w in q_words if w in fl)
            if hits:
                scored.append((hits, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:top_k]]

    def get_class_comment(self, label: str) -> Optional[str]:
        """
        Directly fetch the rdfs:comment for a class by label.
        Useful for getting the full educational description.
        """
        uri = self._label_to_class_uri.get(label.lower())
        if uri:
            return self._first_literal(uri, RDFS.comment)
        return None

    def get_treatment_examples(self, limit: int = 4) -> List[Tuple[str, Optional[str]]]:
        g = self.graph
        treatment_uri = self._label_to_class_uri.get("treatment")
        if not treatment_uri:
            return []

        # Collect Treatment and all its subclasses
        subclasses = set([treatment_uri])
        changed = True
        while changed:
            changed = False
            for cls in g.subjects(RDFS.subClassOf, None):
                for parent in g.objects(cls, RDFS.subClassOf):
                    if parent in subclasses and cls not in subclasses:
                        subclasses.add(cls)
                        changed = True

        results = []
        for cls in subclasses:
            for inst in g.subjects(RDF.type, cls):
                lbl = self._label_of(inst)
                desc = self._first_literal(inst, URIRef("http://example.org/menstrual-health#description"))
                note = self._first_literal(inst, URIRef("http://example.org/menstrual-health#educationalNote"))
                # Prefer educationalNote (shorter, user-friendly) over description
                display = note or desc
                results.append((lbl, display))
                if len(results) >= limit:
                    return results

        return results

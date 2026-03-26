import re
from typing import Dict, Optional, List, Tuple

from rdflib import URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL


class OntologyValidator:
    def __init__(self, ontology_manager):
        self.om = ontology_manager
        self.g = ontology_manager.graph

        self.label_to_uri: Dict[str, URIRef] = {}
        self.prop_label_to_uri: Dict[str, URIRef] = {}

        self._build_label_index()

    def _norm(self, s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"\s+", " ", s)
        return s

    def _uri_name(self, uri: URIRef) -> str:
        u = str(uri)
        return u.split("#")[-1] if "#" in u else u.rstrip("/").split("/")[-1]

    def _first_literal(self, subj: URIRef, pred: URIRef) -> Optional[str]:
        for obj in self.g.objects(subj, pred):
            if isinstance(obj, Literal):
                return str(obj)
        return None

    def _build_label_index(self):
        # -------------------------
        # 1) Index Classes
        # -------------------------
        for cls in self.g.subjects(RDF.type, OWL.Class):
            label = self._first_literal(cls, RDFS.label) or self._uri_name(cls)
            self.label_to_uri[self._norm(label)] = cls
            # also index by local name
            self.label_to_uri[self._norm(self._uri_name(cls))] = cls

        # -------------------------
        # 2) Index Individuals/Instances
        # Your OWL instances are typed (rdf:type mh:SomeClass) but not owl:NamedIndividual,
        # so index any subject with rdf:type excluding classes/properties.
        # -------------------------
        for inst, inst_type in self.g.subject_objects(RDF.type):
            if (inst, RDF.type, OWL.Class) in self.g:
                continue
            if (inst, RDF.type, OWL.ObjectProperty) in self.g or (inst, RDF.type, OWL.DatatypeProperty) in self.g:
                continue

            label = self._first_literal(inst, RDFS.label) or self._uri_name(inst)
            self.label_to_uri[self._norm(label)] = inst
            # also index by local name
            self.label_to_uri[self._norm(self._uri_name(inst))] = inst

        # -------------------------
        # 3) Index Properties (Object + Datatype)
        # IMPORTANT FIX:
        # Index BOTH the rdfs:label (e.g., "has Symptom") and the URI local name (e.g., "hasSymptom")
        # -------------------------
        for p in self.g.subjects(RDF.type, OWL.ObjectProperty):
            label = self._first_literal(p, RDFS.label) or self._uri_name(p)
            local = self._uri_name(p)

            self.prop_label_to_uri[self._norm(label)] = p
            self.prop_label_to_uri[self._norm(local)] = p

        for p in self.g.subjects(RDF.type, OWL.DatatypeProperty):
            label = self._first_literal(p, RDFS.label) or self._uri_name(p)
            local = self._uri_name(p)

            self.prop_label_to_uri[self._norm(label)] = p
            self.prop_label_to_uri[self._norm(local)] = p

        # -------------------------
        # 4) Helpful aliases
        # -------------------------
        self.prop_label_to_uri[self._norm("subclassof")] = RDFS.subClassOf
        self.prop_label_to_uri[self._norm("subClassOf")] = RDFS.subClassOf
        self.prop_label_to_uri[self._norm("label")] = RDFS.label
        self.prop_label_to_uri[self._norm("comment")] = RDFS.comment
        self.prop_label_to_uri[self._norm("type")] = RDF.type
        self.prop_label_to_uri[self._norm("rdf:type")] = RDF.type

        # IMPORTANT:
        # DO NOT force-map "description" to RDFS.comment,
        # because your ontology has mh:description as a DatatypeProperty and we already index it above.

    def resolve_concept(self, label: str) -> Optional[URIRef]:
        syn = {
            "polycystic ovary syndrome": "pcos",
            "polycystic ovary syndrome (pcos)": "pcos",
        }
        key = self._norm(label)
        key = syn.get(key, key)
        return self.label_to_uri.get(key)


    def resolve_property(self, label: str) -> Optional[URIRef]:
        return self.prop_label_to_uri.get(self._norm(label))

    # -------------------------
    # Validation methods
    # -------------------------
    def validate_concepts_exist(self, concepts: List[str]) -> Tuple[bool, List[str]]:
        """
        Require at least one ontology concept for grounding,
        but allow extra natural-language tags with warnings.
        """
        msgs = []
        resolved_count = 0
        unknown = []

        for c in concepts or []:
            if self.resolve_concept(c):
                resolved_count += 1
            else:
                unknown.append(c)

        if resolved_count == 0:
            msgs.append("No ontology concepts were identified in LLM output (grounding weak).")

        for c in unknown:
            msgs.append(f"Unknown ontology concept (allowed): {c}")

        return (resolved_count > 0), msgs
    
    def validate_claims(self, claims: List[dict]) -> Tuple[bool, List[str]]:
        """
        Lightweight integrity checks:
        - subject must exist
        - predicate must exist
        - STRICT check only for subClassOf triples
        - subClassOf must be used ONLY between OWL Classes (not instances)
        """
        errors = []

        for i, cl in enumerate(claims or []):
            s = cl.get("s", "")
            p = cl.get("p", "")
            o = cl.get("o", "")

            s_uri = self.resolve_concept(s)
            if not s_uri:
                errors.append(f"Claim {i}: unknown subject concept '{s}'")
                continue

            p_uri = self.resolve_property(p)
            if not p_uri:
                errors.append(f"Claim {i}: unknown predicate '{p}'")
                continue

            # Only enforce ontology structure strictly for subClassOf
            if str(p_uri) == str(RDFS.subClassOf):
                # subClassOf should only apply to Classes
                if (s_uri, RDF.type, OWL.Class) not in self.g:
                    errors.append(f"Claim {i}: subClassOf used on non-class subject '{s}' (likely an instance).")
                    continue

                o_uri = self.resolve_concept(o)
                if not o_uri:
                    errors.append(f"Claim {i}: subclassOf object '{o}' not found as ontology concept")
                    continue

                if (o_uri, RDF.type, OWL.Class) not in self.g:
                    errors.append(f"Claim {i}: subClassOf used with non-class object '{o}'")
                    continue

                if (s_uri, RDFS.subClassOf, o_uri) not in self.g and s_uri != o_uri:
                    errors.append(f"Claim {i}: ontology does not support '{s} subClassOf {o}'")

        return (len(errors) == 0), errors

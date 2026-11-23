"""Explainable material matching; fuzzy suggestions are never auto-approved."""
from difflib import SequenceMatcher
import json
import re

from .audit import append_match_event
from .cleansing import normalize_text, normalize_unit


def _compatible_spec(input_spec, candidate_spec):
    left, right = normalize_text(input_spec), normalize_text(candidate_spec)
    return not (left and right and left != right)


def find_candidates(cursor, input_name, input_specification=None, input_unit=None,
                    source_product_code=None):
    unit = normalize_unit(input_unit)
    cursor.execute("""SELECT material_id, material_code, canonical_name, category_name,
        specification, standard_unit FROM materials WHERE is_active=1""")
    materials = cursor.fetchall()
    if not materials:
        return []
    by_id = {row[0]: row for row in materials}
    exact_code = []
    if source_product_code:
        for row in materials:
            if row[1] and str(row[1]).strip() == str(source_product_code).strip():
                exact_code.append((row, "official_code", 1.0))
        if not exact_code:
            cursor.execute("SELECT material_id FROM material_aliases WHERE source_product_code=%s", (str(source_product_code).strip(),))
            alias_ids = {alias_row[0] for alias_row in cursor.fetchall()}
            exact_code.extend((row, "source_product_code", 1.0) for row in materials if row[0] in alias_ids)
    if exact_code:
        ambiguous_code = len({row[0] for row, _, _ in exact_code}) > 1
        results = []
        for row, method, score in exact_code:
            unit_ok = not unit or normalize_unit(row[5]) == unit
            spec_ok = _compatible_spec(input_specification, row[4])
            exact = unit_ok and spec_ok and not ambiguous_code
            display_method = method if unit_ok else "code_unit_mismatch"
            if unit_ok and not spec_ok:
                display_method = "code_specification_mismatch"
            if ambiguous_code:
                display_method = "ambiguous_source_product_code"
            results.append(_format(row, display_method, score if unit_ok else 0.75, exact))
        return results

    cursor.execute("SELECT material_id, alias_normalized FROM material_aliases")
    aliases = {}
    for material_id, alias in cursor.fetchall():
        aliases.setdefault(material_id, set()).add(alias)

    normalized_name = normalize_text(input_name)
    candidates = []
    for row in materials:
        material_id, code, name, category, specification, standard_unit = row
        if unit and normalize_unit(standard_unit) != unit:
            continue
        if not _compatible_spec(input_specification, specification):
            continue
        normalized_canonical = normalize_text(name)
        exact_alias = normalized_name in aliases.get(material_id, set())
        spec_verified = not normalize_text(input_specification) or (
            bool(normalize_text(specification)) and normalize_text(input_specification) == normalize_text(specification)
        )
        if normalized_name == normalized_canonical:
            candidates.append(_format(row, "exact_canonical_name_unit", 0.99, spec_verified))
            continue
        if exact_alias:
            candidates.append(_format(row, "exact_alias_unit", 0.98, spec_verified))
            continue
        name_score = max(SequenceMatcher(None, normalized_name, normalized_canonical).ratio(),
                         _containment(normalized_name, normalized_canonical))
        alias_score = max((SequenceMatcher(None, normalized_name, alias).ratio()
                           for alias in aliases.get(material_id, set())), default=0)
        score = max(name_score, alias_score)
        if score >= 0.55:
            candidates.append(_format(row, "fuzzy_name_suggestion", min(score, 0.89), False))
    return sorted(candidates, key=lambda candidate: candidate["confidence_score"], reverse=True)[:5]


def _grams(text):
    compact = re.sub(r"[\s.\-_/,()]+", "", text)
    return {compact[i:i + 3] for i in range(len(compact) - 2)} or ({compact} if compact else set())


def _containment(query_text, candidate_text):
    """Share of the typed text (3-character pieces, ignoring spaces and dots) found in
    a usually much longer official name, so "SD40" finds "SD.40" and a short Thai
    name finds the long TPSO description. Scaled to at most 0.85: it can only
    produce a suggestion for the user to confirm, never an automatic match.
    """
    query = _grams(query_text)
    if not query:
        return 0.0
    return 0.85 * len(query & _grams(candidate_text)) / len(query)


def _format(row, method, score, exact):
    return {"material_id": row[0], "material_code": row[1], "canonical_name": row[2],
            "category_name": row[3], "specification": row[4], "standard_unit": row[5],
            "match_method": method, "confidence_score": score, "exact": exact}


def log_match_event(cursor, *, input_name, input_specification, input_unit,
                    candidate_material_id, candidate_name, match_method, confidence,
                    status, evidence, project_id=None, item_id=None, observation_id=None,
                    actor="system"):
    cursor.execute("""INSERT INTO match_events
        (project_id,item_id,observation_id,input_name,input_specification,input_unit,
         candidate_material_id,candidate_name,match_method,confidence_score,
         decision_status,evidence_json,actor)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (project_id, item_id, observation_id, input_name, input_specification, input_unit,
         candidate_material_id, candidate_name, match_method, confidence, status,
         json.dumps(evidence, ensure_ascii=False, default=str), actor))
    append_match_event(project_id=project_id, item_id=item_id, observation_id=observation_id,
                       input_name=input_name, input_specification=input_specification,
                       input_unit=input_unit, candidate_material_id=candidate_material_id,
                       candidate_name=candidate_name, match_method=match_method,
                       confidence_score=confidence, decision_status=status,
                       evidence=evidence, actor=actor)


def log_candidate_set(cursor, *, input_name, input_specification, input_unit,
                      candidates, project_id=None, item_id=None, actor="system"):
    if not candidates:
        log_match_event(cursor, input_name=input_name, input_specification=input_specification,
                        input_unit=input_unit, candidate_material_id=None, candidate_name=None,
                        match_method="no_compatible_candidate", confidence=None,
                        status="UNMATCHED", evidence={"reason": "no candidate with compatible unit/spec"},
                        project_id=project_id, item_id=item_id, actor=actor)
        return
    selected = candidates[0] if candidates[0]["exact"] else None
    for rank, candidate in enumerate(candidates, start=1):
        status = "AUTO_MATCHED" if selected and candidate is selected else (
            "NEEDS_REVIEW" if not selected else "ALTERNATIVE_CANDIDATE")
        log_match_event(cursor, input_name=input_name, input_specification=input_specification,
                        input_unit=input_unit, candidate_material_id=candidate["material_id"],
                        candidate_name=candidate["canonical_name"],
                        match_method=candidate["match_method"],
                        confidence=candidate["confidence_score"], status=status,
                        evidence={"rank": rank, "material_code": candidate["material_code"],
                                  "candidate_specification": candidate["specification"],
                                  "candidate_unit": candidate["standard_unit"],
                                  "exact_key_match": candidate["exact"]},
                        project_id=project_id, item_id=item_id, actor=actor)

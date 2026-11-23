"""Human review queue for records held out of price analytics."""
from .audit import append_event
from .db import connection, query
from .matching import find_candidates, log_match_event


def list_price_review_queue(limit=50):
    return query("""SELECT po.observation_id,ps.source_name,po.product_name,po.specification,
        po.province_name,po.observation_date,po.unit,po.price,po.quality_note
        FROM price_observations po JOIN price_sources ps ON ps.source_id=po.source_id
        WHERE po.quality_status='review' ORDER BY po.observation_date DESC,po.observation_id DESC
        LIMIT %s""", (limit,))


def resolve_price_review(observation_id, decision, actor="user"):
    if decision not in {"valid", "rejected"}:
        raise ValueError("decision ต้องเป็น valid หรือ rejected")
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""UPDATE price_observations SET quality_status=%s
            WHERE observation_id=%s AND quality_status='review'""", (decision, observation_id))
        changed = cursor.rowcount
    append_event("price_quality_decision", observation_id=observation_id,
                 decision=decision, actor=actor, changed=bool(changed))
    return changed


def list_unmatched_observations(limit=50):
    """Retail prices that could not be tied to a material (so they cannot enter Top 3)."""
    return query("""SELECT po.observation_id,ps.source_name,po.source_product_code,po.product_name,
        po.specification,po.unit,po.price,po.observation_date
        FROM price_observations po JOIN price_sources ps ON ps.source_id=po.source_id
        WHERE po.material_id IS NULL AND ps.source_kind='retailer' AND po.quality_status<>'rejected'
        ORDER BY po.observation_date DESC,po.observation_id DESC LIMIT %s""", (limit,))


def observation_candidates(observation):
    with connection() as conn:
        cursor = conn.cursor()
        return find_candidates(cursor, observation["product_name"], observation["specification"],
                               observation["unit"])


def confirm_observation_match(observation_id, material_id, actor="user"):
    """Tie a retail price to a material; its store SKU is remembered for future imports."""
    from .ingest import remember_store_sku
    from .cleansing import normalize_unit
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""SELECT source_id,source_product_code,product_name,specification,unit
            FROM price_observations WHERE observation_id=%s""", (observation_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"ไม่พบราคา observation {observation_id}")
        source_id, sku, name, spec, unit = row
        cursor.execute("SELECT canonical_name,standard_unit FROM materials WHERE material_id=%s AND is_active=1",
                       (material_id,))
        material = cursor.fetchone()
        if not material:
            raise ValueError("ไม่พบวัสดุปลายทาง")
        if normalize_unit(material[1]) != normalize_unit(unit):
            raise ValueError("หน่วยไม่ตรงกัน จึงยืนยันการจับคู่ไม่ได้")
        cursor.execute("UPDATE price_observations SET material_id=%s WHERE observation_id=%s",
                       (material_id, observation_id))
        remember_store_sku(cursor, material_id, source_id, name, sku)
        log_match_event(cursor, input_name=name, input_specification=spec, input_unit=unit,
                        candidate_material_id=material_id, candidate_name=material[0],
                        match_method="user_confirmation", confidence=1.0, status="USER_CONFIRMED",
                        evidence={"store_sku": sku, "sku_remembered": bool(sku)},
                        observation_id=observation_id, actor=actor)
    append_event("price_match_confirmed", observation_id=observation_id, material_id=material_id, actor=actor)

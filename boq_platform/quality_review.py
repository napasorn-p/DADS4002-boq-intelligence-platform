"""Human review queue for records held out of price analytics."""
from .audit import append_event
from .db import connection, query


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

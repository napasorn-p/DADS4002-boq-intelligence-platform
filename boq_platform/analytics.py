"""SQL-first BOQ cost analytics and explainable next-action rules."""
from decimal import Decimal

from .config import RETAIL_MAX_AGE_DAYS
from .db import query


def project_summary(project_id):
    rows = query("""SELECT p.project_id,p.project_name,p.scope_type,p.province_code,
        p.province_name,p.budget_total,COUNT(bi.item_id) AS line_count,
        SUM(CASE WHEN bi.material_id IS NOT NULL THEN 1 ELSE 0 END) AS matched_count,
        SUM(CASE WHEN bi.budget_unit_price IS NOT NULL THEN 1 ELSE 0 END) AS budgeted_count,
        SUM(CASE WHEN bi.budget_unit_price IS NOT NULL THEN bi.quantity*bi.budget_unit_price ELSE 0 END) AS boq_cost
        FROM boq_projects p LEFT JOIN boq_items bi ON bi.project_id=p.project_id AND bi.is_deleted=0
        WHERE p.project_id=%s GROUP BY p.project_id,p.project_name,p.scope_type,
        p.province_code,p.province_name,p.budget_total""", (project_id,))
    return rows[0] if rows else None


def top_cost_items(project_id, limit=3):
    return query("""SELECT bi.item_id,COALESCE(pr.room_name,'(ไม่ระบุพื้นที่)') AS room_name,
        bi.input_name,COALESCE(m.canonical_name,bi.input_name) AS material_name,
        bi.quantity,bi.input_unit,bi.budget_unit_price,
        (bi.quantity*bi.budget_unit_price) AS boq_line_cost,
        bi.match_status
        FROM boq_items bi LEFT JOIN materials m ON m.material_id=bi.material_id
        LEFT JOIN project_rooms pr ON pr.room_id=bi.room_id
        WHERE bi.project_id=%s AND bi.is_deleted=0 AND bi.budget_unit_price IS NOT NULL
        ORDER BY boq_line_cost DESC,bi.item_id LIMIT %s""", (project_id, limit))


def top_retail_prices_per_item(project_id, max_age_days=RETAIL_MAX_AGE_DAYS):
    project = query("SELECT province_code FROM boq_projects WHERE project_id=%s", (project_id,))
    if not project:
        return []
    province_code = project[0]["province_code"]
    region_clause = "AND po.province_code=%s" if province_code else "AND po.province_code IS NULL"
    params = [project_id, max_age_days]
    if province_code:
        params.append(province_code)
    return query(f"""WITH eligible_items AS (
            SELECT bi.item_id,bi.quantity,bi.input_unit,bi.material_id,
                   COALESCE(m.canonical_name,bi.input_name) AS material_name
            FROM boq_items bi LEFT JOIN materials m ON m.material_id=bi.material_id
            WHERE bi.project_id=%s AND bi.is_deleted=0 AND bi.material_id IS NOT NULL
        ), ranked AS (
            SELECT ei.item_id,ei.material_name,ei.quantity,ei.input_unit,
                   ps.source_name,po.price,po.regular_price,po.vat_included,
                   po.shipping_fee,po.province_name,po.branch_name,po.observation_date,
                   po.product_url,po.stock_status,
                   ROW_NUMBER() OVER (PARTITION BY ei.item_id,ps.source_id
                       ORDER BY po.observation_date DESC,po.retrieved_at DESC) AS rn
            FROM eligible_items ei
            JOIN price_observations po ON po.material_id=ei.material_id
                AND LOWER(po.unit)=LOWER(ei.input_unit)
            JOIN price_sources ps ON ps.source_id=po.source_id AND ps.source_kind='retailer'
            WHERE po.quality_status='valid'
              AND po.vat_included=1
              AND COALESCE(LOWER(po.stock_status),'') NOT IN ('out of stock','unavailable','หมด','สินค้าหมด')
              AND po.observation_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
              {region_clause}
        ), latest_per_store AS (SELECT * FROM ranked WHERE rn=1),
        ranked_offers AS (SELECT *,ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY price,source_name) AS price_rank
                          FROM latest_per_store)
        SELECT item_id,material_name,quantity,input_unit,source_name,price,
               regular_price,vat_included,shipping_fee,province_name,branch_name,
               observation_date,product_url,stock_status
        FROM ranked_offers WHERE price_rank<=3 ORDER BY item_id,price_rank""", params)


def retailer_basket_comparison(project_id, max_age_days=RETAIL_MAX_AGE_DAYS):
    project = query("SELECT province_code FROM boq_projects WHERE project_id=%s", (project_id,))
    if not project:
        return []
    province_code = project[0]["province_code"]
    region_clause = "AND po.province_code=%s" if province_code else "AND po.province_code IS NULL"
    params = [project_id, max_age_days]
    if province_code:
        params.append(province_code)
    params.append(project_id)
    return query(f"""WITH eligible_items AS (
            SELECT bi.item_id,bi.quantity,bi.input_unit,bi.material_id
            FROM boq_items bi
            WHERE bi.project_id=%s AND bi.is_deleted=0 AND bi.material_id IS NOT NULL
        ), ranked AS (
            SELECT ei.item_id,ei.quantity,ei.material_id,ei.input_unit,
                   po.source_id,po.price,po.observation_date,
                   ROW_NUMBER() OVER (PARTITION BY ei.item_id,po.source_id
                       ORDER BY po.observation_date DESC,po.retrieved_at DESC) AS rn
            FROM eligible_items ei
            JOIN price_observations po ON po.material_id=ei.material_id
                AND LOWER(po.unit)=LOWER(ei.input_unit)
            JOIN price_sources ps ON ps.source_id=po.source_id AND ps.source_kind='retailer'
            WHERE po.quality_status='valid'
              AND po.vat_included=1
              AND COALESCE(LOWER(po.stock_status),'') NOT IN ('out of stock','unavailable','หมด','สินค้าหมด')
              AND po.observation_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
              {region_clause}
        ), latest AS (SELECT * FROM ranked WHERE rn=1), item_count AS (
            SELECT COUNT(*) AS n FROM boq_items WHERE project_id=%s AND is_deleted=0
        )
        SELECT ps.source_name,ic.n AS eligible_lines,
               COUNT(DISTINCT l.item_id) AS covered_lines,
               SUM(l.quantity*l.price) AS covered_total,
               CASE WHEN ic.n=0 THEN 0 ELSE COUNT(DISTINCT l.item_id)/ic.n END AS coverage_ratio,
               CASE WHEN COUNT(DISTINCT l.item_id)=ic.n AND ic.n>0 THEN 1 ELSE 0 END AS full_coverage
        FROM price_sources ps CROSS JOIN item_count ic
        LEFT JOIN latest l ON l.source_id=ps.source_id
        WHERE ps.source_kind='retailer' AND ps.is_active=1
        GROUP BY ps.source_id,ps.source_name,ic.n
        ORDER BY full_coverage DESC,covered_total ASC,coverage_ratio DESC""", params)


def official_price_trends(project_id):
    return query("""WITH ranked AS (
        SELECT bi.item_id,m.canonical_name,po.price,po.period_year,po.period_month,
               ROW_NUMBER() OVER (PARTITION BY bi.item_id ORDER BY po.period_year DESC,po.period_month DESC) AS rn
        FROM boq_items bi JOIN materials m ON m.material_id=bi.material_id
        JOIN price_observations po ON po.material_id=m.material_id
        JOIN price_sources ps ON ps.source_id=po.source_id AND ps.source_kind='official'
        WHERE bi.project_id=%s AND bi.is_deleted=0 AND po.quality_status='valid'
          AND po.province_code=(SELECT province_code FROM boq_projects WHERE project_id=%s)
          AND po.period_year IS NOT NULL AND po.period_month IS NOT NULL
    ) SELECT item_id,canonical_name,price,period_year,period_month,rn
      FROM ranked WHERE rn<=2 ORDER BY item_id,rn""", (project_id, project_id))


def generate_insights(project_id):
    summary = project_summary(project_id)
    if not summary:
        raise ValueError(f"ไม่พบโครงการ {project_id}")
    top_cost = top_cost_items(project_id)
    offers = top_retail_prices_per_item(project_id)
    retailers = retailer_basket_comparison(project_id)
    trends = official_price_trends(project_id)

    full_baskets = [row for row in retailers if row["full_coverage"]]
    best_basket = full_baskets[0] if full_baskets else None
    top_3_retailers = []
    for rank, row in enumerate(full_baskets[:3], start=1):
        top_3_retailers.append({**row, "basket_rank": rank})
    baseline = summary["boq_cost"] or Decimal("0")
    savings = None
    savings_pct = None
    all_budgeted = int(summary["budgeted_count"] or 0) == int(summary["line_count"] or 0)
    if best_basket and baseline > 0 and all_budgeted:
        savings = baseline - (best_basket["covered_total"] or Decimal("0"))
        savings_pct = (savings / baseline * Decimal("100")) if baseline else None

    store_counts = {}
    for row in offers:
        store_counts[row["item_id"]] = store_counts.get(row["item_id"], 0) + 1

    actions = []
    unresolved = int(summary["line_count"] or 0) - int(summary["matched_count"] or 0)
    if unresolved:
        actions.append({"keyword": "VERIFY_SPEC", "priority": "สูง",
                        "evidence": f"มี {unresolved} รายการที่ยังจับคู่ไม่สำเร็จ",
                        "next_action": "ตรวจชื่อ เกรด ขนาด และหน่วย แล้วเลือกวัสดุที่ตรงจากรายการแนะนำก่อนใช้ราคา"})
    if summary["line_count"] and not all_budgeted:
        actions.append({"keyword": "ADD_BUDGET_BASELINE", "priority": "กลาง",
                        "evidence": f"มีราคา BOQ ครบ {summary['budgeted_count']}/{summary['line_count']} รายการ",
                        "next_action": "เติมราคาต่อหน่วยจาก BOQ ให้ครบก่อนคำนวณเปอร์เซ็นต์โอกาสประหยัด"})
    if summary.get("province_code") is None:
        actions.append({"keyword": "SET_LOCATION", "priority": "สูง",
                        "evidence": "โครงการยังไม่มีรหัสจังหวัดสำหรับกรองราคาในพื้นที่",
                        "next_action": "ระบุจังหวัดของไซต์งาน แล้วนำเข้าราคาหรือใบเสนอราคาที่จัดส่งถึงพื้นที่นั้น"})
    no_price = [item for item in top_cost if item.get("item_id") not in store_counts]
    if no_price:
        actions.append({"keyword": "REQUEST_QUOTES", "priority": "สูง",
                        "evidence": f"{len(no_price)} ในรายการต้นทุนสูงสุดยังไม่มีราคาจากร้านที่เทียบได้",
                        "next_action": "ขอใบเสนอราคาจากร้านที่ต้องการอย่างน้อย 3 แห่ง โดยระบุสเปก จำนวน พื้นที่ส่ง และ VAT"})
    if summary["line_count"] and not best_basket and not no_price:
        coverage = max((float(row["coverage_ratio"] or 0) for row in retailers), default=0)
        actions.append({"keyword": "COMPLETE_PRICE_COVERAGE", "priority": "สูง",
                        "evidence": f"ร้านที่ครอบคลุมมากที่สุดมีราคาเทียบได้ {coverage:.0%} ของรายการ BOQ",
                        "next_action": "เติม snapshot/ใบเสนอราคาสำหรับรายการที่ขาดให้ครบ ก่อนจัดอันดับยอดรวมร้านหรือคำนวณโอกาสประหยัด"})
    if top_cost:
        names = ", ".join(str(row["material_name"]) for row in top_cost[:3])
        actions.append({"keyword": "REVIEW_TOP_COST", "priority": "กลาง",
                        "evidence": f"รายการต้นทุนสูงสุด: {names}",
                        "next_action": "ทบทวนปริมาณและสเปกของ 3 รายการนี้ก่อนขอราคาหรืออนุมัติงบ"})
    rising = []
    by_item = {}
    for row in trends:
        by_item.setdefault(row["item_id"], []).append(row)
    for item_id, values in by_item.items():
        if len(values) == 2 and values[1]["price"] and values[0]["price"]:
            # rn=1 is most recent, rn=2 is previous period.
            newest, previous = values[0], values[1]
            if newest["price"] > previous["price"]:
                rising.append(newest["canonical_name"])
    if rising:
        actions.append({"keyword": "MONITOR_PRICE", "priority": "กลาง",
                        "evidence": "ราคาทางการล่าสุดสูงกว่ารอบก่อนของ " + ", ".join(rising[:3]),
                        "next_action": "ตรวจราคาซ้ำก่อนสั่งซื้อ และขอใบเสนอราคาที่มีวันหมดอายุชัดเจน"})
    if baseline and best_basket and savings is not None:
        if savings > 0:
            actions.append({"keyword": "VALIDATE_SAVING", "priority": "สูง",
                            "evidence": f"ตะกร้าร้านที่ครอบคลุมครบต่ำกว่า BOQ ประมาณ {savings:,.2f} บาท",
                            "next_action": "ยืนยันสเปก สต็อก ค่าขนส่ง และ VAT กับร้านก่อนนับเป็นงบที่ลดได้"})
        else:
            actions.append({"keyword": "REVIEW_BUDGET", "priority": "สูง",
                            "evidence": f"ตะกร้าร้านที่ครอบคลุมครบสูงกว่า BOQ ประมาณ {abs(savings):,.2f} บาท",
                            "next_action": "ตรวจราคาตั้งต้นและปริมาณ แล้วปรับงบหรือขอราคาใหม่ก่อนจัดซื้อ"})
    if not actions:
        actions.append({"keyword": "KEEP_MONITORING", "priority": "ต่ำ",
                        "evidence": "ยังไม่พบรายการที่เข้าเงื่อนไขแจ้งเตือน",
                        "next_action": "อัปเดตราคาและทบทวนผลเมื่อมี BOQ หรือข้อมูลร้านค้าเพิ่มเติม"})

    return {"project": summary, "top_cost_items": top_cost,
            "top_retail_offers": offers, "retailer_baskets": retailers,
            "top_3_retailers": top_3_retailers,
            "best_full_basket": best_basket, "estimated_savings": savings,
            "estimated_savings_pct": savings_pct, "official_trends": trends,
            "action_plan": actions}

"""Terminal and notebook-friendly display helpers (no Streamlit dependency)."""
from decimal import Decimal


def money(value):
    if value is None:
        return "N/A"
    return f"฿{Decimal(str(value)):,.2f}"


def _table(rows, columns):
    if not rows:
        return "(ไม่มีข้อมูลที่เข้าเงื่อนไข)"
    widths = [max(len(label), *(len(str(row.get(key, ""))) for row in rows)) for key, label in columns]
    header = " | ".join(label.ljust(widths[i]) for i, (_, label) in enumerate(columns))
    divider = "-+-".join("-" * width for width in widths)
    body = [" | ".join(str(row.get(key, "")).ljust(widths[i]) for i, (key, _) in enumerate(columns)) for row in rows]
    return "\n".join([header, divider, *body])


def print_dashboard(insight):
    project = insight["project"]
    print("\n" + "=" * 76)
    print(f"BOQ INTELLIGENCE DASHBOARD | {project['project_name']} (Project {project['project_id']})")
    print("=" * 76)
    print(f"พื้นที่: {project.get('province_name') or 'ไม่ระบุ'} | ขอบเขต: {project['scope_type']}")
    print(f"รายการ: {project['line_count']} | จับคู่แล้ว: {project['matched_count']}")
    print(f"ต้นทุน BOQ ที่มีราคาอ้างอิง: {money(project['boq_cost'])}")
    if insight["best_full_basket"]:
        best = insight["best_full_basket"]
        print(f"ตะกร้าร้านที่ครอบคลุมครบ: {best['source_name']} | {money(best['covered_total'])}")
        pct = insight["estimated_savings_pct"]
        pct_text = f"{pct:.2f}%" if pct is not None else "N/A"
        print(f"ส่วนต่างจาก BOQ โดยประมาณ: {money(insight['estimated_savings'])} ({pct_text})")
    else:
        print("ตะกร้าร้าน: ยังไม่มีร้านที่มีราคาครบทุกวัสดุที่จับคู่แล้ว จึงยังไม่สรุปยอดประหยัดรวม")

    print("\nเทียบราคา BOQ กับราคากลาง สนค. (Dataset 2, จังหวัดเดียวกัน, เดือนล่าสุด)")
    official = insight.get("official_summary")
    if official:
        pct = official["diff_pct"]
        direction = "สูงกว่า" if official["diff"] > 0 else "ต่ำกว่า"
        print(f"เทียบได้ {official['lines_compared']}/{official['lines_total']} รายการ | "
              f"BOQ {money(official['boq_cost'])} vs ราคากลาง {money(official['official_cost'])}")
        print(f"BOQ {direction}ราคากลาง {money(abs(official['diff']))}"
              f"{f' ({abs(pct):.1f}%)' if pct is not None else ''}")
        rows = [{"item_id": row["item_id"], "material": row["material_name"],
                 "boq": money(row["budget_unit_price"]), "official": money(row["official_unit_price"]),
                 "period": f"{row['period_year']}-{row['period_month']:02d}",
                 "diff": money(row["diff_vs_official"]),
                 "pct": f"{row['diff_pct']:+.1f}%" if row["diff_pct"] is not None else "N/A"}
                for row in insight["official_reference"] if row["budget_unit_price"] is not None][:5]
        print(_table(rows, [("item_id", "ID"), ("material", "วัสดุ"), ("boq", "BOQ/หน่วย"),
                            ("official", "ราคากลาง/หน่วย"), ("period", "เดือน"),
                            ("diff", "ส่วนต่างรวม"), ("pct", "%")]))
    else:
        print("(ยังไม่มีรายการที่มีทั้งราคา BOQ และราคากลางในจังหวัด/หน่วยเดียวกัน)")

    print("\nวัสดุ Top 3 ตามต้นทุน BOQ")
    top = []
    for row in insight["top_cost_items"]:
        top.append({"item_id": row["item_id"], "material_name": row["material_name"],
                    "qty": f"{row['quantity']} {row['input_unit']}",
                    "line_cost": money(row["boq_line_cost"]), "match": row["match_status"]})
    print(_table(top, [("item_id", "ID"), ("material_name", "วัสดุ"),
                       ("qty", "จำนวน"), ("line_cost", "ต้นทุน"), ("match", "จับคู่")]))

    print("\nร้าน Top 3 ต่อวัสดุ (เฉพาะราคาที่เทียบได้)")
    offers = []
    offer_counts = {}
    for row in insight["top_retail_offers"]:
        count = offer_counts.get(row["item_id"], 0)
        if count >= 3:
            continue
        offer_counts[row["item_id"]] = count + 1
        offers.append({"item_id": row["item_id"], "material": row["material_name"],
                       "store": row["source_name"], "price": money(row["price"]),
                       "unit": row["input_unit"], "date": row["observation_date"],
                       "branch": row["branch_name"] or row["province_name"] or "ไม่ระบุ"})
    print(_table(offers, [("item_id", "ID"), ("material", "วัสดุ"),
                          ("store", "ร้าน"), ("price", "ราคาต่อหน่วย"),
                          ("unit", "หน่วย"), ("date", "วันที่"), ("branch", "พื้นที่")]))

    print("\nร้าน Top 3 สำหรับ BOQ ทั้งตะกร้า (ต้องมีราคาครบทุกรายการ)")
    top3_rows = [{"rank": row["basket_rank"], "store": row["source_name"],
                  "total": money(row["covered_total"])}
                 for row in insight["top_3_retailers"]]
    print(_table(top3_rows, [("rank", "อันดับ"), ("store", "ร้าน"), ("total", "ยอดราคาสินค้า")]))
    if not top3_rows:
        print("ยังไม่มีร้านที่มีราคาเทียบได้ครบทุกบรรทัด จึงไม่จัดอันดับยอดรวม")
    print("\nCoverage ของร้านทั้งหมด (ยอดนี้ไม่ใช่ยอดรวมทั้ง BOQ หากข้อมูลไม่ครบ)")
    basket_rows = [{"store": row["source_name"],
                    "coverage": f"{row['covered_lines']}/{row['eligible_lines']}",
                    "covered_total": money(row["covered_total"]),
                    "rankable": "ใช่" if row["full_coverage"] else "ยังไม่ครบ"}
                   for row in insight["retailer_baskets"]]
    print(_table(basket_rows, [("store", "ร้าน"), ("coverage", "รายการครอบคลุม"),
                               ("covered_total", "ยอดที่มีราคา"), ("rankable", "จัดอันดับยอดรวม")]))

    print("\nAction Plan")
    for action in insight["action_plan"]:
        print(f"[{action['priority']}] {action['keyword']} — {action['evidence']}")
        print(f"    Next action: {action['next_action']}")
    print("\nหมายเหตุ: Top 3 ใช้ราคาที่ระบุว่ารวม VAT แล้วและตรงจังหวัด; ยอดตะกร้ายังไม่รวมค่าขนส่ง")
    print("ยอดประหยัดเป็นค่าประมาณ ต้องยืนยันสเปก สต็อก และค่าขนส่งกับร้านก่อนตัดสินใจ")

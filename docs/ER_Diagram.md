# ER Diagram - BOQ Intelligence Platform

Source of truth: `schema.sql`. Workbench model: `docs/boq_model.mwb`. Exported picture: `docs/er_diagram.png`.

![ER diagram](er_diagram.png)

```mermaid
erDiagram
    MASTER_PRODUCT ||--o| TPSO_PRICE : "TPSO detail (same id)"
    MASTER_PRODUCT ||--o| MATERIAL_PRICES_LONG : "retail detail (same id)"
    USER_INPUT_BATCH ||--o{ USER_INPUT_LINE : "has lines (deleted together)"
    MASTER_PRODUCT |o--o{ USER_INPUT_LINE : "reference price (optional)"

    MASTER_PRODUCT {
        int id PK
        enum source "TPSO or RETAIL"
        varchar store_name
        char commodity_code
        int item_id
        varchar category
        varchar product_name
        varchar unit
        decimal quantity
        decimal price
        varchar availability
        varchar price_basis
        varchar note
        char price_period
        date retrieved_date
    }
    TPSO_PRICE {
        int id PK, FK
        tinyint type
        varchar typeName
        varchar commodityCode
        varchar commodityNameTH
        varchar unitName
        tinyint curMonth
        smallint curYear
        decimal priceCur
        decimal priceVAT
        datetime createdAt
    }
    MATERIAL_PRICES_LONG {
        int id PK, FK
        int item_id
        varchar category
        varchar item_name
        varchar unit
        decimal quantity
        varchar store_name
        decimal price
        varchar availability
        varchar price_basis
        varchar note
        date retrieved_date
    }
    USER_INPUT_BATCH {
        int batch_id PK
        enum input_method "manual or csv"
        varchar project_name
        varchar file_name "required when csv"
        varchar created_by
        datetime created_at
        int total_rows
        int error_rows
        enum status
    }
    USER_INPUT_LINE {
        int line_id PK
        int batch_id FK
        int line_no "unique within batch"
        int product_id FK "optional"
        varchar item_name
        varchar unit
        decimal quantity "> 0"
        decimal unit_price ">= 0 or empty"
        varchar note
    }
```

`tpso_price` and `material_prices_long` use the same `id` as their `master_product` row (the foreign key is on the primary key), so each detail row belongs to exactly one master row. `user_input_line` holds the BOQ lines users enter in the GUI (`app_gui.py`), by hand or from CSV; users may create, edit and delete batches and lines, while the price tables stay read-only for them. `product_id` optionally links a line to a price for comparison.

> `er_diagram.png` and `boq_model.mwb` do not show `user_input_line` yet: add it in Workbench and re-export.

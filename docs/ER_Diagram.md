# ER Diagram - BOQ Intelligence Platform

Source of truth: `schema.sql`. Workbench model: `docs/boq_model.mwb`. Exported picture: `docs/er_diagram.png`.

![ER diagram](er_diagram.png)

```mermaid
erDiagram
    MASTER_PRODUCT ||--o| TPSO_PRICE : "TPSO detail (same id)"
    MASTER_PRODUCT ||--o| MATERIAL_PRICES_LONG : "retail detail (same id)"

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
```

`tpso_price` and `material_prices_long` use the same `id` as their `master_product` row (the foreign key is on the primary key), so each detail row belongs to exactly one master row. `user_input_batch` is not linked to the other tables yet.

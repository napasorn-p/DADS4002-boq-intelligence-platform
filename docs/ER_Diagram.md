# ER Diagram - BOQ Intelligence Platform MVP

The diagram separates canonical materials, price snapshots, sources, projects and matching evidence. A price comparison is eligible only when the canonical material, unit, specification, area and time window are compatible.

```mermaid
erDiagram
    PRICE_SOURCES ||--o{ PRICE_OBSERVATIONS : provides
    MATERIALS o|--o{ PRICE_OBSERVATIONS : identifies
    MATERIALS ||--o{ MATERIAL_ALIASES : has
    PRICE_SOURCES o|--o{ MATERIAL_ALIASES : names
    BOQ_PROJECTS ||--o{ PROJECT_ROOMS : contains
    BOQ_PROJECTS ||--o{ BOQ_ITEMS : includes
    PROJECT_ROOMS o|--o{ BOQ_ITEMS : groups
    MATERIALS o|--o{ BOQ_ITEMS : matches
    PRICE_OBSERVATIONS o|--o{ BOQ_ITEMS : selected_for
    BOQ_PROJECTS o|--o{ MATCH_EVENTS : creates
    BOQ_ITEMS o|--o{ MATCH_EVENTS : records
    MATERIALS o|--o{ MATCH_EVENTS : candidate
    PRICE_OBSERVATIONS o|--o{ MATCH_EVENTS : candidate_for

    PRICE_SOURCES {
        bigint source_id PK
        varchar source_name UK
        enum source_kind
        tinyint dataset_no
        varchar base_url
    }
    MATERIALS {
        bigint material_id PK
        varchar material_code UK
        varchar canonical_name
        varchar category_name
        varchar specification
        varchar standard_unit
    }
    MATERIAL_ALIASES {
        bigint alias_id PK
        bigint material_id FK
        bigint source_id FK
        varchar alias_text
        varchar alias_normalized
        varchar source_product_code
    }
    PRICE_OBSERVATIONS {
        bigint observation_id PK
        bigint source_id FK
        bigint material_id FK
        char source_record_hash
        date observation_date
        varchar province_code
        varchar unit
        decimal price
        boolean vat_included
        decimal shipping_fee
    }
    BOQ_PROJECTS {
        bigint project_id PK
        varchar project_name
        enum scope_type
        varchar province_code
        decimal budget_total
    }
    PROJECT_ROOMS {
        bigint room_id PK
        bigint project_id FK
        varchar room_name
        varchar floor_label "NOT NULL, default empty string"
    }
    BOQ_ITEMS {
        bigint item_id PK
        bigint project_id FK
        bigint room_id FK
        bigint material_id FK
        bigint chosen_observation_id FK
        varchar input_name
        decimal quantity
        varchar input_unit
        decimal budget_unit_price
        enum match_status
        boolean is_deleted
    }
    MATCH_EVENTS {
        bigint match_event_id PK
        bigint project_id FK
        bigint item_id FK
        bigint observation_id FK
        bigint candidate_material_id FK
        varchar match_method
        decimal confidence_score
        varchar decision_status
        json evidence_json
        datetime created_at
    }
```

`match_events` is the queryable evidence table. Every event is also appended to `logs/match_audit.jsonl`; events must not be overwritten.

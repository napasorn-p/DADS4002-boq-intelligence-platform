-- MySQL 8+ schema for BOQ Intelligence Platform MVP.
-- Data-source observations retain the original source and observation date.

CREATE DATABASE IF NOT EXISTS boq_intelligence
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE boq_intelligence;

CREATE TABLE IF NOT EXISTS price_sources (
    source_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_name VARCHAR(120) NOT NULL,
    source_kind ENUM('official','retailer','user_quote') NOT NULL,
    dataset_no TINYINT UNSIGNED NULL,
    base_url VARCHAR(500) NULL,
    collection_method VARCHAR(60) NOT NULL DEFAULT 'manual_snapshot',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (source_id),
    UNIQUE KEY uq_price_sources_name (source_name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS materials (
    material_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    material_code VARCHAR(64) NULL,
    canonical_name VARCHAR(255) NOT NULL,
    category_name VARCHAR(120) NULL,
    specification VARCHAR(255) NULL,
    standard_unit VARCHAR(40) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (material_id),
    UNIQUE KEY uq_material_code (material_code),
    KEY ix_material_name (canonical_name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS material_aliases (
    alias_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    material_id BIGINT UNSIGNED NOT NULL,
    source_id BIGINT UNSIGNED NULL,
    alias_text VARCHAR(255) NOT NULL,
    alias_normalized VARCHAR(255) NOT NULL,
    source_product_code VARCHAR(100) NULL,
    PRIMARY KEY (alias_id),
    KEY ix_alias_normalized (alias_normalized),
    KEY ix_alias_product_code (source_product_code),
    CONSTRAINT fk_alias_material FOREIGN KEY (material_id) REFERENCES materials(material_id),
    CONSTRAINT fk_alias_source FOREIGN KEY (source_id) REFERENCES price_sources(source_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS price_observations (
    observation_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_id BIGINT UNSIGNED NOT NULL,
    material_id BIGINT UNSIGNED NULL,
    source_record_hash CHAR(64) NOT NULL,
    source_product_code VARCHAR(100) NULL,
    product_name VARCHAR(255) NOT NULL,
    brand VARCHAR(120) NULL,
    specification VARCHAR(255) NULL,
    province_code VARCHAR(8) NULL,
    province_name VARCHAR(100) NULL,
    branch_name VARCHAR(150) NULL,
    observation_date DATE NOT NULL,
    period_year SMALLINT UNSIGNED NULL,
    period_month TINYINT UNSIGNED NULL,
    unit VARCHAR(40) NOT NULL,
    price DECIMAL(14,4) NOT NULL,
    regular_price DECIMAL(14,4) NULL,
    vat_included BOOLEAN NULL,
    shipping_fee DECIMAL(14,4) NULL,
    stock_status VARCHAR(40) NULL,
    promotion_label VARCHAR(255) NULL,
    product_url VARCHAR(1000) NULL,
    quality_status ENUM('valid','review','rejected') NOT NULL DEFAULT 'review',
    quality_note VARCHAR(500) NULL,
    raw_fields JSON NULL,
    retrieved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (observation_id),
    UNIQUE KEY uq_source_record_hash (source_id, source_record_hash),
    KEY ix_price_material_date (material_id, observation_date),
    KEY ix_price_source_date (source_id, observation_date),
    CONSTRAINT fk_price_source FOREIGN KEY (source_id) REFERENCES price_sources(source_id),
    CONSTRAINT fk_price_material FOREIGN KEY (material_id) REFERENCES materials(material_id),
    CONSTRAINT ck_price_nonnegative CHECK (price >= 0),
    CONSTRAINT ck_month_range CHECK (period_month IS NULL OR period_month BETWEEN 1 AND 12)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS boq_projects (
    project_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_name VARCHAR(200) NOT NULL,
    scope_type ENUM('house','room','item') NOT NULL,
    province_code VARCHAR(8) NULL,
    province_name VARCHAR(100) NULL,
    budget_total DECIMAL(16,2) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS project_rooms (
    room_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL,
    room_name VARCHAR(120) NOT NULL,
    floor_label VARCHAR(40) NULL,
    PRIMARY KEY (room_id),
    UNIQUE KEY uq_project_room (project_id, room_name, floor_label),
    CONSTRAINT fk_room_project FOREIGN KEY (project_id) REFERENCES boq_projects(project_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS boq_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL,
    room_id BIGINT UNSIGNED NULL,
    material_id BIGINT UNSIGNED NULL,
    source_row_no INT UNSIGNED NULL,
    source_product_code VARCHAR(100) NULL,
    input_name VARCHAR(255) NOT NULL,
    input_specification VARCHAR(255) NULL,
    quantity DECIMAL(14,4) NOT NULL,
    input_unit VARCHAR(40) NOT NULL,
    budget_unit_price DECIMAL(14,4) NULL,
    match_status ENUM('AUTO_MATCHED','USER_CONFIRMED','NEEDS_REVIEW','UNMATCHED') NOT NULL DEFAULT 'UNMATCHED',
    chosen_observation_id BIGINT UNSIGNED NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id),
    KEY ix_boq_project (project_id),
    KEY ix_boq_material (material_id),
    CONSTRAINT fk_boq_project FOREIGN KEY (project_id) REFERENCES boq_projects(project_id),
    CONSTRAINT fk_boq_room FOREIGN KEY (room_id) REFERENCES project_rooms(room_id),
    CONSTRAINT fk_boq_material FOREIGN KEY (material_id) REFERENCES materials(material_id),
    CONSTRAINT fk_boq_chosen_observation FOREIGN KEY (chosen_observation_id) REFERENCES price_observations(observation_id),
    CONSTRAINT ck_boq_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_boq_budget_nonnegative CHECK (budget_unit_price IS NULL OR budget_unit_price >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS match_events (
    match_event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NULL,
    item_id BIGINT UNSIGNED NULL,
    observation_id BIGINT UNSIGNED NULL,
    input_name VARCHAR(255) NOT NULL,
    input_specification VARCHAR(255) NULL,
    input_unit VARCHAR(40) NULL,
    candidate_material_id BIGINT UNSIGNED NULL,
    candidate_name VARCHAR(255) NULL,
    match_method VARCHAR(40) NOT NULL,
    confidence_score DECIMAL(6,5) NULL,
    decision_status VARCHAR(32) NOT NULL,
    evidence_json JSON NULL,
    actor VARCHAR(100) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_event_id),
    KEY ix_match_item_time (item_id, created_at),
    CONSTRAINT fk_match_project FOREIGN KEY (project_id) REFERENCES boq_projects(project_id),
    CONSTRAINT fk_match_item FOREIGN KEY (item_id) REFERENCES boq_items(item_id),
    CONSTRAINT fk_match_observation FOREIGN KEY (observation_id) REFERENCES price_observations(observation_id),
    CONSTRAINT fk_match_candidate FOREIGN KEY (candidate_material_id) REFERENCES materials(material_id)
) ENGINE=InnoDB;

INSERT INTO price_sources (source_name, source_kind, dataset_no, base_url, collection_method)
VALUES
 ('MOC Open Data CSI', 'official', 2, 'https://data.moc.go.th/OpenData/CSIProductIndexes', 'api'),
 ('Thai Watsadu', 'retailer', 5, 'https://www.thaiwatsadu.com/', 'manual_snapshot'),
 ('HomePro', 'retailer', 6, 'https://www.homepro.co.th/', 'manual_snapshot'),
 ('DoHome', 'retailer', NULL, 'https://www.dohome.co.th/', 'manual_snapshot'),
 ('Global House', 'retailer', NULL, 'https://globalhouse.co.th/', 'manual_snapshot'),
 ('Hiachet', 'retailer', NULL, 'https://www.hiachet.com/', 'quote_or_manual_snapshot')
ON DUPLICATE KEY UPDATE base_url = VALUES(base_url);

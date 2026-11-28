-- schema.sql
-- BOQ Intelligence Platform: database structure (MySQL 8.0.16+).
-- Source design: MySQL Workbench model docs/boq_model.mwb (ER diagram: docs/er_diagram.png).
--
-- Tables
--   master_product        one row per product price, from TPSO or a retail store
--   tpso_price            TPSO monthly price fields, 1:1 with master_product (same id)
--   material_prices_long  retail store prices, 1:1 with master_product (same id)
--   user_input_batch      one row per BOQ input session (manual entry or CSV upload)
--   user_input_line       one row per BOQ line in a batch (user-editable)
--
-- Structure only: this file holds no data. Safe to run again; existing tables are kept.
-- To rebuild from scratch: DROP DATABASE boq_intelligence; then run this file.

CREATE DATABASE IF NOT EXISTS boq_intelligence
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE boq_intelligence;

CREATE TABLE IF NOT EXISTS master_product (
  id int NOT NULL,
  source enum('TPSO','RETAIL') NOT NULL,
  store_name varchar(50) NOT NULL,
  commodity_code char(16) DEFAULT NULL,
  item_id int DEFAULT NULL,
  category varchar(100) DEFAULT NULL,
  product_name varchar(500) NOT NULL,
  unit varchar(30) NOT NULL,
  quantity decimal(12,2) DEFAULT NULL,
  price decimal(14,2) DEFAULT NULL,
  availability varchar(20) NOT NULL,
  price_basis varchar(40) DEFAULT NULL,
  note varchar(500) DEFAULT NULL,
  price_period char(7) NOT NULL,
  retrieved_date date DEFAULT NULL,
  PRIMARY KEY (id),
  KEY idx_commodity (commodity_code),
  KEY idx_item (item_id),
  KEY idx_store (store_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tpso_price (
  id int NOT NULL,
  type tinyint NOT NULL,
  typeName varchar(50) NOT NULL,
  commodityCode varchar(16) NOT NULL,
  commodityNameTH varchar(255) NOT NULL,
  unitName varchar(30) NOT NULL,
  curMonth tinyint NOT NULL,
  curYear smallint NOT NULL,
  priceCur decimal(14,2) NOT NULL,
  priceVAT decimal(14,2) DEFAULT NULL,
  createdAt datetime(6) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_commodity (commodityCode),
  CONSTRAINT fk_tpso_master FOREIGN KEY (id) REFERENCES master_product (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS material_prices_long (
  id int NOT NULL,
  item_id int NOT NULL,
  category varchar(100) NOT NULL,
  item_name varchar(255) NOT NULL,
  unit varchar(30) NOT NULL,
  quantity decimal(12,2) NOT NULL,
  store_name varchar(50) NOT NULL,
  price decimal(12,2) DEFAULT NULL,
  availability varchar(20) NOT NULL,
  price_basis varchar(40) DEFAULT NULL,
  note varchar(500) DEFAULT NULL,
  retrieved_date date DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_item_store (item_id, store_name),
  KEY idx_store (store_name),
  CONSTRAINT fk_retail_master FOREIGN KEY (id) REFERENCES master_product (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_input_batch (
  batch_id int NOT NULL AUTO_INCREMENT,
  input_method enum('manual','csv') NOT NULL,
  project_name varchar(150) DEFAULT NULL,
  file_name varchar(255) DEFAULT NULL,
  created_by varchar(100) NOT NULL,
  created_at datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  total_rows int NOT NULL DEFAULT 0,
  error_rows int NOT NULL DEFAULT 0,
  status enum('draft','validated','has_error','confirmed') NOT NULL DEFAULT 'draft',
  PRIMARY KEY (batch_id),
  CONSTRAINT chk_csv_file CHECK ((input_method <> 'csv') OR (file_name IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One row per BOQ line a user enters by hand or uploads in a CSV. Users may create,
-- edit and delete these rows (and their batch); the price tables above are read-only
-- for them. product_id optionally links the line to a price in master_product.
CREATE TABLE IF NOT EXISTS user_input_line (
  line_id int NOT NULL AUTO_INCREMENT,
  batch_id int NOT NULL,
  line_no int NOT NULL,
  product_id int DEFAULT NULL,
  item_name varchar(255) NOT NULL,
  unit varchar(30) NOT NULL,
  quantity decimal(12,2) NOT NULL,
  unit_price decimal(14,2) DEFAULT NULL,
  note varchar(500) DEFAULT NULL,
  PRIMARY KEY (line_id),
  UNIQUE KEY uq_batch_line (batch_id, line_no),
  KEY idx_product (product_id),
  CONSTRAINT fk_line_batch FOREIGN KEY (batch_id) REFERENCES user_input_batch (batch_id) ON DELETE CASCADE,
  CONSTRAINT fk_line_product FOREIGN KEY (product_id) REFERENCES master_product (id),
  CONSTRAINT chk_line_quantity CHECK (quantity > 0),
  CONSTRAINT chk_line_price CHECK (unit_price IS NULL OR unit_price >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Synthetic PostgreSQL schema for testing the schemahand parser.
-- 12 tables, 15 foreign keys, 2 schemas (app, audit), table + column comments.
-- Every value below is made up. No real business appears here.

CREATE SCHEMA app;
CREATE SCHEMA audit;

CREATE TABLE app.customers (
    id            INTEGER PRIMARY KEY,
    "full_name"   VARCHAR(120) NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at    TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

COMMENT ON TABLE app.customers IS 'People and companies who buy from us.';
COMMENT ON COLUMN app.customers.email IS 'Unique email address used for login.';

CREATE TABLE app.addresses (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES app.customers(id),
    line1         VARCHAR(200) NOT NULL,
    city          VARCHAR(80) NOT NULL,
    postal_code   VARCHAR(20)
);

CREATE TABLE app.categories (
    id                  INTEGER PRIMARY KEY,
    name                VARCHAR(80) NOT NULL,
    parent_category_id  INTEGER,
    CONSTRAINT fk_categories_parent FOREIGN KEY (parent_category_id)
        REFERENCES app.categories (id)
);

CREATE TABLE app.suppliers (
    id       INTEGER PRIMARY KEY,
    name     VARCHAR(120) NOT NULL,
    active   BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE app.products (
    id            INTEGER PRIMARY KEY,
    sku           VARCHAR(40) NOT NULL UNIQUE,
    name          VARCHAR(150) NOT NULL,
    price         NUMERIC(10,2) NOT NULL DEFAULT 0,
    category_id   INTEGER,
    supplier_id   INTEGER REFERENCES app.suppliers(id),
    CHECK (price >= 0),
    CONSTRAINT fk_products_category FOREIGN KEY (category_id)
        REFERENCES app.categories (id)
);

COMMENT ON TABLE app.products IS 'Items we sell to customers.';

CREATE TABLE app.orders (
    id                   INTEGER PRIMARY KEY,
    customer_id          INTEGER NOT NULL,
    billing_address_id   INTEGER REFERENCES app.addresses(id),
    shipping_address_id  INTEGER REFERENCES app.addresses(id),
    order_date           DATE NOT NULL DEFAULT now(),
    total_amount         NUMERIC(12,2) NOT NULL DEFAULT 0,
    CHECK (total_amount >= 0),
    FOREIGN KEY (customer_id) REFERENCES app.customers (id)
);

CREATE TABLE app.order_items (
    order_id     INTEGER NOT NULL,
    product_id   INTEGER NOT NULL REFERENCES app.products(id),
    quantity     INTEGER NOT NULL DEFAULT 1,
    unit_price   NUMERIC(10,2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES app.orders (id)
);

CREATE TABLE app.payments (
    id           INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES app.orders(id),
    amount       NUMERIC(12,2) NOT NULL,
    method       VARCHAR(30) NOT NULL DEFAULT 'card',
    paid_at      TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE app.invoices (
    id            INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL,
    customer_id   INTEGER NOT NULL,
    issued_at     TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    total_amount  NUMERIC(12,2) NOT NULL
);

ALTER TABLE app.invoices
    ADD CONSTRAINT fk_invoices_order FOREIGN KEY (order_id)
        REFERENCES app.orders (id) ON DELETE CASCADE;

ALTER TABLE app.invoices
    ADD CONSTRAINT fk_invoices_customer FOREIGN KEY (customer_id)
        REFERENCES app.customers (id);

CREATE TABLE app.inventory (
    id            INTEGER PRIMARY KEY,
    product_id    INTEGER NOT NULL REFERENCES app.products(id),
    warehouse     VARCHAR(60) NOT NULL,
    quantity_on_hand INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE "audit"."login_events" (
    id             INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL,
    "user_agent"   TEXT,
    happened_at    TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

COMMENT ON COLUMN audit.login_events.user_agent IS 'Raw browser string, kept only for fraud checks.';

CREATE TABLE audit.change_log (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL,
    table_name    VARCHAR(60) NOT NULL,
    changed_at    TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

ALTER TABLE audit.login_events
    ADD CONSTRAINT fk_login_events_customer FOREIGN KEY (customer_id)
        REFERENCES app.customers (id);

ALTER TABLE audit.change_log
    ADD CONSTRAINT fk_change_log_customer FOREIGN KEY (customer_id)
        REFERENCES app.customers (id);

CREATE INDEX idx_orders_customer ON app.orders (customer_id);

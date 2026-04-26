# Entity Schema: order-service

> Auto-generated from SQLAlchemy models on 2026-04-26 00:15 UTC. Do not edit manually.

---

## Table: `admin_users`

| Column | Type | Nullable | PK | FK |
|---|---|---|---|---|
| `id` | `CHAR(32)` | NO | PK |  |
| `tenant_id` | `CHAR(32)` | NO |  |  |
| `email` | `VARCHAR(254)` | NO |  |  |
| `password_hash` | `VARCHAR(255)` | NO |  |  |
| `role` | `VARCHAR(30)` | NO |  |  |
| `totp_secret` | `VARCHAR(100)` | YES |  |  |
| `is_active` | `BOOLEAN` | NO |  |  |
| `created_at` | `DATETIME` | NO |  |  |
| `updated_at` | `DATETIME` | NO |  |  |

**Constraints:**
- UNIQUE (`tenant_id`, `email`) (uq_admin_users_tenant_email)
- CHECK `role IN ('merchant_owner', 'merchant_admin', 'merchant_viewer', 'merchant_support')` (ck_admin_users_role)

---

## Table: `guest_sessions`

| Column | Type | Nullable | PK | FK |
|---|---|---|---|---|
| `id` | `CHAR(32)` | NO | PK |  |
| `tenant_id` | `CHAR(32)` | NO |  |  |
| `token` | `VARCHAR(255)` | NO |  |  |
| `expires_at` | `DATETIME` | NO |  |  |
| `created_at` | `DATETIME` | NO |  |  |

**Constraints:**
- UNIQUE (`token`)

**Indexes:**
- `idx_guest_sessions_expires`: (`expires_at`)
- `idx_guest_sessions_token`: UNIQUE (`token`)

---

## Table: `orders`

| Column | Type | Nullable | PK | FK |
|---|---|---|---|---|
| `id` | `CHAR(32)` | NO | PK |  |
| `tenant_id` | `CHAR(32)` | NO |  |  |
| `reference` | `VARCHAR(30)` | NO |  |  |
| `status` | `VARCHAR(20)` | NO |  |  |
| `customer_id` | `CHAR(32)` | YES |  |  |
| `guest_email` | `VARCHAR(254)` | YES |  |  |
| `shipping_address` | `JSONB` | NO |  |  |
| `shipping_method_id` | `CHAR(32)` | NO |  |  |
| `shipping_cost_minor` | `INTEGER` | NO |  |  |
| `subtotal_minor` | `INTEGER` | NO |  |  |
| `tax_minor` | `INTEGER` | NO |  |  |
| `total_minor` | `INTEGER` | NO |  |  |
| `notification_id` | `CHAR(32)` | YES |  |  |
| `notification_status` | `VARCHAR(20)` | YES |  |  |
| `payment_intent_id` | `VARCHAR(100)` | YES |  |  |
| `idempotency_key` | `VARCHAR(64)` | YES |  |  |
| `created_at` | `DATETIME` | NO |  |  |
| `updated_at` | `DATETIME` | NO |  |  |

**Constraints:**
- UNIQUE (`tenant_id`, `idempotency_key`) (uq_orders_tenant_idempotency_key)
- UNIQUE (`tenant_id`, `reference`) (uq_orders_tenant_reference)
- CHECK `customer_id IS NOT NULL OR guest_email IS NOT NULL` (ck_orders_customer_or_guest)

**Indexes:**
- `idx_orders_guest_email`: (`guest_email`)
- `idx_orders_tenant_status`: (`tenant_id`, `status`)

**Relationships:**
- `lines` → `order_lines` (one-to-many)

---

## Table: `shipping_methods`

| Column | Type | Nullable | PK | FK |
|---|---|---|---|---|
| `id` | `CHAR(32)` | NO | PK |  |
| `tenant_id` | `CHAR(32)` | NO |  |  |
| `name` | `VARCHAR(100)` | NO |  |  |
| `description` | `VARCHAR(500)` | YES |  |  |
| `cost_minor` | `INTEGER` | NO |  |  |
| `estimated_days_min` | `INTEGER` | YES |  |  |
| `estimated_days_max` | `INTEGER` | YES |  |  |
| `is_active` | `BOOLEAN` | NO |  |  |
| `created_at` | `DATETIME` | NO |  |  |
| `updated_at` | `DATETIME` | NO |  |  |

**Constraints:**
- UNIQUE (`tenant_id`, `name`) (uq_shipping_methods_tenant_name)
- CHECK `cost_minor >= 0` (ck_shipping_methods_cost_minor)

---

## Table: `order_lines`

| Column | Type | Nullable | PK | FK |
|---|---|---|---|---|
| `id` | `CHAR(32)` | NO | PK |  |
| `order_id` | `CHAR(32)` | NO |  | `orders.id` ON DELETE CASCADE |
| `sku_id` | `CHAR(32)` | NO |  |  |
| `product_name` | `VARCHAR(200)` | NO |  |  |
| `variant_label` | `VARCHAR(200)` | YES |  |  |
| `quantity` | `INTEGER` | NO |  |  |
| `unit_price_minor` | `INTEGER` | NO |  |  |
| `subtotal_minor` | `INTEGER` | NO |  |  |

**Constraints:**
- CHECK `quantity >= 1` (ck_order_lines_quantity)
- CHECK `unit_price_minor >= 0` (ck_order_lines_unit_price)

**Indexes:**
- `idx_order_lines_order_id`: (`order_id`)

**Relationships:**
- `order` → `orders` (many-to-one)

---

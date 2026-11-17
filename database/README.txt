ShopSphere SQLite Database
==========================

The application stores its database in ShopSphere/shopsphere.db.
It is created automatically when you run: py app.py

SQLite features enabled:
- Foreign key enforcement
- WAL journal mode for improved concurrent reads/writes
- 15-second busy timeout
- Indexed customer/order/product lookups
- Parameterized SQL queries
- Password hashes (Werkzeug), never plaintext passwords
- Safe additive schema initialization (existing records are preserved)

Tables:
users                 Customer and administrator accounts
products              Product catalogue and current stock
cart_items            Per-customer shopping cart
orders                Order header, delivery and payment selection
order_items           Immutable product/price/quantity snapshot per order
payment_records       Payment method and demo/payment state (no real payment)
inventory_movements   Stock adjustment audit trail
order_status_history  Order status timeline

Admin tools:
Sign in as an admin, then open Admin > Database.
The page shows record counts and recent stock/order activity.
Use Download database backup to create a consistent SQLite backup.

Backup advice:
Keep dated backups outside the project folder too. Never edit shopsphere.db
while the Flask app is running. To restore, stop Flask and replace the database
file with a known-good backup.

Demo payment note:
Cash on Delivery and Demo E-Wallet are records for a school project only.
No real payment is collected or processed.

SHOPSPHERE: E-COMMERCE ORDER PROCESSING AND INVENTORY MANAGEMENT SYSTEM
=======================================================================

PROJECT STRUCTURE
- app.py
- database/
- static/css/
- static/js/
- templates/
- uploads/
- requirements.txt

REQUIREMENTS
- Python 3.10+
- Flask 3.x
- SQLite (included with Python's sqlite3 module; no separate Python package needed)

RUN ON WINDOWS (PowerShell)
1. Open this folder in VS Code.
2. Open Terminal > New Terminal.
3. Create a virtual environment:
   py -m venv venv
4. Activate it:
   .\venv\Scripts\Activate.ps1
   If PowerShell blocks activation, run:
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\venv\Scripts\Activate.ps1
5. Install packages:
   py -m pip install -r requirements.txt
6. Start the app:
   py app.py
7. Open http://127.0.0.1:5000

DATABASE
- The SQLite database file shopsphere.db is created automatically beside app.py
  the first time the application starts.
- Tables are initialized automatically, with sample products and a demo admin.
- The admin Database Management page includes table counts, SQLite integrity
  check, foreign-key check, inventory activity, order-status history, and backup.
- Database backups are generated using SQLite's online backup API.
- To reset the demo database, stop the server and delete shopsphere.db, then run
  py app.py again. This permanently deletes local demo accounts, products, carts,
  and orders. Back up first if you need the records.

DEMO ADMIN
Email: admin@shopsphere.com
Password: Admin123!
If this email already exists in an older database, its existing password is kept.

IMPROVEMENTS INCLUDED
- Catalog filters: keyword, category, minimum/maximum price, and sorting.
- Admin dashboard: pending orders, delivered revenue, low-stock and out-of-stock alerts.
- Safer quantity validation for cart actions.
- Transaction-protected customer/admin order cancellation and stock restoration.
- Session cookie protections (HttpOnly and SameSite=Lax).
- Database integrity and foreign-key checks in admin database management.
- Existing hashed passwords, parameterized SQL, CSRF form tokens, and role checks retained.

FEATURES
- Customer registration and login (hashed passwords)
- Product catalog, search, category and price filters, sorting, quick view
- Wishlist (browser-local convenience feature)
- Shopping cart with stock validation
- Checkout with contact number, delivery address, and demo payment selection
- Transaction-safe order creation, unique order number, and automatic stock deduction
- Customer order history, order detail receipt, visual status tracking, and pending-order cancellation
- Admin order fulfillment workflow and stock restoration on cancellation
- Inventory management with stock movement audit trail and low-stock visibility
- SQLite foreign keys, indexes, parameterized SQL, CSRF form tokens, and backup

NOTE
Checkout is a school/demo workflow and does not collect real payments.
Set a strong SECRET_KEY environment variable and use HTTPS with COOKIE_SECURE=1
before deploying beyond a local classroom demonstration. Do not use the demo admin
password in a real deployment.

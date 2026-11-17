import os
import secrets
import sqlite3
from functools import wraps
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, g, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "shopsphere-dev-key-change-before-deployment")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "shopsphere.db")


# -------------------- DATABASE --------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 15000")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE, timeout=15)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 15000")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer'
                CHECK(role IN ('customer', 'admin')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'General',
            price REAL NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            image_url TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            UNIQUE(user_id, product_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            total REAL NOT NULL CHECK(total >= 0),
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled')),
            shipping_address TEXT NOT NULL,
            contact_number TEXT NOT NULL DEFAULT '',
            payment_method TEXT NOT NULL DEFAULT 'Cash on Delivery',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            unit_price REAL NOT NULL CHECK(unit_price >= 0),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_cart_user ON cart_items(user_id);

        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            change_amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            reference TEXT NOT NULL DEFAULT '',
            actor_user_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL,
            FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS order_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by INTEGER,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY(changed_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS payment_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            method TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            status TEXT NOT NULL DEFAULT 'Pending',
            reference TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS product_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, product_id, order_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
        CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory_movements(product_id);
        CREATE INDEX IF NOT EXISTS idx_status_order ON order_status_history(order_id);
        CREATE INDEX IF NOT EXISTS idx_reviews_product ON product_reviews(product_id);
        CREATE INDEX IF NOT EXISTS idx_reviews_user ON product_reviews(user_id);
    """)

    # Safe schema upgrades for databases created by earlier ShopSphere versions.
    order_columns = {row[1] for row in db.execute('PRAGMA table_info(orders)').fetchall()}
    if 'contact_number' not in order_columns:
        db.execute("ALTER TABLE orders ADD COLUMN contact_number TEXT NOT NULL DEFAULT ''")
    if 'payment_method' not in order_columns:
        db.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Cash on Delivery'")

    # Create the demo administrator only if the email does not already exist.
    admin = db.execute("SELECT id FROM users WHERE email = ?", ("admin@shopsphere.com",)).fetchone()
    if admin is None:
        db.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("ShopSphere Admin", "admin@shopsphere.com",
             generate_password_hash("Admin123!"), "admin")
        )

    product_count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if product_count == 0:
        sample_products = [
            ("Wireless Headphones", "Comfortable wireless headphones with clear sound.", "Electronics", 1299.00, 18, "https://images.unsplash.com/photo-150,"),
            ("Smart Watch", "Everyday smart watch for notifications and activity.", "Electronics", 1899.00, 12, "https://images.unsplash.com/photo-1523275335684-37898b6baf30"),
            ("Backpack", "Durable backpack for school, work, and travel.", "Accessories", 899.00, 25, "https://images.unsplash.com/photo-1553062407-98eeb64c6a62"),
            ("Running Shoes", "Lightweight shoes designed for daily comfort.", "Fashion", 2199.00, 14, "https://images.unsplash.com/photo-1542291026-7eec264c27ff"),
            ("Desk Lamp", "Modern LED desk lamp for study spaces.", "Home", 649.00, 30, "https://images.unsplash.com/photo-150.",),
            ("Water Bottle", "Reusable stainless bottle for daily hydration.", "Lifestyle", 399.00, 40, "https://images.unsplash.com/photo-1602143407151-7111542de6e8"),
        ]
        sample_products[0] = ("Wireless Headphones", "Comfortable wireless headphones with clear sound.", "Electronics", 1299.00, 18, "https://images.unsplash.com/photo-1505740420928-5e560c06d30e")
        sample_products[4] = ("Desk Lamp", "Modern LED desk lamp for study spaces.", "Home", 649.00, 30, "https://images.unsplash.com/photo-1507473885765-e6ed057f782c")
        db.executemany(
            "INSERT INTO products (name, description, category, price, stock, image_url) VALUES (?, ?, ?, ?, ?, ?)",
            sample_products
        )

    # Backfill audit rows for existing stock without changing any current quantities.
    db.execute("""INSERT INTO inventory_movements (product_id, change_amount, reason, reference)
                  SELECT p.id, p.stock, 'Opening balance', 'Database initialization'
                  FROM products p
                  WHERE p.stock > 0 AND NOT EXISTS
                    (SELECT 1 FROM inventory_movements m WHERE m.product_id = p.id)""")
    db.commit()
    db.close()


def record_stock_change(db, product_id, change_amount, reason, reference=''):
    """Record a stock adjustment in the same transaction as the stock update."""
    db.execute("""INSERT INTO inventory_movements
                  (product_id, change_amount, reason, reference, actor_user_id)
                  VALUES (?, ?, ?, ?, ?)""",
               (product_id, change_amount, reason, reference, session.get('user_id')))


# -------------------- SECURITY / HELPERS --------------------

def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(24)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        sent = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, description="Your form session expired. Please go back, refresh, and try again.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in as an administrator.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def cart_details(user_id):
    return get_db().execute("""
        SELECT c.id, c.quantity, p.id AS product_id, p.name, p.price,
               p.stock, p.image_url, (c.quantity * p.price) AS subtotal
        FROM cart_items c
        JOIN products p ON p.id = c.product_id
        WHERE c.user_id = ? AND p.active = 1
        ORDER BY c.id DESC
    """, (user_id,)).fetchall()


@app.context_processor
def inject_globals():
    count = 0
    if session.get("user_id"):
        row = get_db().execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM cart_items WHERE user_id = ?",
            (session["user_id"],)
        ).fetchone()
        count = row[0] if row else 0
    return {"cart_count": count, "current_year": datetime.now().year}


# -------------------- CUSTOMER ROUTES --------------------

@app.route("/")
def home():
    db = get_db()
    query = request.args.get("q", "").strip()[:100]
    category = request.args.get("category", "").strip()[:60]
    sort = request.args.get("sort", "newest")
    min_price = request.args.get("min_price", "").strip()
    max_price = request.args.get("max_price", "").strip()
    sql = "SELECT * FROM products WHERE active = 1"
    params = []
    if query:
        sql += " AND (name LIKE ? OR description LIKE ? OR category LIKE ?)"
        term = f"%{query}%"
        params.extend([term, term, term])
    if category:
        sql += " AND category = ?"
        params.append(category)
    try:
        if min_price:
            sql += " AND price >= ?"
            params.append(max(0, float(min_price)))
        if max_price:
            sql += " AND price <= ?"
            params.append(max(0, float(max_price)))
    except ValueError:
        flash("Price filters must contain valid numbers.", "warning")
        min_price = max_price = ""
    sort_options = {
        "newest": "p.created_at DESC, p.id DESC",
        "price_asc": "p.price ASC, p.name COLLATE NOCASE ASC",
        "price_desc": "p.price DESC, p.name COLLATE NOCASE ASC",
        "name": "p.name COLLATE NOCASE ASC",
        "stock": "p.stock DESC, p.name COLLATE NOCASE ASC",
    }
    sql += " ORDER BY " + sort_options.get(sort, sort_options["newest"])
    sql = sql.replace("SELECT * FROM products WHERE active = 1", "SELECT p.*, COALESCE(AVG(r.rating), 0) AS average_rating, COUNT(r.id) AS review_count FROM products p LEFT JOIN product_reviews r ON r.product_id = p.id WHERE p.active = 1")
    sql = sql.replace("name LIKE ? OR description LIKE ? OR category LIKE ?", "p.name LIKE ? OR p.description LIKE ? OR p.category LIKE ?")
    sql = sql.replace("category = ?", "p.category = ?").replace("price >= ?", "p.price >= ?").replace("price <= ?", "p.price <= ?")
    sql = sql.replace(" ORDER BY ", " GROUP BY p.id ORDER BY ")
    products = db.execute(sql, params).fetchall()
    categories = db.execute(
        "SELECT DISTINCT category FROM products WHERE active = 1 ORDER BY category"
    ).fetchall()
    return render_template("shop.html", products=products, categories=categories,
                           search=query, selected_category=category, sort=sort,
                           min_price=min_price, max_price=max_price)


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = get_db().execute(
        "SELECT * FROM products WHERE id = ? AND active = 1", (product_id,)
    ).fetchone()
    if not product:
        abort(404)
    db = get_db()
    rating_summary = db.execute(
        "SELECT COALESCE(AVG(rating), 0) AS average_rating, COUNT(*) AS review_count FROM product_reviews WHERE product_id = ?",
        (product_id,)
    ).fetchone()
    reviews = db.execute(
        "SELECT r.*, u.full_name FROM product_reviews r JOIN users u ON u.id = r.user_id WHERE r.product_id = ? ORDER BY r.created_at DESC",
        (product_id,)
    ).fetchall()
    eligible_orders = []
    if session.get("user_id"):
        eligible_orders = db.execute("""
            SELECT o.id, o.order_number FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            WHERE o.user_id = ? AND o.status = 'Delivered' AND oi.product_id = ?
              AND NOT EXISTS (SELECT 1 FROM product_reviews r WHERE r.order_id = o.id AND r.product_id = ? AND r.user_id = o.user_id)
            ORDER BY o.id DESC
        """, (session["user_id"], product_id, product_id)).fetchall()
    return render_template("product_detail.html", product=product,
                           rating_summary=rating_summary, reviews=reviews,
                           eligible_orders=eligible_orders)


@app.route("/product/<int:product_id>/review", methods=["POST"])
@login_required
def submit_review(product_id):
    db = get_db()
    try:
        rating = int(request.form.get("rating", "0"))
        order_id = int(request.form.get("order_id", "0"))
    except ValueError:
        flash("Please select a valid rating and delivered order.", "warning")
        return redirect(url_for("product_detail", product_id=product_id))
    comment = request.form.get("comment", "").strip()[:1000]
    if rating < 1 or rating > 5:
        flash("Please choose a rating from 1 to 5 stars.", "warning")
        return redirect(url_for("product_detail", product_id=product_id))
    eligible = db.execute("""
        SELECT o.id FROM orders o JOIN order_items oi ON oi.order_id = o.id
        WHERE o.id = ? AND o.user_id = ? AND o.status = 'Delivered' AND oi.product_id = ?
    """, (order_id, session["user_id"], product_id)).fetchone()
    if not eligible:
        abort(403)
    try:
        db.execute("INSERT INTO product_reviews (user_id, product_id, order_id, rating, comment) VALUES (?, ?, ?, ?, ?)",
                   (session["user_id"], product_id, order_id, rating, comment))
        db.commit()
        flash("Thank you! Your verified product review has been published.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("You have already reviewed this product for that order.", "warning")
    return redirect(url_for("product_detail", product_id=product_id) + "#reviews")


@app.route("/product/<int:product_id>/review/<int:review_id>/delete", methods=["POST"])
@login_required
def delete_review(product_id, review_id):
    db = get_db()
    result = db.execute("DELETE FROM product_reviews WHERE id = ? AND product_id = ? AND user_id = ?",
                        (review_id, product_id, session["user_id"]))
    db.commit()
    flash("Your review was deleted." if result.rowcount else "Review not found.", "success" if result.rowcount else "warning")
    return redirect(url_for("product_detail", product_id=product_id) + "#reviews")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name and email, and use a password with at least 8 characters.", "danger")
            return render_template("register.html")
        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password))
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("That email is already registered. Please log in.", "danger")
            return render_template("register.html")
        session.clear()
        session["user_id"] = cursor.lastrowid
        session["full_name"] = name
        session["role"] = "customer"
        flash("Your account has been created.", "success")
        return redirect(url_for("home"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash("Welcome back!", "success")
            return redirect(url_for("admin_dashboard") if user["role"] == "admin" else url_for("home"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/cart")
@login_required
def cart():
    items = cart_details(session["user_id"])
    total = sum(item["subtotal"] for item in items)
    return render_template("cart.html", items=items, total=total)


@app.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    db = get_db()
    product = db.execute(
        "SELECT id, stock, active FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if not product or not product["active"]:
        abort(404)
    try:
        quantity = int(request.form.get("quantity", 1))
    except (TypeError, ValueError):
        flash("Please enter a valid quantity.", "danger")
        return redirect(request.referrer or url_for("home"))
    if quantity < 1 or quantity > 99:
        flash("Quantity must be between 1 and 99.", "danger")
        return redirect(request.referrer or url_for("home"))
    existing = db.execute(
        "SELECT quantity FROM cart_items WHERE user_id = ? AND product_id = ?",
        (session["user_id"], product_id)
    ).fetchone()
    already = existing["quantity"] if existing else 0
    if already + quantity > product["stock"]:
        flash("There is not enough stock for that quantity.", "danger")
    elif existing:
        db.execute(
            "UPDATE cart_items SET quantity = ? WHERE user_id = ? AND product_id = ?",
            (already + quantity, session["user_id"], product_id)
        )
        db.commit()
        flash("Cart updated.", "success")
    else:
        db.execute(
            "INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)",
            (session["user_id"], product_id, quantity)
        )
        db.commit()
        flash("Product added to cart.", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def update_cart(item_id):
    db = get_db()
    item = db.execute("""
        SELECT c.id, c.product_id, p.stock FROM cart_items c
        JOIN products p ON p.id = c.product_id
        WHERE c.id = ? AND c.user_id = ?
    """, (item_id, session["user_id"])).fetchone()
    if not item:
        abort(404)
    try:
        quantity = int(request.form.get("quantity", 1))
    except (TypeError, ValueError):
        flash("Please enter a valid quantity.", "danger")
        return redirect(url_for("cart"))
    if quantity < 1:
        db.execute("DELETE FROM cart_items WHERE id = ? AND user_id = ?", (item_id, session["user_id"]))
    elif quantity > item["stock"]:
        flash("Requested quantity exceeds available stock.", "danger")
    else:
        db.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (quantity, item_id))
    db.commit()
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def remove_cart_item(item_id):
    db = get_db()
    db.execute("DELETE FROM cart_items WHERE id = ? AND user_id = ?", (item_id, session["user_id"]))
    db.commit()
    flash("Item removed from cart.", "success")
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    db = get_db()
    items = cart_details(session["user_id"])
    if not items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("home"))
    total = sum(item["subtotal"] for item in items)
    if request.method == "POST":
        address = request.form.get("shipping_address", "").strip()
        contact_number = request.form.get("contact_number", "").strip()
        payment_method = request.form.get("payment_method", "Cash on Delivery").strip()
        allowed_payments = {"Cash on Delivery", "Demo E-Wallet (no real charge)"}
        if len(address) < 8 or len(contact_number) < 7 or payment_method not in allowed_payments:
            flash("Enter a complete address, a valid contact number, and choose a payment method.", "danger")
            return render_template("checkout.html", items=items, total=total)
        try:
            db.execute("BEGIN IMMEDIATE")
            # Recheck stock inside the transaction to avoid overselling.
            for item in items:
                current = db.execute(
                    "SELECT stock, active FROM products WHERE id = ?", (item["product_id"],)
                ).fetchone()
                if not current or not current["active"] or current["stock"] < item["quantity"]:
                    raise ValueError(f"Not enough stock for {item['name']}.")
            order_number = "SS-" + secrets.token_hex(4).upper()
            cursor = db.execute(
                "INSERT INTO orders (order_number, user_id, total, shipping_address, contact_number, payment_method) VALUES (?, ?, ?, ?, ?, ?)",
                (order_number, session["user_id"], total, address, contact_number, payment_method)
            )
            order_id = cursor.lastrowid
            for item in items:
                db.execute("""
                    INSERT INTO order_items (order_id, product_id, product_name, unit_price, quantity)
                    VALUES (?, ?, ?, ?, ?)
                """, (order_id, item["product_id"], item["name"], item["price"], item["quantity"]))
                db.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?",
                    (item["quantity"], item["product_id"])
                )
                record_stock_change(db, item["product_id"], -item["quantity"],
                                    "Customer checkout", order_number)
            db.execute("DELETE FROM cart_items WHERE user_id = ?", (session["user_id"],))
            db.execute("INSERT INTO payment_records (order_id, method, amount, status) VALUES (?, ?, ?, ?)",
                       (order_id, payment_method, total, "Pending" if payment_method == "Cash on Delivery" else "Demo - Not Charged"))
            db.execute("INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, note) VALUES (?, NULL, 'Pending', ?, 'Order placed')",
                       (order_id, session["user_id"]))
            db.commit()
        except ValueError as error:
            db.rollback()
            flash(str(error), "danger")
            return redirect(url_for("cart"))
        except sqlite3.Error:
            db.rollback()
            flash("Checkout could not be completed. Please try again.", "danger")
            return redirect(url_for("cart"))
        flash(f"Order {order_number} placed successfully!", "success")
        return redirect(url_for("order_detail", order_id=order_id))
    return render_template("checkout.html", items=items, total=total)


@app.route("/orders")
@login_required
def orders():
    rows = get_db().execute(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    return render_template("orders.html", orders=rows)


@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = get_db().execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, session["user_id"])
    ).fetchone()
    if not order:
        abort(404)
    items = get_db().execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    return render_template("order_detail.html", order=order, items=items)


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, session["user_id"])
    ).fetchone()
    if not order:
        abort(404)
    if order["status"] != "Pending":
        flash("Only pending orders can be cancelled.", "warning")
        return redirect(url_for("order_detail", order_id=order_id))
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE orders SET status = 'Cancelled' WHERE id = ? AND status = 'Pending'", (order_id,))
        lines = db.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)
        ).fetchall()
        for line in lines:
            if line["product_id"] is not None:
                db.execute("UPDATE products SET stock = stock + ? WHERE id = ?",
                           (line["quantity"], line["product_id"]))
                record_stock_change(db, line["product_id"], line["quantity"], "Order cancellation", str(order_id))
        db.execute("INSERT INTO order_status_history (order_id, old_status, new_status, changed_by, note) VALUES (?, 'Pending', 'Cancelled', ?, 'Cancelled by customer')",
                   (order_id, session["user_id"]))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        flash("The order could not be cancelled. Please try again.", "danger")
        return redirect(url_for("order_detail", order_id=order_id))
    flash("Order cancelled and item stock restored.", "success")
    return redirect(url_for("order_detail", order_id=order_id))


# -------------------- ADMIN ROUTES --------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        "products": db.execute("SELECT COUNT(*) FROM products WHERE active = 1").fetchone()[0],
        "customers": db.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'").fetchone()[0],
        "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "revenue": db.execute("SELECT COALESCE(SUM(total), 0) FROM orders WHERE status = 'Delivered'").fetchone()[0],
        "low_stock": db.execute("SELECT COUNT(*) FROM products WHERE active = 1 AND stock BETWEEN 1 AND 5").fetchone()[0],
        "out_stock": db.execute("SELECT COUNT(*) FROM products WHERE active = 1 AND stock = 0").fetchone()[0],
        "pending": db.execute("SELECT COUNT(*) FROM orders WHERE status = 'Pending'").fetchone()[0],
    }
    low_stock_products = db.execute("SELECT id, name, stock FROM products WHERE active = 1 AND stock <= 5 ORDER BY stock ASC, name LIMIT 8").fetchall()
    recent_orders = db.execute("""
        SELECT o.*, u.full_name, u.email FROM orders o
        JOIN users u ON u.id = o.user_id ORDER BY o.id DESC LIMIT 8
    """).fetchall()
    return render_template("admin.html", stats=stats, orders=recent_orders,
                           low_stock_products=low_stock_products)


@app.route("/admin/products")
@admin_required
def admin_products():
    products = get_db().execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return render_template("admin_products.html", products=products)


@app.route("/admin/products/new", methods=["GET", "POST"])
@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_form(product_id=None):
    db = get_db()
    product = None
    if product_id is not None:
        product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip() or "General"
        image_url = request.form.get("image_url", "").strip()
        try:
            price = float(request.form.get("price", "0"))
            stock = int(request.form.get("stock", "0"))
        except ValueError:
            flash("Price and stock must be valid numbers.", "danger")
            return render_template("product_form.html", product=product)
        if not name or price < 0 or stock < 0:
            flash("Enter a product name, a non-negative price, and non-negative stock.", "danger")
            return render_template("product_form.html", product=product)
        if product:
            stock_delta = stock - product["stock"]
            if stock_delta:
                record_stock_change(db, product_id, stock_delta, "Admin stock adjustment", "Product edit")
            db.execute("""
                UPDATE products SET name=?, description=?, category=?, price=?, stock=?, image_url=?
                WHERE id=?
            """, (name, description, category, price, stock, image_url, product_id))
            flash("Product updated.", "success")
        else:
            cursor = db.execute("""
                INSERT INTO products (name, description, category, price, stock, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, description, category, price, stock, image_url))
            if stock:
                record_stock_change(db, cursor.lastrowid, stock, "Initial stock", "Product creation")
            flash("Product created.", "success")
        db.commit()
        return redirect(url_for("admin_products"))
    return render_template("product_form.html", product=product)


@app.route("/admin/products/<int:product_id>/toggle", methods=["POST"])
@admin_required
def toggle_product(product_id):
    db = get_db()
    product = db.execute("SELECT active FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        abort(404)
    db.execute("UPDATE products SET active = ? WHERE id = ?",
               (0 if product["active"] else 1, product_id))
    db.commit()
    flash("Product visibility updated.", "success")
    return redirect(url_for("admin_products"))


@app.route("/admin/orders")
@admin_required
def admin_orders():
    rows = get_db().execute("""
        SELECT o.*, u.full_name, u.email FROM orders o
        JOIN users u ON u.id = o.user_id ORDER BY o.id DESC
    """).fetchall()
    return render_template("admin_orders.html", orders=rows)


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    status = request.form.get("status", "")
    allowed = {"Pending", "Processing", "Shipped", "Delivered", "Cancelled"}
    if status not in allowed:
        abort(400)
    db = get_db()
    order = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        abort(404)
    old_status = order["status"]
    if old_status == "Cancelled" and status != "Cancelled":
        flash("Cancelled orders cannot be reopened in this starter version.", "warning")
        return redirect(url_for("admin_orders"))
    try:
        db.execute("BEGIN IMMEDIATE")
        if old_status != "Cancelled" and status == "Cancelled":
            lines = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?",
                               (order_id,)).fetchall()
            for line in lines:
                if line["product_id"] is not None:
                    db.execute("UPDATE products SET stock = stock + ? WHERE id = ?",
                               (line["quantity"], line["product_id"]))
                    record_stock_change(db, line["product_id"], line["quantity"], "Admin cancelled order", str(order_id))
        db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        db.execute("INSERT INTO order_status_history (order_id, old_status, new_status, changed_by) VALUES (?, ?, ?, ?)",
                   (order_id, old_status, status, session.get("user_id")))
        db.commit()
    except sqlite3.Error:
        db.rollback()
        flash("The order status could not be updated. Please try again.", "danger")
        return redirect(url_for("admin_orders"))
    flash("Order status updated.", "success")
    return redirect(url_for("admin_orders"))


@app.route("/admin/database")
@admin_required
def admin_database():
    db = get_db()
    table_names = ["users", "products", "cart_items", "orders", "order_items",
                   "payment_records", "inventory_movements", "order_status_history"]
    counts = {name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
              for name in table_names}
    recent_stock = db.execute("""SELECT m.*, p.name AS product_name
        FROM inventory_movements m LEFT JOIN products p ON p.id=m.product_id
        ORDER BY m.id DESC LIMIT 20""").fetchall()
    recent_status = db.execute("""SELECT h.*, o.order_number, u.full_name
        FROM order_status_history h JOIN orders o ON o.id=h.order_id
        LEFT JOIN users u ON u.id=h.changed_by ORDER BY h.id DESC LIMIT 20""").fetchall()
    integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_key_issues = db.execute("PRAGMA foreign_key_check").fetchall()
    return render_template("admin_database.html", counts=counts,
                           recent_stock=recent_stock, recent_status=recent_status,
                           database_name=os.path.basename(DATABASE),
                           integrity=integrity, foreign_key_issue_count=len(foreign_key_issues))


@app.route("/admin/database/backup")
@admin_required
def database_backup():
    from flask import send_file
    os.makedirs(os.path.join(BASE_DIR, "backups"), exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BASE_DIR, "backups", f"shopsphere_backup_{stamp}.db")
    source = sqlite3.connect(DATABASE)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return send_file(backup_path, as_attachment=True, download_name=os.path.basename(backup_path))


@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The page or item could not be found."), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

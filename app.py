import os
import sqlite3
import json
from datetime import datetime
from werkzeug.wrappers import Request, Response
from werkzeug.utils import redirect
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import NotFound
from werkzeug.middleware.shared_data import SharedDataMiddleware
from jinja2 import Environment, FileSystemLoader
from werkzeug.security import generate_password_hash, check_password_hash

# --- Configuration ---
DB_NAME = "app.db"
BASE_URL = "http://127.0.0.1:8000"
env = Environment(loader=FileSystemLoader("templates"))

# Mock Session
current_session = {'user': {'user_id': 1, 'username': 'Guest User'}}
current_cart = []  

def render(template, **context):
    def url_for(endpoint, filename=None):
        if endpoint == 'static': return f"/static/{filename}"
        return f"/{endpoint}"
    
    context.update({
        "base_url": BASE_URL, 
        "url_for": url_for,
        "user": current_session.get('user'),
        "cart_count": len(current_cart)
    })
    return Response(env.get_template(template).render(**context), content_type="text/html")

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- Database Auto-Setup ---
def init_db():
    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        address TEXT,
        birthdate TEXT,
        role TEXT DEFAULT 'Customer' CHECK(role IN ('Customer', 'Admin')),
        created_at DATETIME,
        updated_at DATETIME
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name VARCHAR(100) NOT NULL,
            supplier_id INTEGER,
            model_name VARCHAR(120) NOT NULL,
            sku VARCHAR(100) UNIQUE NOT NULL,
            barcode VARCHAR(100),
            cost_price NUMERIC(10, 2) NOT NULL,
            selling_price NUMERIC(10, 2) NOT NULL,
            stock_qty INTEGER DEFAULT 0,
            reorder_level INTEGER DEFAULT 0,
            unit VARCHAR(20),
            status VARCHAR(20)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_transactions (
            order_transaction_id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER NOT NULL, 
            product_id INTEGER, 
            order_date DATETIME NOT NULL, 
            subtotal NUMERIC(10, 2) NOT NULL, 
            discount_amount NUMERIC(10, 2), 
            tax_amount NUMERIC(10, 2), 
            total_amount NUMERIC(10, 2) NOT NULL, 
            rider_name VARCHAR(120), 
            fulfillment_method VARCHAR(8), 
            payment_method VARCHAR(6), 
            amount_tendered NUMERIC(10, 2), 
            change_given NUMERIC(10, 2), 
            status VARCHAR(9) NOT NULL, 
            FOREIGN KEY(product_id) REFERENCES products (product_id)
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name VARCHAR(120) NOT NULL,
        handler VARCHAR(120),
        address TEXT,
        contact_number VARCHAR(20),
        email VARCHAR(100)
        )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS inventory_movements (
        movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        type TEXT CHECK(type IN ('IN', 'OUT', 'ADJUST')),
        quantity INTEGER NOT NULL,
        reason TEXT,
        moved_at DATETIME,
        FOREIGN KEY(product_id) REFERENCES products(product_id),
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
    """)
    conn.commit()
    conn.close()

# --- View Functions ---

def confirm_order(request):
    """Handles the 'Confirm Order' logic from the cart"""
    if request.method == 'POST':
        data = json.loads(request.data)
        db = get_db()
        try:
            user_id = current_session['user']['user_id']
            for pid in current_cart:
                product = db.execute("SELECT selling_price FROM products WHERE product_id = ?", (pid,)).fetchone()
                if product:
                    price = product['selling_price']
                    tax = 100.00
                    delivery_fee = 100.00 if data.get('fulfillment') == 'Delivery' else 0.00
                    total = price + tax + delivery_fee

                    query = """
                        INSERT INTO order_transactions (
                            user_id, product_id, order_date, subtotal, 
                            discount_amount, tax_amount, total_amount, 
                            rider_name, fulfillment_method, payment_method, 
                            amount_tendered, change_given, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    values = (
                        user_id, pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), price, 
                        0.00, tax, total, 
                        data.get('rider_name'), data.get('fulfillment'), 
                        'Cash', 0.00, 0.00, 'Pending'
                    )
                    db.execute(query, values)
            
            db.commit()
            current_cart.clear() 
            return Response(json.dumps({"status": "success"}), content_type="application/json")
        except Exception as e:
            return Response(json.dumps({"status": "error", "message": str(e)}), status=500)
        finally:
            db.close()
    return Response("Method Not Allowed", status=405)

def orders(request):
    user = current_session.get('user')
    if not user:
        return redirect("/")

    db = get_db()
    # We rename columns in the query to match the HTML expectations
    items = db.execute("""
        SELECT 
            order_transaction_id AS transaction_id, 
            total_amount, 
            payment_method, 
            fulfillment_method, 
            rider_name, 
            amount_tendered,
            change_given,
            status, 
            order_date AS created_at
        FROM order_transactions 
        WHERE user_id = ?
        ORDER BY order_date DESC
    """, (user['user_id'],)).fetchall()
    db.close()
    
    return render("orders.html", orders=items, title="My Orders")

def cancel_order(request):
    """Updates order status to 'Cancelled' via POST"""
    # Check if it's a POST request as sent by your JS
    if request.method == 'POST':
        order_id = request.args.get('id')
        if not order_id:
            return Response("Missing ID", status=400)
        
        db = get_db()
        try:
            db.execute("""
                UPDATE order_transactions 
                SET status = 'Cancelled' 
                WHERE order_transaction_id = ? AND status = 'Pending'
            """, (order_id,))
            db.commit()
            return Response("Success", status=200)
        except Exception as e:
            return Response(str(e), status=500)
        finally:
            db.close()
    return Response("Method Not Allowed", status=405)

def delete_order(request):
    """Permanently removes the order via POST"""
    if request.method == 'POST':
        order_id = request.args.get('id')
        if not order_id:
            return Response("Missing ID", status=400)

        db = get_db()
        try:
            db.execute("DELETE FROM order_transactions WHERE order_transaction_id = ?", (order_id,))
            db.commit()
            return Response("Deleted", status=200)
        except Exception as e:
            return Response(str(e), status=500)
        finally:
            db.close()
    return Response("Method Not Allowed", status=405)
    
def home(request):
    return render("home.html", title="Home")

def products(request):
    db = get_db()
    items = db.execute("SELECT product_id AS ProductID, model_name AS ModelName, selling_price AS SellingPrice, status AS Status FROM products").fetchall()
    db.close()
    return render("products.html", products=items, title="Products")

def add_to_cart(request):
    product_id = request.args.get('id')
    if product_id:
        current_cart.append(int(product_id)) # Adds ID to the list [cite: 21]
    return redirect("/products")

def cart(request):
    db = get_db()
    items = []
    total = 0
    
    # Debug: Print the cart to your console to see if it's empty
    print(f"Current Cart Contents: {current_cart}") 
    
    for pid in current_cart:
        # Ensure 'product_id' matches your schema 
        row = db.execute("SELECT product_id AS id, model_name AS ModelName, selling_price AS SellingPrice FROM products WHERE product_id = ?", (pid,)).fetchone()
    
        if row:
            items.append(dict(row))
            total += row['SellingPrice']
            
    db.close()
    return render("cart.html", cart_items=items, total=total, title="Your Cart")

def cart(request):
    db = get_db()
    items = []
    total = 0
    for pid in current_cart:
        row = db.execute("SELECT product_id AS id, model_name AS ModelName, selling_price AS SellingPrice FROM products WHERE product_id = ?", (pid,)).fetchone()
        if row:
            items.append(dict(row))
            total += row['SellingPrice']
    db.close()
    return render("cart.html", cart_items=items, total=total, title="Your Cart")

def remove_from_cart(request):
    product_id = request.args.get('id')
    if product_id:
        product_id = int(product_id)
        if product_id in current_cart:
            current_cart.remove(product_id)
    return Response("Success", status=200)

def about(request):
    return render("about.html", title="About Us")

def login_view(request):
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        if user and check_password_hash(user['password_hash'], password):
            current_session['user'] = {
                'user_id': user['user_id'], 
                'username': user['full_name'],
                'role': user['role']
            }

            role_cleaned = str(user['role']).strip().lower()
            if role_cleaned == 'admin':
                return redirect("/admin")
            return redirect("/home")
        else:
            error_data = {
                "status": "error",
                "message": "Invalid email or password"
            }
            return Response(
                json.dumps(error_data), 
                status=401, 
                content_type="application/json"
            )

    today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render("login.html", today=today, title="Login")

def register(request):
    if request.method == 'POST':
        full_name = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        address = request.form.get('address')
        birthdate = request.form.get('birthdate')
        role = request.form.get('role', 'Customer') 
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        hashed_pw = generate_password_hash(password)
        db = get_db()
        try:
            db.execute("""
                INSERT INTO users (full_name, email, password_hash, address, birthdate, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (full_name, email, hashed_pw, address, birthdate, role, now, now))
            db.commit()
            
            new_user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            
            if new_user:
                current_session['user'] = {
                    'user_id': new_user['user_id'], 
                    'username': new_user['full_name'],
                    'role': new_user['role']
                }
                
                if str(new_user['role']).strip().lower() == 'admin':
                    return redirect("/admin")
                return redirect("/home")
        except sqlite3.IntegrityError:
            return Response("Email already registered", status=400)
        finally:
            db.close()
    return redirect("/")

def admin_view(request):
    user = current_session.get('user')
    # Bouncer check: if not admin, kick back to login/home (NOT /admin)
    if not user or str(user.get('role')).strip().lower() != 'admin':
        return redirect("/") 
        
    return render("admin.html", title="Admin Dashboard")

current_session = {'user': None}

def logout(request):
    """Resets the session to Guest"""
    current_session['user'] = None
    current_cart.clear()
    return redirect("/")

def update_profile(request):
    """Handles updating user details in the database"""
    if request.method == 'POST':
        user_id = current_session['user']['user_id']
        new_name = request.form.get('fullname')
        new_email = request.form.get('email')
        new_password = request.form.get('password')
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db = get_db()
        try:
            # 1. Update Name and Email
            db.execute("""
                UPDATE users 
                SET full_name = ?, email = ?, updated_at = ? 
                WHERE user_id = ?
            """, (new_name, new_email, updated_at, user_id))

            # 2. Update Password only if a new one was provided
            if new_password and new_password.strip() != "":
                hashed_pw = generate_password_hash(new_password)
                db.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (hashed_pw, user_id))

            db.commit()

            # 3. Update the session so the UI refreshes with the new name/email
            current_session['user']['username'] = new_name
            current_session['user']['email'] = new_email
            
            return redirect("/home")
        except Exception as e:
            return Response(f"Update Error: {e}", status=400)
        finally:
            db.close()
    return redirect("/home")

def transactions_view(request):
    # Security Bouncer
    user = current_session.get('user')
    if not user or str(user.get('role')).lower() != 'admin':
        return redirect("/")

    db = get_db()
    # Comprehensive query to get details from all related tables
    query = """
        SELECT 
            ot.*, 
            u.full_name AS customer_name, 
            p.model_name AS product_name
        FROM order_transactions ot
        LEFT JOIN users u ON ot.user_id = u.user_id
        LEFT JOIN products p ON ot.product_id = p.product_id
        ORDER BY ot.order_date DESC
    """
    rows = db.execute(query).fetchall()
    db.close()
    
    return render("transactions.html", transactions=rows, title="System Transactions")
    
def update_transaction(request):
    if request.method == 'POST':
        tx_id = request.form.get('tx_id')
        status = request.form.get('status')
        tendered = request.form.get('amount_tendered')

        db = get_db()
        # This assumes your table 'order_transactions' has a column 'amount_tendered'
        db.execute("""
            UPDATE order_transactions 
            SET status = ?, amount_tendered = ? 
            WHERE order_transaction_id = ?
        """, (status, tendered, tx_id))
        db.commit()
        db.close()
        
    return redirect("/transactions")

def users_management(request):
    # Security Bouncer: Only admins allowed
    user = current_session.get('user')
    if not user or str(user.get('role')).lower() != 'admin':
        return redirect("/")

    db = get_db()
    # Fetch all user details
    users_list = db.execute("""
        SELECT user_id, full_name, email, role, address, created_at 
        FROM users 
        ORDER BY created_at DESC
    """).fetchall()
    db.close()
    
    return render("users.html", all_users=users_list, title="User Management")

def add_user(request):
    if request.method == 'POST':
        full_name = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db = get_db()
        try:
            db.execute("""
                INSERT INTO users (full_name, email, password_hash, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (full_name, email, generate_password_hash(password), role, now, now))
            db.commit()
        except Exception as e:
            print(f"Error adding user: {e}")
        finally:
            db.close()
    return redirect("/users")

# 2. EDIT USER (via Modal)
def edit_user(request):
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        full_name = request.form.get('fullname')
        email = request.form.get('email')
        role = request.form.get('role')
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db = get_db()
        db.execute("""
            UPDATE users 
            SET full_name = ?, email = ?, role = ?, updated_at = ?
            WHERE user_id = ?
        """, (full_name, email, role, now, user_id))
        db.commit()
        db.close()
    return redirect("/users")

# 3. DELETE USER
def delete_user(request, user_id):
    # Optional: Prevent admin from deleting themselves
    current_admin_id = current_session.get('user', {}).get('user_id')
    if str(current_admin_id) == str(user_id):
        return Response("Error: You cannot delete your own account.", status=400)

    db = get_db()
    db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    db.commit()
    db.close()
    return redirect("/users")

# 1. View all products
def items_management(request):
    user = current_session.get('user')
    if not user or str(user.get('role')).lower() != 'admin':
        return redirect("/")

    db = get_db()
    items = db.execute("SELECT * FROM products ORDER BY model_name ASC").fetchall()
    db.close()
    return render("items.html", all_items=items, title="Product Management")

# 1. ADD NEW PRODUCT
def add_item(request):
    if request.method == 'POST':
        # Capture all fields from the schema
        category = request.form.get('category_name')
        supplier = request.form.get('supplier_id')
        model = request.form.get('model_name')
        sku = request.form.get('sku')
        barcode = request.form.get('barcode')
        cost = request.form.get('cost_price')
        selling = request.form.get('selling_price')
        qty = request.form.get('stock_qty')
        reorder = request.form.get('reorder_level', 5)
        unit = request.form.get('unit', 'pcs')
        status = request.form.get('status', 'Available')

        db = get_db()
        try:
            db.execute("""
                INSERT INTO products (
                    category_name, supplier_id, model_name, sku, barcode, 
                    cost_price, selling_price, stock_qty, reorder_level, unit, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (category, supplier, model, sku, barcode, cost, selling, qty, reorder, unit, status))
            db.commit()
        except Exception as e:
            print(f"Error adding product: {e}")
        finally:
            db.close()
    return redirect("/items")

# 2. EDIT PRODUCT
def edit_item(request):
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        category = request.form.get('category_name')
        model = request.form.get('model_name')
        sku = request.form.get('sku')
        cost = request.form.get('cost_price')
        selling = request.form.get('selling_price')
        qty = request.form.get('stock_qty')
        status = request.form.get('status')

        db = get_db()
        db.execute("""
            UPDATE products 
            SET category_name = ?, model_name = ?, sku = ?, 
                cost_price = ?, selling_price = ?, stock_qty = ?, status = ? 
            WHERE product_id = ?
        """, (category, model, sku, cost, selling, qty, status, product_id))
        db.commit()
        db.close()
    return redirect("/items")

# 3. Delete Product
def delete_item(request, product_id):
    db = get_db()
    db.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
    db.commit()
    db.close()
    return redirect("/items")

def inventory_management(request):
    user = current_session.get('user')
    if not user or str(user.get('role')).lower() != 'admin':
        return redirect("/")

    db = get_db()
    # Joins movements with products and users to see who moved what
    movements = db.execute("""
        SELECT m.*, p.model_name, u.full_name as admin_name
        FROM inventory_movements m
        JOIN products p ON m.product_id = p.product_id
        JOIN users u ON m.user_id = u.user_id
        ORDER BY m.moved_at DESC
    """).fetchall()
    
    # Also fetch products for the "Add Movement" dropdown
    products = db.execute("SELECT product_id, model_name FROM products").fetchall()
    db.close()
    
    return render("inventory.html", movements=movements, products=products)

def record_movement(request):
    """Records a new stock movement (Add functionality)"""
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        m_type = request.form.get('type')  # 'IN', 'OUT', or 'ADJUST'
        qty = request.form.get('quantity')
        reason = request.form.get('reason')
        admin_id = current_session.get('user', {}).get('user_id')
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db = get_db()
        # Record the movement in history [cite: 53]
        db.execute("""
            INSERT INTO inventory_movements (product_id, user_id, type, quantity, reason, moved_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (product_id, admin_id, m_type, qty, reason, now))
        
        # Update the actual product stock level [cite: 49, 50]
        if m_type == 'IN':
            db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE product_id = ?", (qty, product_id))
        elif m_type == 'OUT':
            db.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE product_id = ?", (qty, product_id))
            
        db.commit()
        db.close()
    return redirect("/inventory")

def edit_movement(request):
    if request.method == 'POST':
        movement_id = request.form.get('movement_id')
        m_type = request.form.get('type') # Get the new type
        reason = request.form.get('reason')
        qty = request.form.get('quantity')

        db = get_db()
        db.execute("""
            UPDATE inventory_movements 
            SET type = ?, reason = ?, quantity = ? 
            WHERE movement_id = ?
        """, (m_type, reason, qty, movement_id))
        db.commit()
        db.close()
    return redirect("/inventory")

def delete_movement(request, movement_id):
    """Removes a movement record from history"""
    db = get_db()
    db.execute("DELETE FROM inventory_movements WHERE movement_id = ?", (movement_id,))
    db.commit()
    db.close()
    return redirect("/inventory")

def suppliers_management(request):
    # Security Bouncer: Only admins can view suppliers [cite: 50]
    user = current_session.get('user')
    if not user or str(user.get('role')).lower() != 'admin':
        return redirect("/")

    db = get_db()
    # conn.execute pulls all rows to display in your HTML table [cite: 54]
    suppliers = db.execute("SELECT * FROM suppliers").fetchall()
    db.close()
    
    return render("suppliers.html", suppliers=suppliers)

def add_supplier(request):
    if request.method == 'POST':
        # Extracting data from the form [cite: 55]
        company = request.form.get('company_name')
        handler = request.form.get('handler')
        address = request.form.get('address')
        contact = request.form.get('contact_number')
        email = request.form.get('email')

        db = get_db()
        # conn.execute inserts the new supplier record safely [cite: 55]
        db.execute("""
            INSERT INTO suppliers (company_name, handler, address, contact_number, email)
            VALUES (?, ?, ?, ?, ?)
        """, (company, handler, address, contact, email))
        db.commit()
        db.close()
    
    return redirect("/suppliers")

def delete_supplier(request, supplier_id):
    db = get_db()
    # conn.execute removes the supplier based on the ID passed from the URL 
    db.execute("DELETE FROM suppliers WHERE supplier_id = ?", (supplier_id,))
    db.commit()
    db.close()
    return redirect("/suppliers")

def edit_supplier(request):
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id')
        company = request.form.get('company_name')
        handler = request.form.get('handler')
        address = request.form.get('address')
        contact = request.form.get('contact_number')
        email = request.form.get('email')

        db = get_db()
        db.execute("""
            UPDATE suppliers 
            SET company_name = ?, handler = ?, address = ?, contact_number = ?, email = ?
            WHERE supplier_id = ?
        """, (company, handler, address, contact, email, supplier_id))
        db.commit()
        db.close()
    return redirect("/suppliers")
# --- Routing ---
url_map = Map([
    Rule("/", endpoint="login_view"), # Changed from "login" to "login_view"
    Rule("/register", endpoint="register"),
    Rule("/update-profile", endpoint="update_profile"),
    Rule("/logout", endpoint="logout"),
    Rule("/home", endpoint="home"),
    Rule("/admin", endpoint="admin_view"),
    Rule("/products", endpoint="products"),
    Rule("/add-to-cart", endpoint="add_to_cart"),
    Rule("/cart", endpoint="cart"),
    Rule("/confirm-order", endpoint="confirm_order"),
    Rule("/orders", endpoint="orders"),
    Rule("/cancel-order", endpoint="cancel_order"),
    Rule("/remove-from-cart", endpoint="remove_from_cart"),
    Rule("/about", endpoint="about"),
    Rule("/delete-order", endpoint="delete_order"),
    Rule("/transactions", endpoint="transactions_view"),
    Rule("/users", endpoint="users_management"),
    Rule("/add-user", endpoint="add_user"),
    Rule("/edit-user", endpoint="edit_user"),
    Rule("/delete-user/<int:user_id>", endpoint="delete_user"),
    Rule("/items", endpoint="items_management"),
    Rule("/add-item", endpoint="add_item"),
    Rule("/delete-item/<int:product_id>", endpoint="delete_item"),
    Rule("/edit-item", endpoint="edit_item"),
    Rule("/update-transaction", endpoint="update_transaction"),
    Rule("/inventory", endpoint="inventory_management"),
    Rule("/record-movement", endpoint="record_movement"),
    Rule("/edit-movement", endpoint="edit_movement"),
    Rule("/delete-movement/<int:movement_id>", endpoint="delete_movement"),
    Rule("/suppliers", endpoint="suppliers_management"),
    Rule("/add-supplier", endpoint="add_supplier"),
    Rule("/delete-supplier/<int:supplier_id>", endpoint="delete_supplier"),
    Rule("/edit-supplier", endpoint="edit_supplier"), # Add this line
])

@Request.application
def wsgi_app(request):
    adapter = url_map.bind_to_environ(request.environ)
    try:
        endpoint, values = adapter.match()
        return globals()[endpoint](request, **values)
    except NotFound:
        return Response("404 Not Found", status=404)
    except Exception as e:
        return Response(f"Internal Error: {e}", status=500)

app = SharedDataMiddleware(wsgi_app, {
    '/static': os.path.join(os.path.dirname(__file__), 'static')
})

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    init_db()
    run_simple("127.0.0.1", 8000, app, use_reloader=True)
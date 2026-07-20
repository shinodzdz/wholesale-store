from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
import sqlite3, os, random, string, hashlib
from datetime import datetime

_basedir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_basedir, 'templates'))
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-to-a-random-secret')
app.config['SHOP_NAME'] = 'Dépot Bouras Béchar'
app.config['SHOP_TAGLINE'] = 'طلب المنتجات الغذائية بالجملة'
app.config['PUBLIC_URL'] = os.environ.get('PUBLIC_URL', '')

def get_public_url():
    if app.config['PUBLIC_URL']:
        return app.config['PUBLIC_URL'].rstrip('/') + '/'
    # Try to detect local IP
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return f'http://{ip}:{os.environ.get("PORT", 5000)}/'
    except:
        return request.host_url if request else 'http://localhost:5000/'

@app.context_processor
def inject_globals():
    return {
        'shop_name': app.config['SHOP_NAME'],
        'shop_tagline': app.config['SHOP_TAGLINE'],
        'public_url': get_public_url()
    }

DB_PATH = os.path.join(_basedir, 'database.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT DEFAULT 'قطعة',
            category TEXT DEFAULT 'عام',
            available INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            phone TEXT,
            address TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            shop_name TEXT,
            notes TEXT,
            total REAL DEFAULT 0,
            status TEXT DEFAULT 'جديد',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (shop_id) REFERENCES shops(id)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            unit TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
    ''')
    if not conn.execute('SELECT * FROM admins').fetchone():
        conn.execute('INSERT INTO admins (username, password) VALUES (?, ?)',
                     ('admin', hashlib.sha256('admin123'.encode()).hexdigest()))
    conn.commit()
    conn.close()

init_db()

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ─── Admin ───

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        conn = get_db()
        user = conn.execute('SELECT * FROM admins WHERE username=? AND password=?',
                           (username, password)).fetchone()
        conn.close()
        if user:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin'))
        return render_template('admin_login.html', error='خطأ في اسم المستخدم أو كلمة المرور')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin():
    conn = get_db()
    shops = conn.execute('SELECT * FROM shops ORDER BY created_at DESC').fetchall()
    products = conn.execute('SELECT * FROM products WHERE available=1 ORDER BY category, name').fetchall()
    new_orders_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM orders WHERE status='جديد'"
    ).fetchone()['cnt']
    pending_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM orders WHERE status NOT IN ('تم التوصيل')"
    ).fetchone()['cnt']
    recent_orders = conn.execute('''
        SELECT o.*, s.name as shop_name FROM orders o
        JOIN shops s ON o.shop_id = s.id
        ORDER BY o.created_at DESC LIMIT 20
    ''').fetchall()
    conn.close()
    return render_template('admin.html', shops=shops, products=products, orders=recent_orders,
                           new_orders_count=new_orders_count, pending_count=pending_count)

# ─── Products ───

@app.route('/admin/products', methods=['GET', 'POST'])
@admin_required
def manage_products():
    conn = get_db()
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        unit = request.form.get('unit', 'قطعة')
        category = request.form.get('category', 'عام')
        conn.execute('INSERT INTO products (name, price, unit, category) VALUES (?, ?, ?, ?)',
                     (name, price, unit, category))
        conn.commit()
    products = conn.execute('SELECT * FROM products ORDER BY category, name').fetchall()
    conn.close()
    return render_template('products.html', products=products)

@app.route('/admin/products/delete/<int:id>')
@admin_required
def delete_product(id):
    conn = get_db()
    conn.execute('DELETE FROM products WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_products'))

@app.route('/admin/products/toggle/<int:id>')
@admin_required
def toggle_product(id):
    conn = get_db()
    p = conn.execute('SELECT available FROM products WHERE id=?', (id,)).fetchone()
    if p:
        conn.execute('UPDATE products SET available=? WHERE id=?', (0 if p['available'] else 1, id))
        conn.commit()
    conn.close()
    return redirect(url_for('manage_products'))

@app.route('/admin/products/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_product(id):
    conn = get_db()
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        unit = request.form.get('unit', 'قطعة')
        category = request.form.get('category', 'عام')
        conn.execute('UPDATE products SET name=?, price=?, unit=?, category=? WHERE id=?',
                     (name, price, unit, category, id))
        conn.commit()
        conn.close()
        return redirect(url_for('manage_products'))
    product = conn.execute('SELECT * FROM products WHERE id=?', (id,)).fetchone()
    conn.close()
    return render_template('product_edit.html', product=product)

# ─── Shops ───

@app.route('/admin/shops', methods=['GET', 'POST'])
@admin_required
def manage_shops():
    conn = get_db()
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        code = generate_code()
        while conn.execute('SELECT id FROM shops WHERE code=?', (code,)).fetchone():
            code = generate_code()
        conn.execute('INSERT INTO shops (name, code, phone, address) VALUES (?, ?, ?, ?)',
                     (name, code, phone, address))
        conn.commit()
    shops = conn.execute('SELECT * FROM shops ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('shops.html', shops=shops)

@app.route('/admin/shops/delete/<int:id>')
@admin_required
def delete_shop(id):
    conn = get_db()
    conn.execute('DELETE FROM shops WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_shops'))

@app.route('/admin/shops/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_shop(id):
    conn = get_db()
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        conn.execute('UPDATE shops SET name=?, phone=?, address=? WHERE id=?',
                     (name, phone, address, id))
        conn.commit()
        conn.close()
        return redirect(url_for('manage_shops'))
    shop = conn.execute('SELECT * FROM shops WHERE id=?', (id,)).fetchone()
    conn.close()
    return render_template('shop_edit.html', shop=shop)

# ─── Shop Orders ───

@app.route('/')
def index():
    return redirect(url_for('shop_login'))

@app.route('/shop', methods=['GET', 'POST'])
def shop_login():
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        conn = get_db()
        shop = conn.execute('SELECT * FROM shops WHERE code=?', (code,)).fetchone()
        conn.close()
        if shop:
            return redirect(url_for('shop_dashboard', code=code))
        return render_template('shop_login.html', error='كود غير صحيح')
    return render_template('shop_login.html')

@app.route('/shop/<code>')
def shop_dashboard(code):
    conn = get_db()
    shop = conn.execute('SELECT * FROM shops WHERE code=?', (code,)).fetchone()
    if not shop:
        conn.close()
        return redirect(url_for('shop_login'))
    orders = conn.execute(
        'SELECT * FROM orders WHERE shop_id=? ORDER BY created_at DESC LIMIT 10',
        (shop['id'],)
    ).fetchall()
    conn.close()
    return render_template('shop_dashboard.html', shop=shop, orders=orders)

@app.route('/shop/<code>/order')
def shop_order(code):
    conn = get_db()
    shop = conn.execute('SELECT * FROM shops WHERE code=?', (code,)).fetchone()
    if not shop:
        conn.close()
        return redirect(url_for('shop_login'))
    products = conn.execute('SELECT * FROM products WHERE available=1 ORDER BY category, name').fetchall()
    categories = conn.execute('SELECT DISTINCT category FROM products WHERE available=1 ORDER BY category').fetchall()
    last_order = conn.execute(
        'SELECT * FROM orders WHERE shop_id=? ORDER BY created_at DESC LIMIT 1',
        (shop['id'],)
    ).fetchone()
    conn.close()
    return render_template('shop_order.html', shop=shop, products=products,
                           categories=[c['category'] for c in categories], last_order=last_order)

@app.route('/shop/<code>/orders')
def shop_orders(code):
    conn = get_db()
    shop = conn.execute('SELECT * FROM shops WHERE code=?', (code,)).fetchone()
    if not shop:
        conn.close()
        return redirect(url_for('shop_login'))
    orders = conn.execute(
        'SELECT * FROM orders WHERE shop_id=? ORDER BY created_at DESC',
        (shop['id'],)
    ).fetchall()
    conn.close()
    return render_template('shop_orders.html', shop=shop, orders=orders)

@app.route('/api/submit-order', methods=['POST'])
def submit_order():
    data = request.json
    code = data.get('code')
    items = data.get('items', [])
    notes = data.get('notes', '')

    if not code or not items:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'})

    conn = get_db()
    shop = conn.execute('SELECT * FROM shops WHERE code=?', (code,)).fetchone()
    if not shop:
        conn.close()
        return jsonify({'success': False, 'error': 'كود غير صحيح'})

    total = sum(float(item['price']) * float(item['qty']) for item in items)
    cursor = conn.execute(
        'INSERT INTO orders (shop_id, shop_name, notes, total) VALUES (?, ?, ?, ?)',
        (shop['id'], shop['name'], notes, total)
    )
    order_id = cursor.lastrowid

    for item in items:
        conn.execute(
            'INSERT INTO order_items (order_id, product_name, quantity, price, unit) VALUES (?, ?, ?, ?, ?)',
            (order_id, item['name'], float(item['qty']), float(item['price']), item.get('unit', ''))
        )

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'order_id': order_id})

# ─── View Orders ───

@app.route('/admin/orders')
@admin_required
def view_orders():
    conn = get_db()
    orders = conn.execute('''
        SELECT o.*, s.name as shop_name, s.phone, s.address
        FROM orders o JOIN shops s ON o.shop_id = s.id
        ORDER BY o.created_at DESC
    ''').fetchall()
    conn.close()
    return render_template('orders.html', orders=orders)

@app.route('/admin/shops/<int:id>/orders')
@admin_required
def shop_orders_admin(id):
    conn = get_db()
    shop = conn.execute('SELECT * FROM shops WHERE id=?', (id,)).fetchone()
    if not shop:
        conn.close()
        return redirect(url_for('manage_shops'))
    orders = conn.execute('''
        SELECT o.*, s.name as shop_name, s.phone, s.address
        FROM orders o JOIN shops s ON o.shop_id = s.id WHERE o.shop_id=?
        ORDER BY o.created_at DESC
    ''', (id,)).fetchall()
    conn.close()
    return render_template('orders.html', orders=orders, shop_filter=shop)

@app.route('/admin/order/<int:id>')
@admin_required
def order_detail(id):
    conn = get_db()
    order = conn.execute('''
        SELECT o.*, s.name as shop_name, s.phone, s.address
        FROM orders o JOIN shops s ON o.shop_id = s.id WHERE o.id=?
    ''', (id,)).fetchone()
    items = conn.execute('SELECT * FROM order_items WHERE order_id=?', (id,)).fetchall()
    conn.close()
    return render_template('order_detail.html', order=order, items=items)

@app.route('/admin/order/status/<int:id>', methods=['POST'])
@admin_required
def update_status(id):
    status = request.form['status']
    conn = get_db()
    conn.execute('UPDATE orders SET status=? WHERE id=?', (status, id))
    conn.commit()
    conn.close()
    return redirect(url_for('view_orders'))

@app.route('/admin/order/delete/<int:id>', methods=['POST'])
@admin_required
def delete_order(id):
    conn = get_db()
    conn.execute('DELETE FROM order_items WHERE order_id=?', (id,))
    conn.execute('DELETE FROM orders WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('view_orders'))

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        current = hashlib.sha256(request.form['current'].encode()).hexdigest()
        new = request.form['new']
        confirm = request.form['confirm']
        conn = get_db()
        admin = conn.execute('SELECT * FROM admins WHERE username=?', (session['admin_username'],)).fetchone()
        if admin['password'] != current:
            conn.close()
            return render_template('change_password.html', error='كلمة المرور الحالية غير صحيحة')
        if new != confirm:
            conn.close()
            return render_template('change_password.html', error='كلمة المرور الجديدة غير متطابقة')
        if len(new) < 4:
            conn.close()
            return render_template('change_password.html', error='كلمة المرور يجب أن تكون 4 أحرف على الأقل')
        conn.execute('UPDATE admins SET password=? WHERE username=?',
                     (hashlib.sha256(new.encode()).hexdigest(), session['admin_username']))
        conn.commit()
        conn.close()
        return render_template('change_password.html', success='✅ تم تغيير كلمة المرور بنجاح')
    return render_template('change_password.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

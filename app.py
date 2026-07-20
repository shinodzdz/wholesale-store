from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import os, random, string, hashlib
from datetime import datetime

_basedir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_basedir, 'templates'))
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-to-a-random-secret')

db_url = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(_basedir, "database.db")}')
db_url = db_url.replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SHOP_NAME'] = 'Dépot Bouras Béchar'
app.config['SHOP_TAGLINE'] = 'طلب المنتجات الغذائية بالجملة'
app.config['PUBLIC_URL'] = os.environ.get('PUBLIC_URL', '')

db = SQLAlchemy(app)

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), default='قطعة')
    category = db.Column(db.String(100), default='عام')
    available = db.Column(db.Integer, default=1)

class Shop(db.Model):
    __tablename__ = 'shops'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    phone = db.Column(db.String(50))
    address = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.now)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    shop_name = db.Column(db.String(200))
    notes = db.Column(db.Text)
    total = db.Column(db.Float, default=0)
    status = db.Column(db.String(50), default='جديد')
    created_at = db.Column(db.DateTime, default=datetime.now)
    shop = db.relationship('Shop', backref='orders')

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50))

def init_db():
    db.create_all()
    if not Admin.query.first():
        db.session.add(Admin(username='admin', password=hashlib.sha256('admin123'.encode()).hexdigest()))
        db.session.commit()

with app.app_context():
    init_db()

def get_public_url():
    if app.config['PUBLIC_URL']:
        return app.config['PUBLIC_URL'].rstrip('/') + '/'
    try:
        return request.host_url
    except:
        return 'https://'

@app.context_processor
def inject_globals():
    return {
        'shop_name': app.config['SHOP_NAME'],
        'shop_tagline': app.config['SHOP_TAGLINE'],
        'public_url': get_public_url()
    }

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
        admin = Admin.query.filter_by(username=username, password=password).first()
        if admin:
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
    shops = Shop.query.order_by(Shop.created_at.desc()).all()
    products = Product.query.filter_by(available=1).order_by(Product.category, Product.name).all()
    new_orders_count = Order.query.filter_by(status='جديد').count()
    pending_count = Order.query.filter(Order.status != 'تم التوصيل').count()
    recent_orders = Order.query.options(db.joinedload(Order.shop)).order_by(Order.created_at.desc()).limit(20).all()
    return render_template('admin.html', shops=shops, products=products, orders=recent_orders,
                           new_orders_count=new_orders_count, pending_count=pending_count)

# ─── Products ───

@app.route('/admin/products', methods=['GET', 'POST'])
@admin_required
def manage_products():
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        unit = request.form.get('unit', 'قطعة')
        category = request.form.get('category', 'عام')
        db.session.add(Product(name=name, price=price, unit=unit, category=category))
        db.session.commit()
    products = Product.query.order_by(Product.category, Product.name).all()
    return render_template('products.html', products=products)

@app.route('/admin/products/delete/<int:id>')
@admin_required
def delete_product(id):
    product = db.session.get(Product, id)
    if product:
        db.session.delete(product)
        db.session.commit()
    return redirect(url_for('manage_products'))

@app.route('/admin/products/toggle/<int:id>')
@admin_required
def toggle_product(id):
    product = db.session.get(Product, id)
    if product:
        product.available = 0 if product.available else 1
        db.session.commit()
    return redirect(url_for('manage_products'))

@app.route('/admin/products/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_product(id):
    product = db.session.get(Product, id)
    if not product:
        return redirect(url_for('manage_products'))
    if request.method == 'POST':
        product.name = request.form['name']
        product.price = float(request.form['price'])
        product.unit = request.form.get('unit', 'قطعة')
        product.category = request.form.get('category', 'عام')
        db.session.commit()
        return redirect(url_for('manage_products'))
    return render_template('product_edit.html', product=product)

# ─── Shops ───

@app.route('/admin/shops', methods=['GET', 'POST'])
@admin_required
def manage_shops():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        code = generate_code()
        while Shop.query.filter_by(code=code).first():
            code = generate_code()
        db.session.add(Shop(name=name, code=code, phone=phone, address=address))
        db.session.commit()
    shops = Shop.query.order_by(Shop.created_at.desc()).all()
    return render_template('shops.html', shops=shops)

@app.route('/admin/shops/delete/<int:id>')
@admin_required
def delete_shop(id):
    shop = db.session.get(Shop, id)
    if shop:
        Order.query.filter_by(shop_id=id).delete()
        db.session.delete(shop)
        db.session.commit()
    return redirect(url_for('manage_shops'))

@app.route('/admin/shops/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_shop(id):
    shop = db.session.get(Shop, id)
    if not shop:
        return redirect(url_for('manage_shops'))
    if request.method == 'POST':
        shop.name = request.form['name']
        shop.phone = request.form.get('phone', '')
        shop.address = request.form.get('address', '')
        db.session.commit()
        return redirect(url_for('manage_shops'))
    return render_template('shop_edit.html', shop=shop)

# ─── Shop Orders ───

@app.route('/')
def index():
    return redirect(url_for('shop_login'))

@app.route('/shop', methods=['GET', 'POST'])
def shop_login():
    if request.method == 'POST':
        code = request.form['code'].strip().upper()
        shop = Shop.query.filter_by(code=code).first()
        if shop:
            return redirect(url_for('shop_dashboard', code=code))
        return render_template('shop_login.html', error='كود غير صحيح')
    return render_template('shop_login.html')

@app.route('/shop/<code>')
def shop_dashboard(code):
    shop = Shop.query.filter_by(code=code).first()
    if not shop:
        return redirect(url_for('shop_login'))
    orders = Order.query.filter_by(shop_id=shop.id).order_by(Order.created_at.desc()).limit(10).all()
    return render_template('shop_dashboard.html', shop=shop, orders=orders)

@app.route('/shop/<code>/order')
def shop_order(code):
    shop = Shop.query.filter_by(code=code).first()
    if not shop:
        return redirect(url_for('shop_login'))
    products = Product.query.filter_by(available=1).order_by(Product.category, Product.name).all()
    categories = [row[0] for row in Product.query.filter_by(available=1).with_entities(Product.category).distinct().order_by(Product.category).all()]
    last_order = Order.query.filter_by(shop_id=shop.id).order_by(Order.created_at.desc()).first()
    return render_template('shop_order.html', shop=shop, products=products,
                           categories=categories, last_order=last_order)

@app.route('/shop/<code>/orders')
def shop_orders(code):
    shop = Shop.query.filter_by(code=code).first()
    if not shop:
        return redirect(url_for('shop_login'))
    orders = Order.query.filter_by(shop_id=shop.id).order_by(Order.created_at.desc()).all()
    return render_template('shop_orders.html', shop=shop, orders=orders)

@app.route('/api/submit-order', methods=['POST'])
def submit_order():
    data = request.json
    code = data.get('code')
    items = data.get('items', [])
    notes = data.get('notes', '')

    if not code or not items:
        return jsonify({'success': False, 'error': 'بيانات ناقصة'})

    shop = Shop.query.filter_by(code=code).first()
    if not shop:
        return jsonify({'success': False, 'error': 'كود غير صحيح'})

    total = sum(float(item['price']) * float(item['qty']) for item in items)
    order = Order(shop_id=shop.id, shop_name=shop.name, notes=notes, total=total)
    db.session.add(order)
    db.session.flush()

    for item in items:
        db.session.add(OrderItem(
            order_id=order.id,
            product_name=item['name'],
            quantity=float(item['qty']),
            price=float(item['price']),
            unit=item.get('unit', '')
        ))

    db.session.commit()
    return jsonify({'success': True, 'order_id': order.id})

# ─── View Orders ───

@app.route('/admin/orders')
@admin_required
def view_orders():
    orders = Order.query.options(db.joinedload(Order.shop)).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)

@app.route('/admin/shops/<int:id>/orders')
@admin_required
def shop_orders_admin(id):
    shop = db.session.get(Shop, id)
    if not shop:
        return redirect(url_for('manage_shops'))
    orders = Order.query.options(db.joinedload(Order.shop)).filter_by(shop_id=id).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders, shop_filter=shop)

@app.route('/admin/order/<int:id>')
@admin_required
def order_detail(id):
    order = Order.query.options(db.joinedload(Order.shop)).get_or_404(id)
    items = OrderItem.query.filter_by(order_id=id).all()
    return render_template('order_detail.html', order=order, items=items)

@app.route('/admin/order/status/<int:id>', methods=['POST'])
@admin_required
def update_status(id):
    order = db.session.get(Order, id)
    if order:
        order.status = request.form['status']
        db.session.commit()
    return redirect(url_for('view_orders'))

@app.route('/admin/order/delete/<int:id>', methods=['POST'])
@admin_required
def delete_order(id):
    order = db.session.get(Order, id)
    if order:
        OrderItem.query.filter_by(order_id=id).delete()
        db.session.delete(order)
        db.session.commit()
    return redirect(url_for('view_orders'))

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        current = hashlib.sha256(request.form['current'].encode()).hexdigest()
        new = request.form['new']
        confirm = request.form['confirm']
        admin = Admin.query.filter_by(username=session['admin_username']).first()
        if admin.password != current:
            return render_template('change_password.html', error='كلمة المرور الحالية غير صحيحة')
        if new != confirm:
            return render_template('change_password.html', error='كلمة المرور الجديدة غير متطابقة')
        if len(new) < 4:
            return render_template('change_password.html', error='كلمة المرور يجب أن تكون 4 أحرف على الأقل')
        admin.password = hashlib.sha256(new.encode()).hexdigest()
        db.session.commit()
        return render_template('change_password.html', success='✅ تم تغيير كلمة المرور بنجاح')
    return render_template('change_password.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

"""
Web version of the accounting software - Flask backend
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from functools import wraps
from datetime import datetime
import os
import io
import csv

from database import Database
try:
    from persian_date import shamsi_now, gregorian_to_shamsi, format_shamsi_datetime, get_shamsi_month_start
    PERSIAN_DATE_AVAILABLE = True
except:
    PERSIAN_DATE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

db = Database()
db.connect()

PERMISSIONS = {
    'Admin':   {'add_customer':True,'edit_customer':True,'delete_customer':True,'add_product':True,'edit_product':True,'delete_product':True,'create_invoice':True,'process_return':True,'view_reports':True,'manage_users':True,'backup_restore':True,'export_data':True,'invoice_settings':True},
    'Manager': {'add_customer':True,'edit_customer':True,'delete_customer':True,'add_product':True,'edit_product':True,'delete_product':True,'create_invoice':True,'process_return':True,'view_reports':True,'manage_users':False,'backup_restore':False,'export_data':True,'invoice_settings':True},
    'Cashier': {'add_customer':True,'edit_customer':False,'delete_customer':False,'add_product':False,'edit_product':False,'delete_product':False,'create_invoice':True,'process_return':True,'view_reports':False,'manage_users':False,'backup_restore':False,'export_data':False,'invoice_settings':False},
    'Viewer':  {'add_customer':False,'edit_customer':False,'delete_customer':False,'add_product':False,'edit_product':False,'delete_product':False,'create_invoice':False,'process_return':False,'view_reports':True,'manage_users':False,'backup_restore':False,'export_data':False,'invoice_settings':False},
}

def has_permission(perm):
    role = session.get('role', '')
    return PERMISSIONS.get(role, {}).get(perm, False)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def perm_required(perm):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'username' not in session:
                return redirect(url_for('login'))
            if not has_permission(perm):
                return jsonify({'success': False, 'message': 'دسترسی ندارید'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def fmt_date(date_str):
    if not date_str:
        return ''
    if PERSIAN_DATE_AVAILABLE:
        try:
            return format_shamsi_datetime(date_str)
        except:
            pass
    return date_str[:16] if date_str else ''

# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        success, message, role = db.authenticate_user(username, password)
        if success:
            session['username'] = username
            session['role'] = role
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': message})
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    success, message = db.register_user(username, password)
    return jsonify({'success': success, 'message': message})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── DASHBOARD ───────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html',
        username=session.get('username'),
        role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {})
    )

@app.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    daily = db.get_daily_sales(today)
    low_stock = db.get_low_stock_products(10)
    db.cursor.execute("SELECT COUNT(*) FROM customers")
    cust_count = db.cursor.fetchone()[0]
    db.cursor.execute("SELECT COUNT(*) FROM products")
    prod_count = db.cursor.fetchone()[0]
    db.cursor.execute("SELECT COUNT(*) FROM invoices")
    inv_count = db.cursor.fetchone()[0]
    return jsonify({
        'today_sales': daily.get('total_sales', 0) if daily else 0,
        'today_invoices': daily.get('invoice_count', 0) if daily else 0,
        'customers': cust_count,
        'products': prod_count,
        'invoices': inv_count,
        'low_stock_count': len(low_stock)
    })

# ─── CUSTOMERS ───────────────────────────────────────────────────────────────

@app.route('/customers')
@login_required
def customers():
    return render_template('customers.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))

@app.route('/api/customers')
@login_required
def api_customers():
    q = request.args.get('q', '')
    rows = db.search_customers(q)
    return jsonify([{'id':r[0],'name':r[1],'phone':r[2],'address':r[3],'created_at':r[4]} for r in rows])

@app.route('/api/customers', methods=['POST'])
@perm_required('add_customer')
def api_add_customer():
    data = request.get_json()
    success, msg, cid = db.add_customer(data.get('name',''), data.get('phone',''), data.get('address',''))
    return jsonify({'success': success, 'message': msg, 'id': cid})

@app.route('/api/customers/<int:cid>', methods=['PUT'])
@perm_required('edit_customer')
def api_update_customer(cid):
    data = request.get_json()
    success, msg = db.update_customer(cid, data.get('name',''), data.get('phone',''), data.get('address',''))
    return jsonify({'success': success, 'message': msg})

@app.route('/api/customers/<int:cid>', methods=['DELETE'])
@perm_required('delete_customer')
def api_delete_customer(cid):
    success, msg = db.delete_customer(cid)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/customers/<int:cid>/invoices')
@login_required
def api_customer_invoices(cid):
    rows = db.get_customer_invoices(cid)
    return jsonify([{'id':r[0],'date':fmt_date(r[1]),'total':r[2]} for r in rows])

# ─── PRODUCTS ────────────────────────────────────────────────────────────────

@app.route('/products')
@login_required
def products():
    return render_template('products.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))

@app.route('/api/products')
@login_required
def api_products():
    q = request.args.get('q', '')
    rows = db.search_products(q)
    return jsonify([{'id':r[0],'name':r[1],'barcode':r[2],'price':r[3],'cost_price':r[4],'stock':r[5],'category':r[6]} for r in rows])

@app.route('/api/products/barcode/<barcode>')
@login_required
def api_product_barcode(barcode):
    p = db.get_product_by_barcode(barcode)
    if p:
        return jsonify({'id':p[0],'name':p[1],'barcode':p[2],'price':p[3],'cost_price':p[4],'stock':p[5],'category':p[6]})
    return jsonify({'error': 'محصول یافت نشد'}), 404

@app.route('/api/products', methods=['POST'])
@perm_required('add_product')
def api_add_product():
    data = request.get_json()
    success, msg, pid = db.add_product(
        data.get('name',''), data.get('barcode',''), data.get('price',0),
        data.get('cost_price',0), data.get('stock',0), data.get('category','عمومی'))
    return jsonify({'success': success, 'message': msg, 'id': pid})

@app.route('/api/products/<int:pid>', methods=['PUT'])
@perm_required('edit_product')
def api_update_product(pid):
    data = request.get_json()
    success, msg = db.update_product(pid, data.get('name',''), data.get('barcode',''),
        data.get('price',0), data.get('cost_price',0), data.get('stock',0), data.get('category','عمومی'))
    return jsonify({'success': success, 'message': msg})

@app.route('/api/products/<int:pid>', methods=['DELETE'])
@perm_required('delete_product')
def api_delete_product(pid):
    success, msg = db.delete_product(pid)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/products/<int:pid>/stock', methods=['POST'])
@perm_required('edit_product')
def api_update_stock(pid):
    data = request.get_json()
    success, msg = db.update_stock(pid, int(data.get('quantity', 0)))
    return jsonify({'success': success, 'message': msg})

@app.route('/api/products/low-stock')
@login_required
def api_low_stock():
    rows = db.get_low_stock_products(10)
    return jsonify([{'id':r[0],'name':r[1],'barcode':r[2],'price':r[3],'stock':r[5],'category':r[6]} for r in rows])

# ─── INVOICES ────────────────────────────────────────────────────────────────

@app.route('/invoices')
@login_required
def invoices():
    return render_template('invoices.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))

@app.route('/api/invoices')
@login_required
def api_invoices():
    rows = db.get_all_invoices(200)
    return jsonify([{'id':r[0],'date':fmt_date(r[1]),'total':r[2],'customer':r[3]} for r in rows])

@app.route('/api/invoices', methods=['POST'])
@perm_required('create_invoice')
def api_create_invoice():
    data = request.get_json()
    customer_id = data.get('customer_id')
    items = data.get('items', [])
    success, msg, inv_id = db.create_invoice(customer_id, items)
    return jsonify({'success': success, 'message': msg, 'invoice_id': inv_id})

@app.route('/api/invoices/<int:inv_id>')
@login_required
def api_get_invoice(inv_id):
    inv = db.get_invoice(inv_id)
    if not inv:
        return jsonify({'error': 'فاکتور یافت نشد'}), 404
    inv['date'] = fmt_date(inv['date'])
    return jsonify(inv)

@app.route('/api/invoices/<int:inv_id>', methods=['DELETE'])
@perm_required('create_invoice')
def api_delete_invoice(inv_id):
    success, msg = db.delete_invoice(inv_id)
    return jsonify({'success': success, 'message': msg})

@app.route('/invoice/<int:inv_id>/view')
@login_required
def view_invoice(inv_id):
    inv = db.get_invoice(inv_id)
    if not inv:
        return "فاکتور یافت نشد", 404
    settings = db.get_invoice_settings()
    inv['date'] = fmt_date(inv['date'])
    inv['invoice_items'] = inv.pop('items', [])
    return render_template('invoice_view.html', invoice=inv, settings=settings)

# ─── REPORTS ─────────────────────────────────────────────────────────────────

@app.route('/reports')
@login_required
def reports():
    if not has_permission('view_reports'):
        return redirect(url_for('dashboard'))
    return render_template('reports.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))

@app.route('/api/reports/daily')
@perm_required('view_reports')
def api_daily_report():
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    data = db.get_daily_sales(date_str)
    if data:
        data['date_display'] = fmt_date(date_str + ' 00:00:00') if PERSIAN_DATE_AVAILABLE else date_str
    return jsonify(data or {})

@app.route('/api/reports/profit')
@perm_required('view_reports')
def api_profit_report():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    data = db.get_profit_report(start or None, end or None)
    return jsonify(data)

@app.route('/api/reports/best-selling')
@perm_required('view_reports')
def api_best_selling():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    rows = db.get_best_selling_products(start or None, end or None, 10)
    return jsonify([{'name':r[0],'qty':r[1],'revenue':r[2],'avg_price':r[3],'invoices':r[4]} for r in rows])

# ─── SETTINGS / USERS ────────────────────────────────────────────────────────

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))

@app.route('/api/settings/invoice', methods=['GET'])
@login_required
def api_get_invoice_settings():
    return jsonify(db.get_invoice_settings())

@app.route('/api/settings/invoice', methods=['POST'])
@perm_required('invoice_settings')
def api_save_invoice_settings():
    data = request.get_json()
    success, msg = db.save_invoice_settings(data)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/users')
@perm_required('manage_users')
def api_get_users():
    rows = db.get_all_users()
    return jsonify([{'username':r[0],'role':r[1],'created_at':r[2]} for r in rows])

@app.route('/api/users', methods=['POST'])
@perm_required('manage_users')
def api_create_user():
    data = request.get_json()
    success, msg = db.register_user(data.get('username',''), data.get('password',''), data.get('role','Cashier'))
    return jsonify({'success': success, 'message': msg})

@app.route('/api/users/<username>/role', methods=['PUT'])
@perm_required('manage_users')
def api_update_role(username):
    data = request.get_json()
    success, msg = db.update_user_role(username, data.get('role',''), session.get('username'))
    return jsonify({'success': success, 'message': msg})

@app.route('/api/users/<username>', methods=['DELETE'])
@perm_required('manage_users')
def api_delete_user(username):
    success, msg = db.delete_user(username, session.get('username'))
    return jsonify({'success': success, 'message': msg})

@app.route('/api/backup', methods=['POST'])
@perm_required('backup_restore')
def api_backup():
    success, msg, path = db.create_backup()
    return jsonify({'success': success, 'message': msg, 'path': path})

@app.route('/api/export/<table>')
@perm_required('export_data')
def api_export(table):
    allowed = ['customers', 'products', 'invoices', 'invoice_items']
    if table not in allowed:
        return jsonify({'error': 'مجاز نیست'}), 403
    output = io.StringIO()
    db.cursor.execute(f"SELECT * FROM {table}")
    rows = db.cursor.fetchall()
    db.cursor.execute(f"PRAGMA table_info({table})")
    cols = [c[1] for c in db.cursor.fetchall()]
    writer = csv.writer(output)
    writer.writerow(cols)
    writer.writerows(rows)
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{table}.csv'
    )

@app.route('/returns')
@login_required
def returns():
    if not has_permission('process_return'):
        return redirect(url_for('dashboard'))
    return render_template('returns.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))

@app.route('/api/returns/invoice/<int:inv_id>')
@perm_required('process_return')
def api_get_invoice_items_for_return(inv_id):
    items = db.get_invoice_items_for_return(inv_id)
    if not items:
        return jsonify({'error': 'فاکتور یافت نشد یا آیتمی ندارد'}), 404
    return jsonify([{
        'item_id': r[0], 'product_id': r[1], 'name': r[2],
        'quantity': r[3], 'unit_price': r[4], 'total': r[5]
    } for r in items])

@app.route('/api/returns', methods=['POST'])
@perm_required('process_return')
def api_process_return():
    data = request.get_json()
    success, msg, rid = db.process_return(
        data.get('invoice_id'), data.get('product_id'),
        data.get('quantity', 1), data.get('reason', 'سایر'),
        data.get('refund_amount', 0), session.get('username'), ''
    )
    return jsonify({'success': success, 'message': msg, 'id': rid})

@app.route('/api/returns/history')
@perm_required('process_return')
def api_returns_history():
    rows = db.get_returns_history(100)
    return jsonify([{
        'id': r[0], 'invoice_id': r[1], 'product': r[2],
        'quantity': r[3], 'refund': r[4], 'reason': r[5],
        'date': fmt_date(r[6]), 'processed_by': r[7], 'status': r[8]
    } for r in rows])

# ─── CUSTOMER PROFILE ────────────────────────────────────────────────────────

@app.route('/api/customers/<int:cid>/profile')
@login_required
def api_customer_profile(cid):
    c = db.get_customer(cid)
    if not c:
        return jsonify({'error': 'مشتری یافت نشد'}), 404
    invoices = db.get_customer_invoices(cid)
    total_spent = sum(r[2] for r in invoices)
    return jsonify({
        'id': c[0], 'name': c[1], 'phone': c[2], 'address': c[3], 'created_at': c[4],
        'invoice_count': len(invoices),
        'total_spent': total_spent,
        'invoices': [{'id': r[0], 'date': fmt_date(r[1]), 'total': r[2]} for r in invoices]
    })

# ─── AUDIT LOG ───────────────────────────────────────────────────────────────

@app.route('/api/audit-log')
@perm_required('manage_users')
def api_audit_log():
    rows = db.get_audit_log(200)
    return jsonify([{
        'timestamp': r[0], 'username': r[1], 'action': r[2],
        'table': r[3], 'record_id': r[4], 'details': r[5]
    } for r in rows])

# ─── RESTORE BACKUP ──────────────────────────────────────────────────────────

@app.route('/api/restore', methods=['POST'])
@perm_required('backup_restore')
def api_restore():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'فایل انتخاب نشده'})
    f = request.files['file']
    if not f.filename.endswith('.db'):
        return jsonify({'success': False, 'message': 'فقط فایل .db قابل قبول است'})
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    f.save(tmp.name)
    success, msg = db.restore_backup(tmp.name)
    return jsonify({'success': success, 'message': msg})

# ─── INVENTORY & LOW STOCK PAGES ─────────────────────────────────────────────

@app.route('/inventory')
@login_required
def inventory():
    return render_template('inventory.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))

@app.route('/low-stock')
@login_required
def low_stock():
    return render_template('low_stock.html',
        username=session.get('username'), role=session.get('role'),
        permissions=PERMISSIONS.get(session.get('role'), {}))


@app.route('/api/persian-today')
@login_required
def api_persian_today():
    if PERSIAN_DATE_AVAILABLE:
        from persian_date import shamsi_now
        return jsonify({'date': shamsi_now()})
    from datetime import datetime
    return jsonify({'date': datetime.now().strftime('%Y/%m/%d')})


@app.route('/api/shamsi-to-gregorian')
@login_required
def api_shamsi_to_gregorian():
    date_str = request.args.get('date', '')
    if PERSIAN_DATE_AVAILABLE:
        from persian_date import shamsi_to_gregorian
        greg = shamsi_to_gregorian(date_str)
        if greg:
            return jsonify({'gregorian': greg})
    return jsonify({'gregorian': date_str})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🌐 نرم‌افزار حسابداری - نسخه وب")
    print(f"📱 در مرورگر باز کنید: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)

# ─── RETURNS ─────────────────────────────────────────────────────────────────

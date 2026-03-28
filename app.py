# نظام نقاط البيع المتكامل - نسخة نهائية تعمل
# مع: استعادة كلمة المرور، تغيير كلمة المرور، طباعة الفواتير

from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import json
import os
import secrets

# ===================== تهيئة التطبيق =====================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'my-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ===================== نماذج قاعدة البيانات =====================
# يجب تعريف نموذج User أولاً لأنه مرجع للمفاتيح الخارجية
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(20), default='cashier')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # حقول استعادة كلمة المرور
    security_question = db.Column(db.String(200))
    security_answer_hash = db.Column(db.String(200))
    reset_token = db.Column(db.String(100))
    reset_token_expiry = db.Column(db.DateTime)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def set_security_answer(self, answer):
        self.security_answer_hash = generate_password_hash(answer.lower().strip())
    
    def check_security_answer(self, answer):
        return check_password_hash(self.security_answer_hash, answer.lower().strip())
    
    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expiry = datetime.utcnow() + timedelta(hours=24)
        return self.reset_token
    
    def is_admin(self):
        return self.role == 'admin'

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, default=0)
    quantity = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), default='cash')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    
    user = db.relationship('User')
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')
    
    def generate_number(self):
        return f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"

class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    product_name = db.Column(db.String(100))
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, default=0)
    quantity = db.Column(db.Integer, default=1)
    subtotal = db.Column(db.Float, nullable=False)
    
    product = db.relationship('Product')

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50))
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    user = db.relationship('User')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('❌ غير مصرح لك بالدخول', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ===================== قوالب HTML =====================

LOGIN_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول - نظام البيع</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 90%;
            max-width: 380px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        h2 { text-align: center; margin-bottom: 30px; color: #333; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 10px;
            font-size: 16px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            cursor: pointer;
            margin-top: 20px;
        }
        .alert {
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 10px;
            margin-bottom: 15px;
            text-align: center;
        }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #667eea; text-decoration: none; font-size: 14px; }
        .links a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🏪 نظام نقاط البيع</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                    <div class="alert">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" placeholder="اسم المستخدم" required autofocus>
            <input type="password" name="password" placeholder="كلمة المرور" required>
            <button type="submit">دخول</button>
        </form>
        <div class="links">
            <a href="/forgot_password">🔑 نسيت كلمة المرور؟</a>
        </div>
        <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
            المستخدم: admin | admin123
        </div>
    </div>
</body>
</html>
'''

PROFILE_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الملف الشخصي</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body { background: #f0f2f5; padding: 15px; }
        .card {
            background: white;
            border-radius: 20px;
            padding: 30px;
            max-width: 500px;
            margin: 20px auto;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }
        h2 { text-align: center; margin-bottom: 25px; color: #333; }
        .info { background: #f8f9fa; padding: 15px; border-radius: 10px; margin-bottom: 20px; }
        .info p { margin: 8px 0; }
        input, select {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 10px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 10px;
        }
        .btn-back { background: #95a5a6; margin-top: 15px; }
        .alert {
            padding: 10px;
            border-radius: 10px;
            margin-bottom: 15px;
            text-align: center;
        }
        .alert-success { background: #d4edda; color: #155724; }
        .alert-danger { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="card">
        <h2>👤 الملف الشخصي</h2>
        <div class="info">
            <p><strong>اسم المستخدم:</strong> {{ user.username }}</p>
            <p><strong>الاسم الكامل:</strong> {{ user.full_name or 'غير محدد' }}</p>
            <p><strong>الصلاحية:</strong> {% if user.is_admin() %}👑 مدير{% else %}👤 كاشير{% endif %}</p>
            <p><strong>تاريخ التسجيل:</strong> {{ user.created_at.strftime('%Y-%m-%d') }}</p>
        </div>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                    <div class="alert alert-{{ category }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <h3>🔐 تغيير كلمة المرور</h3>
        <form method="POST" action="/change_password">
            <input type="password" name="current_password" placeholder="كلمة المرور الحالية" required>
            <input type="password" name="new_password" placeholder="كلمة المرور الجديدة" required>
            <input type="password" name="confirm_password" placeholder="تأكيد كلمة المرور الجديدة" required>
            <button type="submit">تغيير كلمة المرور</button>
        </form>
        {% if not user.security_question %}
        <h3 style="margin-top: 20px;">🔒 إعداد سؤال استعادة كلمة المرور</h3>
        <form method="POST" action="/set_security_question">
            <select name="question">
                <option value="ما هو اسم والدتك؟">ما هو اسم والدتك؟</option>
                <option value="ما هو اسم مدرستك الأولى؟">ما هو اسم مدرستك الأولى؟</option>
                <option value="ما هو اسم حيوانك الأليف؟">ما هو اسم حيوانك الأليف؟</option>
                <option value="ما هو اسم المدينة التي ولدت فيها؟">ما هو اسم المدينة التي ولدت فيها؟</option>
            </select>
            <input type="text" name="answer" placeholder="الإجابة" required>
            <button type="submit">حفظ السؤال السري</button>
        </form>
        {% endif %}
        <a href="/dashboard"><button class="btn-back">🔙 رجوع</button></a>
    </div>
</body>
</html>
'''

FORGOT_PASSWORD_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>استعادة كلمة المرور</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .card {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 90%;
            max-width: 400px;
        }
        h2 { text-align: center; margin-bottom: 25px; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 10px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            margin-top: 15px;
        }
        .btn-back { background: #95a5a6; margin-top: 10px; }
        .alert { padding: 10px; border-radius: 10px; margin-bottom: 15px; text-align: center; }
        .alert-danger { background: #f8d7da; color: #721c24; }
        .alert-success { background: #d4edda; color: #155724; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔑 استعادة كلمة المرور</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                    <div class="alert alert-{{ category }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="username" placeholder="اسم المستخدم" required>
            <button type="submit">التالي</button>
        </form>
        <a href="/login"><button class="btn-back">🔙 العودة</button></a>
    </div>
</body>
</html>
'''

SECURITY_QUESTION_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>السؤال السري</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .card {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 90%;
            max-width: 400px;
        }
        h2 { text-align: center; margin-bottom: 20px; }
        .question {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
            text-align: center;
            font-size: 18px;
        }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 10px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            margin-top: 15px;
        }
        .btn-back { background: #95a5a6; margin-top: 10px; }
        .alert { padding: 10px; border-radius: 10px; margin-bottom: 15px; text-align: center; }
        .alert-danger { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔐 التحقق من الهوية</h2>
        <div class="question">
            <strong>السؤال السري:</strong><br>
            {{ question }}
        </div>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                    <div class="alert alert-{{ category }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="text" name="answer" placeholder="الإجابة" required>
            <button type="submit">تحقق</button>
        </form>
        <a href="/forgot_password"><button class="btn-back">🔙 رجوع</button></a>
    </div>
</body>
</html>
'''

RESET_PASSWORD_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>إعادة تعيين كلمة المرور</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .card {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 90%;
            max-width: 400px;
        }
        h2 { text-align: center; margin-bottom: 25px; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 10px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            margin-top: 15px;
        }
        .btn-back { background: #95a5a6; margin-top: 10px; }
        .alert { padding: 10px; border-radius: 10px; margin-bottom: 15px; text-align: center; }
        .alert-danger { background: #f8d7da; color: #721c24; }
        .alert-success { background: #d4edda; color: #155724; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔄 إعادة تعيين كلمة المرور</h2>
        <p style="text-align:center; color:#666; margin-bottom:20px;">المستخدم: {{ username }}</p>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                    <div class="alert alert-{{ category }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="POST">
            <input type="password" name="new_password" placeholder="كلمة المرور الجديدة" required>
            <input type="password" name="confirm_password" placeholder="تأكيد كلمة المرور" required>
            <button type="submit">تغيير كلمة المرور</button>
        </form>
        <a href="/login"><button class="btn-back">🔙 العودة</button></a>
    </div>
</body>
</html>
'''

INVOICE_PRINT_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>فاتورة {{ invoice.invoice_number }}</title>
    <style>
        * { font-family: 'Tahoma', 'Arial', sans-serif; margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #f5f5f5; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .invoice {
            max-width: 400px;
            margin: auto;
            background: white;
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }
        .header { text-align: center; border-bottom: 2px dashed #ddd; padding-bottom: 15px; margin-bottom: 15px; }
        .header h1 { color: #2c3e50; font-size: 24px; margin-bottom: 5px; }
        .invoice-info { background: #f8f9fa; padding: 10px; border-radius: 10px; margin-bottom: 15px; font-size: 12px; }
        .invoice-info div { display: flex; justify-content: space-between; margin: 5px 0; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 12px; }
        th, td { padding: 8px; border-bottom: 1px solid #eee; text-align: center; }
        th { background: #f8f9fa; font-weight: bold; }
        .grand-total { font-size: 18px; font-weight: bold; color: #27ae60; margin-top: 10px; padding-top: 10px; border-top: 2px solid #27ae60; text-align: left; }
        .payment-info { background: #e8f5e9; padding: 10px; border-radius: 10px; margin: 15px 0; text-align: center; }
        .footer { text-align: center; margin-top: 20px; padding-top: 15px; border-top: 1px dashed #ddd; font-size: 10px; color: #999; }
        @media print { body { background: white; padding: 0; } .invoice { box-shadow: none; padding: 10px; } .no-print { display: none; } }
        .no-print { text-align: center; margin-top: 15px; }
        button { padding: 10px 20px; background: #3498db; color: white; border: none; border-radius: 8px; cursor: pointer; margin: 5px; }
        button.print-btn { background: #27ae60; }
        button.close-btn { background: #95a5a6; }
    </style>
</head>
<body>
    <div class="invoice">
        <div class="header">
            <h1>🏪 نظام نقاط البيع</h1>
        </div>
        <div class="invoice-info">
            <div><span>📄 رقم الفاتورة:</span><span>{{ invoice.invoice_number }}</span></div>
            <div><span>📅 التاريخ:</span><span>{{ invoice.date.strftime('%Y-%m-%d %H:%M') }}</span></div>
            <div><span>👤 البائع:</span><span>{{ invoice.user.full_name or invoice.user.username }}</span></div>
        </div>
        <table>
            <thead><tr><th>المنتج</th><th>السعر</th><th>الكمية</th><th>الإجمالي</th></tr></thead>
            <tbody>
                {% for item in invoice.items %}
                <tr><td>{{ item.product_name }}</td><td>{{ "%.2f"|format(item.price) }}</td><td>{{ item.quantity }}</td><td>{{ "%.2f"|format(item.subtotal) }}</td></tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="grand-total">الإجمالي: {{ "%.2f"|format(invoice.total) }} ريال</div>
        <div class="payment-info">💳 طريقة الدفع: {% if invoice.payment_method == 'cash' %}كاش{% else %}شبكة{% endif %}</div>
        {% if invoice.notes %}
        <div style="background:#fff3e0; padding:10px; border-radius:10px; margin:15px 0; font-size:11px;">📝 ملاحظات: {{ invoice.notes }}</div>
        {% endif %}
        <div class="footer"><p>شكراً لتسوقكم معنا</p><p>🌟 هذه الفاتورة إلكترونية صالحة للاستخدام 🌟</p></div>
        <div class="no-print">
            <button class="print-btn" onclick="window.print()">🖨️ طباعة</button>
            <button class="close-btn" onclick="window.close()">❌ إغلاق</button>
        </div>
    </div>
    <script>setTimeout(function() { window.print(); }, 500);</script>
</body>
</html>
'''

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة التحكم</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body { background: #f0f2f5; }
        .navbar {
            background: #2c3e50;
            color: white;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }
        .navbar a { color: white; text-decoration: none; margin-left: 15px; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 15px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }
        .stat-card { background: white; border-radius: 15px; padding: 20px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-card h3 { font-size: 24px; color: #27ae60; margin-top: 10px; }
        .menu-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
        .menu-card {
            background: white; border-radius: 15px; padding: 25px; text-align: center; cursor: pointer;
            transition: all 0.3s; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-decoration: none; color: inherit; display: block;
        }
        .menu-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px rgba(0,0,0,0.15); }
        .menu-icon { font-size: 48px; margin-bottom: 15px; }
        button { background: #e74c3c; color: white; padding: 8px 20px; border: none; border-radius: 8px; cursor: pointer; }
        .user-info { display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }
        .profile-link { background: #3498db; padding: 8px 15px; border-radius: 8px; }
        @media (max-width: 768px) { .navbar { flex-direction: column; gap: 10px; text-align: center; } }
    </style>
</head>
<body>
    <div class="navbar">
        <h2>🏪 نظام نقاط البيع</h2>
        <div class="user-info">
            <a href="/profile" class="profile-link">👤 {{ username }}</a>
            <span>{% if is_admin %}👑 مدير{% else %}👤 كاشير{% endif %}</span>
            <a href="/logout"><button>خروج</button></a>
        </div>
    </div>
    <div class="container">
        <div class="stats">
            <div class="stat-card"><div>💰 مبيعات اليوم</div><h3>{{ daily_sales }} ريال</h3></div>
            <div class="stat-card"><div>📊 أرباح اليوم</div><h3 style="color: #3498db;">{{ daily_profit }} ريال</h3></div>
            <div class="stat-card"><div>📦 عدد الفواتير</div><h3>{{ daily_invoices }}</h3></div>
            <div class="stat-card"><div>⚠️ منتجات منخفضة</div><h3 style="color: #e74c3c;">{{ low_stock_count }}</h3></div>
        </div>
        <div class="menu-grid">
            <a href="/cashier" class="menu-card"><div class="menu-icon">💰</div><h3>الكاشير</h3><p>إجراء عمليات البيع</p></a>
            <a href="/products" class="menu-card"><div class="menu-icon">📦</div><h3>المنتجات</h3><p>إدارة المخزون</p></a>
            <a href="/reports" class="menu-card"><div class="menu-icon">📊</div><h3>التقارير</h3><p>تقارير المبيعات والأرباح</p></a>
            <a href="/accounting" class="menu-card"><div class="menu-icon">🏦</div><h3>مركز الحسابات</h3><p>الأرباح والخسائر والمصاريف</p></a>
            {% if is_admin %}<a href="/users" class="menu-card"><div class="menu-icon">👥</div><h3>المستخدمين</h3><p>إضافة وحذف المستخدمين</p></a>{% endif %}
        </div>
    </div>
</body>
</html>
'''

CASHIER_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الكاشير</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body { background: #f0f2f5; padding: 15px; }
        .card { background: white; border-radius: 15px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        input, select { padding: 12px; border: 1px solid #ddd; border-radius: 10px; width: 100%; margin: 5px 0; font-size: 16px; }
        button { padding: 10px 20px; background: #3498db; color: white; border: none; border-radius: 10px; cursor: pointer; margin: 5px; }
        .btn-success { background: #27ae60; }
        .btn-danger { background: #e74c3c; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 12px; border: 1px solid #ddd; text-align: center; }
        th { background: #2c3e50; color: white; }
        .total { font-size: 24px; font-weight: bold; color: #27ae60; text-align: left; margin-top: 15px; }
        .search-box { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .search-box input { flex: 1; }
        @media (max-width: 768px) { th, td { padding: 8px; font-size: 12px; } }
    </style>
</head>
<body>
    <div class="card">
        <h2>🛒 فاتورة البيع</h2>
        <div class="search-box">
            <input type="text" id="barcode" placeholder="باركود المنتج أو الاسم" autofocus>
            <button onclick="searchProduct()">🔍 بحث</button>
        </div>
        <div style="overflow-x: auto;">
            <table id="cart-table">
                <thead><tr><th>المنتج</th><th>السعر</th><th>الكمية</th><th>الإجمالي</th><th></th></tr></thead>
                <tbody id="cart"></tbody>
                <tfoot><tr><td colspan="3" style="text-align:left; font-weight:bold;">الإجمالي:</td><td colspan="2" id="total" style="font-weight:bold; color:#27ae60;">0.00 ريال</td></tr></tfoot>
            </table>
        </div>
        <div style="display: flex; gap: 10px; justify-content: space-between; flex-wrap: wrap; margin-top: 15px;">
            <select id="payment" style="width: auto;"><option value="cash">💵 كاش</option><option value="card">💳 شبكة</option></select>
            <textarea id="notes" rows="2" placeholder="ملاحظات" style="flex: 1;"></textarea>
            <div>
                <button class="btn-success" onclick="saveInvoice()">💾 حفظ</button>
                <button class="btn-danger" onclick="clearCart()">🗑️ تفريغ</button>
                <a href="/dashboard"><button>🔙 رجوع</button></a>
            </div>
        </div>
    </div>
    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script>
        let cart = [], total = 0;
        $('#barcode').keypress(function(e) { if(e.which == 13) searchProduct(); });
        function searchProduct() {
            let query = $('#barcode').val().trim();
            if(!query) return;
            $.ajax({ url: '/api/product/search?q=' + encodeURIComponent(query), success: function(products) {
                if(products.length == 0) alert('❌ المنتج غير موجود');
                else if(products.length == 1) addToCart(products[0]);
                else {
                    let msg = products.map((p,i) => `${i+1}- ${p.name} (${p.price} ريال)`).join('\\n');
                    let choice = prompt('اختر المنتج:\\n' + msg);
                    if(choice && products[choice-1]) addToCart(products[choice-1]);
                }
                $('#barcode').val('').focus();
            }});
        }
        function addToCart(product) {
            if(product.quantity <= 0) { alert('❌ المنتج غير متوفر'); return; }
            let existing = cart.find(item => item.id === product.id);
            if(existing) { existing.qty++; existing.subtotal = existing.price * existing.qty; }
            else { cart.push({ id: product.id, name: product.name, price: product.price, qty: 1, subtotal: product.price }); }
            updateCart();
        }
        function updateCart() {
            let html = ''; total = 0;
            cart.forEach((item, i) => {
                total += item.subtotal;
                html += `<tr><td>${item.name}</td><td>${item.price.toFixed(2)}</td><td><button onclick="updateQty(${i}, -1)">-</button> ${item.qty} <button onclick="updateQty(${i}, 1)">+</button></td><td>${item.subtotal.toFixed(2)}</td><td><button onclick="removeItem(${i})" style="background:#e74c3c;">✖</button></td></tr>`;
            });
            $('#cart').html(html);
            $('#total').text(total.toFixed(2) + ' ريال');
        }
        function updateQty(i, delta) {
            let newQty = cart[i].qty + delta;
            if(newQty < 1) { removeItem(i); return; }
            cart[i].qty = newQty;
            cart[i].subtotal = cart[i].price * newQty;
            updateCart();
        }
        function removeItem(i) { cart.splice(i, 1); updateCart(); }
        function clearCart() { if(confirm('تفريغ الفاتورة؟')) { cart = []; updateCart(); } }
        function saveInvoice() {
            if(cart.length === 0) { alert('❌ لا توجد منتجات'); return; }
            $.ajax({ url: '/save_invoice', method: 'POST', contentType: 'application/json', data: JSON.stringify({ items: cart, payment: $('#payment').val(), total: total, notes: $('#notes').val() }),
                success: function(res) { if(res.success) { alert('✅ تم حفظ الفاتورة'); window.open('/invoice/' + res.invoice_id, '_blank'); clearCart(); $('#notes').val(''); } else alert('❌ ' + res.error); }
            });
        }
    </script>
</body>
</html>
'''

PRODUCTS_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>المنتجات</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tahoma', sans-serif; }
        body { background: #f0f2f5; padding: 15px; }
        .card { background: white; border-radius: 15px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 12px; border: 1px solid #ddd; text-align: center; }
        th { background: #2c3e50; color: white; }
        button { padding: 8px 15px; background: #27ae60; color: white; border: none; border-radius: 8px; cursor: pointer; }
        .btn-edit { background: #f39c12; }
        .btn-delete { background: #e74c3c; }
        .btn-back { background: #95a5a6; margin-top: 15px; }
        .btn-add { margin-bottom: 15px; }
        .search-box { display: flex; gap: 10px; margin-bottom: 20px; }
        .search-box input { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 8px; }
        .low-stock { background: #f8d7da; }
    </style>
</head>
<body>
    <div class="card">
        <h2>📦 إدارة المنتجات</h2>
        {% if is_admin %}<a href="/add_product"><button class="btn-add">+ منتج جديد</button></a>{% endif %}
        <div class="search-box"><input type="text" id="search" placeholder="بحث"><button onclick="searchProducts()">🔍 بحث</button></div>
        <div style="overflow-x: auto;">
            <table><thead><tr><th>الباركود</th><th>المنتج</th><th>سعر الشراء</th><th>سعر البيع</th><th>الكمية</th><th>الحالة</th>{% if is_admin %}<th></th>{% endif %}</tr></thead>
            <tbody id="products-list">
                {% for p in products %}
                <tr {% if p.quantity <= 5 %}class="low-stock"{% endif %}>
                    <td>{{ p.barcode }}</td><td>{{ p.name }}</td><td>{{ "%.2f"|format(p.cost) }} ريال</td><td>{{ "%.2f"|format(p.price) }} ريال</td>
                    <td>{{ p.quantity }}</td><td>{% if p.quantity <= 0 %}⚠️ نفد{% elif p.quantity <= 5 %}⚠️ منخفض{% else %}✅ متوفر{% endif %}</td>
                    {% if is_admin %}<td><a href="/edit_product/{{ p.id }}"><button class="btn-edit">تعديل</button></a><button class="btn-delete" onclick="deleteProduct({{ p.id }})">حذف</button></td>{% endif %}
                </tr>
                {% endfor %}
            </tbody></table>
        </div>
        <a href="/dashboard"><button class="btn-back">🔙 رجوع</button></a>
    </div>
    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script>
        function searchProducts() { let q = $('#search').val(); if(!q) location.reload(); else $.ajax({ url: '/api/products/search?q='+encodeURIComponent(q), success: function(p) { let h=''; p.forEach(pr=>{ h+=`<tr><td>${pr.barcode}</td><td>${pr.name}</td><td>${pr.cost} ريال</td><td>${pr.price} ريال</td><td>${pr.quantity}</td><td>${pr.quantity<=0?'⚠️ نفد':'✅ متوفر'}</td>{% if is_admin %}<td><a href="/edit_product/${pr.id}"><button class="btn-edit">تعديل</button></a><button class="btn-delete" onclick="deleteProduct(${pr.id})">حذف</button></td>{% endif %}</tr>`; }); $('#products-list').html(h); } }); }
        function deleteProduct(id) { if(confirm('حذف المنتج؟')) $.ajax({ url: '/api/product/delete/'+id, method:'POST', success:function(r){ if(r.success){ alert('✅ تم الحذف'); location.reload(); } } }); }
    </script>
</body>
</html>
'''

ADD_PRODUCT_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>إضافة منتج</title>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Tahoma',sans-serif;}body{background:#f0f2f5;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:15px;}.card{background:white;border-radius:20px;padding:30px;width:100%;max-width:450px;box-shadow:0 10px 25px rgba(0,0,0,0.1);}h2{text-align:center;margin-bottom:25px;}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:10px;}button{width:100%;padding:12px;background:#27ae60;color:white;border:none;border-radius:10px;cursor:pointer;margin-top:15px;}.btn-back{background:#95a5a6;margin-top:10px;}.row{display:flex;gap:10px;}.row input{width:50%;}</style></head>
<body><div class="card"><h2>➕ منتج جديد</h2><form method="POST"><input type="text" name="barcode" placeholder="الباركود" required><input type="text" name="name" placeholder="اسم المنتج" required><div class="row"><input type="number" step="0.01" name="cost" placeholder="سعر الشراء" required><input type="number" step="0.01" name="price" placeholder="سعر البيع" required></div><input type="number" name="quantity" placeholder="الكمية" value="0"><button type="submit">💾 حفظ</button><a href="/products"><button type="button" class="btn-back">🔙 إلغاء</button></a></form></div></body></html>
'''

EDIT_PRODUCT_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>تعديل منتج</title>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Tahoma',sans-serif;}body{background:#f0f2f5;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:15px;}.card{background:white;border-radius:20px;padding:30px;width:100%;max-width:450px;box-shadow:0 10px 25px rgba(0,0,0,0.1);}h2{text-align:center;margin-bottom:25px;}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:10px;}button{width:100%;padding:12px;background:#f39c12;color:white;border:none;border-radius:10px;cursor:pointer;margin-top:15px;}.btn-back{background:#95a5a6;margin-top:10px;}.row{display:flex;gap:10px;}.row input{width:50%;}</style></head>
<body><div class="card"><h2>✏️ تعديل: {{ product.name }}</h2><form method="POST"><input type="text" name="barcode" value="{{ product.barcode }}" required><input type="text" name="name" value="{{ product.name }}" required><div class="row"><input type="number" step="0.01" name="cost" value="{{ product.cost }}" required><input type="number" step="0.01" name="price" value="{{ product.price }}" required></div><input type="number" name="quantity" value="{{ product.quantity }}"><button type="submit">💾 تحديث</button><a href="/products"><button type="button" class="btn-back">🔙 إلغاء</button></a></form></div></body></html>
'''

USERS_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>المستخدمين</title>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Tahoma',sans-serif;}body{background:#f0f2f5;padding:15px;}.card{background:white;border-radius:15px;padding:20px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}table{width:100%;border-collapse:collapse;margin:15px 0;}th,td{padding:12px;border:1px solid #ddd;text-align:center;}th{background:#2c3e50;color:white;}button{padding:8px 15px;background:#27ae60;color:white;border:none;border-radius:8px;cursor:pointer;}.btn-delete{background:#e74c3c;}.btn-back{background:#95a5a6;margin-top:15px;}.btn-add{margin-bottom:15px;}.admin-badge{background:#e74c3c;color:white;padding:3px 8px;border-radius:10px;}.cashier-badge{background:#3498db;color:white;padding:3px 8px;border-radius:10px;}</style></head>
<body><div class="card"><h2>👥 المستخدمين</h2><a href="/add_user"><button class="btn-add">+ مستخدم جديد</button></a>
<div style="overflow-x:auto;"><table><thead><tr><th>اسم المستخدم</th><th>الاسم الكامل</th><th>الصلاحية</th><th>تاريخ التسجيل</th><th></th></tr></thead>
<tbody>{% for u in users %}<tr><td>{{ u.username }}</td><td>{{ u.full_name or '-' }}</td><td>{% if u.is_admin() %}<span class="admin-badge">👑 مدير</span>{% else %}<span class="cashier-badge">👤 كاشير</span>{% endif %}</td><td>{{ u.created_at.strftime('%Y-%m-%d') }}</td>
<td>{% if u.id != current_user.id %}<button class="btn-delete" onclick="deleteUser({{ u.id }})">حذف</button>{% else %}<span style="color:gray;">أنت</span>{% endif %}</td></tr>{% endfor %}</tbody></table></div>
<a href="/dashboard"><button class="btn-back">🔙 رجوع</button></a></div>
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script>function deleteUser(id){if(confirm('حذف المستخدم؟')) $.ajax({url:'/api/user/delete/'+id,method:'POST',success:function(r){if(r.success){alert('✅ تم الحذف');location.reload();}}});}</script></body></html>
'''

ADD_USER_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>إضافة مستخدم</title>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Tahoma',sans-serif;}body{background:#f0f2f5;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:15px;}.card{background:white;border-radius:20px;padding:30px;width:100%;max-width:400px;box-shadow:0 10px 25px rgba(0,0,0,0.1);}h2{text-align:center;margin-bottom:25px;}input,select{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:10px;}button{width:100%;padding:12px;background:#27ae60;color:white;border:none;border-radius:10px;cursor:pointer;margin-top:15px;}.btn-back{background:#95a5a6;margin-top:10px;}</style></head>
<body><div class="card"><h2>➕ مستخدم جديد</h2><form method="POST"><input type="text" name="username" placeholder="اسم المستخدم" required><input type="text" name="full_name" placeholder="الاسم الكامل"><input type="password" name="password" placeholder="كلمة المرور" required><select name="role"><option value="cashier">👤 كاشير</option><option value="admin">👑 مدير</option></select><button type="submit">💾 حفظ</button><a href="/users"><button type="button" class="btn-back">🔙 إلغاء</button></a></form></div></body></html>
'''

REPORTS_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>التقارير</title>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Tahoma',sans-serif;}body{background:#f0f2f5;padding:15px;}.card{background:white;border-radius:15px;padding:20px;margin-bottom:20px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}.report-header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:15px;margin-bottom:20px;}input,select{padding:10px;border:1px solid #ddd;border-radius:8px;}button{padding:10px 20px;background:#3498db;color:white;border:none;border-radius:8px;cursor:pointer;}.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin-bottom:20px;}.stat-box{background:#f8f9fa;border-radius:10px;padding:15px;text-align:center;}.stat-box h3{font-size:24px;margin-top:8px;}.profit{color:#27ae60;}.btn-back{background:#95a5a6;margin-top:15px;}table{width:100%;border-collapse:collapse;margin:15px 0;}th,td{padding:10px;border:1px solid #ddd;text-align:center;}th{background:#2c3e50;color:white;}</style></head>
<body><div class="card"><h2>📊 التقارير</h2>
<div class="card"><div class="report-header"><h3>📅 تقرير يومي</h3><div><input type="date" id="daily-date" value="{{ today }}"><button onclick="loadDaily()">عرض</button></div></div><div id="daily-report"></div></div>
<div class="card"><div class="report-header"><h3>📈 تقرير شهري</h3><div><input type="month" id="monthly-date" value="{{ today[:7] }}"><button onclick="loadMonthly()">عرض</button></div></div><div id="monthly-report"></div></div>
<div class="card"><div class="report-header"><h3>📊 تقرير سنوي</h3><div><input type="number" id="year" value="{{ year }}"><button onclick="loadYearly()">عرض</button></div></div><div id="yearly-report"></div></div>
<div class="card"><h3>🏆 أفضل المنتجات</h3><div id="top-products"></div></div>
<a href="/dashboard"><button class="btn-back">🔙 رجوع</button></a></div>
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script>
function loadDaily(){let d=$('#daily-date').val();$.ajax({url:'/api/reports/daily?date='+d,success:function(data){$('#daily-report').html(`<div class="stats-grid"><div class="stat-box"><div>💰 المبيعات</div><h3>${data.total_sales.toFixed(2)} ريال</h3></div><div class="stat-box"><div>📊 الفواتير</div><h3>${data.total_invoices}</h3></div><div class="stat-box"><div class="profit">📈 الأرباح</div><h3 class="profit">${data.profit.toFixed(2)} ريال</h3></div></div><h4>الفواتير</h4><table><thead><tr><th>رقم</th><th>الوقت</th><th>البائع</th><th>الإجمالي</th></tr></thead><tbody>${data.invoices.map(i=>`<tr><td>${i.number}</td><td>${i.time}</td><td>${i.user}</td><td>${i.total.toFixed(2)} ريال</td></tr>`).join('')}</tbody></table>`);}});}
function loadMonthly(){let m=$('#monthly-date').val();$.ajax({url:'/api/reports/monthly?month='+m,success:function(data){$('#monthly-report').html(`<div class="stats-grid"><div class="stat-box"><div>💰 المبيعات</div><h3>${data.total_sales.toFixed(2)} ريال</h3></div><div class="stat-box"><div>📊 الفواتير</div><h3>${data.total_invoices}</h3></div><div class="stat-box"><div class="profit">📈 الأرباح</div><h3 class="profit">${data.profit.toFixed(2)} ريال</h3></div></div><h4>المبيعات اليومية</h4><table><thead><tr><th>اليوم</th><th>المبيعات</th><th>الفواتير</th></tr></thead><tbody>${Object.entries(data.daily_breakdown).map(([d,val])=>`<tr><td>${d}</td><td>${val.sales.toFixed(2)} ريال</td><td>${val.count}</td></tr>`).join('')}</tbody></table>`);}});}
function loadYearly(){let y=$('#year').val();$.ajax({url:'/api/reports/yearly?year='+y,success:function(data){$('#yearly-report').html(`<div class="stats-grid"><div class="stat-box"><div>💰 المبيعات السنوية</div><h3>${data.total_sales.toFixed(2)} ريال</h3></div><div class="stat-box"><div>📊 الفواتير</div><h3>${data.total_invoices}</h3></div><div class="stat-box"><div class="profit">📈 الأرباح</div><h3 class="profit">${data.profit.toFixed(2)} ريال</h3></div></div><h4>المبيعات الشهرية</h4><table><thead><tr><th>الشهر</th><th>المبيعات</th><th>الفواتير</th><th>الربح</th></tr></thead><tbody>${Object.entries(data.monthly_breakdown).map(([m,val])=>`<tr><td>${m}</td><td>${val.sales.toFixed(2)} ريال</td><td>${val.count}</td><td>${val.profit.toFixed(2)} ريال</td></tr>`).join('')}</tbody></table>`);}});}
function loadTopProducts(){$.ajax({url:'/api/reports/top_products',success:function(data){if(data.length){$('#top-products').html(`<table><thead><tr><th>#</th><th>المنتج</th><th>الكمية</th><th>الإيرادات</th></tr></thead><tbody>${data.map((p,i)=>`<tr><td>${i+1}</td><td>${p.name}</td><td>${p.total_sold}</td><td>${p.total_revenue.toFixed(2)} ريال</td></tr>`).join('')}</tbody></table>`);}else{$('#top-products').html('<p>لا توجد مبيعات</p>');}}});}
$(document).ready(function(){loadDaily();loadMonthly();loadYearly();loadTopProducts();});
</script></body></html>
'''

ACCOUNTING_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>مركز الحسابات</title>
<style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Tahoma',sans-serif;}body{background:#f0f2f5;padding:15px;}.card{background:white;border-radius:15px;padding:20px;margin-bottom:20px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin-bottom:20px;}.stat-box{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border-radius:15px;padding:20px;text-align:center;}.stat-box h3{font-size:28px;margin-top:10px;}.profit-box{background:linear-gradient(135deg,#27ae60 0%,#2ecc71 100%);}.expense-box{background:linear-gradient(135deg,#f39c12 0%,#e67e22 100%);}table{width:100%;border-collapse:collapse;margin:15px 0;}th,td{padding:12px;border:1px solid #ddd;text-align:center;}th{background:#2c3e50;color:white;}input,select,textarea{padding:10px;border:1px solid #ddd;border-radius:8px;width:100%;margin:5px 0;}button{padding:10px 20px;background:#27ae60;color:white;border:none;border-radius:8px;cursor:pointer;}.btn-back{background:#95a5a6;margin-top:15px;}.row{display:flex;gap:10px;flex-wrap:wrap;}.row>div{flex:1;min-width:150px;}</style></head>
<body><div class="card"><h2>🏦 مركز الحسابات</h2><div class="stats-grid"><div class="stat-box"><div>💰 الإيرادات</div><h3>{{ total_revenue }} ريال</h3></div><div class="stat-box expense-box"><div>📉 المصاريف</div><h3>{{ total_expenses }} ريال</h3></div><div class="stat-box profit-box"><div>📈 صافي الربح</div><h3>{{ net_profit }} ريال</h3></div></div>
<div class="card"><h3>➕ إضافة مصروف</h3><div class="row"><div><input type="date" id="expense-date" value="{{ today }}"></div><div><select id="expense-category"><option value="rent">🏠 إيجار</option><option value="salary">👥 رواتب</option><option value="electricity">💡 كهرباء</option><option value="water">💧 ماء</option><option value="internet">🌐 إنترنت</option><option value="other">📌 أخرى</option></select></div><div><input type="number" id="expense-amount" placeholder="المبلغ" step="0.01"></div><div><textarea id="expense-desc" placeholder="الوصف" rows="1"></textarea></div><div><button onclick="addExpense()">💾 إضافة</button></div></div></div>
<div class="card"><h3>📋 المصاريف</h3><div style="overflow-x:auto;"><table><thead><tr><th>التاريخ</th><th>الفئة</th><th>المبلغ</th><th>الوصف</th><th>المستخدم</th><th></th></tr></thead><tbody id="expenses-list"></tbody></table></div></div>
<a href="/dashboard"><button class="btn-back">🔙 رجوع</button></a></div>
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script>
function loadExpenses(){$.ajax({url:'/api/expenses',success:function(data){let h='';data.forEach(e=>{let cat={rent:'🏠 إيجار',salary:'👥 رواتب',electricity:'💡 كهرباء',water:'💧 ماء',internet:'🌐 إنترنت',other:'📌 أخرى'}[e.category];h+=`<tr><td>${e.date}</td><td>${cat}</td><td>${e.amount.toFixed(2)} ريال</td><td>${e.description||'-'}</td><td>${e.user}</td><td><button onclick="deleteExpense(${e.id})" style="background:#e74c3c;">حذف</button></td></tr>`;});$('#expenses-list').html(h);}});}
function addExpense(){let data={date:$('#expense-date').val(),category:$('#expense-category').val(),amount:parseFloat($('#expense-amount').val()),description:$('#expense-desc').val()};if(!data.amount||data.amount<=0){alert('❌ مبلغ صحيح');return;}
$.ajax({url:'/api/expenses/add',method:'POST',contentType:'application/json',data:JSON.stringify(data),success:function(r){if(r.success){alert('✅ تم الإضافة');$('#expense-amount').val('');$('#expense-desc').val('');loadExpenses();location.reload();}else alert('❌ '+r.error);}});}
function deleteExpense(id){if(confirm('حذف المصروف؟')) $.ajax({url:'/api/expenses/delete/'+id,method:'POST',success:function(r){if(r.success){alert('✅ تم الحذف');loadExpenses();location.reload();}}});}
$(document).ready(function(){loadExpenses();});
</script></body></html>
'''

# ===================== المسارات =====================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username'], is_active=True).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            flash(f'✨ مرحباً {user.full_name or user.username}', 'success')
            return redirect(url_for('dashboard'))
        flash('❌ اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    return render_template_string(LOGIN_HTML)

@app.route('/dashboard')
@login_required
def dashboard():
    start = datetime.now().replace(hour=0, minute=0, second=0)
    end = datetime.now().replace(hour=23, minute=59, second=59)
    daily_invoices = Invoice.query.filter(Invoice.date.between(start, end)).all()
    daily_sales = sum(i.total for i in daily_invoices)
    daily_profit = 0
    for inv in daily_invoices:
        for item in inv.items:
            daily_profit += (item.price - item.cost) * item.quantity
    low_stock_count = Product.query.filter(Product.quantity <= 5).count()
    return render_template_string(DASHBOARD_HTML, username=current_user.username, is_admin=current_user.is_admin(),
                                  daily_sales=daily_sales, daily_profit=daily_profit, daily_invoices=len(daily_invoices),
                                  low_stock_count=low_stock_count)

@app.route('/cashier')
@login_required
def cashier():
    return render_template_string(CASHIER_HTML)

@app.route('/products')
@login_required
def products_list():
    return render_template_string(PRODUCTS_HTML, products=Product.query.all(), is_admin=current_user.is_admin())

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    if request.method == 'POST':
        try:
            product = Product(barcode=request.form['barcode'], name=request.form['name'],
                              cost=float(request.form.get('cost', 0)), price=float(request.form['price']),
                              quantity=int(request.form.get('quantity', 0)))
            db.session.add(product)
            db.session.commit()
            flash('✅ تم إضافة المنتج', 'success')
            return redirect(url_for('products_list'))
        except Exception as e:
            flash(f'❌ خطأ: {str(e)}', 'danger')
    return render_template_string(ADD_PRODUCT_HTML)

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        try:
            product.barcode = request.form['barcode']
            product.name = request.form['name']
            product.cost = float(request.form.get('cost', 0))
            product.price = float(request.form['price'])
            product.quantity = int(request.form.get('quantity', 0))
            db.session.commit()
            flash('✅ تم التحديث', 'success')
            return redirect(url_for('products_list'))
        except Exception as e:
            flash(f'❌ خطأ: {str(e)}', 'danger')
    return render_template_string(EDIT_PRODUCT_HTML, product=product)

@app.route('/users')
@login_required
@admin_required
def users_list():
    return render_template_string(USERS_HTML, users=User.query.all())

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        try:
            user = User(username=request.form['username'], full_name=request.form.get('full_name'), role=request.form['role'])
            user.set_password(request.form['password'])
            db.session.add(user)
            db.session.commit()
            flash('✅ تم إضافة المستخدم', 'success')
            return redirect(url_for('users_list'))
        except Exception as e:
            flash(f'❌ خطأ: {str(e)}', 'danger')
    return render_template_string(ADD_USER_HTML)

@app.route('/reports')
@login_required
def reports():
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template_string(REPORTS_HTML, today=today, year=datetime.now().year)

@app.route('/accounting')
@login_required
def accounting():
    total_revenue = db.session.query(db.func.sum(Invoice.total)).scalar() or 0
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    net_profit = total_revenue - total_expenses
    return render_template_string(ACCOUNTING_HTML, total_revenue=total_revenue, total_expenses=total_expenses,
                                  net_profit=net_profit, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/invoice/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    return render_template_string(INVOICE_PRINT_HTML, invoice=Invoice.query.get_or_404(invoice_id))

@app.route('/profile')
@login_required
def profile():
    return render_template_string(PROFILE_HTML, user=current_user)

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    if not current_user.check_password(request.form['current_password']):
        flash('❌ كلمة المرور الحالية غير صحيحة', 'danger')
        return redirect(url_for('profile'))
    if request.form['new_password'] != request.form['confirm_password']:
        flash('❌ كلمة المرور غير متطابقة', 'danger')
        return redirect(url_for('profile'))
    current_user.set_password(request.form['new_password'])
    db.session.commit()
    flash('✅ تم تغيير كلمة المرور', 'success')
    return redirect(url_for('profile'))

@app.route('/set_security_question', methods=['POST'])
@login_required
def set_security_question():
    current_user.security_question = request.form['question']
    current_user.set_security_answer(request.form['answer'])
    db.session.commit()
    flash('✅ تم حفظ السؤال السري', 'success')
    return redirect(url_for('profile'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if not user:
            flash('❌ اسم المستخدم غير موجود', 'danger')
            return redirect(url_for('forgot_password'))
        if not user.security_question:
            flash('⚠️ لم يتم إعداد سؤال استعادة', 'danger')
            return redirect(url_for('forgot_password'))
        session['reset_username'] = user.username
        return redirect(url_for('security_question'))
    return render_template_string(FORGOT_PASSWORD_HTML)

@app.route('/security_question', methods=['GET', 'POST'])
def security_question():
    username = session.get('reset_username')
    if not username:
        return redirect(url_for('forgot_password'))
    user = User.query.filter_by(username=username).first()
    if request.method == 'POST':
        if user.check_security_answer(request.form['answer']):
            token = user.generate_reset_token()
            db.session.commit()
            return redirect(url_for('reset_password', token=token))
        flash('❌ الإجابة غير صحيحة', 'danger')
    return render_template_string(SECURITY_QUESTION_HTML, question=user.security_question)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or user.reset_token_expiry < datetime.utcnow():
        flash('❌ رابط غير صالح أو منتهي', 'danger')
        return redirect(url_for('login'))
    if request.method == 'POST':
        if request.form['new_password'] != request.form['confirm_password']:
            flash('❌ كلمة المرور غير متطابقة', 'danger')
            return redirect(url_for('reset_password', token=token))
        user.set_password(request.form['new_password'])
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('✅ تم تغيير كلمة المرور', 'success')
        return redirect(url_for('login'))
    return render_template_string(RESET_PASSWORD_HTML, username=user.username)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ===================== API =====================
@app.route('/api/product/search')
@login_required
def api_search_products():
    q = request.args.get('q', '')
    products = Product.query.filter(Product.name.contains(q) | Product.barcode.contains(q)).limit(10).all()
    return jsonify([{'id': p.id, 'name': p.name, 'price': p.price, 'cost': p.cost, 'quantity': p.quantity} for p in products])

@app.route('/api/products/search')
@login_required
def api_products_search():
    q = request.args.get('q', '')
    products = Product.query.filter(Product.name.contains(q) | Product.barcode.contains(q)).all()
    return jsonify([{'id': p.id, 'barcode': p.barcode, 'name': p.name, 'price': p.price, 'cost': p.cost, 'quantity': p.quantity} for p in products])

@app.route('/api/product/delete/<int:product_id>', methods=['POST'])
@login_required
@admin_required
def api_delete_product(product_id):
    db.session.delete(Product.query.get_or_404(product_id))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/user/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def api_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'لا يمكن حذف نفسك'})
    db.session.delete(User.query.get_or_404(user_id))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/reports/daily')
@login_required
def api_daily_report():
    date = datetime.strptime(request.args.get('date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d')
    start, end = date.replace(hour=0, minute=0, second=0), date.replace(hour=23, minute=59, second=59)
    invoices = Invoice.query.filter(Invoice.date.between(start, end)).all()
    total_sales = sum(i.total for i in invoices)
    profit = sum((item.price - item.cost) * item.quantity for inv in invoices for item in inv.items)
    return jsonify({'total_sales': total_sales, 'total_invoices': len(invoices), 'profit': profit,
                    'invoices': [{'id': i.id, 'number': i.invoice_number, 'total': i.total,
                                  'time': i.date.strftime('%H:%M'), 'user': i.user.full_name or i.user.username} for i in invoices]})

@app.route('/api/reports/monthly')
@login_required
def api_monthly_report():
    year, month = map(int, request.args.get('month', datetime.now().strftime('%Y-%m')).split('-'))
    start, end = datetime(year, month, 1), datetime(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
    invoices = Invoice.query.filter(Invoice.date.between(start, end)).all()
    total_sales = sum(i.total for i in invoices)
    profit = sum((item.price - item.cost) * item.quantity for inv in invoices for item in inv.items)
    daily = {}
    for inv in invoices:
        d = inv.date.day
        daily[d] = {'sales': daily.get(d, {}).get('sales', 0) + inv.total, 'count': daily.get(d, {}).get('count', 0) + 1}
    return jsonify({'total_sales': total_sales, 'total_invoices': len(invoices), 'profit': profit, 'daily_breakdown': daily})

@app.route('/api/reports/yearly')
@login_required
def api_yearly_report():
    year = int(request.args.get('year', datetime.now().year))
    start, end = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    invoices = Invoice.query.filter(Invoice.date.between(start, end)).all()
    total_sales = sum(i.total for i in invoices)
    profit = sum((item.price - item.cost) * item.quantity for inv in invoices for item in inv.items)
    monthly = {}
    for inv in invoices:
        m = inv.date.strftime('%B')
        monthly[m] = {'sales': monthly.get(m, {}).get('sales', 0) + inv.total, 'count': monthly.get(m, {}).get('count', 0) + 1,
                      'profit': monthly.get(m, {}).get('profit', 0) + sum((item.price - item.cost) * item.quantity for item in inv.items)}
    return jsonify({'total_sales': total_sales, 'total_invoices': len(invoices), 'profit': profit, 'monthly_breakdown': monthly})

@app.route('/api/reports/top_products')
@login_required
def api_top_products():
    from sqlalchemy import func
    top = db.session.query(Product.name, func.sum(InvoiceItem.quantity).label('sold'), func.sum(InvoiceItem.subtotal).label('rev')).join(InvoiceItem).group_by(Product.id).order_by(func.sum(InvoiceItem.quantity).desc()).limit(10).all()
    return jsonify([{'name': p[0], 'total_sold': int(p[1] or 0), 'total_revenue': float(p[2] or 0)} for p in top])

@app.route('/api/expenses')
@login_required
def api_expenses():
    return jsonify([{'id': e.id, 'date': e.date.strftime('%Y-%m-%d'), 'category': e.category, 'amount': e.amount, 'description': e.description,
                     'user': e.user.full_name or e.user.username} for e in Expense.query.order_by(Expense.date.desc()).all()])

@app.route('/api/expenses/add', methods=['POST'])
@login_required
def api_add_expense():
    data = request.get_json()
    expense = Expense(date=datetime.strptime(data['date'], '%Y-%m-%d'), category=data['category'], amount=data['amount'],
                      description=data.get('description', ''), user_id=current_user.id)
    db.session.add(expense)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/expenses/delete/<int:expense_id>', methods=['POST'])
@login_required
def api_delete_expense(expense_id):
    if not current_user.is_admin():
        return jsonify({'success': False, 'error': 'غير مصرح'})
    db.session.delete(Expense.query.get_or_404(expense_id))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/save_invoice', methods=['POST'])
@login_required
def save_invoice():
    try:
        data = request.get_json()
        items = data.get('items', [])
        if not items:
            return jsonify({'error': 'لا توجد منتجات'}), 400
        calculated_total = 0
        validated = []
        for item in items:
            product = Product.query.get(item['id'])
            if not product:
                return jsonify({'error': 'منتج غير موجود'}), 404
            if product.quantity < item['qty']:
                return jsonify({'error': f'{product.name} غير متوفر'}), 400
            subtotal = product.price * item['qty']
            calculated_total += subtotal
            validated.append((product, item['qty'], subtotal))
        if abs(calculated_total - float(data['total'])) > 0.01:
            return jsonify({'error': 'خطأ في الحساب'}), 400
        invoice = Invoice(invoice_number=f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}", total=calculated_total,
                          payment_method=data['payment'], user_id=current_user.id, notes=data.get('notes', ''))
        db.session.add(invoice)
        db.session.flush()
        for product, qty, subtotal in validated:
            db.session.add(InvoiceItem(invoice_id=invoice.id, product_id=product.id, product_name=product.name,
                                        price=product.price, cost=product.cost, quantity=qty, subtotal=subtotal))
            product.quantity -= qty
        db.session.commit()
        return jsonify({'success': True, 'invoice_id': invoice.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ===================== إنشاء قاعدة البيانات =====================
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', full_name='المدير العام', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("✅ تم إنشاء المستخدم admin")

# ===================== التشغيل =====================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 نظام نقاط البيع يعمل!")
    print("="*50)
    print("📱 افتح: http://127.0.0.1:5000")
    print("👤 admin | 🔑 admin123")
    print("="*50)
    print("✨ الميزات: تغيير كلمة المرور، استعادة كلمة المرور، طباعة الفواتير")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
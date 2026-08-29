from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, PasswordField, FloatField, DateField, SelectField, TextAreaField, SubmitField, FieldList, FormField, SelectMultipleField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError
from datetime import datetime, date, timedelta
from sqlalchemy import func, extract
import json
import csv
import io
from io import BytesIO, StringIO
import os
import secrets
import base64

# Initialize Flask app
app = Flask(__name__)

def _get_secret_key():
    """Use SECRET_KEY env var if set; otherwise generate and persist one."""
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    key_path = os.path.join(app.instance_path, 'secret_key')
    if os.path.exists(key_path):
        with open(key_path) as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    os.makedirs(app.instance_path, exist_ok=True)
    with open(key_path, 'w') as f:
        f.write(key)
    return key

app.config['SECRET_KEY'] = _get_secret_key()
# Database URL – use PostgreSQL if available, fallback to SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///record_book.db').replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
bootstrap = Bootstrap(app)
csrf = CSRFProtect(app)

# ====================== DEFAULT EXPENSE ITEMS ======================
DEFAULT_EXPENSE_ITEMS = [
    'Sugar', 'Banana', 'Watermelon', 'Pineapple', 'Supercow Milk',
    'Lactorate Milk', 'Sticker', 'Straw', 'Leda', 'Ice', 'Water',
    'Bola', 'Bottle', 'Others', 'Transport (TP)', 'Fuel'
]

# ====================== MODELS ======================

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    productions = db.relationship('Production', backref='user', lazy=True)
    expenses = db.relationship('Expense', backref='user', lazy=True)
    capitals = db.relationship('Capital', backref='admin', lazy=True)
    labours = db.relationship('Labour', backref='admin', lazy=True)


class Business(db.Model):
    __tablename__ = 'business'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tagline = db.Column(db.String(100))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    logo_data = db.Column(db.Text)  # Base64 encoded logo for inline display
    primary_color = db.Column(db.String(7), default='#0000ff')
    secondary_color = db.Column(db.String(7), default='#fa4659')
    products = db.Column(db.Text)  # JSON array of products
    expense_items = db.Column(db.Text)  # JSON array of expense items
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships - specify foreign_keys to avoid ambiguity
    users = db.relationship('User', backref='business', lazy=True, foreign_keys=[User.business_id])
    creator = db.relationship('User', foreign_keys=[created_by], lazy=True)
    
    def get_products(self):
        if self.products:
            try:
                return json.loads(self.products)
            except:
                return ['Banana Shakaa', 'Pineapple Passion', 'WaterMelon Wonder']
        return ['Banana Shakaa', 'Pineapple Passion', 'WaterMelon Wonder']
    
    def get_expense_items(self):
        if self.expense_items:
            try:
                return json.loads(self.expense_items)
            except:
                return DEFAULT_EXPENSE_ITEMS
        return DEFAULT_EXPENSE_ITEMS


class Production(db.Model):
    __tablename__ = 'production'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProductionHistory(db.Model):
    __tablename__ = 'production_history'
    
    id = db.Column(db.Integer, primary_key=True)
    production_id = db.Column(db.Integer, db.ForeignKey('production.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(200))
    edited_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    edited_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    production = db.relationship('Production', backref='history', lazy=True)
    editor = db.relationship('User', foreign_keys=[edited_by], lazy=True)


class Expense(db.Model):
    __tablename__ = 'expense'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    item = db.Column(db.String(50), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Capital(db.Model):
    __tablename__ = 'capital'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Labour(db.Model):
    __tablename__ = 'labour'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ====================== FORMS ======================

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), Length(min=6)])
    is_admin = SelectField('Role', choices=[('False', 'User'), ('True', 'Admin')], validators=[DataRequired()])
    submit = SubmitField('Create User')
    
    def validate_username(self, field):
        user = User.query.filter_by(username=field.data).first()
        if user:
            raise ValidationError('Username already taken. Please choose a different one.')

class ExpenseItemForm(FlaskForm):
    item = SelectField('Item', choices=[], validators=[DataRequired()])
    cost = FloatField('Cost (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    date = DateField('Date', validators=[DataRequired()], default=date.today)

class ProductionForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    amount = FloatField('Amount (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    note = TextAreaField('Note (Optional)')
    submit = SubmitField('Update Production')

class ExpenseForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    items = FieldList(FormField(ExpenseItemForm), min_entries=1)
    submit = SubmitField('Add Expenses')

class CapitalForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    amount = FloatField('Capital Amount (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    submit = SubmitField('Add Capital')

class LabourForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    amount = FloatField('Labour Amount (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    submit = SubmitField('Add Labour')

class ReportFilterForm(FlaskForm):
    period = SelectField('Period', choices=[
        ('custom', 'Custom Range'),
        ('today', 'Today'),
        ('yesterday', 'Yesterday'),
        ('this_week', 'This Week'),
        ('last_week', 'Last Week'),
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('this_year', 'This Year'),
        ('last_year', 'Last Year')
    ], validators=[DataRequired()])
    date_from = DateField('From Date', validators=[Optional()])
    date_to = DateField('To Date', validators=[Optional()])
    expense_items = SelectMultipleField('Filter by Expense Items', choices=[], validators=[Optional()])
    include_productions = SelectField('Include Productions', choices=[('yes', 'Yes'), ('no', 'No')], default='yes')
    include_expenses = SelectField('Include Expenses', choices=[('yes', 'Yes'), ('no', 'No')], default='yes')
    include_capital = SelectField('Include Capital', choices=[('yes', 'Yes'), ('no', 'No')], default='yes')
    include_labour = SelectField('Include Labour', choices=[('yes', 'Yes'), ('no', 'No')], default='yes')
    group_by = SelectField('Group By', choices=[
        ('none', 'No Grouping'),
        ('date', 'Date'),
        ('item', 'Expense Item'),
        ('user', 'User')
    ], default='none')
    submit = SubmitField('Generate Report')

# ====================== HELPERS ======================

def get_business_info():
    """Get business info for the current user's business"""
    if current_user.is_authenticated and current_user.business:
        business = current_user.business
        return {
            'name': business.name,
            'tagline': business.tagline or '',
            'products': business.get_products(),
            'address': business.address or '',
            'phone': business.phone or '',
            'email': business.email or '',
            'logo': business.logo_data,
            'primary_color': business.primary_color,
            'secondary_color': business.secondary_color,
            'id': business.id
        }
    return {
        'name': 'GO-FRESH',
        'tagline': 'Milkshake',
        'products': ['Banana Shakaa', 'Pineapple Passion', 'WaterMelon Wonder'],
        'address': 'NO7 ZEEKAVE (WAZOBIA HOTEL), APAPA LAGOS',
        'phone': '08127038946',
        'email': '',
        'logo': None,
        'primary_color': '#0000ff',
        'secondary_color': '#fa4659',
        'id': None
    }

@app.context_processor
def inject_globals():
    return {
        'current_year': datetime.now().year,
        'business': get_business_info()
    }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'svg'}

def process_logo(file):
    """Process uploaded logo file and return base64 encoded string"""
    if file and allowed_file(file.filename):
        file_data = file.read()
        encoded = base64.b64encode(file_data).decode('utf-8')
        mime_type = file.content_type or 'image/png'
        return f"data:{mime_type};base64,{encoded}"
    return None

def create_default_admin():
    """Seed initial accounts only on first run (empty users table)."""
    if User.query.first() is not None:
        return
    
    # Create default business
    default_business = Business(
        name='GO-FRESH',
        tagline='Milkshake',
        address='NO7 ZEEKAVE (WAZOBIA HOTEL), APAPA LAGOS',
        phone='08127038946',
        email='info@gofresh.com',
        products=json.dumps(['Banana Shakaa', 'Pineapple Passion', 'WaterMelon Wonder']),
        expense_items=json.dumps(DEFAULT_EXPENSE_ITEMS),
        primary_color='#0000ff',
        secondary_color='#fa4659',
        created_by=1
    )
    db.session.add(default_business)
    db.session.commit()
    
    # Create Super Admin
    super_admin = User(
        username='superadmin',
        password=generate_password_hash('superadmin123'),
        is_admin=True,
        is_super_admin=True,
        is_active=True,
        business_id=default_business.id
    )
    db.session.add(super_admin)
    db.session.commit()
    
    # Update business created_by
    default_business.created_by = super_admin.id
    db.session.commit()
    
    # Create regular admin
    admin = User(
        username='admin',
        password=generate_password_hash('admin123'),
        is_admin=True,
        is_super_admin=False,
        is_active=True,
        business_id=default_business.id
    )
    db.session.add(admin)
    db.session.commit()
    
    # Create regular user
    user = User(
        username='user',
        password=generate_password_hash('user123'),
        is_admin=False,
        is_super_admin=False,
        is_active=True,
        business_id=default_business.id
    )
    db.session.add(user)
    db.session.commit()
    
    print("\n" + "="*60)
    print("First run: default accounts created.")
    print("  Super Admin: username='superadmin', password='superadmin123'")
    print("  Admin:       username='admin', password='admin123'")
    print("  User:        username='user', password='user123'")
    print("  IMPORTANT: Change these passwords before real use!")
    print("="*60 + "\n")

def get_date_range(form):
    """Calculate date range based on form selection"""
    today = date.today()
    
    if form.period.data == 'today':
        start_date = today
        end_date = today
    elif form.period.data == 'yesterday':
        start_date = today - timedelta(days=1)
        end_date = start_date
    elif form.period.data == 'this_week':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif form.period.data == 'last_week':
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)
    elif form.period.data == 'this_month':
        start_date = date(today.year, today.month, 1)
        end_date = today
    elif form.period.data == 'last_month':
        if today.month == 1:
            start_date = date(today.year - 1, 12, 1)
        else:
            start_date = date(today.year, today.month - 1, 1)
        if start_date.month == 12:
            end_date = date(start_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(start_date.year, start_date.month + 1, 1) - timedelta(days=1)
    elif form.period.data == 'this_year':
        start_date = date(today.year, 1, 1)
        end_date = today
    elif form.period.data == 'last_year':
        start_date = date(today.year - 1, 1, 1)
        end_date = date(today.year - 1, 12, 31)
    elif form.period.data == 'custom':
        start_date = form.date_from.data or today
        end_date = form.date_to.data or today
        if start_date > end_date:
            start_date, end_date = end_date, start_date
    else:
        start_date = today
        end_date = today
    
    return start_date, end_date

# ====================== AUTHENTICATION ROUTES ======================

@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            if not user.is_active:
                flash('Your account has been disabled. Please contact an administrator.', 'danger')
                return render_template('login.html', form=form)
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ====================== USER DASHBOARD ======================

@app.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    
    # ===== CAPITAL STATISTICS (Global) =====
    total_capital_all_time = db.session.query(func.sum(Capital.amount)).scalar() or 0
    total_capital_today = db.session.query(func.sum(Capital.amount)).filter(
        Capital.date == today
    ).scalar() or 0
    total_capital_month = db.session.query(func.sum(Capital.amount)).filter(
        extract('year', Capital.date) == today.year,
        extract('month', Capital.date) == today.month
    ).scalar() or 0
    
    # ===== PRODUCTION STATISTICS (User-specific) =====
    total_production_today = db.session.query(func.sum(Production.amount)).filter(
        Production.user_id == current_user.id,
        Production.date == today
    ).scalar() or 0
    
    total_production_month = db.session.query(func.sum(Production.amount)).filter(
        Production.user_id == current_user.id,
        extract('year', Production.date) == today.year,
        extract('month', Production.date) == today.month
    ).scalar() or 0
    
    # ===== EXPENSE STATISTICS (User-specific) =====
    total_expense_today = db.session.query(func.sum(Expense.cost)).filter(
        Expense.user_id == current_user.id,
        Expense.date == today
    ).scalar() or 0
    
    total_expense_month = db.session.query(func.sum(Expense.cost)).filter(
        Expense.user_id == current_user.id,
        extract('year', Expense.date) == today.year,
        extract('month', Expense.date) == today.month
    ).scalar() or 0
    
    # ===== RECENT ENTRIES =====
    productions = Production.query.filter_by(
        user_id=current_user.id
    ).order_by(Production.date.desc()).limit(10).all()
    
    expenses = Expense.query.filter_by(
        user_id=current_user.id
    ).order_by(Expense.date.desc()).limit(10).all()
    
    # ===== TODAY'S CAPITAL ENTRIES =====
    capitals_today = Capital.query.filter(
        Capital.date == today
    ).order_by(Capital.date.desc()).all()
    
    # ===== TODAY'S EXPENSES =====
    expenses_today = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date == today
    ).order_by(Expense.item).all()
    
    # ===== EXPENSES GROUPED BY DATE =====
    expenses_by_date = db.session.query(
        Expense.date,
        func.sum(Expense.cost).label('total_cost'),
        func.count(Expense.id).label('count')
    ).filter(
        Expense.user_id == current_user.id
    ).group_by(Expense.date).order_by(Expense.date.desc()).all()
    
    return render_template('dashboard.html', 
                         total_capital_all_time=total_capital_all_time,
                         total_capital_today=total_capital_today,
                         total_capital_month=total_capital_month,
                         capitals_today=capitals_today,
                         total_production_today=total_production_today,
                         total_production_month=total_production_month,
                         productions=productions,
                         total_expense_today=total_expense_today,
                         total_expense_month=total_expense_month,
                         expenses=expenses,
                         expenses_today=expenses_today,
                         expenses_by_date=expenses_by_date,
                         today=today)

# ====================== ADD ENTRY ROUTES ======================

@app.route('/add-entry', methods=['GET', 'POST'])
@login_required
def add_entry():
    production_form = ProductionForm()
    expense_form = ExpenseForm()
    
    # Get business-specific expense items
    business = current_user.business
    expense_items = business.get_expense_items() if business else DEFAULT_EXPENSE_ITEMS
    
    # Populate item choices for expense forms
    for item_form in expense_form.items:
        item_form.item.choices = [(item, item) for item in expense_items]
    
    # Handle Production submission
    if production_form.submit.data and production_form.validate_on_submit():
        production = Production(
            date=production_form.date.data,
            amount=production_form.amount.data,
            note=production_form.note.data,
            user_id=current_user.id
        )
        db.session.add(production)
        db.session.commit()
        flash('Production entry added successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    # Handle multiple expense submission
    if request.method == 'POST' and 'add_multiple_expenses' in request.form:
        expense_date_str = request.form.get('expense_date')
        
        if not expense_date_str:
            flash('Please select a date.', 'danger')
            return redirect(url_for('add_entry'))
        
        try:
            expense_date = datetime.strptime(expense_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('add_entry'))
        
        items_added = 0
        errors = 0
        
        for key, value in request.form.items():
            if key.startswith('items-') and key.endswith('-item'):
                index = key.split('-')[1]
                item_key = f'items-{index}-item'
                cost_key = f'items-{index}-cost'
                
                if item_key in request.form and cost_key in request.form:
                    item = request.form[item_key]
                    cost_str = request.form[cost_key]
                    
                    if item and cost_str:
                        if item not in expense_items:
                            errors += 1
                            continue
                        try:
                            cost = float(cost_str)
                            if cost > 0:
                                expense = Expense(
                                    date=expense_date,
                                    item=item,
                                    cost=cost,
                                    user_id=current_user.id
                                )
                                db.session.add(expense)
                                items_added += 1
                            else:
                                errors += 1
                        except ValueError:
                            errors += 1
        
        if items_added > 0:
            db.session.commit()
            flash(f'{items_added} expense item(s) added successfully for {expense_date.strftime("%B %d, %Y")}!', 'success')
        else:
            flash('No valid expense items were added. Please check your entries.', 'danger')
        
        if errors > 0:
            flash(f'{errors} item(s) had errors and were not added.', 'warning')
        
        return redirect(url_for('add_entry'))
    
    # Handle expense form submission
    if expense_form.submit.data and expense_form.validate_on_submit():
        expense_date = expense_form.items[0].date.data
        if not expense_date:
            expense_date = date.today()
        
        items_added = 0
        for item_form in expense_form.items:
            expense = Expense(
                date=expense_date,
                item=item_form.item.data,
                cost=item_form.cost.data,
                user_id=current_user.id
            )
            db.session.add(expense)
            items_added += 1
        
        db.session.commit()
        flash(f'{items_added} expense item(s) added successfully for {expense_date.strftime("%B %d, %Y")}!', 'success')
        return redirect(url_for('dashboard'))
    
    today = date.today()
    
    return render_template('add_entry.html', 
                         production_form=production_form, 
                         expense_form=expense_form,
                         today=today)

# ====================== PRODUCTION MANAGEMENT ROUTES ======================

@app.route('/edit-production/<int:production_id>', methods=['GET', 'POST'])
@login_required
def edit_production(production_id):
    production = Production.query.get_or_404(production_id)
    
    # Check if user owns this production
    if production.user_id != current_user.id:
        flash('You are not authorized to edit this production.', 'danger')
        return redirect(url_for('dashboard'))
    
    form = ProductionForm(obj=production)
    
    if form.validate_on_submit():
        # Save current state to history before updating
        history = ProductionHistory(
            production_id=production.id,
            date=production.date,
            amount=production.amount,
            note=production.note,
            edited_by=current_user.id
        )
        db.session.add(history)
        
        # Update production
        production.date = form.date.data
        production.amount = form.amount.data
        production.note = form.note.data
        db.session.commit()
        flash('Production updated successfully!', 'success')
        return redirect(request.referrer or url_for('dashboard'))
    
    # Get history for this production
    history = ProductionHistory.query.filter_by(
        production_id=production.id
    ).order_by(ProductionHistory.edited_at.desc()).all()
    
    return render_template('edit_production.html', form=form, production=production, history=history)

@app.route('/delete-production/<int:production_id>', methods=['POST'])
@login_required
def delete_production(production_id):
    production = Production.query.get_or_404(production_id)
    
    # Check if user owns this production
    if production.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'You are not authorized to delete this production.'}), 403
    
    db.session.delete(production)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Production deleted successfully!'})

# ====================== EXPENSE MANAGEMENT ROUTES ======================

@app.route('/get-expenses-by-date')
@login_required
def get_expenses_by_date():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Date required'}), 400
    
    try:
        expense_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    expenses = Expense.query.filter_by(
        user_id=current_user.id,
        date=expense_date
    ).all()
    
    return jsonify([{
        'id': e.id,
        'item': e.item,
        'cost': e.cost,
        'date': e.date.strftime('%Y-%m-%d')
    } for e in expenses])

@app.route('/get-all-expenses')
@login_required
def get_all_expenses():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    
    return jsonify([{
        'id': e.id,
        'item': e.item,
        'cost': e.cost,
        'date': e.date.strftime('%Y-%m-%d')
    } for e in expenses])

@app.route('/delete-expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    
    if expense.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'You are not authorized to delete this expense.'}), 403
    
    db.session.delete(expense)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Expense "{expense.item}" deleted successfully!'})

# ====================== ADMIN ROUTES ======================

@app.route('/admin')
@login_required
def admin_index():
    if not current_user.is_admin and not current_user.is_super_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    today = date.today()
    
    # If super admin, show all data
    if current_user.is_super_admin:
        total_productions = Production.query.count()
        total_expenses = Expense.query.count()
        total_capital_all_time = db.session.query(func.sum(Capital.amount)).scalar() or 0
        total_labour = db.session.query(func.sum(Labour.amount)).scalar() or 0
        total_productions_today = db.session.query(func.sum(Production.amount)).filter(Production.date == today).scalar() or 0
        total_expenses_today = db.session.query(func.sum(Expense.cost)).filter(Expense.date == today).scalar() or 0
        total_capital_today = db.session.query(func.sum(Capital.amount)).filter(Capital.date == today).scalar() or 0
        capitals_today = Capital.query.filter(Capital.date == today).order_by(Capital.date.desc()).all()
        users = User.query.all()
        businesses = Business.query.all()
    else:
        # Regular admin - filter by their business
        business_filter = User.business_id == current_user.business_id
        total_productions = Production.query.join(User).filter(business_filter).count()
        total_expenses = Expense.query.join(User).filter(business_filter).count()
        total_capital_all_time = db.session.query(func.sum(Capital.amount)).join(User).filter(business_filter).scalar() or 0
        total_labour = db.session.query(func.sum(Labour.amount)).join(User).filter(business_filter).scalar() or 0
        total_productions_today = db.session.query(func.sum(Production.amount)).join(User).filter(
            business_filter, Production.date == today
        ).scalar() or 0
        total_expenses_today = db.session.query(func.sum(Expense.cost)).join(User).filter(
            business_filter, Expense.date == today
        ).scalar() or 0
        total_capital_today = db.session.query(func.sum(Capital.amount)).join(User).filter(
            business_filter, Capital.date == today
        ).scalar() or 0
        capitals_today = Capital.query.join(User).filter(
            business_filter, Capital.date == today
        ).order_by(Capital.date.desc()).all()
        users = User.query.filter(business_filter).all()
        businesses = []
    
    return render_template('admin_index.html',
                         total_productions=total_productions,
                         total_expenses=total_expenses,
                         total_capital_all_time=total_capital_all_time,
                         total_capital_today=total_capital_today,
                         total_labour=total_labour,
                         users=users,
                         businesses=businesses,
                         capitals_today=capitals_today,
                         today=today,
                         total_productions_today=total_productions_today,
                         total_expenses_today=total_expenses_today)

@app.route('/admin/create-user', methods=['GET', 'POST'])
@login_required
def admin_create_user():
    if not current_user.is_admin and not current_user.is_super_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    form = CreateUserForm()
    
    # If regular admin (not super admin), force is_admin to False
    if not current_user.is_super_admin:
        form.is_admin.choices = [('False', 'User')]
        form.is_admin.data = 'False'
    
    if form.validate_on_submit():
        if form.password.data != form.confirm_password.data:
            flash('Passwords do not match!', 'danger')
            return render_template('admin_create_user.html', form=form)
        
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists.', 'danger')
            return render_template('admin_create_user.html', form=form)
        
        hashed_password = generate_password_hash(form.password.data)
        
        # Only super admin can create admin users
        is_admin = False
        if current_user.is_super_admin:
            is_admin = form.is_admin.data == 'True'
        
        user = User(
            username=form.username.data,
            password=hashed_password,
            is_admin=is_admin,
            is_super_admin=False,
            is_active=True,
            business_id=current_user.business_id if not current_user.is_super_admin else None
        )
        db.session.add(user)
        db.session.commit()
        
        role = 'Admin' if user.is_admin else 'User'
        flash(f'User {form.username.data} created successfully as {role}!', 'success')
        return redirect(url_for('admin_index'))
    
    return render_template('admin_create_user.html', form=form)

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin and not current_user.is_super_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if user.is_super_admin:
        flash('Cannot delete Super Admin users!', 'danger')
        return redirect(url_for('admin_index'))
    
    if user.is_admin and not current_user.is_super_admin:
        flash('Only Super Admin can delete other Admin users!', 'danger')
        return redirect(url_for('admin_index'))
    
    if user.id == current_user.id:
        flash('You cannot delete your own account!', 'danger')
        return redirect(url_for('admin_index'))
    
    record_count = (len(user.productions) + len(user.expenses)
                    + len(user.capitals) + len(user.labours))
    if record_count > 0:
        flash(f'Cannot delete {user.username}: this user has {record_count} '
              f'record(s) in the books. Remove their records first.', 'danger')
        return redirect(url_for('admin_index'))
    
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted successfully!', 'success')
    return redirect(url_for('admin_index'))

@app.route('/admin/add-capital', methods=['GET', 'POST'])
@login_required
def admin_add_capital():
    if not current_user.is_admin and not current_user.is_super_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    form = CapitalForm()
    if form.validate_on_submit():
        capital = Capital(
            date=form.date.data,
            amount=form.amount.data,
            user_id=current_user.id
        )
        db.session.add(capital)
        db.session.commit()
        flash(f'Capital of ₦{form.amount.data:,.2f} added for {form.date.data.strftime("%B %d, %Y")}!', 'success')
        return redirect(url_for('admin_add_capital'))
    
    capitals = Capital.query.order_by(Capital.date.desc()).all()
    capitals_by_date = {}
    for capital in capitals:
        date_key = capital.date.strftime('%Y-%m-%d')
        if date_key not in capitals_by_date:
            capitals_by_date[date_key] = []
        capitals_by_date[date_key].append(capital)
    
    return render_template('admin_add_capital.html', form=form, capitals_by_date=capitals_by_date)

@app.route('/admin/add-labour', methods=['GET', 'POST'])
@login_required
def admin_add_labour():
    if not current_user.is_admin and not current_user.is_super_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    form = LabourForm()
    if form.validate_on_submit():
        labour = Labour(
            date=form.date.data,
            amount=form.amount.data,
            user_id=current_user.id
        )
        db.session.add(labour)
        db.session.commit()
        flash(f'Labour of ₦{form.amount.data:,.2f} added for {form.date.data.strftime("%B %d, %Y")}!', 'success')
        return redirect(url_for('admin_add_labour'))
    
    recent_labour = Labour.query.order_by(Labour.date.desc()).limit(10).all()
    return render_template('admin_add_labour.html', form=form, recent_labour=recent_labour)

@app.route('/admin/summary')
@login_required
def admin_summary():
    if not current_user.is_admin and not current_user.is_super_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    today = date.today()
    now = datetime.now()
    
    # Get search date from query parameter
    search_date_str = request.args.get('search_date')
    if search_date_str:
        try:
            display_date = datetime.strptime(search_date_str, '%Y-%m-%d').date()
        except ValueError:
            display_date = today
    else:
        display_date = today
    
    # If super admin, show all data
    if current_user.is_super_admin:
        # Day totals
        total_productions_day = db.session.query(func.sum(Production.amount)).filter(Production.date == display_date).scalar() or 0
        total_expenses_day = db.session.query(func.sum(Expense.cost)).filter(Expense.date == display_date).scalar() or 0
        total_capital_day = db.session.query(func.sum(Capital.amount)).filter(Capital.date == display_date).scalar() or 0
        total_labour_day = db.session.query(func.sum(Labour.amount)).filter(Labour.date == display_date).scalar() or 0
        
        # Day breakdowns
        expense_breakdown_day = db.session.query(
            Expense.item, 
            func.sum(Expense.cost).label('total_cost'),
            func.count(Expense.id).label('count')
        ).filter(Expense.date == display_date).group_by(Expense.item).order_by(Expense.item).all()
        
        capitals_day = Capital.query.filter(Capital.date == display_date).order_by(Capital.date.desc()).all()
        productions_day = Production.query.filter(Production.date == display_date).order_by(Production.date.desc()).all()
    else:
        # Regular admin - filter by their business
        business_filter = User.business_id == current_user.business_id
        
        total_productions_day = db.session.query(func.sum(Production.amount)).join(User).filter(
            business_filter, Production.date == display_date
        ).scalar() or 0
        total_expenses_day = db.session.query(func.sum(Expense.cost)).join(User).filter(
            business_filter, Expense.date == display_date
        ).scalar() or 0
        total_capital_day = db.session.query(func.sum(Capital.amount)).join(User).filter(
            business_filter, Capital.date == display_date
        ).scalar() or 0
        total_labour_day = db.session.query(func.sum(Labour.amount)).join(User).filter(
            business_filter, Labour.date == display_date
        ).scalar() or 0
        
        expense_breakdown_day = db.session.query(
            Expense.item, 
            func.sum(Expense.cost).label('total_cost'),
            func.count(Expense.id).label('count')
        ).join(User).filter(
            business_filter, Expense.date == display_date
        ).group_by(Expense.item).order_by(Expense.item).all()
        
        capitals_day = Capital.query.join(User).filter(
            business_filter, Capital.date == display_date
        ).order_by(Capital.date.desc()).all()
        
        productions_day = Production.query.join(User).filter(
            business_filter, Production.date == display_date
        ).order_by(Production.date.desc()).all()
    
    profit_day = total_productions_day - total_capital_day - total_labour_day
    
    return render_template('admin_summary.html',
                         total_productions_day=total_productions_day,
                         total_expenses_day=total_expenses_day,
                         total_capital_day=total_capital_day,
                         total_labour_day=total_labour_day,
                         profit_day=profit_day,
                         expense_breakdown_day=expense_breakdown_day,
                         capitals_day=capitals_day,
                         productions_day=productions_day,
                         display_date=display_date,
                         today=today,
                         now=now,
                         search_date=search_date_str)

@app.route('/admin/report', methods=['GET', 'POST'])
@login_required
def admin_report():
    if not current_user.is_admin and not current_user.is_super_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    form = ReportFilterForm()
    
    # Populate expense items from business
    business = current_user.business
    expense_items = business.get_expense_items() if business else DEFAULT_EXPENSE_ITEMS
    form.expense_items.choices = [(item, item) for item in expense_items]

    report_data = None
    period_filter = None
    now = datetime.now()
    
    if form.validate_on_submit():
        start_date, end_date = get_date_range(form)
        period_filter = f"{start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}"
        
        # Build queries based on filters
        productions_query = Production.query
        expenses_query = Expense.query
        capital_query = Capital.query
        labour_query = Labour.query
        
        # If regular admin, filter by their business
        if not current_user.is_super_admin:
            business_filter = User.business_id == current_user.business_id
            productions_query = productions_query.join(User).filter(business_filter)
            expenses_query = expenses_query.join(User).filter(business_filter)
            capital_query = capital_query.join(User).filter(business_filter)
            labour_query = labour_query.join(User).filter(business_filter)
        
        # Apply date filter
        productions_query = productions_query.filter(
            Production.date >= start_date,
            Production.date <= end_date
        )
        expenses_query = expenses_query.filter(
            Expense.date >= start_date,
            Expense.date <= end_date
        )
        capital_query = capital_query.filter(
            Capital.date >= start_date,
            Capital.date <= end_date
        )
        labour_query = labour_query.filter(
            Labour.date >= start_date,
            Labour.date <= end_date
        )
        
        # Apply expense item filter
        if form.expense_items.data and len(form.expense_items.data) > 0:
            expenses_query = expenses_query.filter(Expense.item.in_(form.expense_items.data))
        
        productions = productions_query.all() if form.include_productions.data == 'yes' else []
        expenses = expenses_query.all() if form.include_expenses.data == 'yes' else []
        capital = capital_query.all() if form.include_capital.data == 'yes' else []
        labour = labour_query.all() if form.include_labour.data == 'yes' else []
        
        # Group data
        group_by = form.group_by.data
        grouped_data = {}
        
        if group_by == 'date':
            grouped_data = {'productions': {}, 'expenses': {}, 'capital': {}, 'labour': {}}
            for p in productions:
                key = p.date.strftime('%Y-%m-%d')
                if key not in grouped_data['productions']:
                    grouped_data['productions'][key] = []
                grouped_data['productions'][key].append(p)
            for e in expenses:
                key = e.date.strftime('%Y-%m-%d')
                if key not in grouped_data['expenses']:
                    grouped_data['expenses'][key] = []
                grouped_data['expenses'][key].append(e)
            for c in capital:
                key = c.date.strftime('%Y-%m-%d')
                if key not in grouped_data['capital']:
                    grouped_data['capital'][key] = []
                grouped_data['capital'][key].append(c)
            for l in labour:
                key = l.date.strftime('%Y-%m-%d')
                if key not in grouped_data['labour']:
                    grouped_data['labour'][key] = []
                grouped_data['labour'][key].append(l)
        
        elif group_by == 'item':
            grouped_data = {}
            for e in expenses:
                if e.item not in grouped_data:
                    grouped_data[e.item] = []
                grouped_data[e.item].append(e)
        
        elif group_by == 'user':
            grouped_data = {'productions': {}, 'expenses': {}, 'capital': {}, 'labour': {}}
            for p in productions:
                key = p.user.username
                if key not in grouped_data['productions']:
                    grouped_data['productions'][key] = []
                grouped_data['productions'][key].append(p)
            for e in expenses:
                key = e.user.username
                if key not in grouped_data['expenses']:
                    grouped_data['expenses'][key] = []
                grouped_data['expenses'][key].append(e)
            for c in capital:
                key = c.user.username
                if key not in grouped_data['capital']:
                    grouped_data['capital'][key] = []
                grouped_data['capital'][key].append(c)
            for l in labour:
                key = l.user.username
                if key not in grouped_data['labour']:
                    grouped_data['labour'][key] = []
                grouped_data['labour'][key].append(l)
        
        total_productions = sum(p.amount for p in productions)
        total_expenses = sum(e.cost for e in expenses)
        total_capital = sum(c.amount for c in capital)
        total_labour = sum(l.amount for l in labour)
        profit = total_productions - total_capital - total_labour
        
        # Expense breakdown for the period
        expense_breakdown_query = db.session.query(
            Expense.item, 
            func.sum(Expense.cost).label('total_cost'),
            func.count(Expense.id).label('count')
        ).filter(
            Expense.date >= start_date,
            Expense.date <= end_date
        )
        if not current_user.is_super_admin:
            expense_breakdown_query = expense_breakdown_query.join(User).filter(
                User.business_id == current_user.business_id
            )
        if form.expense_items.data and len(form.expense_items.data) > 0:
            expense_breakdown_query = expense_breakdown_query.filter(Expense.item.in_(form.expense_items.data))
        expense_breakdown = expense_breakdown_query.group_by(Expense.item).order_by(Expense.item).all()
        
        report_data = {
            'productions': productions,
            'expenses': expenses,
            'capital': capital,
            'labour': labour,
            'grouped_data': grouped_data,
            'expense_breakdown': expense_breakdown,
            'total_productions': total_productions,
            'total_expenses': total_expenses,
            'total_capital': total_capital,
            'total_labour': total_labour,
            'profit': profit,
            'start_date': start_date,
            'end_date': end_date,
            'group_by': group_by
        }
    
    return render_template('admin_report.html', 
                         form=form, 
                         report_data=report_data,
                         period_filter=period_filter,
                         now=now)

# ====================== SUPER ADMIN ROUTES ======================

@app.route('/super-admin')
@login_required
def super_admin_dashboard():
    if not current_user.is_super_admin:
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get all businesses
    businesses = Business.query.all()
    
    # Get all users
    users = User.query.all()
    
    # Stats
    total_businesses = Business.query.count()
    total_users = User.query.count()
    total_admins = User.query.filter_by(is_admin=True).count()
    total_super_admins = User.query.filter_by(is_super_admin=True).count()
    inactive_users = User.query.filter_by(is_active=False).count()
    
    return render_template('super_admin_dashboard.html',
                         businesses=businesses,
                         users=users,
                         total_businesses=total_businesses,
                         total_users=total_users,
                         total_admins=total_admins,
                         total_super_admins=total_super_admins,
                         inactive_users=inactive_users)

@app.route('/super-admin/create-business', methods=['GET', 'POST'])
@login_required
def super_admin_create_business():
    if not current_user.is_super_admin:
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        tagline = request.form.get('tagline')
        address = request.form.get('address')
        phone = request.form.get('phone')
        email = request.form.get('email')
        primary_color = request.form.get('primary_color', '#0000ff')
        secondary_color = request.form.get('secondary_color', '#fa4659')
        products = request.form.get('products', '').split(',')
        products = [p.strip() for p in products if p.strip()]
        expense_items = request.form.get('expense_items', '').split(',')
        expense_items = [e.strip() for e in expense_items if e.strip()]
        
        if not name:
            flash('Business name is required.', 'danger')
            return redirect(url_for('super_admin_create_business'))
        
        # Process logo
        logo_data = None
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename:
                logo_data = process_logo(file)
        
        business = Business(
            name=name,
            tagline=tagline,
            address=address,
            phone=phone,
            email=email,
            logo_data=logo_data,
            primary_color=primary_color,
            secondary_color=secondary_color,
            products=json.dumps(products if products else ['Banana Shakaa', 'Pineapple Passion', 'WaterMelon Wonder']),
            expense_items=json.dumps(expense_items if expense_items else DEFAULT_EXPENSE_ITEMS),
            created_by=current_user.id
        )
        db.session.add(business)
        db.session.commit()
        
        flash(f'Business "{name}" created successfully!', 'success')
        return redirect(url_for('super_admin_dashboard'))
    
    return render_template('super_admin_create_business.html')

@app.route('/super-admin/edit-business/<int:business_id>', methods=['GET', 'POST'])
@login_required
def super_admin_edit_business(business_id):
    if not current_user.is_super_admin:
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    business = Business.query.get_or_404(business_id)
    
    if request.method == 'POST':
        business.name = request.form.get('name', business.name)
        business.tagline = request.form.get('tagline', business.tagline)
        business.address = request.form.get('address', business.address)
        business.phone = request.form.get('phone', business.phone)
        business.email = request.form.get('email', business.email)
        business.primary_color = request.form.get('primary_color', business.primary_color)
        business.secondary_color = request.form.get('secondary_color', business.secondary_color)
        business.is_active = 'is_active' in request.form
        
        # Process products
        products = request.form.get('products', '').split(',')
        products = [p.strip() for p in products if p.strip()]
        if products:
            business.products = json.dumps(products)
        
        # Process expense items
        expense_items = request.form.get('expense_items', '').split(',')
        expense_items = [e.strip() for e in expense_items if e.strip()]
        if expense_items:
            business.expense_items = json.dumps(expense_items)
        
        # Process logo
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename:
                logo_data = process_logo(file)
                if logo_data:
                    business.logo_data = logo_data
        
        # Check if logo should be removed
        if 'remove_logo' in request.form:
            business.logo_data = None
        
        db.session.commit()
        flash(f'Business "{business.name}" updated successfully!', 'success')
        return redirect(url_for('super_admin_dashboard'))
    
    # Parse products and expense items for display
    try:
        products = json.loads(business.products) if business.products else []
    except:
        products = ['Banana Shakaa', 'Pineapple Passion', 'WaterMelon Wonder']
    
    try:
        expense_items = json.loads(business.expense_items) if business.expense_items else []
    except:
        expense_items = DEFAULT_EXPENSE_ITEMS
    
    return render_template('super_admin_edit_business.html', 
                         business=business,
                         products=', '.join(products),
                         expense_items=', '.join(expense_items))

@app.route('/super-admin/create-admin', methods=['GET', 'POST'])
@login_required
def super_admin_create_admin():
    if not current_user.is_super_admin:
        flash('Access denied. Super Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    businesses = Business.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        business_id = request.form.get('business_id')
        is_admin = 'is_admin' in request.form
        
        if not username or not password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('super_admin_create_admin'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('super_admin_create_admin'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists.', 'danger')
            return redirect(url_for('super_admin_create_admin'))
        
        if not business_id:
            flash('Please select a business for this user.', 'danger')
            return redirect(url_for('super_admin_create_admin'))
        
        hashed_password = generate_password_hash(password)
        user = User(
            username=username,
            password=hashed_password,
            is_admin=is_admin,
            is_super_admin=False,
            is_active=True,
            business_id=int(business_id)
        )
        db.session.add(user)
        db.session.commit()
        
        business = Business.query.get(business_id)
        role = 'Admin' if is_admin else 'User'
        flash(f'User "{username}" created successfully as {role} for "{business.name}"!', 'success')
        return redirect(url_for('super_admin_dashboard'))
    
    return render_template('super_admin_create_admin.html', businesses=businesses)

@app.route('/super-admin/toggle-user/<int:user_id>', methods=['POST'])
@login_required
def super_admin_toggle_user(user_id):
    if not current_user.is_super_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    user = User.query.get_or_404(user_id)
    
    # Prevent disabling self
    if user.id == current_user.id:
        return jsonify({'success': False, 'error': 'You cannot disable your own account'}), 400
    
    # Prevent disabling super admin
    if user.is_super_admin:
        return jsonify({'success': False, 'error': 'Cannot disable a Super Admin'}), 400
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'enabled' if user.is_active else 'disabled'
    return jsonify({'success': True, 'message': f'User "{user.username}" has been {status}.'})

@app.route('/super-admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def super_admin_delete_user(user_id):
    if not current_user.is_super_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    user = User.query.get_or_404(user_id)
    
    # Prevent deleting self
    if user.id == current_user.id:
        return jsonify({'success': False, 'error': 'You cannot delete your own account'}), 400
    
    # Prevent deleting super admin
    if user.is_super_admin:
        return jsonify({'success': False, 'error': 'Cannot delete a Super Admin'}), 400
    
    # Check if user has records
    record_count = (len(user.productions) + len(user.expenses) 
                   + len(user.capitals) + len(user.labours))
    if record_count > 0:
        return jsonify({'success': False, 'error': f'User has {record_count} record(s). Delete them first.'}), 400
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User "{user.username}" deleted successfully.'})

@app.route('/super-admin/delete-business/<int:business_id>', methods=['POST'])
@login_required
def super_admin_delete_business(business_id):
    if not current_user.is_super_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    business = Business.query.get_or_404(business_id)
    
    # Check if business has users
    if business.users:
        return jsonify({'success': False, 'error': f'Business has {len(business.users)} user(s). Remove them first.'}), 400
    
    db.session.delete(business)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Business "{business.name}" deleted successfully.'})

# ====================== MAIN ======================

# Create tables and default admin on app startup (for Gunicorn)
with app.app_context():
    db.create_all()
    create_default_admin()

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG') == '1'
    print("\n" + "="*60)
    print("GO-FRESH Electronic Record Book is running!")
    print("="*60)
    print(f"Access the application at: http://{'localhost' if host == '127.0.0.1' else host}:{port}")
    if host == '127.0.0.1':
        print("(Set HOST=0.0.0.0 to allow access from other devices on your network)")
    print("\nDefault Accounts:")
    print("  Super Admin: superadmin / superadmin123")
    print("  Admin:       admin / admin123")
    print("  User:        user / user123")
    print("\n" + "="*60 + "\n")
    app.run(debug=debug, host=host, port=port)
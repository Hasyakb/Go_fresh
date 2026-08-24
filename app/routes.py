from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User, Production, Expense, Capital, Labour
from app.forms import (
    LoginForm, ProductionForm, ExpenseForm, CapitalForm, LabourForm, 
    ReportFilterForm, EXPENSE_ITEMS
)
from datetime import datetime, date
from sqlalchemy import func, extract
from calendar import month_name

bp = Blueprint('main', __name__)

# Create a default admin user if none exists
def create_default_admin():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created: username='admin', password='admin123'")

# Routes

@bp.route('/')
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html', form=form)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    # Calculate total capital
    total_capital = db.session.query(func.sum(Capital.amount)).scalar() or 0
    
    # Get current user's recent productions and expenses
    productions = Production.query.filter_by(user_id=current_user.id).order_by(Production.date.desc()).limit(10).all()
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).limit(10).all()
    
    return render_template('dashboard.html', 
                         total_capital=total_capital,
                         productions=productions,
                         expenses=expenses)

@bp.route('/add-entry', methods=['GET', 'POST'])
@login_required
def add_entry():
    production_form = ProductionForm()
    expense_form = ExpenseForm()
    
    # Remove choices from item field to use predefined list
    expense_form.item.choices = [(item, item) for item in EXPENSE_ITEMS]
    
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
        return redirect(url_for('main.dashboard'))
    
    if expense_form.submit.data and expense_form.validate_on_submit():
        expense = Expense(
            date=expense_form.date.data,
            item=expense_form.item.data,
            cost=expense_form.cost.data,
            user_id=current_user.id
        )
        db.session.add(expense)
        db.session.commit()
        flash('Expense entry added successfully!', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('add_entry.html', 
                         production_form=production_form, 
                         expense_form=expense_form)

@bp.route('/admin')
@login_required
def admin_index():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get counts for admin dashboard
    total_productions = Production.query.count()
    total_expenses = Expense.query.count()
    total_capital = db.session.query(func.sum(Capital.amount)).scalar() or 0
    total_labour = db.session.query(func.sum(Labour.amount)).scalar() or 0
    
    return render_template('admin_index.html',
                         total_productions=total_productions,
                         total_expenses=total_expenses,
                         total_capital=total_capital,
                         total_labour=total_labour)

@bp.route('/admin/add-capital', methods=['GET', 'POST'])
@login_required
def admin_add_capital():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = CapitalForm()
    if form.validate_on_submit():
        capital = Capital(
            date=form.date.data,
            amount=form.amount.data,
            user_id=current_user.id
        )
        db.session.add(capital)
        db.session.commit()
        flash('Capital added successfully!', 'success')
        return redirect(url_for('main.admin_add_capital'))
    
    # Show recent capital entries
    recent_capital = Capital.query.order_by(Capital.date.desc()).limit(10).all()
    return render_template('admin_add_capital.html', form=form, recent_capital=recent_capital)

@bp.route('/admin/add-labour', methods=['GET', 'POST'])
@login_required
def admin_add_labour():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = LabourForm()
    if form.validate_on_submit():
        labour = Labour(
            date=form.date.data,
            amount=form.amount.data,
            user_id=current_user.id
        )
        db.session.add(labour)
        db.session.commit()
        flash('Labour added successfully!', 'success')
        return redirect(url_for('main.admin_add_labour'))
    
    # Show recent labour entries
    recent_labour = Labour.query.order_by(Labour.date.desc()).limit(10).all()
    return render_template('admin_add_labour.html', form=form, recent_labour=recent_labour)

@bp.route('/admin/summary')
@login_required
def admin_summary():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Calculate totals
    total_productions = db.session.query(func.sum(Production.amount)).scalar() or 0
    total_expenses = db.session.query(func.sum(Expense.cost)).scalar() or 0
    total_capital = db.session.query(func.sum(Capital.amount)).scalar() or 0
    total_labour = db.session.query(func.sum(Labour.amount)).scalar() or 0
    
    profit = total_productions - total_capital - total_labour
    
    # Get expense breakdown by item
    expense_breakdown = db.session.query(
        Expense.item, 
        func.sum(Expense.cost).label('total_cost'),
        func.count(Expense.id).label('count')
    ).group_by(Expense.item).order_by(Expense.item).all()
    
    return render_template('admin_summary.html',
                         total_productions=total_productions,
                         total_expenses=total_expenses,
                         total_capital=total_capital,
                         total_labour=total_labour,
                         profit=profit,
                         expense_breakdown=expense_breakdown)

@bp.route('/admin/report', methods=['GET', 'POST'])
@login_required
def admin_report():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    form = ReportFilterForm()
    
    # Populate year choices
    current_year = datetime.now().year
    form.year.choices = [(year, str(year)) for year in range(current_year, current_year - 10, -1)]
    
    report_data = None
    period_filter = None
    
    if form.validate_on_submit():
        period = form.period.data
        start_date = None
        end_date = None
        
        if period == 'day':
            if form.date.data:
                start_date = form.date.data
                end_date = start_date
                period_filter = f"Day: {start_date.strftime('%B %d, %Y')}"
                
        elif period == 'month':
            if form.month.data and form.year.data:
                year = int(form.year.data)
                month = int(form.month.data)
                start_date = date(year, month, 1)
                if month == 12:
                    end_date = date(year + 1, 1, 1)
                else:
                    end_date = date(year, month + 1, 1)
                period_filter = f"Month: {month_name[month]} {year}"
                
        elif period == 'year':
            if form.year.data:
                year = int(form.year.data)
                start_date = date(year, 1, 1)
                end_date = date(year + 1, 1, 1)
                period_filter = f"Year: {year}"
        
        if start_date:
            # Query data for the selected period
            productions = Production.query.filter(
                Production.date >= start_date,
                Production.date < end_date
            ).all()
            
            expenses = Expense.query.filter(
                Expense.date >= start_date,
                Expense.date < end_date
            ).all()
            
            capital = Capital.query.filter(
                Capital.date >= start_date,
                Capital.date < end_date
            ).all()
            
            labour = Labour.query.filter(
                Labour.date >= start_date,
                Labour.date < end_date
            ).all()
            
            # Calculate totals
            total_productions = sum(p.amount for p in productions)
            total_expenses = sum(e.cost for e in expenses)
            total_capital = sum(c.amount for c in capital)
            total_labour = sum(l.amount for l in labour)
            profit = total_productions - total_capital - total_labour
            
            report_data = {
                'productions': productions,
                'expenses': expenses,
                'capital': capital,
                'labour': labour,
                'total_productions': total_productions,
                'total_expenses': total_expenses,
                'total_capital': total_capital,
                'total_labour': total_labour,
                'profit': profit
            }
    
    return render_template('admin_report.html', 
                         form=form, 
                         report_data=report_data,
                         period_filter=period_filter)
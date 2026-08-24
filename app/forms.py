from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FloatField, DateField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional
from datetime import datetime

# Predefined items list for expenses
EXPENSE_ITEMS = [
    'Sugar', 'Banana', 'Watermelon', 'Pineapple', 'Supercow Milk',
    'Lactorate Milk', 'Sticker', 'Straw', 'Leda', 'Ice', 'Water',
    'Bola', 'Bottle', 'Others'
]

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ProductionForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=datetime.now().date)
    amount = FloatField('Amount (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    note = TextAreaField('Note (Optional)')
    submit = SubmitField('Add Production')

class ExpenseForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=datetime.now().date)
    item = SelectField('Item', choices=[(item, item) for item in EXPENSE_ITEMS], validators=[DataRequired()])
    cost = FloatField('Cost (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    submit = SubmitField('Add Expense')

class CapitalForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=datetime.now().date)
    amount = FloatField('Capital Amount (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    submit = SubmitField('Add Capital')

class LabourForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=datetime.now().date)
    amount = FloatField('Labour Amount (₦)', validators=[DataRequired(), NumberRange(min=0.01)])
    submit = SubmitField('Add Labour')

class ReportFilterForm(FlaskForm):
    period = SelectField('Period', choices=[
        ('day', 'Day'),
        ('month', 'Month'),
        ('year', 'Year')
    ], validators=[DataRequired()])
    date = DateField('Date (for Day)', validators=[Optional()])
    month = SelectField('Month (for Month)', choices=[
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ], validators=[Optional()])
    year = SelectField('Year (for Month/Year)', choices=[], validators=[Optional()])
    submit = SubmitField('Generate Report')
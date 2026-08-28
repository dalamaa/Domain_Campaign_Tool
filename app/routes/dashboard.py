from flask import Blueprint, render_template

bp = Blueprint('dashboard', __name__)

@bp.route('/')
def index():
    return render_template('dashboard.html')

@bp.route('/email-accounts')
def email_accounts():
    return render_template('email_accounts.html')

@bp.route('/domains')
def domains():
    return render_template('domains.html')

@bp.route('/settings')
def settings():
    return render_template('settings.html')


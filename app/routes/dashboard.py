from flask import Blueprint, render_template, request

from app.services.email_code_search_service import (
    normalize_email_code,
    search_email_code,
)

bp = Blueprint('dashboard', __name__)

@bp.route('/')
def index():
    return render_template('dashboard.html')

@bp.route('/email-accounts')
def email_accounts():
    return render_template('email_accounts.html')

@bp.route('/email-code-search')
def email_code_search():
    raw_code = request.args.get('code', '')
    code = normalize_email_code(raw_code)
    search = search_email_code(code) if code else None
    return render_template(
        'email_code_search.html',
        email_code=code,
        search=search,
    )

@bp.route('/domains')
def domains():
    return render_template('domains.html')

@bp.route('/team-domains')
def team_domains():
    return render_template('team_domains.html')

@bp.route('/expired-historical')
def expired_historical():
    return render_template('expired_historical.html')

@bp.route('/settings')
def settings():
    return render_template('settings.html')

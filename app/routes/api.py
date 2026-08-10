from flask import Blueprint, jsonify, request
from app.models.models import db, EmailAccount
from sqlalchemy import asc
import re
from sqlalchemy import desc

bp = Blueprint('api', __name__, url_prefix='/api')

def parse_code(code):
    match = re.match(r"([A-Za-z]+)(\d+)", code)
    if not match: return None, None
    return match.group(1), int(match.group(2))

@bp.route('/email-accounts', methods=['GET'])
def get_email_accounts():
    accounts = EmailAccount.query.order_by(asc(EmailAccount.profile_order)).all()
    # Note: State logic will be handled based on reservations in a later phase
    return jsonify([{'code': a.code, 'group': a.group, 'order': a.profile_order, 'enabled': a.enabled, 'state': 'Available'} for a in accounts])

@bp.route('/email-accounts/suggest-order', methods=['POST'])
def suggest_order():
    code = request.json.get('code')
    prefix, num = parse_code(code)
    if not prefix: return jsonify({'error': 'Invalid code format'}), 400

    # Get accounts with same prefix
    accounts = EmailAccount.query.all()
    group_accounts = [a for a in accounts if parse_code(a.code)[0] == prefix]

    if not group_accounts:
        # End of overall sequence
        return jsonify({'suggested_order': (db.session.query(db.func.max(EmailAccount.profile_order)).scalar() or 0) + 1})

    # Find position based on numeric value
    group_accounts.sort(key=lambda a: parse_code(a.code)[1])
    for acc in group_accounts:
        _, acc_num = parse_code(acc.code)
        if num < acc_num:
            return jsonify({'suggested_order': acc.profile_order})

    # After last in group
    return jsonify({'suggested_order': max([a.profile_order for a in group_accounts]) + 1})
# New route to check order availability
@bp.route('/email-accounts/check-order', methods=['POST'])
def check_order():
    data = request.json
    order = int(data['order'])
    existing = EmailAccount.query.filter_by(profile_order=order).first()
    if existing:
        return jsonify({'occupied': True, 'conflicting_code': existing.code})
    return jsonify({'occupied': False})

@bp.route('/email-accounts/add', methods=['POST'])
def add_email_account():
    data = request.json
    code = data['code'].upper()
    prefix, _ = parse_code(code)
    new_order = int(data['order'])

    # Check for existing
    existing = EmailAccount.query.get(code)

    if existing and not data.get('overwrite'):
        return jsonify({'error': 'Code already exists', 'existing': True}), 409
    try:
        if existing:
            # Handle Overwrite: delete first or update
            db.session.delete(existing)
            # Re-fetch or adjust if needed to prevent gap during delete

        if data.get('shift_existing'):
            EmailAccount.query.filter(EmailAccount.profile_order >= new_order).\
            update({"profile_order": EmailAccount.profile_order + 1})

        new_account = EmailAccount(code=code, group=prefix, profile_order=new_order, enabled=True)
        db.session.add(new_account)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/email-accounts/<code>', methods=['DELETE'])
def delete_email_account(code):
    acc = EmailAccount.query.get_or_404(code)
    deleted_order = acc.profile_order

    db.session.delete(acc)
    # Close the gap
    EmailAccount.query.filter(EmailAccount.profile_order > deleted_order).\
        update({"profile_order": EmailAccount.profile_order - 1})

    db.session.commit()
    return jsonify({'success': True})

@bp.route('/email-accounts/fix-order', methods=['POST'])
def fix_order():
    try:
        # Get all accounts ordered by current profile_order
        accounts = EmailAccount.query.order_by(EmailAccount.profile_order).all()

        # Check for continuity
        needs_fix = False
        for i, acc in enumerate(accounts):
            if acc.profile_order != i + 1:
                needs_fix = True
                break

        if not needs_fix:
            return jsonify({'fixed': False, 'message': 'Profile order is already correct.'})

        # Re-number sequentially
        for i, acc in enumerate(accounts):
            acc.profile_order = i + 1

        db.session.commit()
        return jsonify({'fixed': True, 'message': 'Profile order gaps have been removed.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


from flask import Blueprint, jsonify, request
from app.models.models import db, EmailAccount
from sqlalchemy import asc
import re
from sqlalchemy import desc
from datetime import datetime

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

@bp.route('/email-accounts/check-code', methods=['GET'])
def check_code():
    code = request.args.get('code', '').upper()
    acc = EmailAccount.query.get(code)
    if acc:
        return jsonify({
            'exists': True,
            'account': {
                'code': acc.code,
                'group': acc.group,
                'order': acc.profile_order
            }
        })
    return jsonify({'exists': False})

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

@bp.route('/domains', methods=['GET'])
def get_domains():
    from app.models.models import Domain, Campaign, CampaignStatus, CampaignHistory
    domains = Domain.query.all()
    results = []
    action_mapping = {
        'FIRST_OUTREACH': 'First Outreach',
        'FIRST_FOLLOW_UP': 'First Follow-up',
        'FOLLOW_UP': 'Follow-up',
        'PRICE_REDUCTION': 'Price Reduction',
        'REST_STARTED': 'Rest Started',
        'CAMPAIGN_RESTARTED': 'Campaign Restarted',
        'CAMPAIGN_COMPLETED': 'Campaign Completed',
        'FORCE_OVERRIDE': 'Force Override',
        'PARTIAL_OVERRIDE': 'Partial Override'
    }
    for d in domains:
        c = Campaign.query.filter_by(domain_id=d.id).first()
        has_history = bool(c and CampaignHistory.query.filter_by(campaign_id=c.id).first())
        has_values = has_history

        raw_action = c.last_action if c else ''
        friendly_action = action_mapping.get(str(raw_action), raw_action)
        results.append({
            'id': d.id,
            'domain': d.domain_name,
            'expiry': d.expiry_date.isoformat() if d.expiry_date else '',
            'status': c.status.value if c else '',
            'price': c.current_price if c else '',
            'seq': c.current_sequence if has_history else '',
            'lastContact': c.last_contact_date.isoformat() if c and c.last_contact_date else '',
            'lastAction': friendly_action if has_history else '',
            'hasValues': has_values
        })
    return jsonify(results)

@bp.route('/domains', methods=['POST'])
def add_domain():
    from app.models.models import Domain, Campaign, CampaignStatus
    data = request.json
    if Domain.query.filter_by(domain_name=data['domain']).first():
        return jsonify({'error': 'Domain exists'}), 400

    new_dom = Domain(domain_name=data['domain'], expiry_date=data['expiry'])
    db.session.add(new_dom)
    db.session.flush()

    # A new domain starts Dormant (never worked on) unless explicitly started.
    # Sequence 0 means "not started"; the price defaults to 0.
    status = getattr(
        CampaignStatus,
        str(data.get('status', 'DORMANT')).upper(),
        CampaignStatus.DORMANT,
    )
    seq = int(data['seq']) if str(data.get('seq', '')).isdigit() else 0

    new_camp = Campaign(
        domain_id=new_dom.id, status=status,
        start_date=datetime.utcnow(), current_price=int(data.get('price') or 0),
        current_sequence=seq
    )
    db.session.add(new_camp)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/domains/import', methods=['POST'])
def import_domains():
    from app.models.models import Domain, Campaign, CampaignStatus
    data = request.json.get('domains', [])
    try:
        for item in data:
            # Handle empty/invalid price
            price_raw = item.get('price')
            price = int(price_raw) if (price_raw and str(price_raw).isdigit()) else 0

            # Handle empty/invalid sequence. Omitted or invalid sequence means
            # the domain is "not started" (0). A provided/castable sequence is
            # used only when the domain is explicitly started.
            seq_raw = item.get('seq')
            seq = int(seq_raw) if (seq_raw is not None and str(seq_raw).isdigit() and int(seq_raw) > 0) else 0

            # Handle expiry date safely
            expiry_date = None
            if item.get('expiry'):
                try:
                    expiry_date = datetime.strptime(str(item.get('expiry')), '%Y-%m-%d').date()
                except ValueError:
                    pass # Keep None if date is invalid

            # Imported domains start Dormant (never worked on) unless the import
            # explicitly provides an ACTIVE/status AND a real sequence. Sequence 0
            # means "not started". If a status is given but no real sequence, we
            # still require a started sequence before treating it as active.
            status_resolved = getattr(
                CampaignStatus,
                str(item.get('status', 'DORMANT')).upper(),
                CampaignStatus.DORMANT,
            )
            # Only keep an imported sequence/status as a genuine start.
            if seq <= 0:
                status_resolved = CampaignStatus.DORMANT
                price = 0

            new_dom = Domain(domain_name=item.get('domain'), expiry_date=expiry_date)
            db.session.add(new_dom)
            db.session.flush()

            new_camp = Campaign(
                domain_id=new_dom.id,
                status=status_resolved,
                start_date=datetime.utcnow(),
                current_price=price,
                current_sequence=seq
            )
            db.session.add(new_camp)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        print(f"Import Error: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/domains/<int:id>', methods=['PUT', 'DELETE'])
def manage_domain(id):
    from app.models.models import Domain, Campaign, CampaignStatus
    dom = Domain.query.get_or_404(id)

    if request.method == 'DELETE':
        db.session.delete(dom)
        db.session.commit()
        return jsonify({'success': True})

    # Handle PUT (Edit)
    data = request.json

    # Update Domain
    if 'domain' in data:
        dom.domain_name = data['domain']
    if data.get('expiry'):
        dom.expiry_date = datetime.strptime(data['expiry'], '%Y-%m-%d').date()

    # Update Campaign
    camp = Campaign.query.filter_by(domain_id=dom.id).first()
    if camp:
        if 'price' in data:
            camp.current_price = int(data['price'])
        if 'status' in data:
            camp.status = getattr(CampaignStatus, str(data['status']).upper(), camp.status)
        if 'seq' in data:
            camp.current_sequence = int(data['seq'])
        if 'lastContact' in data and data['lastContact']:
            camp.last_contact_date = datetime.strptime(data['lastContact'], '%Y-%m-%d').date()
        if 'lastAction' in data:
            camp.last_action = data['lastAction']
        camp.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})

@bp.route('/domains/<int:id>/history', methods=['GET'])
def get_campaign_history(id):
    from app.models.models import Campaign, CampaignHistory
    camp = Campaign.query.filter_by(domain_id=id).first()
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404

    # Order by action_date descending so latest actions appear first
    history = CampaignHistory.query.filter_by(campaign_id=camp.id).order_by(CampaignHistory.action_date.desc()).all()
    return jsonify([{
        'action': h.action_type.value,
        'date': h.action_date.isoformat(),
        'price_before': h.price_before,
        'price_after': h.price_after,
        'notes': h.notes
    } for h in history])

@bp.route('/domains/<int:id>/history/check', methods=['POST'])
def check_history_action(id):
    from app.models.models import Campaign, CampaignHistory
    data = request.json
    new_seq = int(data.get('seq'))

    camp = Campaign.query.filter_by(domain_id=id).first()
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404

    current_max_seq = db.session.query(db.func.max(CampaignHistory.sequence)).filter_by(campaign_id=camp.id).scalar() or 0

    # Check for skip
    if new_seq > current_max_seq + 1:
        return jsonify({'action': 'INVALID_SKIP', 'message': f'Cannot skip to sequence {new_seq}. Next allowed is {current_max_seq + 1}'}), 400

    existing = CampaignHistory.query.filter_by(campaign_id=camp.id, sequence=new_seq).first()
    if existing:
        return jsonify({'action': 'OVERWRITE', 'message': f'Sequence {new_seq} already exists. Overwriting will modify historical data.'})

    return jsonify({'action': 'CREATE_NEW', 'message': 'This will create a new history record for sequence ' + str(new_seq)})

@bp.route('/domains/<int:id>/history', methods=['PUT'])
def update_campaign_history(id):
    from app.models.models import Campaign, CampaignHistory
    data = request.json
    seq = int(data.get('seq'))

    camp = Campaign.query.filter_by(domain_id=id).first()
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404

    hist = CampaignHistory.query.filter_by(campaign_id=camp.id, sequence=seq).first()
    if hist:
        # Update existing
        hist.price_after = int(data.get('price', hist.price_after))
        hist.notes = data.get('notes', hist.notes)
    else:
        # Create new
        prev = CampaignHistory.query.filter_by(campaign_id=camp.id, sequence=seq-1).first()
        hist = CampaignHistory(
            campaign_id=camp.id,
            sequence=seq,
            action_type=data.get('action_type', 'FORCE_OVERRIDE'),
            price_before=prev.price_after if prev else 0,
            price_after=int(data.get('price')),
            notes=data.get('notes')
                    )
        db.session.add(hist)
        db.session.commit()
        return jsonify({'success': True})

@bp.route('/domains/bulk-edit', methods=['POST'])
def bulk_edit_domains():
    from app.models.models import Domain, Campaign, CampaignStatus, CampaignHistory

    data = request.json
    ids = data.get('ids', [])
    updates = data.get('updates', {})

    try:
        # Pre-validate sequence-history requirement for ALL selected domains
        # before making any changes, so we can name every offending domain
        # and avoid partial/silent failures.
        if 'seq' in updates and int(updates['seq']) > 1:
            missing_history = []
        for domain_id in ids:
            camp = Campaign.query.filter_by(domain_id=domain_id).first()
            if not camp:
                continue
            has_history = CampaignHistory.query.filter_by(
                campaign_id=camp.id
            ).first()
            if not has_history:
                dom = Domain.query.get(domain_id)
                missing_history.append(dom.domain_name if dom else f"ID {domain_id}")
            if missing_history:
                return jsonify({
                    'error': (
                        'No campaign history has been recorded for the following '
                        f'domain(s): {", ".join(missing_history)}. '
                        'A first outreach (sequence 1) must be recorded before '
                        'setting a higher sequence.'
                    )
                }), 400

        # Apply updates (validation already passed)
        for domain_id in ids:
            dom = Domain.query.get(domain_id)
            camp = Campaign.query.filter_by(domain_id=domain_id).first()

            if not dom or not camp:
                continue

            # Update Campaign fields
            if 'status' in updates:
                camp.status = CampaignStatus[updates['status'].upper()]
            if 'price' in updates:
                camp.current_price = int(updates['price'])
            if 'seq' in updates:
                camp.current_sequence = int(updates['seq'])
            if 'lastContact' in updates and updates['lastContact']:
                camp.last_contact_date = datetime.strptime(
                    updates['lastContact'], '%Y-%m-%d'
                ).date()
            if 'lastAction' in updates:
                camp.last_action = updates['lastAction']

            # Update Domain fields
            if 'expiry' in updates and updates['expiry']:
                dom.expiry_date = datetime.strptime(updates['expiry'], '%Y-%m-%d').date()
            camp.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/campaigns/<int:campaign_id>/actions', methods=['GET'])
def get_campaign_actions(campaign_id):
    from app.models.models import CampaignHistory
    history = CampaignHistory.query.filter_by(campaign_id=campaign_id).order_by(CampaignHistory.sequence.asc()).all()
    return jsonify([{
        'sequence': h.sequence,
        'action_type': h.action_type.value,
        'action_date': h.action_date.isoformat(),
        'price_before': h.price_before,
        'price_after': h.price_after,
        'notes': h.notes,
        'edited_at': h.edited_at.isoformat() if h.edited_at else None
    } for h in history])

@bp.route('/campaigns/<int:campaign_id>/actions', methods=['POST'])
def add_campaign_action(campaign_id):
    from app.services.campaign_service import create_new_action, sync_campaign_state
    from app.models.models import db, ActionType
    data = request.json
    try:
        action_type = ActionType(data['action_type'])
        action_date = datetime.fromisoformat(data['action_date'].replace('Z', ''))
        price = int(data['price_after'])
        notes = data.get('notes', '')

        new_hist = create_new_action(campaign_id, action_type, action_date, price, notes)
        db.session.commit()
        sync_campaign_state(campaign_id)

        return jsonify({'success': True, 'action': {
            'sequence': new_hist.sequence,
            'action_type': new_hist.action_type.value
        }}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@bp.route('/campaigns/<int:campaign_id>/actions/<int:sequence>', methods=['GET'])
def get_campaign_action(campaign_id, sequence):
    from app.services.campaign_service import get_history_by_sequence
    hist = get_history_by_sequence(campaign_id, sequence)
    if not hist:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'sequence': hist.sequence,
        'action_type': hist.action_type.value,
        'action_date': hist.action_date.isoformat(),
        'price_after': hist.price_after,
        'notes': hist.notes
    })

@bp.route('/campaigns/<int:campaign_id>/actions/<int:sequence>', methods=['PUT'])
def edit_campaign_action(campaign_id, sequence):
    from app.services.campaign_service import update_existing_action
    from app.models.models import ActionType
    from datetime import datetime
    data = request.json
    try:
        action_type = ActionType(data['action_type'])
        action_date = datetime.fromisoformat(data['action_date'].replace('Z', ''))
        price = int(data['price_after'])
        notes = data.get('notes', '')

        hist = update_existing_action(campaign_id, sequence, action_type, action_date, price, notes)
        if not hist:
            return jsonify({'error': 'Not found'}), 404

        return jsonify({'success': True, 'action': {
            'sequence': hist.sequence,
            'edited_at': hist.edited_at.isoformat()
        }})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


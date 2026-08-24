from flask import Blueprint, jsonify, request
from app.models.models import db, EmailAccount
from sqlalchemy import asc
import re
from sqlalchemy import desc
from datetime import datetime, timedelta

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

@bp.route('/dashboard/overview', methods=['GET'])
def get_dashboard_overview():
    from app.models.models import Domain, Campaign, CampaignStatus
    from datetime import timedelta
    expiry_days = int(request.args.get('expiry_days', 30))
    today = datetime.utcnow().date()

    total_domains = Domain.query.count()
    active_campaigns = Campaign.query.filter_by(status=CampaignStatus.ACTIVE).count()
    resting_campaigns = Campaign.query.filter_by(status=CampaignStatus.RESTING).count()
    dormant_campaigns = Campaign.query.filter_by(status=CampaignStatus.DORMANT).count()

    expiring_count = Domain.query.filter(
        Domain.expiry_date.isnot(None),
        Domain.expiry_date <= today + timedelta(days=expiry_days),
        Domain.expiry_date >= today
    ).count()
    return jsonify({
        'total_domains': total_domains,
        'active_campaigns': active_campaigns,
        'resting_campaigns': resting_campaigns,
        'dormant_campaigns': dormant_campaigns,
        'expiring_count': expiring_count
    })

@bp.route('/settings/reset-config', methods=['GET'])
def get_reset_config():
    from app.services.settings_service import get_setting
    return jsonify({
        'timezone': get_setting('EMAIL_ACCOUNT_RESET_TIMEZONE', 'America/Denver'),
        'time': get_setting('EMAIL_ACCOUNT_RESET_TIME', '08:00')
    })

@bp.route('/settings/reset-config', methods=['POST'])
def update_reset_config_route():
    from app.services.settings_service import update_reset_config
    data = request.json
    try:
        update_reset_config(data.get('timezone', 'America/Denver'), data.get('time', '08:00'))
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/dashboard/reservation-board', methods=['GET'])
def get_reservation_board():
    from app.models.models import EmailAccount, Reservation, Campaign, ReservationStatus
    from sqlalchemy import and_
    today = datetime.utcnow().date()
    accounts = EmailAccount.query.order_by(EmailAccount.profile_order).all()
    results = []

    for acc in accounts:
        state = "AVAILABLE"
        reserved_domain = None

        if not acc.enabled:
            state = "DISABLED"
        else:
            # Actually, simplify: use ReservationEmailLink directly
            from app.models.models import ReservationEmailLink
            link = ReservationEmailLink.query.join(Reservation).filter(
                and_(
                    ReservationEmailLink.email_code == acc.code,
                    Reservation.date == today,
                    Reservation.status == ReservationStatus.RESERVED
                )
        ).first()
            if link:
                state = "RESERVED"
                reserved_domain = link.reservation.campaign.domain.domain_name
            else:
                # Check for completed
                completed = ReservationEmailLink.query.join(Reservation).filter(
                    and_(
                        ReservationEmailLink.email_code == acc.code,
                        Reservation.date == today,
                        Reservation.status == ReservationStatus.COMPLETED
                        )
                ).first()
                if completed:
                    state = "COMPLETED_TODAY"

        results.append({
            'code': acc.code,
            'profile_order': acc.profile_order,
            'group': acc.group,
            'state': state,
            'reserved_domain': reserved_domain
        })
    return jsonify(results)

@bp.route('/domains', methods=['GET'])
def get_domains():
    from app.models.models import Domain, Campaign, CampaignStatus, CampaignHistory
    domains = Domain.query.all()
    results = []
    action_mapping = {
        'FIRST_OUTREACH': 'First Outreach',
        'FIRST_FOLLOW_UP': 'First Follow-up',
        'FOLLOW_UP': 'Follow-up',
        'PRICE_REDUCTION': 'Price Reduction'
    }
    for d in domains:
        c = Campaign.query.filter_by(domain_id=d.id).first()
        has_history = bool(c and CampaignHistory.query.filter_by(campaign_id=c.id).first())
        has_values = has_history

        # Get latest action's emails
        latest_emails = []
        if c and has_history:
            latest = CampaignHistory.query.filter_by(campaign_id=c.id).order_by(CampaignHistory.sequence.desc()).first()
            if latest:
                # Debug print
                print(f"DEBUG: Latest history {latest.id} for campaign {c.id}, found {len(latest.history_email_used)} emails.")
                latest_emails = [e.email_code for e in latest.history_email_used]

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
            'latestEmails': ", ".join(latest_emails),
            'hasValues': has_values
        })
    return jsonify(results)

@bp.route('/domains', methods=['POST'])
def add_domain():
    from app.models.models import Domain, Campaign, CampaignStatus, CampaignEmailBlock, EmailAccount
    data = request.json
    if Domain.query.filter_by(domain_name=data['domain']).first():
        return jsonify({'error': 'Domain exists'}), 400

    expiry_date = None
    if data.get('expiry'):
        expiry_date = datetime.strptime(data['expiry'], '%Y-%m-%d').date()

    new_dom = Domain(domain_name=data['domain'], expiry_date=expiry_date)
    db.session.add(new_dom)
    db.session.flush()

    # A new domain starts Dormant (never worked on) unless explicitly started.
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
    db.session.flush()

    # Save email accounts if provided
    if 'email_accounts' in data:
        for code in data['email_accounts']:
            if not EmailAccount.query.get(code):
                return jsonify({'error': f'Email account {code} not found'}), 400
            db.session.add(CampaignEmailBlock(campaign_id=new_camp.id, email_code=code))
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/domains/<int:id>/email-accounts', methods=['GET'])
def get_domain_email_accounts(id):
    from app.models.models import Campaign, CampaignEmailBlock
    camp = Campaign.query.filter_by(domain_id=id).first()
    if not camp: return jsonify([])
    return jsonify([{'code': b.email_code} for b in camp.email_blocks])

@bp.route('/domains/<int:id>', methods=['PUT'])
def edit_domain(id):
    from app.models.models import Domain, Campaign, CampaignStatus
    data = request.json
    dom = Domain.query.get_or_404(id)
    dom.domain_name = data.get('domain', dom.domain_name)
    if data.get('expiry'):
        dom.expiry_date = datetime.strptime(data['expiry'], '%Y-%m-%d').date()
        db.session.commit()
        return jsonify({'success': True})

@bp.route('/domains/<int:id>', methods=['DELETE'])
def delete_domain(id):
    from app.models.models import Domain, Campaign
    dom = Domain.query.get_or_404(id)
    # This assumes cascading deletes are handled by models
    db.session.delete(dom)
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

@bp.route('/domains/<int:id>/campaign-status', methods=['GET'])
def get_campaign_status(id):
    from app.models.models import Campaign
    camp = Campaign.query.filter_by(domain_id=id).first()
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404
    return jsonify({'status': camp.status.value})

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

    camp = Campaign.query.filter_by(domain_id=camp.id).first()
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

    camp = Campaign.query.filter_by(domain_id=camp.id).first()
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
            action_type=data.get('action_type', 'FIRST_OUTREACH'),
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
            if 'campaignStatus' in updates:
                camp.status = CampaignStatus[updates['campaignStatus'].upper()]
            if 'domainStatus' in updates:
                dom.status = updates['domainStatus'].upper()
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

@bp.route('/campaigns/<int:campaign_id>/actions', methods=['POST'])
def add_campaign_action(campaign_id):
    from app.services.campaign_service import create_new_action, sync_campaign_state
    from app.models.models import ActionType, Campaign, CampaignStatus
    from datetime import datetime
    data = request.json
    try:
        action_type = ActionType(data['action_type'])
        action_date = datetime.fromisoformat(data['action_date'].replace('Z', ''))
        price = int(data['price_after'])
        notes = data.get('notes', '')
        email_codes = data.get('email_codes', [])

        new_hist = create_new_action(campaign_id, action_type, action_date, price, notes, email_codes)
        # Synchronize campaign state
        sync_campaign_state(campaign_id)
        # Update campaign status
        camp = Campaign.query.get(campaign_id)
        if camp and 'campaign_status' in data:
            camp.status = CampaignStatus(data['campaign_status'])

            db.session.commit()
        return jsonify({'success': True, 'sequence': new_hist.sequence}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

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

@bp.route('/campaigns/<int:campaign_id>/actions/<int:sequence>/emails', methods=['GET'])
def get_campaign_action_emails(campaign_id, sequence):
    from app.models.models import CampaignHistory, HistoryEmailUsed
    hist = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=sequence).first()
    if not hist:
        return jsonify({'error': 'Not found'}), 404
    return jsonify([h.email_code for h in hist.history_email_used])

@bp.route('/campaigns/<int:campaign_id>/actions/<int:sequence>', methods=['PUT'])
def edit_campaign_action(campaign_id, sequence):
    from app.services.campaign_service import update_existing_action
    from app.models.models import ActionType, Campaign, CampaignStatus
    from datetime import datetime
    data = request.json
    try:
        action_type = ActionType(data['action_type'])
        action_date = datetime.fromisoformat(data['action_date'].replace('Z', ''))
        price = int(data['price_after'])
        notes = data.get('notes', '')
        email_codes = data.get('email_codes', [])

        hist = update_existing_action(campaign_id, sequence, action_type, action_date, price, notes, email_codes)
        if not hist:
            return jsonify({'error': 'Not found'}), 404
            
        # Update campaign status
        camp = Campaign.query.get(campaign_id)
        if camp and 'campaign_status' in data:
            camp.status = CampaignStatus(data['campaign_status'])
        db.session.commit()
        return jsonify({'success': True, 'action': {
            'sequence': hist.sequence,
            'edited_at': hist.edited_at.isoformat()
        }})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@bp.route('/dashboard/first-follow-ups', methods=['GET'])
def get_first_follow_ups():
    from app.models.models import Campaign, CampaignStatus, CampaignHistory, ActionType, Reservation, ReservationEmailLink, ReservationStatus
    from app.services.campaign_service import get_first_follow_up_window
    from sqlalchemy import and_
    today = datetime.utcnow().date()
    # Debug: Print what we are finding
    eligible_campaigns = Campaign.query.filter(
        Campaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.RESTING, CampaignStatus.DORMANT])
    ).all()
    print(f"DEBUG: Found {len(eligible_campaigns)} campaigns")

    due = []
    past_due = []

    for camp in eligible_campaigns:
        # Check eligibility:
        # Has FIRST_OUTREACH history record.
        first_outreach = CampaignHistory.query.filter_by(
            campaign_id=camp.id,
            action_type=ActionType.FIRST_OUTREACH
        ).order_by(CampaignHistory.sequence.asc()).first()
        if not first_outreach:
            print(f"DEBUG: Campaign {camp.id} skipped - no FIRST_OUTREACH")
            continue

        # Does not have a FIRST_FOLLOW_UP action
        has_follow_up = CampaignHistory.query.filter_by(
            campaign_id=camp.id,
            action_type=ActionType.FIRST_FOLLOW_UP
        ).first()
        if has_follow_up:
            print(f"DEBUG: Campaign {camp.id} skipped - has FOLLOW_UP")
            continue

        earliest, latest = get_first_follow_up_window(camp)
        if not earliest or not latest:
            print(f"DEBUG: Campaign {camp.id} skipped - no window")
            continue
        print(f"DEBUG: Campaign {camp.id} in window {earliest} - {latest}")

        # Emails used
        emails_used = [e.email_code for e in first_outreach.history_email_used]

        # Reservation state
        reservation_state = "Unreserved"
        reserved_by = None

        # Simple reservation logic
        current_res = Reservation.query.filter_by(date=today, campaign_id=camp.id).first()
        if current_res:
             reservation_state = "Reserved"
             reserved_by = camp.domain.domain_name
        else:
            # Check for other reservations
            for email in emails_used:
                link = ReservationEmailLink.query.join(Reservation).filter(
                    and_(
                        ReservationEmailLink.email_code == email,
                        Reservation.date == today,
                        Reservation.status == ReservationStatus.RESERVED
                    )
                ).first()
                if link:
                    reservation_state = "Reserved"
                    reserved_by = link.reservation.campaign.domain.domain_name
                    break

            # Check for completed
            if reservation_state == "Unreserved":
                 for email in emails_used:
                    link = ReservationEmailLink.query.join(Reservation).filter(
                        and_(
                            ReservationEmailLink.email_code == email,
                            Reservation.date == today,
                            Reservation.status == ReservationStatus.COMPLETED
                        )
                    ).first()
                    if link:
                        reservation_state = "Used"
                        break

        days_since = (today - first_outreach.action_date.date()).days
        campaign_info = {
            'domain': camp.domain.domain_name,
            'campaign_id': camp.id,
            'status': camp.status.value,
            'current_sequence': camp.current_sequence,
            'first_outreach_date': first_outreach.action_date.date().isoformat(),
            'earliest_due_date': earliest.isoformat(),
            'latest_due_date': latest.isoformat(),
            'days_since_outreach': days_since,
            'emails_used': emails_used,
            'reservation': {
                'state': reservation_state,
                'reserved_by': reserved_by
            }
        }

        if earliest <= today <= latest:
            due.append(campaign_info)
        elif today > latest:
            past_due.append(campaign_info)
        else:
            # Just add it to a catch-all or confirm why it wasn't added
            print(f"DEBUG: Campaign {camp.id} not due yet, today={today}")

    return jsonify({"due": due, "past_due": past_due})

@bp.route('/campaigns/<int:campaign_id>/reservation', methods=['POST'])
def reserve_campaign(campaign_id):
    from app.models.models import Campaign, Reservation, ReservationEmailLink, ReservationStatus
    from app.services.settings_service import get_setting
    from sqlalchemy import and_

    limit = int(get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1'))
    today = datetime.utcnow().date()
    camp = Campaign.query.get_or_404(campaign_id)

    # Get required emails from campaign's latest action (First Outreach for first-followups)
    # Using the same logic as in get_first_follow_ups
    from app.models.models import CampaignHistory, ActionType
    first_outreach = CampaignHistory.query.filter_by(
        campaign_id=camp.id,
        action_type=ActionType.FIRST_OUTREACH
    ).order_by(CampaignHistory.sequence.asc()).first()

    if not first_outreach:
        return jsonify({'error': 'No outreach found'}), 400

    emails_required = [e.email_code for e in first_outreach.history_email_used]

    # Check conflicts
    conflicts = {}
    for email in emails_required:
        # Count reservations for this email today
        # Exclude reservations by this campaign
        count = ReservationEmailLink.query.join(Reservation).filter(
            and_(
                ReservationEmailLink.email_code == email,
                Reservation.date == today,
                Reservation.status == ReservationStatus.RESERVED,
                Reservation.campaign_id != camp.id
            )
        ).count()

        if count >= limit:
            # Find who reserved
            link = ReservationEmailLink.query.join(Reservation).filter(
                and_(
                    ReservationEmailLink.email_code == email,
                    Reservation.date == today,
                    Reservation.status == ReservationStatus.RESERVED
                )
            ).first()
            if link:
                conflicts[email] = f"{email} is reserved by {link.reservation.campaign.domain.domain_name}"
            else:
                conflicts[email] = f"{email} has reached its daily use limit of {limit}"

    if conflicts:
        return jsonify({'error': 'Conflict', 'details': list(conflicts.values())}), 409

    # Create reservation
    new_res = Reservation(campaign_id=camp.id, date=today, status=ReservationStatus.RESERVED)
    db.session.add(new_res)
    db.session.flush()
    for email in emails_required:
        db.session.add(ReservationEmailLink(reservation_id=new_res.id, email_code=email))

    db.session.commit()
    return jsonify({'success': True})

@bp.route('/campaigns/<int:campaign_id>/reservation', methods=['DELETE'])
def unreserve_campaign(campaign_id):
    from app.models.models import Reservation, ReservationStatus
    today = datetime.utcnow().date()
    res = Reservation.query.filter_by(campaign_id=campaign_id, date=today, status=ReservationStatus.RESERVED).first()
    if res:
        db.session.delete(res)
        db.session.commit()
    return jsonify({'success': True})


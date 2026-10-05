from flask import Blueprint, jsonify, request, send_file
from app.models.models import db, EmailAccount
from sqlalchemy import asc
import csv
import io
import json
from sqlalchemy import desc
from datetime import date, datetime, timedelta
from app.services.time_service import get_business_today

from app.services.email_account_service import (
    BulkEmailAccountValidationError,
    EmailCodeValidationError,
    build_bulk_preview,
    lock_email_account_order,
    parse_code,
    persist_bulk_accounts,
    suggest_profile_order,
    validate_email_codes,
)

bp = Blueprint('api', __name__, url_prefix='/api')


def _parse_campaign_action_date(value):
    """Parse action dates without applying timezone conversion to date-only input."""
    raw_value = str(value).strip()
    if len(raw_value) == 10:
        return datetime.combine(date.fromisoformat(raw_value), datetime.min.time())
    return datetime.fromisoformat(raw_value.replace('Z', ''))


def _parse_team_domain_date(value, field_name):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date (YYYY-MM-DD).")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date (YYYY-MM-DD).") from exc


def _parse_positive_id(value, field_name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value


@bp.route('/backup/export.xlsx', methods=['GET'])
def export_backup_xlsx():
    from app.services.backup_export_service import build_xlsx_export, export_filename

    return send_file(
        build_xlsx_export(),
        as_attachment=True,
        download_name=export_filename('xlsx'),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@bp.route('/backup/export.zip', methods=['GET'])
def export_backup_zip():
    from app.services.backup_export_service import build_csv_zip_export, export_filename

    return send_file(
        build_csv_zip_export(),
        as_attachment=True,
        download_name=export_filename('zip'),
        mimetype='application/zip',
    )


@bp.route('/backup/restore/validate', methods=['POST'])
def validate_backup_restore():
    from app.services.backup_restore_service import preflight_backup

    result = preflight_backup(request.files.get('file'))
    if result['valid']:
        return jsonify(result)
    status_code = 409 if result['database_empty'] is False else 400
    return jsonify(result), status_code


@bp.route('/backup/restore', methods=['POST'])
def restore_backup_route():
    from app.services.backup_restore_service import (
        CONFIRMATION_TEXT,
        BackupRestoreError,
        restore_backup,
    )

    if request.form.get('confirmation') != CONFIRMATION_TEXT:
        return jsonify({
            'success': False,
            'error': f"Type '{CONFIRMATION_TEXT}' to confirm restore.",
        }), 400
    try:
        counts = restore_backup(request.files.get('file'))
        return jsonify({'success': True, 'restored': counts})
    except BackupRestoreError as exc:
        return jsonify({
            'success': False,
            'error': str(exc),
            'errors': exc.errors,
        }), exc.status_code


@bp.route('/export/spreadsheet.xlsx', methods=['GET'])
def export_spreadsheet_xlsx():
    from app.services.spreadsheet_export_service import (
        build_spreadsheet_xlsx,
        spreadsheet_export_filename,
    )

    return send_file(
        build_spreadsheet_xlsx(),
        as_attachment=True,
        download_name=spreadsheet_export_filename('xlsx'),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@bp.route('/export/spreadsheet.zip', methods=['GET'])
def export_spreadsheet_zip():
    from app.services.spreadsheet_export_service import (
        build_spreadsheet_csv_zip,
        spreadsheet_export_filename,
    )

    return send_file(
        build_spreadsheet_csv_zip(),
        as_attachment=True,
        download_name=spreadsheet_export_filename('zip'),
        mimetype='application/zip',
    )


def _email_code_validation_response(exc):
    return jsonify({
        'success': False,
        'error': str(exc),
        'errors': exc.errors,
    }), 400

@bp.route('/email-accounts', methods=['GET'])
def get_email_accounts():
    accounts = EmailAccount.query.order_by(asc(EmailAccount.profile_order)).all()
    return jsonify([{
        'code': a.code,
        'group': a.group,
        'order': a.profile_order,
        'enabled': a.enabled,
        'state': 'Available' if a.enabled else 'Disabled',
    } for a in accounts])


@bp.route('/email-accounts/status', methods=['POST'])
def update_email_account_status():
    from sqlalchemy.exc import SQLAlchemyError

    data = request.get_json(silent=True)
    updates = data.get('accounts') if isinstance(data, dict) else None
    if not isinstance(updates, list) or not updates:
        return jsonify({'error': 'Accounts must be a non-empty list.'}), 400

    normalized_updates = []
    seen_codes = set()
    for update in updates:
        if not isinstance(update, dict):
            return jsonify({'error': 'Each account update must be an object.'}), 400
        code = update.get('code')
        enabled = update.get('enabled')
        if not isinstance(code, str) or not code.strip():
            return jsonify({'error': 'Each account update requires a code.'}), 400
        if type(enabled) is not bool:
            return jsonify({'error': 'Each account update requires a boolean enabled value.'}), 400
        normalized_code = code.strip().upper()
        if normalized_code in seen_codes:
            return jsonify({'error': f'Duplicate account code: {normalized_code}.'}), 400
        seen_codes.add(normalized_code)
        normalized_updates.append((normalized_code, enabled))

    try:
        codes = [code for code, _ in normalized_updates]
        accounts = EmailAccount.query.filter(EmailAccount.code.in_(codes)).all()
        accounts_by_code = {account.code: account for account in accounts}
        missing_codes = [code for code in codes if code not in accounts_by_code]
        if missing_codes:
            return jsonify({
                'error': 'One or more email accounts were not found.',
                'missing_codes': missing_codes,
            }), 404

        for code, enabled in normalized_updates:
            accounts_by_code[code].enabled = enabled
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({'error': 'Unable to update email account status.'}), 500

    return jsonify({
        'success': True,
        'accounts': [{
            'code': accounts_by_code[code].code,
            'group': accounts_by_code[code].group,
            'order': accounts_by_code[code].profile_order,
            'enabled': accounts_by_code[code].enabled,
            'state': 'Available' if accounts_by_code[code].enabled else 'Disabled',
        } for code in codes],
    })

@bp.route('/email-accounts/suggest-order', methods=['POST'])
def suggest_order():
    code = (request.get_json(silent=True) or {}).get('code')
    try:
        code = validate_email_codes(
            [code], require_nonempty=True, check_exists=False
        )[0]
    except EmailCodeValidationError as exc:
        return _email_code_validation_response(exc)

    accounts = EmailAccount.query.all()
    return jsonify({'suggested_order': suggest_profile_order(code, accounts)})


def _bulk_account_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('A JSON object is required.')
    enabled = data.get('enabled', True)
    if type(enabled) is not bool:
        raise ValueError('Enabled must be a boolean.')
    return data.get('codes'), enabled


@bp.route('/email-accounts/bulk/preview', methods=['POST'])
@bp.route('/email-accounts/bulk-preview', methods=['POST'])
def preview_bulk_email_accounts():
    try:
        codes, enabled = _bulk_account_request()
        accounts = EmailAccount.query.order_by(
            EmailAccount.profile_order, EmailAccount.code
        ).all()
        report = build_bulk_preview(codes, enabled, accounts)
        return jsonify(report)
    except ValueError as exc:
        return jsonify({'valid': False, 'error': str(exc)}), 400


@bp.route('/email-accounts/bulk', methods=['POST'])
@bp.route('/email-accounts/bulk-add', methods=['POST'])
def bulk_add_email_accounts():
    try:
        codes, enabled = _bulk_account_request()
        accounts = lock_email_account_order()
        report = build_bulk_preview(codes, enabled, accounts)
        if not report['valid']:
            db.session.rollback()
            return jsonify(report), 400
        new_accounts = persist_bulk_accounts(report, accounts)
        db.session.commit()
        return jsonify({
            'success': True,
            'accounts': [{
                'code': account.code,
                'group': account.group,
                'order': account.profile_order,
                'enabled': account.enabled,
                'state': 'Available' if account.enabled else 'Disabled',
            } for account in new_accounts],
            'final_order': report['final_order'],
        })
    except BulkEmailAccountValidationError as exc:
        db.session.rollback()
        return jsonify(exc.report), 400
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Unable to add email accounts.'}), 500
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
    code = request.args.get('code', '').strip().upper()
    acc = EmailAccount.query.get(code)
    if acc:
        return jsonify({
            'exists': True,
            'account': {
                'code': acc.code,
                'group': acc.group,
                'order': acc.profile_order,
                'enabled': acc.enabled,
                'state': 'Available' if acc.enabled else 'Disabled',
            }
        })
    return jsonify({'exists': False})

@bp.route('/email-accounts/add', methods=['POST'])
def add_email_account():
    data = request.get_json(silent=True) or {}
    try:
        code = validate_email_codes(
            [data.get('code')], require_nonempty=True, check_exists=False
        )[0]
    except EmailCodeValidationError as exc:
        return _email_code_validation_response(exc)
    prefix, _ = parse_code(code)
    new_order = int(data['order'])
    try:
        # Serialize this order-changing path with bulk insertion so a single
        # add cannot calculate against an order that bulk insertion is moving.
        accounts = lock_email_account_order()
        existing = next((account for account in accounts if account.code == code), None)
        if existing and not data.get('overwrite'):
            db.session.rollback()
            return jsonify({'error': 'Code already exists', 'existing': True}), 409

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
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Unable to save email account.'}), 500

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

@bp.route('/settings/business-info', methods=['GET'])
def get_business_info():
    from app.services.time_service import get_business_timezone, get_business_today
    return jsonify({
        'business_timezone': str(get_business_timezone()),
        'business_today': get_business_today().isoformat()
    })

@bp.route('/settings/timezones', methods=['GET'])
def get_timezones():
    from zoneinfo import available_timezones
    timezones = sorted(list(available_timezones()))
    # Create friendly labels
    results = []
    for tz in timezones:
        # Simplistic friendly label
        label = tz.replace('_', ' ')
        results.append({'id': tz, 'label': f"{label} ({tz})"})
    return jsonify(results)

@bp.route('/settings/business-timezone', methods=['POST'])
def save_timezone():
    from app.services.settings_service import set_setting
    from zoneinfo import ZoneInfo
    data = request.json
    tz = data.get('timezone')
    try:
        ZoneInfo(tz) # Validate
        set_setting('BUSINESS_TIMEZONE', tz)
        return jsonify({'success': True})
    except Exception:
        return jsonify({'error': 'Invalid timezone'}), 400

@bp.route('/settings/follow-up-config', methods=['GET'])
def get_follow_up_config():
    from app.services.settings_service import get_setting
    return jsonify({
        'first': {
            'mode': get_setting('FIRST_FOLLOW_UP_MODE', 'fixed'),
            'min': get_setting('FIRST_FOLLOW_UP_MIN', '2'),
            'max': get_setting('FIRST_FOLLOW_UP_MAX', '2')
        },
        'normal': {
            'mode': get_setting('NORMAL_FOLLOW_UP_MODE', 'fixed'),
            'min': get_setting('NORMAL_FOLLOW_UP_MIN', '7'),
            'max': get_setting('NORMAL_FOLLOW_UP_MAX', '7')
        }
    })

@bp.route('/settings/follow-up-config', methods=['POST'])
def save_follow_up_config():
    from app.services.settings_service import set_setting
    data = request.json
    try:
        for key, config in data.items():
            mode = config['mode']
            min_val = int(config['min'])
            max_val = int(config['max'])

            if mode == 'fixed':
                min_val = max_val = int(config.get('fixed', max_val))

            if min_val < 0 or max_val < 0 or min_val > max_val:
                raise ValueError("Invalid range")

            prefix = key.upper()
            set_setting(f'{prefix}_FOLLOW_UP_MODE', mode)
            set_setting(f'{prefix}_FOLLOW_UP_MIN', str(min_val))
            set_setting(f'{prefix}_FOLLOW_UP_MAX', str(max_val))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/settings/resting-eligibility-config', methods=['GET'])
def get_resting_eligibility_config_route():
    from app.services.settings_service import get_resting_eligibility_config
    return jsonify(get_resting_eligibility_config())

@bp.route('/settings/resting-eligibility-config', methods=['POST'])
def save_resting_eligibility_config():
    from app.services.settings_service import update_resting_eligibility_config
    data = request.get_json(silent=True)
    try:
        config = update_resting_eligibility_config(data)
        return jsonify({'success': True, 'config': config})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400

@bp.route('/settings/expiring-soon-days', methods=['GET'])
def get_expiring_soon_days_route():
    from app.services.expiry_service import get_expiring_soon_days
    try:
        return jsonify({'expiring_soon_days': get_expiring_soon_days()})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 500

@bp.route('/settings/expiring-soon-days', methods=['POST'])
def save_expiring_soon_days():
    from app.services.expiry_service import update_expiring_soon_days
    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict) or set(data) != {'expiring_soon_days'}:
            raise ValueError('Expiring Soon settings must contain expiring_soon_days.')
        days = update_expiring_soon_days(data['expiring_soon_days'])
        return jsonify({'success': True, 'expiring_soon_days': days})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400

@bp.route('/settings/ready-for-campaign-days', methods=['GET'])
def get_ready_for_campaign_days_route():
    from app.services.ready_for_campaign_service import get_ready_for_campaign_days
    try:
        return jsonify({'ready_for_campaign_days': get_ready_for_campaign_days()})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 500

@bp.route('/settings/ready-for-campaign-days', methods=['POST'])
def save_ready_for_campaign_days():
    from app.services.ready_for_campaign_service import update_ready_for_campaign_days
    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict) or set(data) != {'ready_for_campaign_days'}:
            raise ValueError('Ready for Campaign settings must contain ready_for_campaign_days.')
        days = update_ready_for_campaign_days(data['ready_for_campaign_days'])
        return jsonify({'success': True, 'ready_for_campaign_days': days})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400

@bp.route('/settings/campaign-temperature', methods=['GET'])
def get_campaign_temperature_settings():
    from app.services.campaign_temperature_service import get_campaign_temperature_config

    try:
        return jsonify(get_campaign_temperature_config())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 500

@bp.route('/settings/campaign-temperature', methods=['POST'])
def save_campaign_temperature_settings():
    from app.services.campaign_temperature_service import (
        update_campaign_temperature_config,
    )

    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict) or set(data) != {
            'hot_through', 'tepid_through', 'ready_at'
        }:
            raise ValueError(
                'Campaign Temperature settings must contain hot_through, '
                'tepid_through, and ready_at.'
            )
        config = update_campaign_temperature_config(
            data['hot_through'], data['tepid_through'], data['ready_at']
        )
        return jsonify({'success': True, **config})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/settings/team-domains', methods=['GET'])
def get_team_domain_settings():
    from app.services.team_domains_service import get_team_domain_config

    try:
        return jsonify(get_team_domain_config())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 500


@bp.route('/settings/team-domains', methods=['POST'])
def save_team_domain_settings():
    from app.services.team_domains_service import update_team_domain_config

    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict) or set(data) != {'warning_days', 'rest_days'}:
            raise ValueError(
                'Team Domains settings must contain warning_days and rest_days.'
            )
        config = update_team_domain_config(data['warning_days'], data['rest_days'])
        return jsonify({'success': True, **config})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/settings/expired-domains', methods=['GET'])
def get_expired_domain_settings():
    from app.services.expired_historical_service import get_expired_domain_settings

    try:
        return jsonify(get_expired_domain_settings())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 500


@bp.route('/settings/expired-domains', methods=['POST'])
def save_expired_domain_settings():
    from app.services.expired_historical_service import update_expired_domain_settings

    data = request.get_json(silent=True)
    try:
        allowed = {
            'expired_domain_retention_days',
            'expired_domain_auto_archive_days',
        }
        if not isinstance(data, dict) or not set(data) or not set(data) <= allowed:
            raise ValueError(
                'Expired Domain settings contain an unsupported field.'
            )
        settings = update_expired_domain_settings(
            retention_days=data.get('expired_domain_retention_days'),
            auto_archive_days=data.get('expired_domain_auto_archive_days'),
        )
        return jsonify({'success': True, **settings})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/expired-historical', methods=['GET'])
@bp.route('/expired-domains', methods=['GET'])
def get_expired_historical():
    from app.services.expired_historical_service import list_expired_historical

    try:
        return jsonify(list_expired_historical(
            expired_search=request.args.get('expired_search', request.args.get('search')),
            historical_search=request.args.get('historical_search', request.args.get('search')),
        ))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 500


@bp.route('/expired-historical/archive', methods=['POST'])
@bp.route('/expired-domains/archive', methods=['POST'])
def archive_expired_domains():
    from app.services.expired_historical_service import (
        ExpiredHistoricalValidationError,
        archive_eligible_domains,
    )

    data = request.get_json(silent=True)
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict) or set(data) - {'domain_ids'}:
            raise ValueError('Archive data may only contain domain_ids.')
        result = archive_eligible_domains(data.get('domain_ids'))
        return jsonify({'success': True, **result})
    except ExpiredHistoricalValidationError as exc:
        payload = {'error': str(exc)}
        if exc.stale_domain_ids:
            payload['stale_domain_ids'] = exc.stale_domain_ids
        return jsonify(payload), 409
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/team-members', methods=['GET'])
def get_team_members():
    from app.services.team_domains_service import list_team_members, serialize_team_member

    return jsonify([serialize_team_member(member) for member in list_team_members()])


@bp.route('/team-members', methods=['POST'])
def add_team_member():
    from app.services.team_domains_service import create_team_member, serialize_team_member

    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict):
            raise ValueError('Team member data must be an object.')
        member = create_team_member(data.get('name'), data.get('member_type'))
        return jsonify({'success': True, 'member': serialize_team_member(member)}), 201
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/team-members/<int:member_id>', methods=['PUT'])
def edit_team_member(member_id):
    from app.services.team_domains_service import update_team_member, serialize_team_member

    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict):
            raise ValueError('Team member data must be an object.')
        member = update_team_member(
            member_id,
            data.get('name'),
            data.get('member_type'),
        )
        return jsonify({'success': True, 'member': serialize_team_member(member)})
    except Exception as exc:
        from app.services.team_domains_service import TeamDomainNotFoundError, TeamDomainValidationError

        if isinstance(exc, TeamDomainNotFoundError):
            return jsonify({'error': str(exc)}), 404
        if isinstance(exc, TeamDomainValidationError):
            return jsonify({'error': str(exc)}), 409
        if isinstance(exc, (TypeError, ValueError)):
            return jsonify({'error': str(exc)}), 400
        raise


@bp.route('/team-members/<int:member_id>', methods=['DELETE'])
def remove_team_member(member_id):
    from app.services.team_domains_service import (
        TeamDomainNotFoundError,
        TeamDomainValidationError,
        delete_team_member,
    )

    try:
        delete_team_member(member_id)
        return jsonify({'success': True})
    except TeamDomainNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except TeamDomainValidationError as exc:
        return jsonify({'error': str(exc)}), 409


@bp.route('/team-domain-assignments', methods=['GET'])
@bp.route('/team-domains', methods=['GET'])
def get_team_domain_assignments():
    from app.services.team_domains_service import list_assignments

    raw_member_id = request.args.get('team_member_id')
    try:
        member_id = None
        if raw_member_id not in (None, ''):
            member_id = _parse_positive_id(int(raw_member_id), 'team_member_id')
        return jsonify(list_assignments(
            search=request.args.get('search'),
            team_member_id=member_id,
        ))
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/team-domain-assignments', methods=['POST'])
@bp.route('/team-domains', methods=['POST'])
def add_team_domain_assignment():
    from app.services.team_domains_service import create_assignment, serialize_assignment

    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict):
            raise ValueError('Team domain assignment data must be an object.')
        assignment = create_assignment(
            _parse_positive_id(data.get('team_member_id'), 'team_member_id'),
            data.get('domain_name'),
            _parse_team_domain_date(data.get('assigned_date'), 'Assigned date'),
            _parse_team_domain_date(data.get('expiry_date'), 'Expiry date'),
        )
        return jsonify({'success': True, 'assignment': serialize_assignment(assignment)}), 201
    except Exception as exc:
        from app.services.team_domains_service import TeamDomainNotFoundError

        if isinstance(exc, TeamDomainNotFoundError):
            return jsonify({'error': str(exc)}), 404
        if isinstance(exc, (TypeError, ValueError)):
            return jsonify({'error': str(exc)}), 400
        raise


@bp.route('/team-domain-assignments/bulk', methods=['POST'])
@bp.route('/team-domains/bulk', methods=['POST'])
def bulk_add_team_domain_assignments():
    from app.services.team_domains_service import (
        TeamDomainNotFoundError,
        TeamDomainValidationError,
        bulk_create_assignments,
        serialize_assignment,
    )

    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict):
            raise ValueError('Bulk team domain assignment data must be an object.')
        assignments = bulk_create_assignments(
            _parse_positive_id(data.get('team_member_id'), 'team_member_id'),
            data.get('domain_names', data.get('domains')),
            _parse_team_domain_date(data.get('assigned_date'), 'Assigned date'),
            _parse_team_domain_date(data.get('expiry_date'), 'Expiry date'),
        )
        return jsonify({
            'success': True,
            'count': len(assignments),
            'assignments': [serialize_assignment(assignment) for assignment in assignments],
        }), 201
    except TeamDomainNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except TeamDomainValidationError as exc:
        return jsonify({'error': str(exc)}), 409
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/team-domain-assignments/<int:assignment_id>', methods=['PUT'])
@bp.route('/team-domains/<int:assignment_id>', methods=['PUT'])
def edit_team_domain_assignment(assignment_id):
    from app.services.team_domains_service import update_assignment, serialize_assignment

    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict):
            raise ValueError('Team domain assignment data must be an object.')
        assignment = update_assignment(
            assignment_id,
            _parse_positive_id(data.get('team_member_id'), 'team_member_id'),
            data.get('domain_name'),
            _parse_team_domain_date(data.get('assigned_date'), 'Assigned date'),
            _parse_team_domain_date(data.get('expiry_date'), 'Expiry date'),
        )
        return jsonify({'success': True, 'assignment': serialize_assignment(assignment)})
    except Exception as exc:
        from app.services.team_domains_service import TeamDomainNotFoundError

        if isinstance(exc, TeamDomainNotFoundError):
            return jsonify({'error': str(exc)}), 404
        if isinstance(exc, (TypeError, ValueError)):
            return jsonify({'error': str(exc)}), 400
        raise


@bp.route('/team-domain-assignments/<int:assignment_id>', methods=['DELETE'])
@bp.route('/team-domains/<int:assignment_id>', methods=['DELETE'])
def remove_team_domain_assignment(assignment_id):
    from app.services.team_domains_service import TeamDomainNotFoundError, delete_assignment

    try:
        delete_assignment(assignment_id)
        return jsonify({'success': True})
    except TeamDomainNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404

@bp.route('/settings/dashboard-section-order', methods=['GET'])
def get_dashboard_section_order_route():
    from app.services.dashboard_section_order_service import get_dashboard_section_order
    return jsonify({'order': get_dashboard_section_order()})

@bp.route('/settings/dashboard-section-order', methods=['POST'])
def save_dashboard_section_order():
    from app.services.dashboard_section_order_service import update_dashboard_section_order
    data = request.get_json(silent=True)
    try:
        if not isinstance(data, dict) or set(data) != {'order'}:
            raise ValueError('Dashboard section order settings must contain order.')
        order = update_dashboard_section_order(data['order'])
        return jsonify({'success': True, 'order': order})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400

@bp.route('/dashboard/overview', methods=['GET'])
def get_dashboard_overview():
    from app.models.models import Domain, Campaign, CampaignStatus
    from app.services.expired_historical_service import is_expired_domain
    from app.services.time_service import get_business_today
    from app.services.expiry_service import expiring_soon_bounds, get_expiring_soon_days
    today = get_business_today()
    expiry_days = get_expiring_soon_days()
    expiry_start, expiry_end = expiring_soon_bounds(today, expiry_days)

    total_domains = sum(
        1 for domain in Domain.query.all()
        if not is_expired_domain(domain, business_today=today)
    )
    active_campaigns = sum(
        1 for campaign in Campaign.query.filter_by(status=CampaignStatus.ACTIVE).all()
        if not is_expired_domain(campaign.domain, business_today=today)
    )
    resting_campaigns = sum(
        1 for campaign in Campaign.query.filter_by(status=CampaignStatus.RESTING).all()
        if not is_expired_domain(campaign.domain, business_today=today)
    )
    dormant_campaigns = sum(
        1 for campaign in Campaign.query.filter_by(status=CampaignStatus.DORMANT).all()
        if not is_expired_domain(campaign.domain, business_today=today)
    )
    expiring_count = Domain.query.filter(
        Domain.expiry_date.isnot(None),
        Domain.expiry_date <= expiry_end,
        Domain.expiry_date >= expiry_start,
        Domain.status.notin_(['SOLD', 'EXPIRED']),
    ).count()
    return jsonify({
        'total_domains': total_domains,
        'active_campaigns': active_campaigns,
        'resting_campaigns': resting_campaigns,
        'dormant_campaigns': dormant_campaigns,
        'expiring_count': expiring_count,
        'expiring_soon_days': expiry_days,
    })

@bp.route('/dashboard/expiring-soon', methods=['GET'])
def get_expiring_soon():
    from sqlalchemy.orm import selectinload
    from app.models.models import Domain
    from app.services.expiry_service import (
        days_until_expiry,
        expiring_soon_bounds,
        get_expiring_soon_days,
        select_latest_campaign,
    )
    from app.services.time_service import get_business_today
    from app.services.dashboard_campaign_context_service import build_campaign_context
    from app.services.expiry_service import select_latest_campaign

    today = get_business_today()
    threshold_days = get_expiring_soon_days()
    expiry_start, expiry_end = expiring_soon_bounds(today, threshold_days)
    domains = Domain.query.options(selectinload(Domain.campaigns)).filter(
        Domain.expiry_date.isnot(None),
        Domain.expiry_date >= expiry_start,
        Domain.expiry_date <= expiry_end,
        Domain.status.notin_(['SOLD', 'EXPIRED']),
    ).order_by(Domain.expiry_date.asc(), Domain.domain_name.asc(), Domain.id.asc()).all()

    results = []
    for domain in domains:
        campaign = select_latest_campaign(domain.campaigns)
        context = build_campaign_context(campaign, business_today=today) if campaign else None
        days_since_last_contact = None
        if campaign and campaign.last_contact_date is not None:
            days_since_last_contact = (today - campaign.last_contact_date).days

        results.append({
            'domain_id': domain.id,
            'domain_name': domain.domain_name,
            'expiry_date': domain.expiry_date.isoformat(),
            'days_until_expiry': days_until_expiry(domain.expiry_date, today),
            'domain_status': domain.status,
            'campaign_id': campaign.id if campaign else None,
            'campaign_status': campaign.status.value if campaign else None,
            'current_sequence': campaign.current_sequence if campaign else None,
            'current_price': campaign.current_price if campaign else None,
            'last_contact_date': (
                campaign.last_contact_date.isoformat()
                if campaign and campaign.last_contact_date else None
            ),
            'days_since_last_contact': days_since_last_contact,
            'handled_by': campaign.handled_by if campaign else None,
            'operational_emails': (
                context['operational_emails'] if context else []
            ),
            'price_progression': (
                context['price_progression'] if context else ''
            ),
            'expiry_severity': context['expiry_severity'] if context else 'neutral',
        })

    return jsonify({
        'business_today': today.isoformat(),
        'expiring_soon_days': threshold_days,
        'count': len(results),
        'domains': results,
    })

@bp.route('/dashboard/ready-for-campaign', methods=['GET'])
def get_ready_for_campaign():
    from math import inf
    from sqlalchemy.orm import selectinload
    from app.models.models import CampaignStatus, Domain
    from app.services.expiry_service import days_until_expiry, select_latest_campaign
    from app.services.ready_for_campaign_service import (
        evaluate_ready_for_campaign,
        get_ready_for_campaign_days,
    )
    from app.services.expired_historical_service import is_expired_domain
    from app.services.time_service import get_business_today
    from app.services.dashboard_campaign_context_service import build_campaign_context

    today = get_business_today()
    threshold_days = get_ready_for_campaign_days()
    results = []
    domains = Domain.query.options(selectinload(Domain.campaigns)).all()

    for domain in domains:
        if str(domain.status or '').upper() == 'SOLD' or is_expired_domain(domain, business_today=today):
            continue

        campaign = select_latest_campaign(domain.campaigns)
        if campaign is None:
            continue

        eligibility = evaluate_ready_for_campaign(
            campaign,
            business_today=today,
            threshold_days=threshold_days,
        )
        if not eligibility['eligible']:
            continue

        days_until = days_until_expiry(domain.expiry_date, today)
        days_since = eligibility['days_since_last_contact']
        if eligibility['reason_code'] == 'dormant':
            ready_reason = 'Campaign is dormant and ready to work.'
        elif eligibility['reason_code'] == 'active_inactivity':
            ready_reason = f'Last contacted {days_since} days ago; campaign is still ACTIVE.'
        else:
            ready_reason = f'Last contacted {days_since} days ago; campaign is currently RESTING.'

        context = build_campaign_context(campaign, business_today=today)

        results.append({
            'domain_id': domain.id,
            'domain_name': domain.domain_name,
            'domain_status': domain.status,
            'campaign_id': campaign.id,
            'campaign_status': campaign.status.value,
            'current_sequence': campaign.current_sequence,
            'current_price': campaign.current_price,
            'last_contact_date': (
                campaign.last_contact_date.isoformat()
                if campaign.last_contact_date else None
            ),
            'days_since_last_contact': days_since,
            'expiry_date': domain.expiry_date.isoformat() if domain.expiry_date else None,
            'days_until_expiry': days_until,
            'handled_by': campaign.handled_by,
            'campaign_start_date': campaign.start_date.isoformat() if campaign.start_date else None,
            'ready_reason_code': eligibility['reason_code'],
            'ready_reason': ready_reason,
            'operational_emails': context['operational_emails'],
            'price_progression': context['price_progression'],
            'expiry_severity': context['expiry_severity'],
            'temperature': context['temperature'],
            'temperature_label': context['label'],
            'temperature_emoji': context['emoji'],
        })

    def sort_key(item):
        expiry_days = item['days_until_expiry']
        age_days = item['days_since_last_contact']
        return (
            0 if expiry_days is not None else 1,
            expiry_days if expiry_days is not None else inf,
            -(age_days if age_days is not None else -1),
            item['domain_name'].lower(),
            item['domain_id'],
        )

    results.sort(key=sort_key)
    return jsonify({
        'business_today': today.isoformat(),
        'ready_for_campaign_days': threshold_days,
        'count': len(results),
        'domains': results,
    })

@bp.route('/dashboard/resting-suggestions', methods=['GET'])
def get_resting_suggestions():
    from app.models.models import Campaign, CampaignStatus, Domain, db
    from app.services.resting_eligibility_service import evaluate_resting_eligibility
    from app.services.settings_service import get_resting_eligibility_config
    from app.services.time_service import get_business_today
    from app.services.dashboard_campaign_context_service import build_campaign_context
    from app.services.expiry_service import select_latest_campaign
    from app.services.campaign_temperature_service import (
        TEMPERATURE_TEPID,
        TEMPERATURE_HOT,
        calculate_campaign_temperature,
        get_campaign_temperature_config,
    )
    from app.services.expired_historical_service import is_expired_domain

    trigger_labels = {
        'sequence': 'Sequence',
        'days_since_last_contact': 'Days Since Last Contact',
        'campaign_age': 'Campaign Age',
        'known_activity_age': 'Known Activity Age',
    }
    metric_names = {
        'sequence': 'current_sequence',
        'days_since_last_contact': 'days_since_last_contact',
        'campaign_age': 'campaign_age_days',
        'known_activity_age': 'known_activity_age_days',
    }

    suggestions = []
    with db.session.no_autoflush:
        today = get_business_today()
        trigger_config = get_resting_eligibility_config()
        temperature_config = get_campaign_temperature_config()
        campaigns = Campaign.query.filter_by(
            status=CampaignStatus.ACTIVE
        ).join(Domain).order_by(Domain.domain_name.asc(), Campaign.id.asc()).all()

        for campaign in campaigns:
            if str(campaign.domain.status or '').upper() == 'SOLD' or is_expired_domain(campaign.domain, business_today=today):
                continue
            if select_latest_campaign(campaign.domain.campaigns) is not campaign:
                continue
            temperature = calculate_campaign_temperature(
                campaign,
                business_today=today,
                temperature_config=temperature_config,
            )
            if temperature not in {TEMPERATURE_HOT, TEMPERATURE_TEPID}:
                continue
            eligibility = evaluate_resting_eligibility(
                campaign,
                trigger_config,
                business_today=today,
            )
            if not eligibility['eligible']:
                continue

            trigger_reasons = []
            for trigger in eligibility['triggered_by']:
                metric = eligibility['metrics'][metric_names[trigger]]
                threshold = trigger_config[trigger]['threshold']
                if trigger == 'sequence':
                    text = f"Sequence {metric} reached threshold {threshold}"
                elif trigger == 'days_since_last_contact':
                    text = f"{metric} days since last contact (threshold {threshold})"
                elif trigger == 'campaign_age':
                    text = f"Campaign age: {metric} days (threshold {threshold})"
                else:
                    text = f"Known activity age: {metric} days (threshold {threshold})"
                trigger_reasons.append({
                    'trigger': trigger,
                    'label': trigger_labels[trigger],
                    'value': metric,
                    'threshold': threshold,
                    'text': text,
                })

            days_until_expiry = (
                (campaign.domain.expiry_date - today).days
                if campaign.domain.expiry_date else None
            )
            context = build_campaign_context(campaign, business_today=today)
            suggestions.append({
                'campaign_id': campaign.id,
                'domain': campaign.domain.domain_name,
                'status': campaign.status.value,
                'current_price': campaign.current_price,
                'current_sequence': campaign.current_sequence,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'last_contact_date': campaign.last_contact_date.isoformat() if campaign.last_contact_date else None,
                'expiry_date': campaign.domain.expiry_date.isoformat() if campaign.domain.expiry_date else None,
                'days_until_expiry': days_until_expiry,
                'triggered_by': eligibility['triggered_by'],
                'eligibility_metrics': eligibility['metrics'],
                'temperature': context['temperature'],
                'temperature_label': context['label'],
                'temperature_emoji': context['emoji'],
                'trigger_thresholds': {
                    trigger: trigger_config[trigger]['threshold']
                    for trigger in eligibility['triggered_by']
                },
                'trigger_reasons': trigger_reasons,
                'operational_emails': context['operational_emails'],
                'price_progression': context['price_progression'],
                'price_progression_items': context['price_progression_items'],
                'expiry_severity': context['expiry_severity'],
            })

    return jsonify({
        'business_today': today.isoformat(),
        'count': len(suggestions),
        'suggestions': suggestions,
    })

@bp.route('/campaigns/<int:campaign_id>/rest', methods=['POST'])
def rest_campaign(campaign_id):
    from app.services.resting_transition_service import (
        RestingTransitionError,
        manually_rest_campaign,
    )

    try:
        result = manually_rest_campaign(campaign_id)
        return jsonify({
            'success': True,
            'campaign_id': result['campaign_id'],
            'status': result['status'],
        })
    except RestingTransitionError as exc:
        return jsonify({'success': False, 'error': str(exc)}), exc.status_code
    except Exception:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Unable to move campaign to Resting.',
        }), 500


@bp.route('/campaigns/bulk-rest', methods=['POST'])
def bulk_rest_campaigns_route():
    from app.services.resting_transition_service import (
        RestingTransitionError,
        bulk_rest_campaigns,
    )

    data = request.get_json(silent=True) or {}
    try:
        result = bulk_rest_campaigns(data.get('domain_ids'))
        return jsonify({'success': True, **result})
    except RestingTransitionError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), exc.status_code
    except Exception:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Unable to move the selected campaigns to Resting.',
        }), 500


@bp.route('/campaigns/<int:campaign_id>/reset', methods=['POST'])
def reset_campaign(campaign_id):
    from sqlalchemy.exc import SQLAlchemyError
    from app.services.campaign_reset_service import (
        CampaignResetError,
        reset_current_campaign,
    )

    try:
        result = reset_current_campaign(campaign_id)
        db.session.commit()
        return jsonify({'success': True, **result})
    except CampaignResetError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), exc.status_code
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Unable to reset campaign. No changes were saved.',
        }), 500
    except Exception:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Unable to reset campaign. No changes were saved.',
        }), 500


@bp.route('/campaigns/bulk-reset', methods=['POST'])
def bulk_reset_campaigns_route():
    from sqlalchemy.exc import SQLAlchemyError
    from app.services.campaign_reset_service import (
        CampaignResetError,
        bulk_reset_campaigns,
    )

    data = request.get_json(silent=True) or {}
    try:
        result = bulk_reset_campaigns(data.get('domain_ids'))
        return jsonify({'success': True, **result})
    except CampaignResetError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), exc.status_code
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Unable to reset campaigns. No changes were saved.',
        }), 500
    except Exception:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Unable to reset campaigns. No changes were saved.',
        }), 500

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

@bp.route('/settings/daily-use-limit', methods=['GET'])
def get_daily_use_limit():
    from app.services.settings_service import get_setting
    return jsonify({
        'limit': get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1')
    })

@bp.route('/settings/daily-use-limit', methods=['POST'])
def save_daily_use_limit():
    from app.services.settings_service import update_daily_use_limit
    data = request.json
    try:
        limit = data.get('limit')
        update_daily_use_limit(limit)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/dashboard/reservation-board', methods=['GET'])
def get_reservation_board():
    from app.models.models import EmailAccount, Reservation, Campaign, ReservationStatus, ReservationEmailLink
    from app.services.expired_historical_service import is_expired_domain
    from app.services.settings_service import get_setting
    from app.services.time_service import get_business_today
    from sqlalchemy import and_

    today = get_business_today()
    limit = int(get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1'))
    accounts = EmailAccount.query.order_by(EmailAccount.profile_order).all()
    results = []

    for acc in accounts:
        state = "AVAILABLE"
        reserved_domains = []

        # Get reservations today for this email account, excluding expired work.
        links = ReservationEmailLink.query.join(Reservation).filter(
            and_(
                ReservationEmailLink.email_code == acc.code,
                Reservation.date == today,
                Reservation.status == ReservationStatus.RESERVED
            )
        ).all()
        links = [
            link for link in links
            if not is_expired_domain(link.reservation.campaign.domain, business_today=today)
        ]
        count = len(links)

        # Check for completed
        completed_links = ReservationEmailLink.query.join(Reservation).filter(
            and_(
                ReservationEmailLink.email_code == acc.code,
                Reservation.date == today,
                Reservation.status == ReservationStatus.COMPLETED
            )
        ).all()
        completed = next(
            (
                link for link in completed_links
                if not is_expired_domain(
                    link.reservation.campaign.domain,
                    business_today=today,
                )
            ),
            None,
        )

        if links:
            state = "RESERVED"
            reserved_domains = [link.reservation.campaign.domain.domain_name for link in links]
        elif not acc.enabled:
            state = "DISABLED"
        elif completed:
            state = "COMPLETED_TODAY"

        results.append({
            'code': acc.code,
            'profile_order': acc.profile_order,
            'group': acc.group,
            'state': state,
            'reserved_domain': reserved_domains[0] if reserved_domains else None,
            'reserved_domains': reserved_domains,
            'count': count,
            'limit': limit
        })
    return jsonify(results)

@bp.route('/dashboard/todays-campaigns', methods=['GET'])
def get_todays_campaigns():
    from app.models.models import Reservation, ReservationStatus, ReservationEmailLink, Campaign
    from app.services.expired_historical_service import is_expired_domain
    from app.services.time_service import get_business_today

    today = get_business_today()

    # Get all reservations for today
    reservations = [
        reservation for reservation in Reservation.query.filter_by(
            date=today,
            status=ReservationStatus.RESERVED,
        ).all()
        if not is_expired_domain(reservation.campaign.domain, business_today=today)
    ]

    # Get all email usage counts for today to identify shared accounts
    email_usage = {}
    for reservation in reservations:
        for link in reservation.email_links:
            email_usage[link.email_code] = email_usage.get(link.email_code, 0) + 1

    shared_emails = {code: count > 1 for code, count in email_usage.items()}

    results = []
    for res in reservations:
        email_codes = [link.email_code for link in res.email_links]

        results.append({
            'domain': res.campaign.domain.domain_name,
            'campaign_id': res.campaign.id,
            'status': res.campaign.status.value,
            'sequence': res.campaign.current_sequence,
            'current_price': res.campaign.current_price,
            'emails': email_codes,
            'shared_emails': [code for code in email_codes if shared_emails.get(code, False)]
        })

    return jsonify(results)

@bp.route('/domains', methods=['GET'])
def get_domains():
    from sqlalchemy.orm import selectinload
    from app.models.models import Domain
    from app.services.domain_campaign_read_service import (
        build_domain_campaign_table_rows,
        serialize_domain_campaign_api_row,
    )
    from app.services.expired_historical_service import is_expired_domain

    today = get_business_today()
    domains = [
        domain for domain in Domain.query.options(selectinload(Domain.campaigns)).all()
        if not is_expired_domain(domain, business_today=today)
    ]
    rows = build_domain_campaign_table_rows(
        domains,
        business_today=today,
    )
    return jsonify([serialize_domain_campaign_api_row(row) for row in rows])


@bp.route('/domains/export-selected', methods=['POST'])
def export_selected_domains():
    from sqlalchemy.orm import selectinload
    from app.models.models import Domain
    from app.services.domain_campaign_read_service import (
        DOMAIN_CAMPAIGN_EXPORT_COLUMNS,
        build_domain_campaign_export_rows,
    )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "domain_ids" not in payload:
        return jsonify({"error": "domain_ids must be provided as a non-empty list."}), 400

    domain_ids = payload["domain_ids"]
    if not isinstance(domain_ids, list) or not domain_ids:
        return jsonify({"error": "domain_ids must be provided as a non-empty list."}), 400
    if any(type(domain_id) is not int or domain_id <= 0 for domain_id in domain_ids):
        return jsonify({"error": "domain_ids must contain positive integer IDs."}), 400

    # Preserve the browser's Set insertion order while removing duplicates.
    ordered_ids = list(dict.fromkeys(domain_ids))
    domains = Domain.query.options(selectinload(Domain.campaigns)).filter(
        Domain.id.in_(ordered_ids)
    ).all()
    domains_by_id = {domain.id: domain for domain in domains}
    missing_ids = [domain_id for domain_id in ordered_ids if domain_id not in domains_by_id]
    if missing_ids:
        return jsonify({
            "error": "One or more selected domains no longer exist.",
            "stale_domain_ids": missing_ids,
        }), 409

    business_today = get_business_today()
    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer)
    writer.writerow(DOMAIN_CAMPAIGN_EXPORT_COLUMNS)
    writer.writerows(build_domain_campaign_export_rows(
        [domains_by_id[domain_id] for domain_id in ordered_ids],
        business_today=business_today,
    ))

    filename = f"domain-campaign-selected-{business_today.isoformat()}.csv"
    return send_file(
        io.BytesIO(csv_buffer.getvalue().encode("utf-8")),
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv",
    )

@bp.route('/domains', methods=['POST'])
def add_domain():
    from app.models.models import Domain, Campaign, CampaignStatus
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
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/domains/<int:id>/email-accounts', methods=['GET'])
def get_domain_email_accounts(id):
    from app.models.models import Campaign, CampaignEmailBlock
    from app.services.expiry_service import select_latest_campaign
    camp = select_latest_campaign(Campaign.query.filter_by(domain_id=id).all())
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
    from sqlalchemy.exc import SQLAlchemyError
    from app.models.models import Domain

    dom = Domain.query.get(id)
    if dom is None:
        return jsonify({'error': 'Domain not found.'}), 404

    try:
        db.session.delete(dom)
        db.session.commit()
        return jsonify({'success': True})
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({'error': 'Unable to delete domain.'}), 500

@bp.route('/domains/import', methods=['POST'])
def import_domains():
    campaign_history_csv = request.files.get('campaign_history_csv')
    email_usage_csv = request.files.get('email_usage_csv')

    if not campaign_history_csv:
        return jsonify({'error': 'Campaign History CSV is required.'}), 400
    if not email_usage_csv:
        return jsonify({'error': 'Email Usage CSV is required.'}), 400

    def is_csv_upload(file_storage):
        filename = (file_storage.filename or '').lower()
        content_type = (file_storage.content_type or '').lower()
        return filename.endswith('.csv') or content_type == 'text/csv'

    if not is_csv_upload(campaign_history_csv):
        return jsonify({'error': 'Campaign History CSV must be a CSV file.'}), 400
    if not is_csv_upload(email_usage_csv):
        return jsonify({'error': 'Email Usage CSV must be a CSV file.'}), 400

    from app.services.bulk_import_service import match_bulk_import_files
    try:
        valid_email_codes = {account.code for account in EmailAccount.query.all()}
        result = match_bulk_import_files(
            campaign_history_csv, email_usage_csv, valid_email_codes
        )
    except (UnicodeDecodeError, csv.Error) as exc:
        return jsonify({'error': f'Unable to parse CSV files: {exc}'}), 400

    if not result['ok']:
        return jsonify({
            'success': False,
            'error': result['error'],
            'duplicates': result['duplicates'],
        }), 400

    if request.form.get('preview_mapping') == '1':
        from app.models.models import Domain, Campaign, CampaignHistory
        from app.services.campaign_mapping_service import build_campaign_mapping_preview
        from app.services.import_eligibility_service import build_import_eligibility
        selections = json.loads(request.form.get('conflict_selections', '{}'))
        for item in result['results']:
            selected = selections.get(item['normalized_domain'])
            if selected is not None and item['email_usage_records']:
                records = item['email_usage_records']
                if isinstance(selected, int) and 0 <= selected < len(records):
                    item['email_usage_codes'] = records[selected]['email_usage_codes']
        mapping = build_campaign_mapping_preview(
            campaign_history_csv,
            result,
            Domain.query.all(),
            Campaign.query.all(),
            CampaignHistory.query.all(),
        )
        eligibility = build_import_eligibility(mapping, result, selections)
        return jsonify({'success': True, 'mapping': mapping, 'eligibility': eligibility})

    return jsonify({
        'success': True,
        'message': 'Both CSV files were matched successfully.',
        'matching': {
            'results': result['results'],
            'duplicates': result['duplicates'],
            'summary': result['summary'],
            'can_proceed': result['can_proceed'],
        },
    })

@bp.route('/domains/import/final', methods=['POST'])
def final_import_domains():
    """Recompute eligibility from source files, then persist eligible rows only."""
    campaign_history_csv = request.files.get('campaign_history_csv')
    email_usage_csv = request.files.get('email_usage_csv')
    if not campaign_history_csv or not email_usage_csv:
        return jsonify({'success': False, 'error': 'Both CSV files are required.'}), 400

    def is_csv(file_storage):
        return (file_storage.filename or '').lower().endswith('.csv') or (file_storage.content_type or '').lower() == 'text/csv'
    if not is_csv(campaign_history_csv) or not is_csv(email_usage_csv):
        return jsonify({'success': False, 'error': 'Both uploaded files must be CSV files.'}), 400

    try:
        from app.models.models import Domain, Campaign, CampaignHistory
        from app.services.bulk_import_service import match_bulk_import_files
        from app.services.campaign_mapping_service import build_campaign_mapping_preview
        from app.services.import_eligibility_service import build_import_eligibility
        from app.services.bulk_import_persistence_service import persist_ready_import
        selections = json.loads(request.form.get('conflict_selections', '{}'))
        if not isinstance(selections, dict):
            raise ValueError('Conflict selections must be an object.')
        valid_codes = {account.code for account in EmailAccount.query.all()}
        matching = match_bulk_import_files(campaign_history_csv, email_usage_csv, valid_codes)
        if not matching['ok']:
            return jsonify({'success': False, 'error': matching['error'], 'duplicates': matching['duplicates']}), 400
        for item in matching['results']:
            selected = selections.get(item['normalized_domain'])
            if selected is not None and item['email_usage_records']:
                if not isinstance(selected, int) or not 0 <= selected < len(item['email_usage_records']):
                    return jsonify({'success': False, 'error': f'Invalid conflict selection for {item["domain"]}.'}), 400
                item['email_usage_codes'] = item['email_usage_records'][selected]['email_usage_codes']
        mapping = build_campaign_mapping_preview(campaign_history_csv, matching, Domain.query.all(), Campaign.query.all(), CampaignHistory.query.all())
        eligibility = build_import_eligibility(mapping, matching, selections)
        results = persist_ready_import(eligibility)
        return jsonify({'success': True, 'results': results, 'eligibility': eligibility})
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

@bp.route('/domains/<int:id>/campaign-status', methods=['GET'])
def get_campaign_status(id):
    from app.models.models import Campaign
    from app.services.expiry_service import select_latest_campaign
    camp = select_latest_campaign(Campaign.query.filter_by(domain_id=id).all())
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404
    return jsonify({'status': camp.status.value})

@bp.route('/domains/<int:id>/history', methods=['GET'])
def get_campaign_history(id):
    from app.models.models import Campaign, CampaignHistory
    from app.services.expiry_service import select_latest_campaign
    camp = select_latest_campaign(Campaign.query.filter_by(domain_id=id).all())
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404

    # Order by action_date descending so latest actions appear first
    history = CampaignHistory.query.filter_by(campaign_id=camp.id).order_by(CampaignHistory.sequence.asc()).all()
    return jsonify([{
        'action': h.action_type.value,
        'date': h.action_date.isoformat() if h.action_date else None,
        'price_before': h.price_before,
        'price_after': h.price_after,
        'notes': h.notes
    } for h in history])

@bp.route('/domains/<int:id>/history/check', methods=['POST'])
def check_history_action(id):
    from app.models.models import Campaign, CampaignHistory
    data = request.json
    new_seq = int(data.get('seq'))

    from app.services.expiry_service import select_latest_campaign
    camp = select_latest_campaign(Campaign.query.filter_by(domain_id=id).all())
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

    from app.services.expiry_service import select_latest_campaign
    camp = select_latest_campaign(Campaign.query.filter_by(domain_id=id).all())
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
    from app.services.campaign_service import (
        FirstFollowUpAlreadyExistsError,
        create_new_action,
        sync_campaign_state,
    )
    from app.models.models import ActionType, Campaign, CampaignStatus
    from datetime import datetime
    data = request.get_json(silent=True) or {}

    try:
        if db.session.get(Campaign, campaign_id) is None:
            return jsonify({'success': False, 'error': 'Campaign not found.'}), 404
        action_type = ActionType(data['action_type'])
        email_codes = validate_email_codes(
            data.get('email_codes', []),
            require_nonempty=action_type == ActionType.FIRST_OUTREACH,
        )
        action_date = _parse_campaign_action_date(data['action_date'])
        price = int(data['price_after'])
        notes = data.get('notes', '')

        campaign_status = None
        if 'campaign_status' in data:
            campaign_status = CampaignStatus(data['campaign_status'])

        new_hist = create_new_action(campaign_id, action_type, action_date, price, notes, email_codes)
        sync_campaign_state(campaign_id, commit=False)
        camp = Campaign.query.get(campaign_id)
        if camp and campaign_status is not None:
            camp.status = campaign_status
        db.session.commit()
        return jsonify({'success': True, 'sequence': new_hist.sequence}), 201
    except EmailCodeValidationError as exc:
        db.session.rollback()
        return _email_code_validation_response(exc)
    except FirstFollowUpAlreadyExistsError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Unable to save campaign action.'}), 400

@bp.route('/campaigns/<int:campaign_id>/actions', methods=['GET'])
def get_campaign_actions(campaign_id):
    from app.models.models import CampaignHistory
    history = CampaignHistory.query.filter_by(campaign_id=campaign_id).order_by(CampaignHistory.sequence.asc()).all()
    return jsonify([{
        'sequence': h.sequence,
        'action_type': h.action_type.value,
        'action_date': h.action_date.isoformat() if h.action_date else None,
        'price_before': h.price_before,
        'price_after': h.price_after,
        'notes': h.notes,
        'edited_at': h.edited_at.isoformat() if h.edited_at else None
    } for h in history])

@bp.route('/campaigns/<int:campaign_id>/actions/<int:sequence>', methods=['GET'])
def get_campaign_action(campaign_id, sequence):
    from app.services.campaign_service import get_history_by_sequence
    from app.services.campaign_email_service import resolve_history_email_selection
    hist = get_history_by_sequence(campaign_id, sequence)
    if not hist:
        return jsonify({'error': 'Not found'}), 404
    email_selection = resolve_history_email_selection(hist)
    return jsonify({
        'sequence': hist.sequence,
        'action_type': hist.action_type.value,
        'action_date': hist.action_date.isoformat() if hist.action_date else None,
        'price_after': hist.price_after,
        'notes': hist.notes,
        'email_codes': email_selection['codes'],
        'email_source': email_selection['source'],
    })

@bp.route('/campaigns/<int:campaign_id>/actions/<int:sequence>/emails', methods=['GET'])
def get_campaign_action_emails(campaign_id, sequence):
    from app.models.models import CampaignHistory, HistoryEmailUsed
    hist = CampaignHistory.query.filter_by(campaign_id=campaign_id, sequence=sequence).first()
    if not hist:
        return jsonify({'error': 'Not found'}), 404
    return jsonify([h.email_code for h in hist.history_email_used])


@bp.route('/campaigns/<int:campaign_id>/operational-emails', methods=['GET'])
def get_operational_campaign_emails(campaign_id):
    """Return the accounts suitable for a new operational action.

    Exact usage for the latest action is preferred.  Imported campaigns that
    have no per-action usage use their campaign-level email associations.
    """
    from app.models.models import Campaign, CampaignHistory
    from app.services.campaign_email_service import resolve_operational_email_codes

    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        return jsonify({'error': 'Campaign not found'}), 404
    latest = CampaignHistory.query.filter_by(campaign_id=campaign.id).order_by(
        CampaignHistory.sequence.desc(), CampaignHistory.id.desc()
    ).first()
    resolution = resolve_operational_email_codes(campaign, latest)
    return jsonify(resolution)

@bp.route('/campaigns/<int:campaign_id>/actions/<int:sequence>', methods=['PUT'])
def edit_campaign_action(campaign_id, sequence):
    from app.services.campaign_service import (
        FirstFollowUpAlreadyExistsError,
        update_existing_action,
    )
    from app.models.models import ActionType, Campaign, CampaignStatus
    from datetime import datetime
    data = request.get_json(silent=True) or {}

    try:
        if db.session.get(Campaign, campaign_id) is None:
            return jsonify({'success': False, 'error': 'Campaign not found.'}), 404
        action_type = ActionType(data['action_type'])
        email_codes = None
        if 'email_codes' in data:
            email_codes = validate_email_codes(
                data.get('email_codes', []), require_nonempty=True
            )
        action_date = _parse_campaign_action_date(data['action_date'])
        price = int(data['price_after'])
        notes = data.get('notes', '')

        campaign_status = None
        if 'campaign_status' in data:
            campaign_status = CampaignStatus(data['campaign_status'])

        hist = update_existing_action(
            campaign_id,
            sequence,
            action_type,
            action_date,
            price,
            notes,
            email_codes,
            commit=False,
        )
        if not hist:
            return jsonify({'error': 'Not found'}), 404
            
        camp = Campaign.query.get(campaign_id)
        if camp and campaign_status is not None:
            camp.status = campaign_status
        db.session.commit()
        return jsonify({'success': True, 'action': {
            'sequence': hist.sequence,
            'edited_at': hist.edited_at.isoformat()
        }})
    except EmailCodeValidationError as exc:
        db.session.rollback()
        return _email_code_validation_response(exc)
    except FirstFollowUpAlreadyExistsError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Unable to save campaign action changes.'}), 400

@bp.route('/dashboard/first-follow-ups', methods=['GET'])
def get_first_follow_ups():
    from app.models.models import Campaign, CampaignStatus, CampaignHistory, ActionType, Reservation, ReservationStatus
    from app.services.dashboard_campaign_context_service import build_campaign_context
    from app.services.resting_eligibility_service import evaluate_resting_eligibility
    from app.services.settings_service import get_resting_eligibility_config
    from app.services.time_service import get_business_today
    from app.services.settings_service import get_setting
    from app.services.expiry_service import select_latest_campaign
    from app.services.campaign_temperature_service import (
        TEMPERATURE_HOT,
        TEMPERATURE_READY,
        TEMPERATURE_TEPID,
        calculate_campaign_temperature,
        get_campaign_temperature_config,
    )
    from app.services.expired_historical_service import is_expired_domain
    from sqlalchemy import and_

    today = get_business_today()
    min_days = int(get_setting('FIRST_FOLLOW_UP_MIN', '2'))
    max_days = int(get_setting('FIRST_FOLLOW_UP_MAX', '5'))
    resting_config = get_resting_eligibility_config()
    temperature_config = get_campaign_temperature_config()

    eligible_campaigns = Campaign.query.filter(
        Campaign.status == CampaignStatus.ACTIVE,
        Campaign.current_sequence == 1
    ).all()

    due = []
    past_due = []

    for camp in eligible_campaigns:
        if str(camp.domain.status or '').upper() == 'SOLD' or is_expired_domain(camp.domain, business_today=today):
            continue
        if select_latest_campaign(camp.domain.campaigns) is not camp:
            continue
        temperature = calculate_campaign_temperature(
            camp,
            business_today=today,
            temperature_config=temperature_config,
        )
        if temperature == TEMPERATURE_READY:
            continue
        latest = CampaignHistory.query.filter_by(
            campaign_id=camp.id
        ).order_by(CampaignHistory.sequence.desc()).first()

        if not latest:
            continue

        if not latest.action_date:
            continue
        days_since = (today - latest.action_date.date()).days
        if days_since < min_days:
            continue

        context = build_campaign_context(
            camp, business_today=today, latest_history=latest
        )
        rest_suggested = (
            temperature in {TEMPERATURE_HOT, TEMPERATURE_TEPID}
            and evaluate_resting_eligibility(
                camp,
                resting_config,
                business_today=today,
            )['eligible']
        )
        emails_used = context['operational_emails']
        res = Reservation.query.filter_by(
            campaign_id=camp.id, date=today, status=ReservationStatus.RESERVED
            ).first()

        res_info = {
            'state': 'Reserved' if res else 'Unreserved',
            'reserved_by': res.campaign.domain.domain_name if res else None
        }

        camp_info = {
            'domain': camp.domain.domain_name,
            'campaign_id': camp.id,
            'days_since_outreach': days_since,
            'emails_used': emails_used,
            'reservation': res_info,
            'resting_suggested': rest_suggested,
            'operational_emails': context['operational_emails'],
            'current_sequence': context['current_sequence'],
            'current_price': context['current_price'],
            'last_contact_date': context['last_contact_date'],
            'days_since_last_contact': context['days_since_last_contact'],
            'temperature': context['temperature'],
            'temperature_label': context['label'],
            'temperature_emoji': context['emoji'],
            'expiry_date': context['expiry_date'],
            'days_until_expiry': context['days_until_expiry'],
            'expiry_severity': context['expiry_severity'],
            'price_progression': context['price_progression'],
            'price_progression_items': context['price_progression_items'],
        }

        if days_since <= max_days:
            due.append(camp_info)
        else:
            past_due.append(camp_info)

    return jsonify({"due": due, "past_due": past_due})

@bp.route('/dashboard/normal-follow-ups', methods=['GET'])
def get_normal_follow_ups():
    from app.models.models import Campaign, CampaignStatus, CampaignHistory, Reservation, ReservationStatus
    from app.services.dashboard_campaign_context_service import build_campaign_context
    from app.services.resting_eligibility_service import evaluate_resting_eligibility
    from app.services.settings_service import get_resting_eligibility_config
    from app.services.time_service import get_business_today
    from app.services.settings_service import get_setting
    from app.services.expiry_service import select_latest_campaign
    from app.services.campaign_temperature_service import (
        calculate_campaign_temperature,
        get_campaign_temperature_config,
        is_active_followup_temperature,
    )
    from app.services.expired_historical_service import is_expired_domain

    today = get_business_today()
    min_days = int(get_setting('NORMAL_FOLLOW_UP_MIN', '7'))
    max_days = int(get_setting('NORMAL_FOLLOW_UP_MAX', '7'))
    resting_config = get_resting_eligibility_config()
    temperature_config = get_campaign_temperature_config()

    eligible_campaigns = Campaign.query.filter(
        Campaign.status == CampaignStatus.ACTIVE,
        Campaign.current_sequence > 1
    ).all()

    due = []
    past_due = []

    for camp in eligible_campaigns:
        if str(camp.domain.status or '').upper() == 'SOLD' or is_expired_domain(camp.domain, business_today=today):
            continue
        if select_latest_campaign(camp.domain.campaigns) is not camp:
            continue
        temperature = calculate_campaign_temperature(
            camp,
            business_today=today,
            temperature_config=temperature_config,
        )
        if not is_active_followup_temperature(temperature):
            continue
        latest = CampaignHistory.query.filter_by(
            campaign_id=camp.id
        ).order_by(CampaignHistory.sequence.desc()).first()

        if not latest:
            continue

        if not latest.action_date:
            continue
        days_since = (today - latest.action_date.date()).days
        if days_since < min_days:
            continue

        context = build_campaign_context(
            camp, business_today=today, latest_history=latest
        )
        rest_suggested = evaluate_resting_eligibility(
            camp,
            resting_config,
            business_today=today,
        )['eligible']
        emails_used = context['operational_emails']
        res = Reservation.query.filter_by(
            campaign_id=camp.id, date=today, status=ReservationStatus.RESERVED
        ).first()

        res_info = {
            'state': 'Reserved' if res else 'Unreserved',
            'reserved_by': res.campaign.domain.domain_name if res else None
        }

        camp_info = {
            'domain': camp.domain.domain_name,
            'campaign_id': camp.id,
            'days_since_contact': days_since,
            'emails_used': emails_used,
            'reservation': res_info,
            'resting_suggested': rest_suggested,
            'operational_emails': context['operational_emails'],
            'current_sequence': context['current_sequence'],
            'current_price': context['current_price'],
            'last_contact_date': context['last_contact_date'],
            'days_since_last_contact': context['days_since_last_contact'],
            'temperature': context['temperature'],
            'temperature_label': context['label'],
            'temperature_emoji': context['emoji'],
            'expiry_date': context['expiry_date'],
            'days_until_expiry': context['days_until_expiry'],
            'expiry_severity': context['expiry_severity'],
            'price_progression': context['price_progression'],
            'price_progression_items': context['price_progression_items'],
        }

        if days_since <= max_days:
            due.append(camp_info)
        else:
            past_due.append(camp_info)

    return jsonify({"due": due, "past_due": past_due})


@bp.route('/dashboard/cooling', methods=['GET'])
def get_cooling_campaigns():
    from sqlalchemy.orm import selectinload
    from app.models.models import CampaignHistory, CampaignStatus, Domain
    from app.services.campaign_temperature_service import (
        get_campaign_temperature_config,
        is_cooling_campaign,
        temperature_details,
        calculate_campaign_temperature,
    )
    from app.services.dashboard_campaign_context_service import build_campaign_context
    from app.services.expiry_service import select_latest_campaign
    from app.services.time_service import get_business_today
    from app.services.expired_historical_service import is_expired_domain

    today = get_business_today()
    temperature_config = get_campaign_temperature_config()
    domains = Domain.query.options(selectinload(Domain.campaigns)).filter(
        Domain.status.notin_(['SOLD', 'EXPIRED'])
    ).order_by(Domain.domain_name.asc(), Domain.id.asc()).all()

    results = []
    for domain in domains:
        if is_expired_domain(domain, business_today=today):
            continue
        campaign = select_latest_campaign(domain.campaigns)
        if campaign is None or campaign.status not in {
            CampaignStatus.ACTIVE,
            CampaignStatus.RESTING,
        }:
            continue
        temperature = calculate_campaign_temperature(
            campaign,
            business_today=today,
            temperature_config=temperature_config,
        )
        if not is_cooling_campaign(campaign, temperature):
            continue

        latest = CampaignHistory.query.filter_by(
            campaign_id=campaign.id
        ).order_by(CampaignHistory.sequence.desc(), CampaignHistory.id.desc()).first()
        context = build_campaign_context(
            campaign,
            business_today=today,
            latest_history=latest,
        )
        presentation = temperature_details(temperature)
        results.append({
            'campaign_id': campaign.id,
            'domain': campaign.domain.domain_name,
            'status': campaign.status.value,
            'temperature': temperature,
            'temperature_label': presentation['label'],
            'temperature_emoji': presentation['emoji'],
            'current_sequence': context['current_sequence'],
            'current_price': context['current_price'],
            'last_contact_date': context['last_contact_date'],
            'days_since_last_contact': context['days_since_last_contact'],
            'expiry_date': context['expiry_date'],
            'days_until_expiry': context['days_until_expiry'],
            'expiry_severity': context['expiry_severity'],
            'operational_emails': context['operational_emails'],
            'price_progression': context['price_progression'],
            'price_progression_items': context['price_progression_items'],
            'can_rest': campaign.status == CampaignStatus.ACTIVE,
        })

    return jsonify({
        'business_today': today.isoformat(),
        'count': len(results),
        'domains': results,
    })

@bp.route('/campaigns/<int:campaign_id>/reservation', methods=['POST'])
def reserve_campaign(campaign_id):
    from app.models.models import (
        ActionType,
        Campaign,
        CampaignHistory,
        EmailAccount,
        Reservation,
        ReservationEmailLink,
        ReservationStatus,
    )
    from app.services.campaign_email_service import resolve_operational_email_codes
    from app.services.settings_service import get_setting
    from app.services.time_service import get_business_today
    from sqlalchemy import and_
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError

    limit = int(get_setting('EMAIL_ACCOUNT_DAILY_USE_LIMIT', '1'))
    today = get_business_today()
    camp = Campaign.query.get_or_404(campaign_id)

    # Get required emails from the first outreach.  Exact per-action usage is
    # preferred; imported campaigns use their campaign-level associations.
    first_outreach = CampaignHistory.query.filter_by(
        campaign_id=camp.id,
        action_type=ActionType.FIRST_OUTREACH
    ).order_by(CampaignHistory.sequence.asc()).first()

    if not first_outreach:
        return jsonify({'error': 'No outreach found'}), 400

    existing = Reservation.query.filter_by(
        campaign_id=camp.id, date=today
    ).first()
    if existing:
        return jsonify({'error': 'This campaign is already reserved for today.'}), 409

    resolution = resolve_operational_email_codes(camp, first_outreach)
    emails_required = resolution['codes']
    if not emails_required:
        return jsonify({
            'error': 'No email accounts are associated with this campaign outreach.'
        }), 400

    missing_codes = [
        code for code in emails_required
        if db.session.get(EmailAccount, code) is None
    ]
    if missing_codes:
        return jsonify({
            'error': 'Email account(s) no longer exist: ' + ', '.join(missing_codes)
        }), 400

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
            links = ReservationEmailLink.query.join(Reservation).filter(
                and_(
                    ReservationEmailLink.email_code == email,
                    Reservation.date == today,
                    Reservation.status == ReservationStatus.RESERVED
                )
            ).all()
            if links:
                reserved_domains = [link.reservation.campaign.domain.domain_name for link in links]
                conflicts[email] = f"{email} is reserved by {', '.join(reserved_domains)}"
            else:
                conflicts[email] = f"{email} has reached its daily use limit of {limit}"

    if conflicts:
        return jsonify({'error': 'Conflict', 'details': list(conflicts.values())}), 409

    # Create reservation and links as one unit.  A concurrent request may still
    # win the unique campaign/date constraint, so turn that race into a clear
    # client error rather than an IntegrityError response.
    try:
        new_res = Reservation(
            campaign_id=camp.id,
            date=today,
            status=ReservationStatus.RESERVED,
        )
        db.session.add(new_res)
        db.session.flush()
        for email in emails_required:
            db.session.add(
                ReservationEmailLink(reservation_id=new_res.id, email_code=email)
            )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if Reservation.query.filter_by(campaign_id=camp.id, date=today).first():
            return jsonify({'error': 'This campaign is already reserved for today.'}), 409
        return jsonify({
            'error': 'Unable to reserve campaign. No changes were saved.'
        }), 500
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            'error': 'Unable to reserve campaign. No changes were saved.'
        }), 500
    return jsonify({'success': True})

@bp.route('/campaigns/<int:campaign_id>/reservation', methods=['DELETE'])
def unreserve_campaign(campaign_id):
    from app.models.models import Reservation, ReservationStatus
    from app.services.time_service import get_business_today

    today = get_business_today()
    res = Reservation.query.filter_by(campaign_id=campaign_id, date=today, status=ReservationStatus.RESERVED).first()
    if res:
        db.session.delete(res)
        db.session.commit()
    return jsonify({'success': True})

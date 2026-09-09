import csv
import io
import json
import zipfile
from datetime import date, datetime

import pytest

from app.models.models import (
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    Domain,
    EmailAccount,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    Setting,
    db,
)
from app.services.backup_export_service import DATASET_COLUMNS, build_csv_zip_export
from app.services.backup_restore_service import (
    CONFIRMATION_TEXT,
    BackupRestoreError,
    parse_and_validate_backup,
    preflight_backup,
    restore_backup,
)
from app.services.spreadsheet_export_service import build_spreadsheet_csv_zip
from tests.test_backup_export import _seed_export_data


def _authenticate(client):
    client.application.config.update(
        TESTING=True,
        SECRET_KEY='test-session-secret',
        ADMIN_USERNAME='admin',
        ADMIN_PASSWORD='test-password',
    )
    with client.session_transaction() as session:
        session['authenticated'] = True


def _clear_operational_database():
    for model in (
        ReservationEmailLink,
        HistoryEmailUsed,
        CampaignEmailBlock,
        Reservation,
        CampaignHistory,
        Campaign,
        Domain,
        EmailAccount,
        Setting,
    ):
        model.query.delete()
    db.session.commit()


def _archive_bytes():
    return build_csv_zip_export().getvalue()


def _rewrite_archive(content, csv_mutations=None, manifest_mutation=None, remove=None):
    csv_mutations = csv_mutations or {}
    remove = set(remove or ())
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        members = {info.filename: source.read(info.filename) for info in source.infolist()}
    manifest = json.loads(members['manifest.json'])
    for filename, mutation in csv_mutations.items():
        rows = list(csv.reader(io.StringIO(members[filename].decode('utf-8'))))
        mutation(rows)
        members[filename] = ('\n'.join(','.join(row) for row in rows) + '\n').encode('utf-8')
        dataset = next(item for item in manifest['datasets'] if item['filename'] == filename)
        dataset['row_count'] = len(rows) - 1
    if manifest_mutation:
        manifest_mutation(manifest)
    members['manifest.json'] = json.dumps(manifest, indent=2).encode('utf-8')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as target:
        for filename, data in members.items():
            if filename not in remove:
                target.writestr(filename, data)
    return output.getvalue()


def _seed_and_export(app):
    with app.app_context():
        _seed_export_data()
        content = _archive_bytes()
        _clear_operational_database()
        return content


def _logical_csv_snapshot(content):
    id_columns = {
        'domains': {'domain_id'},
        'campaigns': {'campaign_id'},
        'campaign_history': {'history_id'},
        'history_email_used': {'history_email_used_id', 'history_id'},
        'email_accounts': set(),
        'campaign_email_associations': {'association_id', 'campaign_id'},
        'reservations': {'reservation_id', 'campaign_id'},
        'reservation_email_links': {'link_id', 'reservation_id'},
        'settings': set(),
    }
    snapshot = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name, columns in DATASET_COLUMNS.items():
            rows = list(csv.DictReader(io.StringIO(archive.read(f'{name}.csv').decode('utf-8'))))
            snapshot[name] = [
                tuple(row[column] for column in columns if column not in id_columns[name])
                for row in rows
            ]
    return snapshot


def test_valid_exact_zip_preflight_is_read_only_and_reports_counts(app):
    content = _seed_and_export(app)
    with app.app_context():
        before = [model.query.count() for model in (
            Domain, Campaign, EmailAccount, CampaignHistory, HistoryEmailUsed,
            CampaignEmailBlock, Reservation, ReservationEmailLink, Setting,
        )]
        result = preflight_backup(io.BytesIO(content))
        after = [model.query.count() for model in (
            Domain, Campaign, EmailAccount, CampaignHistory, HistoryEmailUsed,
            CampaignEmailBlock, Reservation, ReservationEmailLink, Setting,
        )]
    assert result['valid'] is True
    assert result['database_empty'] is True
    assert result['format_name'] == 'domain-campaign-exact-backup'
    assert result['format_version'] == 1
    assert result['datasets']['domains'] == 2
    assert before == after == [0] * 9


@pytest.mark.parametrize('mutation,expected', [
    (lambda content: _rewrite_archive(content, remove=['manifest.json']), 'manifest'),
    (lambda content: _rewrite_archive(content, manifest_mutation=lambda m: m.update(format_name='wrong')), 'format'),
    (lambda content: _rewrite_archive(content, manifest_mutation=lambda m: m.update(format_version=99)), 'version'),
    (lambda content: _rewrite_archive(content, remove=['campaigns.csv']), 'missing required member'),
])
def test_invalid_archive_contract_is_rejected(app, mutation, expected):
    content = _seed_and_export(app)
    with app.app_context():
        result = preflight_backup(io.BytesIO(mutation(content)))
    assert result['valid'] is False
    assert any(expected in error.lower() for error in result['errors'])


def test_spreadsheet_zip_is_not_accepted(app):
    with app.app_context():
        _clear_operational_database()
        result = preflight_backup(io.BytesIO(build_spreadsheet_csv_zip().getvalue()))
    assert result['valid'] is False
    assert any('manifest' in error.lower() for error in result['errors'])


def test_malformed_zip_and_wrong_headers_are_rejected(app):
    with app.app_context():
        _clear_operational_database()
        malformed = preflight_backup(io.BytesIO(b'not a zip'))
    assert malformed['valid'] is False
    assert any('zip' in error.lower() for error in malformed['errors'])

    content = _seed_and_export(app)
    tampered = _rewrite_archive(content, csv_mutations={
        'domains.csv': lambda rows: rows[0].__setitem__(0, 'wrong'),
    })
    with app.app_context():
        result = preflight_backup(io.BytesIO(tampered))
    assert result['valid'] is False
    assert any('headers' in error.lower() for error in result['errors'])


@pytest.mark.parametrize('filename,column,value,needle', [
    ('domains.csv', 'expiry_date', 'not-a-date', 'ISO date'),
    ('campaigns.csv', 'created_at', 'not-a-datetime', 'ISO datetime'),
    ('campaigns.csv', 'current_price', 'not-an-int', 'integer'),
    ('email_accounts.csv', 'enabled', 'yes', "'true' or 'false'"),
    ('campaigns.csv', 'status', 'BROKEN', 'one of'),
])
def test_invalid_scalar_values_are_rejected(app, filename, column, value, needle):
    content = _seed_and_export(app)

    def mutate(rows):
        index = rows[0].index(column)
        rows[1][index] = value

    tampered = _rewrite_archive(content, csv_mutations={filename: mutate})
    with app.app_context():
        result = preflight_backup(io.BytesIO(tampered))
    assert result['valid'] is False
    assert any(needle.lower() in error.lower() for error in result['errors'])


def test_relationship_and_duplicate_constraints_are_rejected(app):
    content = _seed_and_export(app)
    cases = [
        ({'domains.csv': lambda rows: rows[2].__setitem__(1, 'EXAMPLE.COM')}, 'normalized domain'),
        ({'campaigns.csv': lambda rows: rows[2].__setitem__(2, rows[1][2])}, 'lifecycle'),
        ({'campaigns.csv': lambda rows: rows[1].__setitem__(1, 'missing.example.com')}, 'missing domain'),
        ({'campaign_email_associations.csv': lambda rows: rows[1].__setitem__(5, 'UNKNOWN')}, 'unknown email'),
        ({'campaign_email_associations.csv': lambda rows: rows.append(rows[1][:])}, 'duplicate campaign email'),
        ({'reservations.csv': lambda rows: rows.append(rows[1][:])}, 'duplicate reservation date'),
        ({'reservation_email_links.csv': lambda rows: rows.append(rows[1][:])}, 'duplicate reservation email'),
    ]
    for mutations, needle in cases:
        tampered = _rewrite_archive(content, csv_mutations=mutations)
        with app.app_context():
            result = preflight_backup(io.BytesIO(tampered))
        assert result['valid'] is False, needle
        assert any(needle in error.lower() for error in result['errors']), (needle, result['errors'])


def test_nonempty_database_refuses_validation_and_restore(app):
    with app.app_context():
        _seed_export_data()
        content = _archive_bytes()
        validation = preflight_backup(io.BytesIO(content))
    assert validation['valid'] is False
    assert validation['database_empty'] is False
    with app.app_context():
        with pytest.raises(BackupRestoreError, match='not empty'):
            restore_backup(io.BytesIO(content))
        assert Domain.query.count() == 2


def test_successful_restore_reconstructs_all_logical_state_and_nullable_values(app):
    content = _seed_and_export(app)
    with app.app_context():
        counts = restore_backup(io.BytesIO(content))
        assert counts['domains'] == 2
        assert Domain.query.filter_by(domain_name='example.com').one().expiry_date == date(2030, 1, 2)
        domain = Domain.query.filter_by(domain_name='example.com').one()
        campaigns = sorted(domain.campaigns, key=lambda item: (item.created_at, item.id))
        assert len(campaigns) == 2
        assert campaigns[0].status.value == 'RESTING'
        assert campaigns[1].status.value == 'ACTIVE'
        assert campaigns[1].current_price == 100
        assert campaigns[1].current_sequence == 1
        history = CampaignHistory.query.filter_by(campaign_id=campaigns[1].id).one()
        assert history.action_date is None
        assert HistoryEmailUsed.query.filter_by(history_id=history.id, email_code='T05').count() == 1
        assert CampaignEmailBlock.query.filter_by(campaign_id=campaigns[1].id, email_code='T05').count() == 1
        reservation = Reservation.query.filter_by(campaign_id=campaigns[1].id).one()
        assert ReservationEmailLink.query.filter_by(reservation_id=reservation.id, email_code='T05').count() == 1
        assert EmailAccount.query.filter_by(code='T05').one().enabled is False
        assert Setting.query.filter_by(key='BUSINESS_TIMEZONE').one().value == 'UTC'
        assert Setting.query.filter_by(key='ADMIN_PASSWORD').count() == 0


def test_exact_backup_round_trip_preserves_logical_state_while_ids_are_generated(app):
    original = _seed_and_export(app)
    original_snapshot = _logical_csv_snapshot(original)
    with app.app_context():
        restore_backup(io.BytesIO(original))
        restored = build_csv_zip_export().getvalue()
    assert _logical_csv_snapshot(restored) == original_snapshot


def test_nullable_defaults_are_restored_as_null_instead_of_fabricated(app):
    content = _seed_and_export(app)

    def blank_column(rows, column):
        index = rows[0].index(column)
        for row in rows[1:]:
            row[index] = ''

    tampered = _rewrite_archive(content, csv_mutations={
        'domains.csv': lambda rows: blank_column(rows, 'created_at'),
        'campaigns.csv': lambda rows: (blank_column(rows, 'created_at'), blank_column(rows, 'updated_at')),
        'campaign_history.csv': lambda rows: blank_column(rows, 'campaign_created_at'),
        'history_email_used.csv': lambda rows: blank_column(rows, 'campaign_created_at'),
        'campaign_email_associations.csv': lambda rows: blank_column(rows, 'campaign_created_at'),
        'reservations.csv': lambda rows: (blank_column(rows, 'campaign_created_at'), blank_column(rows, 'is_override'), blank_column(rows, 'created_at'), blank_column(rows, 'updated_at')),
        'reservation_email_links.csv': lambda rows: blank_column(rows, 'campaign_created_at'),
        'email_accounts.csv': lambda rows: blank_column(rows, 'enabled'),
    })
    with app.app_context():
        restore_backup(io.BytesIO(tampered))
        assert all(domain.created_at is None for domain in Domain.query.all())
        assert all(campaign.created_at is None and campaign.updated_at is None for campaign in Campaign.query.all())
        assert all(account.enabled is None for account in EmailAccount.query.all())
        reservation = Reservation.query.one()
        assert reservation.is_override is None
        assert reservation.created_at is None and reservation.updated_at is None


def test_restore_requires_explicit_confirmation_and_endpoint_is_authenticated(app, client):
    content = _seed_and_export(app)
    app.config.update(TESTING=False, SECRET_KEY='secret', ADMIN_USERNAME='admin', ADMIN_PASSWORD='password')
    assert client.post(
        '/api/backup/restore/validate',
        data={'file': (io.BytesIO(content), 'backup.zip')},
        content_type='multipart/form-data',
    ).status_code == 401
    assert client.post('/api/backup/restore', data={'file': (io.BytesIO(content), 'backup.zip')}).status_code == 401
    _authenticate(client)
    with app.app_context():
        response = client.post('/api/backup/restore', data={'file': (io.BytesIO(content), 'backup.zip')}, content_type='multipart/form-data')
    assert response.status_code == 400
    assert CONFIRMATION_TEXT in response.get_json()['error']


def test_restore_endpoint_successfully_restores_uploaded_zip(app, client):
    content = _seed_and_export(app)
    _authenticate(client)
    response = client.post(
        '/api/backup/restore',
        data={
            'file': (io.BytesIO(content), 'backup.zip'),
            'confirmation': CONFIRMATION_TEXT,
        },
        content_type='multipart/form-data',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    with app.app_context():
        assert Domain.query.count() == 2


def test_mid_restore_failure_rolls_back_everything(app, monkeypatch):
    content = _seed_and_export(app)
    with app.app_context():
        original_flush = db.session.flush
        calls = {'count': 0}

        def fail_after_some_flushes(*args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 4:
                raise RuntimeError('injected restore failure')
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(db.session, 'flush', fail_after_some_flushes)
        with pytest.raises(BackupRestoreError):
            restore_backup(io.BytesIO(content))
        assert [model.query.count() for model in (
            Domain, Campaign, EmailAccount, CampaignHistory, HistoryEmailUsed,
            CampaignEmailBlock, Reservation, ReservationEmailLink, Setting,
        )] == [0] * 9


def test_settings_page_exposes_zip_restore_flow(client):
    html = client.get('/settings').get_data(as_text=True)
    assert 'Restore Exact App Backup' in html
    assert '/api/backup/restore/validate' in html
    assert '/api/backup/restore' in html
    assert 'RESTORE EXACT BACKUP' in html
    assert 'human-friendly' not in html.split('Restore Exact App Backup', 1)[1].split('</div>', 1)[0]

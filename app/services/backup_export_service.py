"""Build deterministic, restore-oriented exports without changing application state."""

import csv
import io
import json
import subprocess
import zipfile
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

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
)
from app.services.time_service import get_business_today


EXACT_BACKUP_FORMAT_NAME = 'domain-campaign-exact-backup'
EXACT_BACKUP_FORMAT_VERSION = 1
EXACT_BACKUP_APPLICATION = 'Domain Campaign Tool'


# The key is a business setting, while the value is the stable export filename
# stem and the ordered columns used by both formats.
DATASET_COLUMNS = OrderedDict([
    ('domains', [
        'domain_id', 'domain_name', 'expiry_date', 'status', 'notes', 'created_at',
    ]),
    ('campaigns', [
        'campaign_id', 'domain_name', 'lifecycle_ordinal', 'created_at', 'updated_at',
        'status', 'start_date', 'last_contact_date', 'current_price',
        'current_sequence', 'rest_start_date', 'rest_end_date', 'handled_by',
        'last_action', 'notes',
    ]),
    ('campaign_history', [
        'history_id', 'domain_name', 'lifecycle_ordinal', 'campaign_created_at',
        'sequence', 'action_type', 'action_date', 'edited_at', 'price_before',
        'price_after', 'sequence_before', 'sequence_after', 'notes',
    ]),
    ('history_email_used', [
        'history_email_used_id', 'history_id', 'domain_name', 'lifecycle_ordinal',
        'campaign_created_at', 'sequence', 'email_code',
    ]),
    ('email_accounts', ['code', 'group', 'profile_order', 'enabled']),
    ('campaign_email_associations', [
        'association_id', 'campaign_id', 'domain_name', 'lifecycle_ordinal',
        'campaign_created_at', 'email_code',
    ]),
    ('reservations', [
        'reservation_id', 'campaign_id', 'domain_name', 'lifecycle_ordinal',
        'campaign_created_at', 'date', 'status', 'is_override', 'created_at',
        'updated_at',
    ]),
    ('reservation_email_links', [
        'link_id', 'reservation_id', 'domain_name', 'lifecycle_ordinal',
        'campaign_created_at', 'date', 'email_code',
    ]),
    ('settings', ['key', 'value']),
])

DATASET_SHEET_NAMES = OrderedDict(
    (name, name.replace('_', ' ').title()) for name in DATASET_COLUMNS
)

_SENSITIVE_SETTING_MARKERS = (
    'PASSWORD', 'SECRET', 'DATABASE', 'TOKEN', 'CREDENTIAL', 'SESSION',
    'AUTH', 'USERNAME',
)


def _export_value(value):
    if value is None:
        return ''
    if hasattr(value, 'value') and not isinstance(value, (date, datetime)):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return value


def _campaign_sort_key(campaign):
    return (campaign.created_at or datetime.min, campaign.id or 0)


def _campaign_context():
    campaigns = Campaign.query.all()
    contexts = {}
    for campaign in campaigns:
        ordered = sorted(campaign.domain.campaigns, key=_campaign_sort_key)
        ordinal = next(index for index, item in enumerate(ordered, 1) if item.id == campaign.id)
        contexts[campaign.id] = {
            'campaign': campaign,
            'domain_name': campaign.domain.domain_name,
            'lifecycle_ordinal': ordinal,
            'campaign_created_at': campaign.created_at,
        }
    return contexts


def _git_revision():
    """Return the current revision when local Git metadata is available."""
    try:
        project_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=1,
            check=True,
        )
        revision = result.stdout.strip()
        return revision or None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _schema_revision():
    """Schema revision is optional and never queries the database."""
    return None


def build_manifest(datasets, *, business_date=None, exported_at=None):
    """Build manifest metadata for the supplied exact-backup datasets."""
    business_date = business_date or get_business_today()
    exported_at = exported_at or datetime.now(timezone.utc)
    return {
        'format_name': EXACT_BACKUP_FORMAT_NAME,
        'format_version': EXACT_BACKUP_FORMAT_VERSION,
        'application': EXACT_BACKUP_APPLICATION,
        'exported_at': exported_at.isoformat(),
        'business_date': business_date.isoformat(),
        'git_revision': _git_revision(),
        'schema_revision': _schema_revision(),
        'datasets': [
            {
                'dataset': name,
                'filename': f'{name}.csv',
                'sheet_name': DATASET_SHEET_NAMES[name],
                'columns': list(columns),
                'row_count': len(rows),
            }
            for name, columns, rows in datasets
        ],
    }


def _write_manifest_sheet(sheet, manifest):
    for key in (
        'format_name', 'format_version', 'application', 'exported_at',
        'business_date', 'git_revision', 'schema_revision',
    ):
        sheet.append([key, manifest[key] if manifest[key] is not None else ''])
    sheet.append([])
    sheet.append(['dataset', 'sheet_name', 'filename', 'columns', 'row_count'])
    for dataset in manifest['datasets']:
        sheet.append([
            dataset['dataset'],
            dataset['sheet_name'],
            dataset['filename'],
            json.dumps(dataset['columns'], ensure_ascii=False),
            dataset['row_count'],
        ])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    header_row = 9
    for cell in sheet[header_row]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = f'A{header_row + 1}'
    for index in range(1, 6):
        values = [str(sheet.cell(row, index).value or '') for row in range(1, sheet.max_row + 1)]
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = min(max(map(len, values)) + 2, 80)


def build_export_datasets():
    """Return ``[(name, columns, rows), ...]`` in deterministic order."""
    contexts = _campaign_context()
    domains = sorted(Domain.query.all(), key=lambda item: (item.domain_name, item.id or 0))
    campaigns = sorted(
        (context['campaign'] for context in contexts.values()),
        key=lambda item: (item.domain.domain_name, *_campaign_sort_key(item)),
    )

    rows = OrderedDict((name, []) for name in DATASET_COLUMNS)
    rows['domains'] = [
        {
            'domain_id': domain.id,
            'domain_name': domain.domain_name,
            'expiry_date': domain.expiry_date,
            'status': domain.status,
            'notes': domain.notes,
            'created_at': domain.created_at,
        }
        for domain in domains
    ]
    rows['campaigns'] = [
        {
            'campaign_id': campaign.id,
            'domain_name': campaign.domain.domain_name,
            'lifecycle_ordinal': contexts[campaign.id]['lifecycle_ordinal'],
            'created_at': campaign.created_at,
            'updated_at': campaign.updated_at,
            'status': campaign.status,
            'start_date': campaign.start_date,
            'last_contact_date': campaign.last_contact_date,
            'current_price': campaign.current_price,
            'current_sequence': campaign.current_sequence,
            'rest_start_date': campaign.rest_start_date,
            'rest_end_date': campaign.rest_end_date,
            'handled_by': campaign.handled_by,
            'last_action': campaign.last_action,
            'notes': campaign.notes,
        }
        for campaign in campaigns
    ]

    histories = sorted(
        CampaignHistory.query.all(),
        key=lambda item: (
            item.campaign.domain.domain_name,
            contexts[item.campaign_id]['lifecycle_ordinal'],
            item.action_date or datetime.min,
            item.sequence if item.sequence is not None else -1,
            item.id or 0,
        ),
    )
    rows['campaign_history'] = [
        {
            'history_id': history.id,
            'domain_name': history.campaign.domain.domain_name,
            'lifecycle_ordinal': contexts[history.campaign_id]['lifecycle_ordinal'],
            'campaign_created_at': history.campaign.created_at,
            'sequence': history.sequence,
            'action_type': history.action_type,
            'action_date': history.action_date,
            'edited_at': history.edited_at,
            'price_before': history.price_before,
            'price_after': history.price_after,
            'sequence_before': history.sequence_before,
            'sequence_after': history.sequence_after,
            'notes': history.notes,
        }
        for history in histories
    ]

    history_used = sorted(
        HistoryEmailUsed.query.all(),
        key=lambda item: (
            item.history.campaign.domain.domain_name,
            contexts[item.history.campaign_id]['lifecycle_ordinal'],
            item.history.sequence if item.history.sequence is not None else -1,
            item.email_code,
            item.id or 0,
        ),
    )
    rows['history_email_used'] = [
        {
            'history_email_used_id': used.id,
            'history_id': used.history_id,
            'domain_name': used.history.campaign.domain.domain_name,
            'lifecycle_ordinal': contexts[used.history.campaign_id]['lifecycle_ordinal'],
            'campaign_created_at': used.history.campaign.created_at,
            'sequence': used.history.sequence,
            'email_code': used.email_code,
        }
        for used in history_used
    ]
    rows['email_accounts'] = [
        {
            'code': account.code,
            'group': account.group,
            'profile_order': account.profile_order,
            'enabled': account.enabled,
        }
        for account in sorted(EmailAccount.query.all(), key=lambda item: (item.profile_order, item.code))
    ]

    associations = sorted(
        CampaignEmailBlock.query.all(),
        key=lambda item: (
            item.campaign.domain.domain_name,
            contexts[item.campaign_id]['lifecycle_ordinal'],
            item.email_code,
            item.id or 0,
        ),
    )
    rows['campaign_email_associations'] = [
        {
            'association_id': association.id,
            'campaign_id': association.campaign_id,
            'domain_name': association.campaign.domain.domain_name,
            'lifecycle_ordinal': contexts[association.campaign_id]['lifecycle_ordinal'],
            'campaign_created_at': association.campaign.created_at,
            'email_code': association.email_code,
        }
        for association in associations
    ]

    reservations = sorted(
        Reservation.query.all(),
        key=lambda item: (
            item.campaign.domain.domain_name,
            contexts[item.campaign_id]['lifecycle_ordinal'],
            item.date,
            item.id or 0,
        ),
    )
    rows['reservations'] = [
        {
            'reservation_id': reservation.id,
            'campaign_id': reservation.campaign_id,
            'domain_name': reservation.campaign.domain.domain_name,
            'lifecycle_ordinal': contexts[reservation.campaign_id]['lifecycle_ordinal'],
            'campaign_created_at': reservation.campaign.created_at,
            'date': reservation.date,
            'status': reservation.status,
            'is_override': reservation.is_override,
            'created_at': reservation.created_at,
            'updated_at': reservation.updated_at,
        }
        for reservation in reservations
    ]
    reservation_links = sorted(
        ReservationEmailLink.query.all(),
        key=lambda item: (
            item.reservation.campaign.domain.domain_name,
            contexts[item.reservation.campaign_id]['lifecycle_ordinal'],
            item.reservation.date,
            item.email_code,
            item.id or 0,
        ),
    )
    rows['reservation_email_links'] = [
        {
            'link_id': link.id,
            'reservation_id': link.reservation_id,
            'domain_name': link.reservation.campaign.domain.domain_name,
            'lifecycle_ordinal': contexts[link.reservation.campaign_id]['lifecycle_ordinal'],
            'campaign_created_at': link.reservation.campaign.created_at,
            'date': link.reservation.date,
            'email_code': link.email_code,
        }
        for link in reservation_links
    ]

    settings = [
        {'key': setting.key, 'value': setting.value}
        for setting in sorted(Setting.query.all(), key=lambda item: item.key)
        if not any(marker in setting.key.upper() for marker in _SENSITIVE_SETTING_MARKERS)
    ]
    rows['settings'] = settings

    return [
        (name, DATASET_COLUMNS[name], [{column: _export_value(row.get(column)) for column in DATASET_COLUMNS[name]} for row in dataset_rows])
        for name, dataset_rows in rows.items()
    ]


def build_xlsx_export():
    workbook = Workbook()
    workbook.remove(workbook.active)
    datasets = build_export_datasets()
    manifest = build_manifest(datasets)
    for name, columns, rows in datasets:
        sheet = workbook.create_sheet(DATASET_SHEET_NAMES[name])
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = 'A2'
        for row in rows:
            sheet.append([row[column] for column in columns])
        for index, column in enumerate(columns, 1):
            values = [str(row[column]) if row[column] != '' else '' for row in rows]
            width = min(max([len(column), *(len(value) for value in values)] or [len(column)]) + 2, 45)
            sheet.column_dimensions[chr(64 + index) if index <= 26 else sheet.cell(1, index).column_letter].width = width
    _write_manifest_sheet(workbook.create_sheet('Manifest'), manifest)
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def build_csv_zip_export():
    output = io.BytesIO()
    datasets = build_export_datasets()
    manifest = build_manifest(datasets)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, columns, rows in datasets:
            csv_output = io.StringIO(newline='')
            writer = csv.DictWriter(csv_output, fieldnames=columns, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr(f'{name}.csv', csv_output.getvalue().encode('utf-8'))
        archive.writestr(
            'manifest.json',
            json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
        )
    output.seek(0)
    return output


def export_filename(extension):
    return f'domain-campaign-backup-{get_business_today().isoformat()}.{extension}'

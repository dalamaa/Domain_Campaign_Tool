"""Strict ZIP restore for the normalized Exact App Backup format."""

import csv
import io
import json
import stat
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import PurePosixPath

from sqlalchemy import null, text
from sqlalchemy.exc import SQLAlchemyError

from app.models.models import (
    ActionType,
    Campaign,
    CampaignEmailBlock,
    CampaignHistory,
    CampaignStatus,
    Domain,
    DomainStatus,
    EmailAccount,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    ReservationStatus,
    Setting,
    db,
)
from app.services.backup_export_service import (
    DATASET_COLUMNS,
    DATASET_SHEET_NAMES,
    EXACT_BACKUP_APPLICATION,
    EXACT_BACKUP_FORMAT_NAME,
    EXACT_BACKUP_FORMAT_VERSION,
    _SENSITIVE_SETTING_MARKERS,
)
from app.services.bulk_import_service import is_valid_domain, normalize_domain


MAX_BACKUP_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
RESTORE_LOCK_KEY = 735918273645
CONFIRMATION_TEXT = 'RESTORE EXACT BACKUP'

OPERATIONAL_MODELS = (
    Domain,
    Campaign,
    EmailAccount,
    CampaignEmailBlock,
    CampaignHistory,
    HistoryEmailUsed,
    Reservation,
    ReservationEmailLink,
    Setting,
)


class BackupRestoreError(Exception):
    """Base class for safe, user-facing restore failures."""

    status_code = 400

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or [message]


class BackupRestoreValidationError(BackupRestoreError):
    pass


class BackupRestoreDatabaseNotEmptyError(BackupRestoreError):
    status_code = 409


@dataclass
class RestorePlan:
    manifest: dict
    datasets: dict


def operational_database_is_empty():
    """Return whether every application data table has zero rows."""
    return all(model.query.count() == 0 for model in OPERATIONAL_MODELS)


def _required_string(value):
    if value == '':
        raise ValueError('is required')
    return value


def _optional_string(value):
    return None if value == '' else value


def _integer(value):
    if value == '':
        raise ValueError('is required')
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('must be an integer') from exc


def _positive_integer(value):
    parsed = _integer(value)
    if parsed <= 0:
        raise ValueError('must be a positive integer')
    return parsed


def _nullable(parser):
    def parse(value):
        return None if value == '' else parser(value)
    return parse


def _date(value):
    if value == '':
        raise ValueError('is required')
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('must be an ISO date') from exc


def _datetime(value):
    if value == '':
        raise ValueError('is required')
    if 'T' not in value and ' ' not in value:
        raise ValueError('must be an ISO datetime')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError('must be an ISO datetime') from exc
    if parsed.tzinfo is not None:
        raise ValueError('must not include a timezone offset')
    return parsed


def _manifest_datetime(value):
    if value == '':
        raise ValueError('is required')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError('must be an ISO datetime') from exc


def _boolean(value):
    if value == 'true':
        return True
    if value == 'false':
        return False
    raise ValueError("must be exactly 'true' or 'false'")


def _enum(enum_type):
    def parse(value):
        if value == '':
            raise ValueError('is required')
        try:
            return enum_type(value)
        except ValueError as exc:
            allowed = ', '.join(member.value for member in enum_type)
            raise ValueError(f'must be one of: {allowed}') from exc
    return parse


def _preserve_null(value):
    """Use a SQL NULL expression so nullable model defaults cannot fire."""
    return null() if value is None else value


FIELD_PARSERS = {
    'domains': {
        'domain_id': _positive_integer,
        'domain_name': _required_string,
        'expiry_date': _nullable(_date),
        'status': _enum(DomainStatus),
        'notes': _optional_string,
        'created_at': _nullable(_datetime),
    },
    'campaigns': {
        'campaign_id': _positive_integer,
        'domain_name': _required_string,
        'lifecycle_ordinal': _positive_integer,
        'created_at': _nullable(_datetime),
        'updated_at': _nullable(_datetime),
        'status': _enum(CampaignStatus),
        'start_date': _nullable(_date),
        'last_contact_date': _nullable(_date),
        'current_price': _integer,
        'current_sequence': _integer,
        'rest_start_date': _nullable(_date),
        'rest_end_date': _nullable(_date),
        'handled_by': _optional_string,
        'last_action': _optional_string,
        'notes': _optional_string,
    },
    'campaign_history': {
        'history_id': _positive_integer,
        'domain_name': _required_string,
        'lifecycle_ordinal': _positive_integer,
        'campaign_created_at': _nullable(_datetime),
        'sequence': _nullable(_integer),
        'action_type': _enum(ActionType),
        'action_date': _nullable(_datetime),
        'edited_at': _nullable(_datetime),
        'price_before': _nullable(_integer),
        'price_after': _nullable(_integer),
        'sequence_before': _nullable(_integer),
        'sequence_after': _nullable(_integer),
        'notes': _optional_string,
    },
    'history_email_used': {
        'history_email_used_id': _positive_integer,
        'history_id': _positive_integer,
        'domain_name': _required_string,
        'lifecycle_ordinal': _positive_integer,
        'campaign_created_at': _nullable(_datetime),
        'sequence': _nullable(_integer),
        'email_code': _required_string,
    },
    'email_accounts': {
        'code': _required_string,
        'group': _required_string,
        'profile_order': _integer,
        'enabled': _nullable(_boolean),
    },
    'campaign_email_associations': {
        'association_id': _positive_integer,
        'campaign_id': _positive_integer,
        'domain_name': _required_string,
        'lifecycle_ordinal': _positive_integer,
        'campaign_created_at': _nullable(_datetime),
        'email_code': _required_string,
    },
    'reservations': {
        'reservation_id': _positive_integer,
        'campaign_id': _positive_integer,
        'domain_name': _required_string,
        'lifecycle_ordinal': _positive_integer,
        'campaign_created_at': _nullable(_datetime),
        'date': _date,
        'status': _enum(ReservationStatus),
        'is_override': _nullable(_boolean),
        'created_at': _nullable(_datetime),
        'updated_at': _nullable(_datetime),
    },
    'reservation_email_links': {
        'link_id': _positive_integer,
        'reservation_id': _positive_integer,
        'domain_name': _required_string,
        'lifecycle_ordinal': _positive_integer,
        'campaign_created_at': _nullable(_datetime),
        'date': _date,
        'email_code': _required_string,
    },
    'settings': {
        'key': _required_string,
        'value': _optional_string,
    },
}


def _read_zip_bytes(file_storage):
    if file_storage is None:
        raise BackupRestoreValidationError('An Exact App Backup ZIP file is required.')
    stream = getattr(file_storage, 'stream', file_storage)
    if not hasattr(stream, 'read'):
        raise BackupRestoreValidationError('The uploaded backup file could not be read.')
    try:
        stream.seek(0)
        content = stream.read(MAX_BACKUP_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise BackupRestoreValidationError('The uploaded backup file could not be read.') from exc
    if len(content) > MAX_BACKUP_BYTES:
        raise BackupRestoreValidationError(
            f'Backup ZIP is too large. The maximum supported size is {MAX_BACKUP_BYTES // (1024 * 1024)} MB.'
        )
    return content


def _validate_manifest(manifest):
    errors = []
    if not isinstance(manifest, dict):
        return ['manifest.json must contain a JSON object.']
    if manifest.get('format_name') != EXACT_BACKUP_FORMAT_NAME:
        errors.append(f"Unsupported backup format. Expected '{EXACT_BACKUP_FORMAT_NAME}'.")
    if type(manifest.get('format_version')) is not int or manifest.get('format_version') != EXACT_BACKUP_FORMAT_VERSION:
        errors.append(f"Unsupported backup format version. Expected {EXACT_BACKUP_FORMAT_VERSION}.")
    if manifest.get('application') != EXACT_BACKUP_APPLICATION:
        errors.append(f"Unsupported backup application. Expected '{EXACT_BACKUP_APPLICATION}'.")
    for field, parser in (('exported_at', _manifest_datetime), ('business_date', _date)):
        value = manifest.get(field)
        if not isinstance(value, str):
            errors.append(f'manifest.json {field} is required.')
            continue
        try:
            parser(value)
        except ValueError as exc:
            errors.append(f'manifest.json {field} {exc}.')

    manifest_datasets = manifest.get('datasets')
    expected_names = list(DATASET_COLUMNS)
    if not isinstance(manifest_datasets, list) or [
        item.get('dataset') for item in manifest_datasets if isinstance(item, dict)
    ] != expected_names:
        errors.append('manifest.json datasets do not match the Exact App Backup contract.')
        return errors

    for item, name in zip(manifest_datasets, expected_names):
        if not isinstance(item, dict):
            errors.append(f'manifest dataset {name} must be an object.')
            continue
        expected = {
            'dataset': name,
            'filename': f'{name}.csv',
            'sheet_name': DATASET_SHEET_NAMES[name],
            'columns': list(DATASET_COLUMNS[name]),
        }
        for field, expected_value in expected.items():
            if item.get(field) != expected_value:
                errors.append(f'manifest dataset {name} has an invalid {field}.')
        row_count = item.get('row_count')
        if type(row_count) is not int or row_count < 0:
            errors.append(f'manifest dataset {name} row_count must be a non-negative integer.')
    return errors


def _validate_zip_members(archive):
    infos = archive.infolist()
    names = [info.filename for info in infos]
    errors = []
    if len(names) != len(set(names)):
        errors.append('Backup ZIP contains duplicate members.')
    if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
        errors.append('Backup ZIP contains too much uncompressed data.')
    expected = {'manifest.json', *(f'{name}.csv' for name in DATASET_COLUMNS)}
    for info in infos:
        name = info.filename
        path = PurePosixPath(name)
        mode = (info.external_attr >> 16) & 0xFFFF
        is_symlink = stat.S_ISLNK(mode)
        is_executable = bool(mode & 0o111)
        if info.is_dir() or is_symlink or is_executable or name.startswith('/') or '\\' in name or '..' in path.parts:
            errors.append(f'Backup ZIP contains an unsafe path: {name}.')
        elif name not in expected:
            errors.append(f'Backup ZIP contains an unexpected member: {name}.')
    missing = sorted(expected - set(names))
    errors.extend(f'Backup ZIP is missing required member: {name}.' for name in missing)
    return errors


def _parse_csv_dataset(archive, name, manifest_item):
    filename = manifest_item['filename']
    try:
        content = archive.read(filename).decode('utf-8-sig')
        source_rows = list(csv.reader(io.StringIO(content), strict=True))
    except (KeyError, UnicodeDecodeError, csv.Error, RuntimeError, zipfile.BadZipFile, OSError) as exc:
        raise BackupRestoreValidationError(f'{filename} is not a valid UTF-8 CSV file.') from exc
    expected_columns = list(DATASET_COLUMNS[name])
    if not source_rows or source_rows[0] != expected_columns:
        raise BackupRestoreValidationError(f'{filename} headers do not match the Exact App Backup contract.')
    if manifest_item['row_count'] != len(source_rows) - 1:
        raise BackupRestoreValidationError(
            f'{filename} row count does not match manifest.json.'
        )
    parsers = FIELD_PARSERS[name]
    parsed = []
    errors = []
    for row_number, values in enumerate(source_rows[1:], 2):
        if len(values) != len(expected_columns):
            errors.append(f'{filename} row {row_number} has the wrong number of columns.')
            continue
        record = {}
        for column, value in zip(expected_columns, values):
            try:
                record[column] = parsers[column](value)
            except ValueError as exc:
                errors.append(f'{filename} row {row_number} column {column}: {exc}.')
        if len(record) == len(expected_columns):
            parsed.append(record)
    if errors:
        raise BackupRestoreValidationError('Backup CSV validation failed.', errors)
    return parsed


def _campaign_key(record):
    return (
        record['domain_name'],
        record['lifecycle_ordinal'],
        record['created_at'],
    )


def _validate_relationships(datasets):
    errors = []
    domains = datasets['domains']
    domain_by_id = {}
    domain_by_name = {}
    normalized_names = {}
    for row in domains:
        if row['domain_id'] in domain_by_id:
            errors.append(f"Duplicate domain_id {row['domain_id']}.")
        domain_by_id[row['domain_id']] = row
        if row['domain_name'] in domain_by_name:
            errors.append(f"Duplicate domain name {row['domain_name']}.")
        domain_by_name[row['domain_name']] = row
        normalized = normalize_domain(row['domain_name'])
        if not is_valid_domain(row['domain_name']):
            errors.append(f"Invalid domain name {row['domain_name']}.")
        if normalized in normalized_names:
            errors.append(
                f"Duplicate normalized domain name {row['domain_name']} conflicts with {normalized_names[normalized]}.")
        normalized_names[normalized] = row['domain_name']

    email_accounts = datasets['email_accounts']
    email_codes = set()
    for row in email_accounts:
        if row['code'] in email_codes:
            errors.append(f"Duplicate email account code {row['code']}.")
        email_codes.add(row['code'])

    campaigns = datasets['campaigns']
    campaign_by_id = {}
    campaigns_by_domain = {}
    campaign_by_key = {}
    for row in campaigns:
        source_id = row['campaign_id']
        if source_id in campaign_by_id:
            errors.append(f'Duplicate campaign_id {source_id}.')
        campaign_by_id[source_id] = row
        if row['domain_name'] not in domain_by_name:
            errors.append(f"Campaign {source_id} references missing domain {row['domain_name']}.")
            continue
        key = _campaign_key(row)
        if key in campaign_by_key:
            errors.append(f"Duplicate campaign lifecycle for {row['domain_name']}.")
        campaign_by_key[key] = row
        campaigns_by_domain.setdefault(row['domain_name'], []).append(row)

    for domain_name, rows in campaigns_by_domain.items():
        ordinals = [row['lifecycle_ordinal'] for row in rows]
        if len(ordinals) != len(set(ordinals)):
            errors.append(f'Duplicate lifecycle ordinal for {domain_name}.')
        if set(ordinals) != set(range(1, len(rows) + 1)):
            errors.append(f'Lifecycle ordinals for {domain_name} must be contiguous starting at 1.')
        ordered = sorted(rows, key=lambda row: (row['created_at'] or datetime.min, row['campaign_id']))
        if [row['campaign_id'] for row in ordered] != [
            row['campaign_id'] for row in sorted(rows, key=lambda row: row['lifecycle_ordinal'])
        ]:
            errors.append(f'Lifecycle ordering for {domain_name} does not match created_at then source campaign_id.')

    def resolve_campaign(row, dataset_name, identifier_field=None):
        if identifier_field is not None:
            campaign = campaign_by_id.get(row[identifier_field])
            if campaign is None:
                errors.append(f"{dataset_name} references missing campaign_id {row[identifier_field]}.")
                return None
            if (
                campaign['domain_name'], campaign['lifecycle_ordinal'], campaign['created_at']
            ) != (
                row['domain_name'], row['lifecycle_ordinal'], row['campaign_created_at']
            ):
                errors.append(f'{dataset_name} campaign logical reference does not match campaign_id {row[identifier_field]}.')
            return campaign
        key = (row['domain_name'], row['lifecycle_ordinal'], row['campaign_created_at'])
        campaign = campaign_by_key.get(key)
        if campaign is None:
            errors.append(f'{dataset_name} references a missing campaign lifecycle.')
        return campaign

    history_by_id = {}
    history_unique = set()
    history_source_ids = set()
    for row in datasets['campaign_history']:
        campaign = resolve_campaign(row, 'campaign_history')
        if campaign is not None:
            row['_campaign_id'] = campaign['campaign_id']
        if row['history_id'] in history_source_ids:
            errors.append(f"Duplicate history_id {row['history_id']}.")
        history_source_ids.add(row['history_id'])
        history_by_id[row['history_id']] = row
        unique_key = (row.get('_campaign_id'), row['sequence'])
        if row.get('_campaign_id') is not None and row['sequence'] is not None:
            if unique_key in history_unique:
                errors.append('Duplicate campaign history sequence.')
            history_unique.add(unique_key)

    def validate_email_code(code, dataset_name):
        if code not in email_codes:
            errors.append(f'{dataset_name} references unknown email account {code}.')

    used_unique = set()
    used_source_ids = set()
    for row in datasets['history_email_used']:
        history = history_by_id.get(row['history_id'])
        if history is None:
            errors.append(f"history_email_used references missing history_id {row['history_id']}.")
        else:
            row['_history_id'] = history['history_id']
            if (
                history.get('_campaign_id'), history['sequence']
            ) != (
                campaign_by_key.get((row['domain_name'], row['lifecycle_ordinal'], row['campaign_created_at']), {}).get('campaign_id'),
                row['sequence'],
            ):
                errors.append(f"history_email_used logical reference does not match history_id {row['history_id']}.")
        validate_email_code(row['email_code'], 'history_email_used')
        if row['history_email_used_id'] in used_source_ids:
            errors.append(f"Duplicate history_email_used_id {row['history_email_used_id']}.")
        used_source_ids.add(row['history_email_used_id'])
        unique_key = (row['history_id'], row['email_code'])
        if unique_key in used_unique:
            errors.append('Duplicate history email association.')
        used_unique.add(unique_key)

    association_unique = set()
    association_source_ids = set()
    for row in datasets['campaign_email_associations']:
        campaign = resolve_campaign(row, 'campaign_email_associations', 'campaign_id')
        if campaign is not None:
            row['_campaign_id'] = campaign['campaign_id']
        if row['association_id'] in association_source_ids:
            errors.append(f"Duplicate association_id {row['association_id']}.")
        association_source_ids.add(row['association_id'])
        validate_email_code(row['email_code'], 'campaign_email_associations')
        unique_key = (row['campaign_id'], row['email_code'])
        if unique_key in association_unique:
            errors.append('Duplicate campaign email association.')
        association_unique.add(unique_key)

    reservation_by_id = {}
    reservation_unique = set()
    for row in datasets['reservations']:
        campaign = resolve_campaign(row, 'reservations', 'campaign_id')
        if campaign is not None:
            row['_campaign_id'] = campaign['campaign_id']
        if row['reservation_id'] in reservation_by_id:
            errors.append(f"Duplicate reservation_id {row['reservation_id']}.")
        reservation_by_id[row['reservation_id']] = row
        unique_key = (row['campaign_id'], row['date'])
        if unique_key in reservation_unique:
            errors.append('Duplicate reservation date for campaign.')
        reservation_unique.add(unique_key)

    link_unique = set()
    link_source_ids = set()
    for row in datasets['reservation_email_links']:
        reservation = reservation_by_id.get(row['reservation_id'])
        if reservation is None:
            errors.append(f"reservation_email_links references missing reservation_id {row['reservation_id']}.")
        else:
            if (
                reservation['campaign_id'], reservation['domain_name'], reservation['lifecycle_ordinal'],
                reservation['campaign_created_at'], reservation['date'],
            ) != (
                campaign_by_key.get((row['domain_name'], row['lifecycle_ordinal'], row['campaign_created_at']), {}).get('campaign_id'),
                row['domain_name'], row['lifecycle_ordinal'], row['campaign_created_at'], row['date'],
            ):
                errors.append(f"reservation_email_links logical reference does not match reservation_id {row['reservation_id']}.")
        if row['link_id'] in link_source_ids:
            errors.append(f"Duplicate link_id {row['link_id']}.")
        link_source_ids.add(row['link_id'])
        validate_email_code(row['email_code'], 'reservation_email_links')
        unique_key = (row['reservation_id'], row['email_code'])
        if unique_key in link_unique:
            errors.append('Duplicate reservation email link.')
        link_unique.add(unique_key)

    setting_keys = set()
    for row in datasets['settings']:
        key = row['key']
        if any(marker in key.upper() for marker in _SENSITIVE_SETTING_MARKERS):
            errors.append(f'Sensitive setting {key} is not allowed in an Exact App Backup.')
        if any(character in key for character in '\r\n\x00'):
            errors.append(f'Invalid setting key {key!r}.')
        if key in setting_keys:
            errors.append(f'Duplicate setting key {key}.')
        setting_keys.add(key)
    return errors


def parse_and_validate_backup(file_storage):
    """Parse and validate the entire ZIP without querying or changing data."""
    content = _read_zip_bytes(file_storage)
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupRestoreValidationError('The uploaded file is not a valid ZIP archive.') from exc
    with archive:
        member_errors = _validate_zip_members(archive)
        if member_errors:
            raise BackupRestoreValidationError('Backup ZIP structure is invalid.', member_errors)
        try:
            manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError, zipfile.BadZipFile, OSError) as exc:
            raise BackupRestoreValidationError('manifest.json is missing or malformed.') from exc
        manifest_errors = _validate_manifest(manifest)
        if manifest_errors:
            raise BackupRestoreValidationError('Backup manifest validation failed.', manifest_errors)
        datasets = {}
        for item in manifest['datasets']:
            datasets[item['dataset']] = _parse_csv_dataset(archive, item['dataset'], item)
        relationship_errors = _validate_relationships(datasets)
        if relationship_errors:
            raise BackupRestoreValidationError('Backup relationship validation failed.', relationship_errors)
        return RestorePlan(manifest=manifest, datasets=datasets)


def _safe_database_empty():
    try:
        return operational_database_is_empty()
    except Exception:
        return None


def preflight_backup(file_storage):
    """Return a JSON-ready validation summary; never writes database data."""
    database_empty = _safe_database_empty()
    try:
        plan = parse_and_validate_backup(file_storage)
    except BackupRestoreError as exc:
        return {
            'valid': False,
            'database_empty': database_empty,
            'format_name': None,
            'format_version': None,
            'exported_at': None,
            'business_date': None,
            'datasets': {},
            'errors': exc.errors,
        }
    errors = []
    if database_empty is not True:
        errors.append(
            'Operational database is not empty; Exact App Backup restore is allowed only into an empty database.'
            if database_empty is False else
            'Unable to determine whether the operational database is empty.'
        )
    return {
        'valid': not errors,
        'database_empty': database_empty,
        'format_name': plan.manifest['format_name'],
        'format_version': plan.manifest['format_version'],
        'exported_at': plan.manifest['exported_at'],
        'business_date': plan.manifest['business_date'],
        'datasets': {name: len(rows) for name, rows in plan.datasets.items()},
        'errors': errors,
    }


def _acquire_restore_lock():
    bind = db.session.get_bind()
    if bind.dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(:lock_key)'), {'lock_key': RESTORE_LOCK_KEY})


def _restore_rows(plan):
    maps = {
        'domains': {},
        'campaigns': {},
        'history': {},
        'reservations': {},
    }
    datasets = plan.datasets

    db.session.add_all([
        EmailAccount(
            code=row['code'], group=row['group'], profile_order=row['profile_order'],
            enabled=_preserve_null(row['enabled']),
        )
        for row in datasets['email_accounts']
    ])
    db.session.flush()

    domain_objects = [
        Domain(
            domain_name=row['domain_name'], expiry_date=row['expiry_date'],
            status=row['status'].value, notes=row['notes'], created_at=_preserve_null(row['created_at']),
        )
        for row in sorted(datasets['domains'], key=lambda item: (item['domain_name'], item['domain_id']))
    ]
    db.session.add_all(domain_objects)
    db.session.flush()
    for row, obj in zip(sorted(datasets['domains'], key=lambda item: (item['domain_name'], item['domain_id'])), domain_objects):
        maps['domains'][row['domain_id']] = obj

    campaign_rows = sorted(
        datasets['campaigns'],
        key=lambda item: (item['domain_name'], item['lifecycle_ordinal']),
    )
    campaign_objects = [
        Campaign(
            domain_id=maps['domains'][next(
                domain['domain_id'] for domain in datasets['domains']
                if domain['domain_name'] == row['domain_name']
            )].id,
            status=row['status'], start_date=row['start_date'],
            last_contact_date=row['last_contact_date'], current_price=row['current_price'],
            current_sequence=row['current_sequence'], rest_start_date=row['rest_start_date'],
            rest_end_date=row['rest_end_date'], handled_by=row['handled_by'],
            last_action=row['last_action'], notes=row['notes'],
            created_at=_preserve_null(row['created_at']), updated_at=_preserve_null(row['updated_at']),
        )
        for row in campaign_rows
    ]
    db.session.add_all(campaign_objects)
    db.session.flush()
    for row, obj in zip(campaign_rows, campaign_objects):
        maps['campaigns'][row['campaign_id']] = obj

    history_rows = sorted(
        datasets['campaign_history'],
        key=lambda item: (
            item['domain_name'], item['lifecycle_ordinal'],
            item['sequence'] if item['sequence'] is not None else -1,
            item['history_id'],
        ),
    )
    history_objects = [
        CampaignHistory(
            campaign_id=maps['campaigns'][row['_campaign_id']].id,
            sequence=row['sequence'], action_type=row['action_type'],
            action_date=row['action_date'], edited_at=row['edited_at'],
            price_before=row['price_before'], price_after=row['price_after'],
            sequence_before=row['sequence_before'], sequence_after=row['sequence_after'],
            notes=row['notes'],
        )
        for row in history_rows
    ]
    db.session.add_all(history_objects)
    db.session.flush()
    for row, obj in zip(history_rows, history_objects):
        maps['history'][row['history_id']] = obj

    db.session.add_all([
        HistoryEmailUsed(
            history_id=maps['history'][row['history_id']].id,
            email_code=row['email_code'],
        )
        for row in datasets['history_email_used']
    ])
    db.session.add_all([
        CampaignEmailBlock(
            campaign_id=maps['campaigns'][row['campaign_id']].id,
            email_code=row['email_code'],
        )
        for row in datasets['campaign_email_associations']
    ])

    reservation_rows = sorted(
        datasets['reservations'],
        key=lambda item: (item['domain_name'], item['lifecycle_ordinal'], item['date'], item['reservation_id']),
    )
    reservation_objects = [
        Reservation(
            campaign_id=maps['campaigns'][row['campaign_id']].id,
            date=row['date'], status=row['status'], is_override=_preserve_null(row['is_override']),
            created_at=_preserve_null(row['created_at']), updated_at=_preserve_null(row['updated_at']),
        )
        for row in reservation_rows
    ]
    db.session.add_all(reservation_objects)
    db.session.flush()
    for row, obj in zip(reservation_rows, reservation_objects):
        maps['reservations'][row['reservation_id']] = obj

    db.session.add_all([
        ReservationEmailLink(
            reservation_id=maps['reservations'][row['reservation_id']].id,
            email_code=row['email_code'],
        )
        for row in datasets['reservation_email_links']
    ])
    db.session.add_all([Setting(key=row['key'], value=row['value']) for row in datasets['settings']])
    db.session.flush()
    return maps


def _operational_counts():
    """Return counts using the same dataset names as the exact backup."""
    model_by_dataset = {
        'domains': Domain,
        'campaigns': Campaign,
        'campaign_history': CampaignHistory,
        'history_email_used': HistoryEmailUsed,
        'email_accounts': EmailAccount,
        'campaign_email_associations': CampaignEmailBlock,
        'reservations': Reservation,
        'reservation_email_links': ReservationEmailLink,
        'settings': Setting,
    }
    return {name: model.query.count() for name, model in model_by_dataset.items()}


def restore_backup(file_storage):
    """Fully validate, then restore one Exact App Backup transactionally."""
    plan = parse_and_validate_backup(file_storage)
    transaction = None
    try:
        transaction = db.session.begin()
        _acquire_restore_lock()
        if not operational_database_is_empty():
            raise BackupRestoreDatabaseNotEmptyError(
                'Operational database is not empty; no changes were saved.'
            )
        _restore_rows(plan)
        expected_counts = {name: len(rows) for name, rows in plan.datasets.items()}
        counts = _operational_counts()
        if counts != expected_counts:
            raise BackupRestoreError(
                'Restored record counts do not match the Exact App Backup. No changes were saved.'
            )
        transaction.commit()
        return counts
    except BackupRestoreError:
        if transaction is not None:
            transaction.rollback()
        raise
    except SQLAlchemyError as exc:
        if transaction is not None:
            transaction.rollback()
        raise BackupRestoreError('Unable to restore Exact App Backup. No changes were saved.') from exc
    except Exception as exc:
        if transaction is not None:
            transaction.rollback()
        raise BackupRestoreError('Unable to restore Exact App Backup. No changes were saved.') from exc

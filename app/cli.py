"""Flask CLI commands for operational application tasks."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
from flask.cli import with_appcontext

from app.services import backup_export_service, spreadsheet_export_service


def register_cli(app):
    """Register application CLI commands on ``app``."""
    app.cli.add_command(backup)


@click.group()
def backup():
    """Backup application data."""


@backup.command("export")
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
        path_type=Path,
    ),
)
@with_appcontext
def export_backups(output_dir):
    """Write the exact ZIP and human-friendly XLSX exports."""
    timestamp, exact_path, human_path = _backup_paths(output_dir)
    temporary_paths = []
    published_paths = []

    try:
        # Generate both exports before creating any output files.
        exact_bytes = _stream_bytes(backup_export_service.build_csv_zip_export())
        human_bytes = _stream_bytes(spreadsheet_export_service.build_spreadsheet_xlsx())

        temporary_paths.append(_write_temporary_file(output_dir, exact_path.name, exact_bytes))
        temporary_paths.append(_write_temporary_file(output_dir, human_path.name, human_bytes))

        os.replace(temporary_paths[0], exact_path)
        published_paths.append(exact_path)
        os.replace(temporary_paths[1], human_path)
        published_paths.append(human_path)
    except Exception as exc:
        for path in temporary_paths:
            _remove_file(path)
        for path in published_paths:
            _remove_file(path)
        raise click.ClickException(f"Backup export failed: {exc}") from exc

    click.echo(f"status=ok")
    click.echo(f"timestamp={timestamp}")
    click.echo(f"exact_zip={exact_path}")
    click.echo(f"human_xlsx={human_path}")


def _stream_bytes(stream):
    if hasattr(stream, "getvalue"):
        return stream.getvalue()
    stream.seek(0)
    return stream.read()


def _backup_paths(output_dir):
    timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    while True:
        rendered = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        exact_path = output_dir / f"domain_campaign_exact_{rendered}.zip"
        human_path = output_dir / f"domain_campaign_human_{rendered}.xlsx"
        if not exact_path.exists() and not human_path.exists():
            return rendered, exact_path, human_path
        timestamp += timedelta(seconds=1)


def _write_temporary_file(output_dir, final_name, content):
    temporary = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=output_dir,
        prefix=f".{final_name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
    except Exception:
        _remove_file(temporary_path)
        raise
    return temporary_path


def _remove_file(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass

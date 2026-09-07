import hmac

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


bp = Blueprint('auth', __name__)


def _safe_next_url(value):
    if isinstance(value, str) and value.startswith('/') and not value.startswith('//'):
        return value
    return url_for('dashboard.index')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    error = request.args.get('error')
    next_url = request.args.get('next') or request.form.get('next')

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        configured_username = current_app.config.get('ADMIN_USERNAME')
        configured_password = current_app.config.get('ADMIN_PASSWORD')

        if not all(
            isinstance(value, str) and value
            for value in (
                configured_username,
                configured_password,
                current_app.secret_key,
            )
        ):
            error = 'Authentication is not configured.'
            return render_template(
                'login.html', error=error, next_url=next_url
            ), 503

        valid_username = isinstance(username, str) and hmac.compare_digest(
            username, configured_username
        )
        valid_password = isinstance(password, str) and hmac.compare_digest(
            password, configured_password
        )
        if valid_username and valid_password:
            session.clear()
            session['authenticated'] = True
            return redirect(_safe_next_url(next_url))

        error = 'Invalid username or password.'

    return render_template('login.html', error=error, next_url=next_url)


@bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

from flask import Flask, render_template, request, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
import psycopg2
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler
import logging
import datetime
from google.cloud import monitoring_v3
# Inicjalizacja klienta logowania
client = google.cloud.logging.Client()

# Ustawienie globalnego handlera
handler = CloudLoggingHandler(client)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(handler)


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secret-key')

oauth = OAuth(app)
google = oauth.register(
    'google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    refresh_token_url=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={'scope': 'email profile'}
)
unix_socket = '/cloudsql/{}'.format(os.environ.get('DB_HOST'))

def get_db_connection():
    return psycopg2.connect(
        host = unix_socket,
        database=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        port = 5432
    )

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'google_token' not in session:
        return render_template('login.html')
    
    email = session.get('email', '')
    
    if request.method == 'POST':
        logging.info(f"New email scheduled to be sent to {email}.")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO emails (email_to, subject, message, send_time) VALUES (%s, %s, %s, %s)',
                       (email, request.form['subject'], request.form['message'], request.form['send_time']))
        conn.commit()
        cursor.close()
        conn.close()
        update_pending_emails_metric()
        return redirect(url_for('index'))
    
    return render_template('dashboard.html', email=email)

@app.route('/login')
def login():
    redirect_uri = url_for('authorized', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/logout')
def logout():
    session.pop('google_token', None)
    session.pop('email', None)
    return redirect(url_for('index'))

@app.route('/login/authorized')
def authorized():
    token = oauth.google.authorize_access_token()
    if token is None:
        return 'Access denied or login canceled by the user'
    session['google_token'] = (token['access_token'], '')
    resp = oauth.google.get('userinfo')
    user_info = resp.json()
    session['email'] = user_info['email']
    return redirect(url_for('index'))

@app.route('/send')
def send_scheduled_emails():
    conn = get_db_connection()
    cursor = conn.cursor()
    logging.info("Initiating scheduled email sending process.")
    
    cursor.execute("SELECT id, email_to, subject, message FROM emails WHERE send_time <= NOW()")
    emails = cursor.fetchall()
    
    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
    
    for email_id, recipient, subject, message in emails:
        email = Mail(
            from_email='emailnotifier4@gmail.com',
            to_emails=recipient,
            subject=subject,
            plain_text_content=message
        )
        response = sg.send(email)
        
        if response.status_code == 202:
            cursor.execute("DELETE FROM emails WHERE id = %s", (email_id,))
    
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM emails")
    cursor.close()
    conn.close()
    update_pending_emails_metric()
    
    return f"Processed {len(emails)} emails."

def update_pending_emails_metric():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM emails WHERE send_time <= NOW()")
    result = cursor.fetchone()  # Fetch the first row of the result
    
    # Check if result is not None and the first element of the tuple is not None
    pending_emails_count = 0
    if result and result[0] is not None:
        pending_emails_count = result[0]

    cursor.close()
    conn.close()
    client = monitoring_v3.MetricServiceClient()
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    project_path = client.common_project_path(project_id)
    
    series = monitoring_v3.TimeSeries()
    series.metric.type = 'custom.googleapis.com/emails_count'
    series.resource.type = 'global'
    
    now = datetime.datetime.utcnow()
    seconds = int(now.timestamp())
    series.points = [{
        'interval': {
            'end_time': {'seconds': seconds}
        },
        'value': {'int64_value': int(pending_emails_count)}
    }]
    
    client.create_time_series(request={"name": project_path, "time_series": [series]})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
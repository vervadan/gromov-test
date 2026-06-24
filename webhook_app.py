import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

GMAIL_USER = os.environ.get('GMAIL_USER', '')
GMAIL_PASS = os.environ.get('GMAIL_PASS', '')

INVOICE_MAP = {
    '1385884-1': 'Избегатель',
    '1385884-2': 'Транжира',
    '1385884-3': 'Накопитель',
    '1385884-4': 'Стратег',
}

PDF_MAP = {
    'Избегатель': ('https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_izbegatel.pdf', 'guide_izbegatel.pdf'),
    'Транжира': ('https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_tranzira.pdf', 'guide_tranzira.pdf'),
    'Накопитель': ('https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_nakopitel.pdf', 'guide_nakopitel.pdf'),
    'Стратег': ('https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_strateg.pdf', 'guide_strateg.pdf'),
}

def find_email(obj):
    # Email в metadata.custEmail
    meta = obj.get('metadata', {})
    if meta.get('custEmail'):
        return meta['custEmail']
    if meta.get('customerNumber') and '@' in str(meta.get('customerNumber', '')):
        return meta['customerNumber']
    return None

def find_invoice_number(obj):
    meta = obj.get('metadata', {})
    inv = meta.get('dashboardInvoiceOriginalNumber', '')
    if inv:
        return inv
    order = meta.get('orderNumber', '')
    if order:
        parts = order.split('-')
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1]}"
    return None

def send_pdf_email(to_email, product_name):
    if product_name not in PDF_MAP:
        print(f"Unknown product: {product_name}")
        return False

    pdf_url, pdf_file = PDF_MAP[product_name]
    resp = requests.get(pdf_url)
    if resp.status_code != 200:
        print(f"Failed to download PDF: {resp.status_code}")
        return False

    msg = MIMEMultipart()
    msg['From'] = f'Алексей Громов <{GMAIL_USER}>'
    msg['To'] = to_email
    msg['Subject'] = f'Твой разбор готов — {product_name}'

    body = f"""Привет!

Ты прошёл тест и получил свой тип — {product_name}.

В этом письме — полный разбор и план на 30 дней. Сохрани файл, он твой.

Алексей Громов
t.me/gromov_schitaet"""

    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    part = MIMEBase('application', 'octet-stream')
    part.set_payload(resp.content)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{pdf_file}"')
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_email, msg.as_bytes())
        print(f"Email sent to {to_email} with {product_name}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'no data'}), 400

    if data.get('event') != 'payment.succeeded':
        return jsonify({'status': 'ignored'}), 200

    obj = data.get('object', {})
    email = find_email(obj)
    invoice_num = find_invoice_number(obj)
    product_name = INVOICE_MAP.get(invoice_num, '')

    print(f"Email: {email}, Invoice: {invoice_num}, Product: {product_name}")

    if not email:
        print("No email found")
        return jsonify({'status': 'no_email'}), 200

    if not product_name:
        print(f"Unknown invoice: {invoice_num}")
        return jsonify({'status': 'unknown_invoice'}), 200

    send_pdf_email(email, product_name)
    return jsonify({'status': 'ok'}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

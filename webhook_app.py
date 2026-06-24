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

PDF_MAP = {
    'Избегатель': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_izbegatel.pdf',
    'Транжира': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_tranzira.pdf',
    'Накопитель': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_nakopitel.pdf',
    'Стратег': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_strateg.pdf',
}

PDF_FILES = {
    'Избегатель': 'guide_izbegatel.pdf',
    'Транжира': 'guide_tranzira.pdf',
    'Накопитель': 'guide_nakopitel.pdf',
    'Стратег': 'guide_strateg.pdf',
}

def find_email(data):
    """Ищем email во всех возможных местах"""
    obj = data.get('object', {})
    
    # custEmail на верхнем уровне объекта
    if obj.get('custEmail'):
        return obj['custEmail']
    
    # customerNumber
    if obj.get('customerNumber'):
        val = obj['customerNumber']
        if '@' in str(val):
            return val
    
    # receipt.customer.email
    receipt = obj.get('receipt', {})
    customer = receipt.get('customer', {})
    if customer.get('email'):
        return customer['email']
    
    # metadata
    meta = obj.get('metadata', {})
    if meta.get('email'):
        return meta['email']
    
    # recipient
    recipient = obj.get('recipient', {})
    if recipient.get('email'):
        return recipient['email']
        
    return None

def find_product(data):
    """Ищем название товара"""
    obj = data.get('object', {})
    receipt = obj.get('receipt', {})
    items = receipt.get('items', [])
    if items:
        return items[0].get('description', '')
    return ''

def send_pdf_email(to_email, product_name):
    pdf_url = PDF_MAP.get(product_name)
    pdf_file = PDF_FILES.get(product_name)
    if not pdf_url:
        print(f"Unknown product: {product_name}")
        return False

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

    print(f"Webhook: {json.dumps(data, ensure_ascii=False)[:500]}")

    if data.get('event') != 'payment.succeeded':
        return jsonify({'status': 'ignored'}), 200

    email = find_email(data)
    product_name = find_product(data)

    print(f"Email: {email}, Product: {product_name}")

    if not email:
        print("No email found")
        return jsonify({'status': 'no_email'}), 200

    if not product_name:
        print("No product found")
        return jsonify({'status': 'no_product'}), 200

    send_pdf_email(email, product_name)
    return jsonify({'status': 'ok'}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

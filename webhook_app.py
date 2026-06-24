import os
import json
import base64
import threading
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

UNISENDER_API_KEY = os.environ.get('UNISENDER_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'gromov.schitaet@gmail.com')
SENDER_NAME = 'Алексей Громов'

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

    try:
        resp = requests.get(pdf_url, timeout=30)
        if resp.status_code != 200:
            print(f"Failed to download PDF: {resp.status_code}")
            return False
    except Exception as e:
        print(f"PDF download error: {e}")
        return False

    pdf_b64 = base64.b64encode(resp.content).decode('utf-8')

    body_text = f"""Привет!

Ты прошёл тест и получил свой тип — {product_name}.

В этом письме — полный разбор и план на 30 дней. Сохрани файл, он твой.

Алексей Громов
t.me/gromov_schitaet"""

    body_html = f"""<p>Привет!</p>
<p>Ты прошёл тест и получил свой тип — <strong>{product_name}</strong>.</p>
<p>В этом письме — полный разбор и план на 30 дней. Сохрани файл, он твой.</p>
<p>Алексей Громов<br><a href="https://t.me/gromov_schitaet">t.me/gromov_schitaet</a></p>"""

    payload = {
        'api_key': UNISENDER_API_KEY,
        'format': 'json',
        'email': to_email,
        'sender_name': SENDER_NAME,
        'sender_email': SENDER_EMAIL,
        'subject': f'Твой разбор готов — {product_name}',
        'body': body_html,
        'list_id': '1',
        'attachments[0][name]': pdf_file,
        'attachments[0][content]': pdf_b64,
    }

    try:
        r = requests.post(
            'https://api.unisender.com/ru/api/sendEmail',
            data=payload,
            timeout=30
        )
        result = r.json()
        print(f"Unisender response: {result}")
        if 'result' in result:
            print(f"Email sent to {to_email} with {product_name}")
            return True
        else:
            print(f"Unisender error: {result}")
            return False
    except Exception as e:
        print(f"Unisender request error: {e}")
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

    t = threading.Thread(target=send_pdf_email, args=(email, product_name))
    t.daemon = True
    t.start()

    return jsonify({'status': 'ok'}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

import os
import json
import smtplib
import hashlib
import hmac
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Конфиг из переменных окружения
GMAIL_USER = os.environ.get('GMAIL_USER', '')
GMAIL_PASS = os.environ.get('GMAIL_PASS', '')
YUKASSA_SECRET = os.environ.get('YUKASSA_SECRET', '')

# Соответствие товаров и PDF
PDF_MAP = {
    'Избегатель': {
        'url': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_izbegatel.pdf',
        'filename': 'guide_izbegatel.pdf',
        'title': 'Избегатель — разбор финансового типа'
    },
    'Транжира': {
        'url': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_tranzira.pdf',
        'filename': 'guide_tranzira.pdf',
        'title': 'Транжира — разбор финансового типа'
    },
    'Накопитель': {
        'url': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_nakopitel.pdf',
        'filename': 'guide_nakopitel.pdf',
        'title': 'Накопитель — разбор финансового типа'
    },
    'Стратег': {
        'url': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_strateg.pdf',
        'filename': 'guide_strateg.pdf',
        'title': 'Стратег — разбор финансового типа'
    },
}

def send_pdf_email(to_email, product_name):
    pdf_info = PDF_MAP.get(product_name)
    if not pdf_info:
        print(f"Unknown product: {product_name}")
        return False

    # Скачиваем PDF
    resp = requests.get(pdf_info['url'])
    if resp.status_code != 200:
        print(f"Failed to download PDF: {resp.status_code}")
        return False

    # Составляем письмо
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

    # Прикрепляем PDF
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(resp.content)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{pdf_info["filename"]}"')
    msg.attach(part)

    # Отправляем
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

    print(f"Webhook received: {json.dumps(data, ensure_ascii=False)}")

    # Проверяем что это успешная оплата
    event_type = data.get('event')
    if event_type != 'payment.succeeded':
        return jsonify({'status': 'ignored'}), 200

    payment = data.get('object', {})
    
    # Email покупателя
    receipt = payment.get('receipt', {})
    customer = receipt.get('customer', {})
    email = customer.get('email', '')
    
    if not email:
        # Пробуем другое место
        email = payment.get('metadata', {}).get('email', '')

    if not email:
        print("No email found in payment")
        return jsonify({'status': 'no_email'}), 200

    # Название товара
    items = receipt.get('items', [])
    product_name = ''
    if items:
        product_name = items[0].get('description', '')

    print(f"Payment: email={email}, product={product_name}")

    if product_name and email:
        send_pdf_email(email, product_name)

    return jsonify({'status': 'ok'}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

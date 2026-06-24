import os
import json
import threading
from flask import Flask, request, jsonify
import requests
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
SPREADSHEET_ID = '144DPnL8HljhfmT5FRQuXqqWVKJn5qm2YUTQ5pcqLjME'

INVOICE_MAP = {
    '1385884-1': 'Избегатель',
    '1385884-2': 'Транжира',
    '1385884-3': 'Накопитель',
    '1385884-4': 'Стратег',
}

PDF_MAP = {
    'Избегатель': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_izbegatel.pdf',
    'Транжира': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_tranzira.pdf',
    'Накопитель': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_nakopitel.pdf',
    'Стратег': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_strateg.pdf',
}

def get_sheet():
    creds_json = os.environ.get('GOOGLE_CREDS_JSON', '')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID).sheet1

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

def save_order(invoice_num, product_name):
    try:
        sheet = get_sheet()
        # Проверяем нет ли уже такого invoice
        records = sheet.get_all_values()
        for row in records[1:]:
            if row and row[0] == invoice_num:
                print(f"Invoice {invoice_num} already exists")
                return
        sheet.append_row([invoice_num, product_name, '', 'pending'])
        print(f"Saved order: {invoice_num} -> {product_name}")
    except Exception as e:
        print(f"Sheet error: {e}")

def send_pdf_to_telegram(chat_id, product_name):
    if product_name not in PDF_MAP:
        return False
    pdf_url = PDF_MAP[product_name]
    try:
        pdf_resp = requests.get(pdf_url, timeout=30)
        if pdf_resp.status_code != 200:
            print(f"PDF download failed: {pdf_resp.status_code}")
            return False
        # Отправляем документ
        files = {'document': (f'guide_{product_name}.pdf', pdf_resp.content, 'application/pdf')}
        data = {
            'chat_id': chat_id,
            'caption': f'Твой разбор — {product_name}. Сохрани файл, он твой.\n\nt.me/gromov_schitaet'
        }
        r = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
            files=files,
            data=data,
            timeout=30
        )
        print(f"Telegram sendDocument: {r.status_code} {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def send_tg_message(chat_id, text):
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': chat_id, 'text': text},
            timeout=10
        )
    except Exception as e:
        print(f"TG message error: {e}")

def handle_tg_update(update):
    message = update.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '').strip()

    if not chat_id or not text:
        return

    print(f"TG message from {chat_id}: {text}")

    if text.startswith('/start'):
        parts = text.split()
        if len(parts) > 1:
            # /start 1385884-2
            invoice_num = parts[1]
        else:
            send_tg_message(chat_id, 
                'Привет! Чтобы получить свой PDF, напиши номер заказа из письма ЮКассы.\n\nФормат: /get 1385884-2')
            return

        try:
            sheet = get_sheet()
            records = sheet.get_all_values()
            for i, row in enumerate(records[1:], start=2):
                if row and row[0] == invoice_num:
                    product_name = row[1]
                    status = row[3] if len(row) > 3 else 'pending'
                    if status == 'sent':
                        send_tg_message(chat_id, 'Этот заказ уже был отправлен. Проверь предыдущие сообщения в этом чате.')
                        return
                    send_tg_message(chat_id, f'Нашёл твой заказ — {product_name}. Отправляю файл...')
                    ok = send_pdf_to_telegram(chat_id, product_name)
                    if ok:
                        sheet.update_cell(i, 3, str(chat_id))
                        sheet.update_cell(i, 4, 'sent')
                    return
            send_tg_message(chat_id, 
                f'Заказ {invoice_num} не найден. Проверь номер — он в письме от ЮКассы.\n\nЕсли проблема не решается, напиши в поддержку.')
        except Exception as e:
            print(f"Error processing order: {e}")
            send_tg_message(chat_id, 'Произошла ошибка. Попробуй через минуту.')

    elif text.startswith('/get'):
        parts = text.split()
        if len(parts) < 2:
            send_tg_message(chat_id, 'Укажи номер заказа: /get 1385884-2')
            return
        # Переиспользуем логику /start
        handle_tg_update({'message': {'chat': {'id': chat_id}, 'text': f'/start {parts[1]}'}})

    else:
        send_tg_message(chat_id, 
            'Чтобы получить PDF, напиши номер заказа из письма ЮКассы:\n\n/get 1385884-2\n\n(замени на свой номер)')

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'no data'}), 400

    if data.get('event') != 'payment.succeeded':
        return jsonify({'status': 'ignored'}), 200

    obj = data.get('object', {})
    invoice_num = find_invoice_number(obj)
    product_name = INVOICE_MAP.get(invoice_num, '')

    print(f"Payment: Invoice: {invoice_num}, Product: {product_name}")

    if invoice_num and product_name:
        t = threading.Thread(target=save_order, args=(invoice_num, product_name))
        t.daemon = True
        t.start()

    return jsonify({'status': 'ok'}), 200

@app.route('/tg', methods=['POST'])
def tg_webhook():
    update = request.get_json(silent=True)
    if update:
        t = threading.Thread(target=handle_tg_update, args=(update,))
        t.daemon = True
        t.start()
    return jsonify({'ok': True}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

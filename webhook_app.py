import os
import json
import threading
from datetime import datetime, timezone, timedelta
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

PAYMENT_LINKS = {
    'izbegatel': ('Избегатель', 'https://yookassa.ru/my/i/ajuPQ2eykFS6/l'),
    'tranzira': ('Транжира', 'https://yookassa.ru/my/i/ajuPkTtwzv4z/l'),
    'nakopitel': ('Накопитель', 'https://yookassa.ru/my/i/ajuPqQXocT-I/l'),
    'strateg': ('Стратег', 'https://yookassa.ru/my/i/ajuPvDqZHxXI/l'),
}

PDF_MAP = {
    'Избегатель': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_izbegatel.pdf',
    'Транжира': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_tranzira.pdf',
    'Накопитель': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_nakopitel.pdf',
    'Стратег': 'https://raw.githubusercontent.com/vervadan/gromov-test/main/guide_strateg.pdf',
}

user_states = {}

MAIN_KEYBOARD = {
    'keyboard': [
        [{'text': '🧪 Пройти тест'}, {'text': '📩 Получить файл'}],
        [{'text': '💬 Поддержка'}]
    ],
    'resize_keyboard': True,
    'persistent': True
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

def save_order(invoice_num, product_name, email, payment_id, payment_dt):
    try:
        sheet = get_sheet()
        records = sheet.get_all_values()
        for row in records[1:]:
            if row and row[0] == invoice_num:
                print(f"Invoice {invoice_num} already exists")
                return
        sheet.append_row([invoice_num, product_name, email, '', 'pending', payment_id, payment_dt])
        print(f"Saved order: {invoice_num} -> {product_name} -> {email}")
    except Exception as e:
        print(f"Sheet error: {e}")

def send_pdf_to_telegram(chat_id, product_name):
    if product_name not in PDF_MAP:
        return False
    pdf_url = PDF_MAP[product_name]
    try:
        pdf_resp = requests.get(pdf_url, timeout=30)
        if pdf_resp.status_code != 200:
            return False
        files = {'document': (f'guide_{product_name}.pdf', pdf_resp.content, 'application/pdf')}
        data = {
            'chat_id': chat_id,
            'caption': f'Твой разбор — {product_name}. Сохрани файл.\n\nt.me/gromov_schitaet'
        }
        r = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument',
            files=files, data=data, timeout=30
        )
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def send_tg_message(chat_id, text, keyboard=None):
    payload = {'chat_id': chat_id, 'text': text}
    if keyboard:
        payload['reply_markup'] = json.dumps(keyboard)
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json=payload,
            timeout=10
        )
    except Exception as e:
        print(f"TG message error: {e}")

def find_orders_by_email(user_email):
    sheet = get_sheet()
    records = sheet.get_all_values()
    orders = []
    for i, row in enumerate(records[1:], start=2):
        if len(row) >= 3 and row[2].lower().strip() == user_email:
            orders.append({
                'row': i,
                'invoice': row[0],
                'product': row[1],
                'status': row[4] if len(row) > 4 else 'pending'
            })
    return orders

def deliver_order(chat_id, order, sheet):
    product_name = order['product']
    send_tg_message(chat_id, f'Отправляю файл — {product_name}...')
    ok = send_pdf_to_telegram(chat_id, product_name)
    if ok:
        sheet.update_cell(order['row'], 4, str(chat_id))
        sheet.update_cell(order['row'], 5, 'sent')

def handle_tg_update(update):
    message = update.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '').strip()

    if not chat_id or not text:
        return

    print(f"TG message from {chat_id}: {text}")

    state = user_states.get(chat_id, {})

    # Ждём выбор из списка
    if state.get('state') == 'waiting_choice':
        orders = state.get('orders', [])
        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(orders):
                del user_states[chat_id]
                try:
                    sheet = get_sheet()
                    deliver_order(chat_id, orders[idx], sheet)
                except Exception as e:
                    print(f"Deliver error: {e}")
                    send_tg_message(chat_id, 'Произошла ошибка. Попробуй через минуту.')
                return
        send_tg_message(chat_id, f'Напиши цифру от 1 до {len(orders)}.')
        return

    # Ждём email
    if state.get('state') == 'waiting_email' and not text.startswith('/') and text not in ['🧪 Пройти тест', '📩 Получить файл', '💬 Поддержка']:
        del user_states[chat_id]
        user_email = text.lower().strip()
        try:
            orders = find_orders_by_email(user_email)
            if not orders:
                send_tg_message(chat_id,
                    f'Оплата для {user_email} не найдена.\n\n'
                    f'Проверь email — он должен совпадать с тем, что вводил при оплате.\n\n'
                    f'Если проблема не решается — напиши в поддержку.',
                    MAIN_KEYBOARD)
                return

            if len(orders) == 1:
                sheet = get_sheet()
                deliver_order(chat_id, orders[0], sheet)
            else:
                lines = [f'На {user_email} найдено {len(orders)} заказа. Какой файл прислать?\n']
                for i, o in enumerate(orders, 1):
                    status = '✓ отправлен' if o['status'] == 'sent' else 'не получен'
                    lines.append(f'{i}. {o["product"]} — {status}')
                lines.append('\nНапиши цифру.')
                send_tg_message(chat_id, '\n'.join(lines))
                user_states[chat_id] = {'state': 'waiting_choice', 'orders': orders}
        except Exception as e:
            print(f"Error: {e}")
            send_tg_message(chat_id, 'Произошла ошибка. Попробуй через минуту.')
        return

    # Кнопки и команды
    if text in ['/start', '🧪 Пройти тест'] or text.startswith('/start '):
        parts = text.split()
        if len(parts) > 1 and not text.startswith('🧪'):
            type_key = parts[1].lower()
            if type_key in PAYMENT_LINKS:
                product_name, pay_url = PAYMENT_LINKS[type_key]
                send_tg_message(chat_id,
                    f'Твой тип — {product_name}.\n\n'
                    f'Полный разбор и план на 30 дней — 390 ₽.\n\n'
                    f'Оплати по ссылке:\n{pay_url}\n\n'
                    f'После оплаты вернись сюда и нажми «📩 Получить файл».',
                    MAIN_KEYBOARD)
                return

        if text == '🧪 Пройти тест':
            send_tg_message(chat_id,
                'Пройди тест — узнаешь свой тип финансового мышления:\n\nhttps://vervadan.github.io/gromov-test',
                MAIN_KEYBOARD)
        else:
            send_tg_message(chat_id,
                'Привет. Я Алексей Громов — разбираю, почему деньги не задерживаются, даже когда их достаточно.\n\n'
                'Если ты здесь — значит уже прошёл тест. Хорошо.\n\n'
                'Выбери что нужно:',
                MAIN_KEYBOARD)

    elif text in ['/get', '📩 Получить файл']:
        user_states[chat_id] = {'state': 'waiting_email'}
        send_tg_message(chat_id, 'Напиши email который указывал при оплате:')

    elif text == '💬 Поддержка':
        send_tg_message(chat_id,
            'Если что-то пошло не так — напиши напрямую:\n\n@vervadan',
            MAIN_KEYBOARD)

    else:
        send_tg_message(chat_id,
            'Выбери действие:',
            MAIN_KEYBOARD)

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
    email = find_email(obj)
    payment_id = obj.get('id', '')

    captured_at = obj.get('captured_at') or obj.get('created_at', '')
    try:
        dt = datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
        msk = dt.astimezone(timezone(timedelta(hours=3)))
        payment_dt = msk.strftime('%d.%m.%Y %H:%M')
    except:
        payment_dt = captured_at

    print(f"Payment: Invoice: {invoice_num}, Product: {product_name}, Email: {email}, ID: {payment_id}")

    if invoice_num and product_name:
        t = threading.Thread(target=save_order, args=(invoice_num, product_name, email or '', payment_id, payment_dt))
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

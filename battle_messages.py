"""Обновление одного сообщения с полем боя для каждого участника."""
from copy import deepcopy


def update_battle_message(match, chat_id, text, keyboard, send, edit, force=False):
    messages = match.setdefault('battle_messages', {})
    cached = messages.get(chat_id)
    content = (text, keyboard)
    if cached:
        if not force and cached['content'] == content:
            return
        result = edit(chat_id, cached['id'], text, keyboard)
        description = (result or {}).get('description', '').lower()
        if result and (result.get('ok') or 'message is not modified' in description):
            cached['content'] = deepcopy(content)
            return
        # После ошибки следующий показ должен повторить попытку.
        cached['content'] = None
        if not (result and result.get('error_code') == 400 and
                ('message to edit not found' in description or
                 "message can't be edited" in description or
                 'message_id_invalid' in description)):
            return
        messages.pop(chat_id, None)

    result = send(chat_id, text, keyboard)
    if result and result.get('ok'):
        message_id = result.get('result', {}).get('message_id')
        if message_id is not None:
            messages[chat_id] = {'id': message_id, 'content': deepcopy(content)}

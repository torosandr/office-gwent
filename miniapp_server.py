"""Local Mini App server. Run: python miniapp_server.py --local"""
import argparse
import json
import os
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
# The existing game loads its card catalogue relative to the working directory.
os.chdir(ROOT)
import config
from web_service import Service, WebError


def local_ips():
    """Собирает IPv4-адреса этого компьютера (кроме loopback), чтобы их можно было
    разрешить как адреса сервера для игры по локальной сети."""
    import socket
    try:
        ip = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        ip = []
    return [a for a in ip if not a.startswith('127.')]


def make_server(service, host='0.0.0.0', port=8765, bot=None):
    allowed_ips = local_ips()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, format, *args):
            pass

        def respond(self, status, content, content_type='application/json; charset=utf-8', cache_control='no-store'):
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', cache_control)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)

        def check_origin(self):
            authority = self.headers.get('Host', '').split(':')[0]
            allowed_hosts = {'127.0.0.1', 'localhost'} | set(allowed_ips)
            public_url = os.environ.get('MINIAPP_PUBLIC_URL', '').rstrip('/')
            if public_url:
                allowed_hosts.add(urlsplit(public_url).netloc.split(':')[0])
            if authority not in allowed_hosts:
                raise WebError('Недопустимый адрес сервера.', 403)
            origin = self.headers.get('Origin')
            if origin:
                origin_host = urlsplit(origin).hostname
                if origin_host not in allowed_hosts:
                    raise WebError('Запрос с другого сайта запрещён.', 403)

        def uid(self):
            authorization = self.headers.get('Authorization', '')
            if not authorization.startswith('Bearer '):
                raise WebError('Войдите в игру.', 401)
            return service.identify(authorization[7:])

        def do_GET(self):
            try:
                self.check_origin()
                path = urlsplit(self.path).path
                if path == '/api/config':
                    return self.respond(200, {'local': service.local, 'telegram': bool(service.bot_token),
                                              'storage': 'postgresql' if service.database.postgres else 'sqlite'})
                if path == '/api/state':
                    return self.respond(200, service.state(self.uid()))
                if path == '/api/menu':
                    return self.respond(200, service.menu(self.uid()))
                if path == '/api/cards':
                    return self.respond(200, service.cards_catalog(self.uid()))
                if path == '/api/heroes':
                    return self.respond(200, service.heroes(self.uid()))
                if path == '/api/packs':
                    return self.respond(200, service.my_packs(self.uid()))
                if path == '/api/rating':
                    return self.respond(200, service.rating())
                if path == '/api/deck-candidates':
                    return self.respond(200, service.deck_candidates(self.uid()))
                if path == '/health':
                    return self.respond(200, {'ok': True})
                if path == '/telegram-health':
                    return self.respond(200, {'ok': bool(bot)})
                files = {'/pack.svg': ('pack.svg', 'image/svg+xml'), '/': ('index.html', 'text/html; charset=utf-8'),
                         '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                         '/sounds.js': ('sounds.js', 'text/javascript; charset=utf-8'),
                         '/animations.js': ('animations.js', 'text/javascript; charset=utf-8'),
                         '/style.css': ('style.css', 'text/css; charset=utf-8'),
                         '/art/trainee-v1.webp': ('art/trainee-v1.webp', 'image/webp'),
                         '/art/coffee-machine-v1.webp': ('art/coffee-machine-v1.webp', 'image/webp'),
                         '/art/deadline-v1.webp': ('art/deadline-v1.webp', 'image/webp'),
                         '/art/meeting-v1.webp': ('art/meeting-v1.webp', 'image/webp')}
                files.update({'/art/drone-v1.webp': ('art/drone-v1.webp', 'image/webp'),'/art/women-meeting-v1.webp': ('art/women-meeting-v1.webp', 'image/webp'),'/art/expired-v1.webp': ('art/expired-v1.webp', 'image/webp'),'/art/smoke-v1.webp': ('art/smoke-v1.webp', 'image/webp'),'/art/contest-panini-v1.webp': ('art/contest-panini-v1.webp', 'image/webp'),'/art/espresso-v1.webp': ('art/espresso-v1.webp', 'image/webp'),'/art/cherry-panini-v1.webp': ('art/cherry-panini-v1.webp', 'image/webp'),'/art/vegetable-panini-v1.webp': ('art/vegetable-panini-v1.webp', 'image/webp'),'/art/printer-v1.webp': ('art/printer-v1.webp', 'image/webp'),'/art/meeting-spell-v1.webp': ('art/meeting-spell-v1.webp', 'image/webp'),'/art/cappuccino-v1.webp': ('art/cappuccino-v1.webp', 'image/webp'),'/art/anticipation-v1.webp': ('art/anticipation-v1.webp', 'image/webp'),'/art/stepan-v1.webp': ('art/stepan-v1.webp', 'image/webp'),'/art/buckwheat-v1.webp': ('art/buckwheat-v1.webp', 'image/webp'),'/art/accountant-v1.webp': ('art/accountant-v1.webp', 'image/webp'),'/art/workload-v1.webp': ('art/workload-v1.webp', 'image/webp'),'/art/manager-v1.webp': ('art/manager-v1.webp', 'image/webp'),'/art/guard-v1.webp': ('art/guard-v1.webp', 'image/webp'),'/art/dishwasher-v1.webp': ('art/dishwasher-v1.webp', 'image/webp'),'/art/tanya-v1.webp': ('art/tanya-v1.webp', 'image/webp')})
                files.update({'/art/tester-v1.webp': ('art/tester-v1.webp', 'image/webp'),'/art/reduction-v1.webp': ('art/reduction-v1.webp', 'image/webp'),'/art/beer-v1.webp': ('art/beer-v1.webp', 'image/webp'),'/art/friday-v1.webp': ('art/friday-v1.webp', 'image/webp')})
                files.update({'/art/laziness-v1.webp': ('art/laziness-v1.webp', 'image/webp'),'/art/indifference-v1.webp': ('art/indifference-v1.webp', 'image/webp'),'/art/marketer-v1.webp': ('art/marketer-v1.webp', 'image/webp')})
                files['/art/chicken-panini-v1.webp'] = ('art/chicken-panini-v1.webp', 'image/webp')
                files.update({key.replace('.webp', '.png'): (name.replace('.webp', '.png'), 'image/png') for key, (name, mime) in list(files.items()) if mime == 'image/webp'})
                if path not in files:
                    raise WebError('Страница не найдена.', 404)
                name, mime = files[path]
                self.respond(200, (ROOT / 'web' / name).read_bytes(), mime,
                             cache_control='public, max-age=604800, immutable' if mime in ('image/webp', 'image/png') else 'no-store')
            except WebError as error:
                self.respond(error.status, {'error': str(error)})
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            try:
                path = urlsplit(self.path).path
                # Webhook Telegram: не проверяем Origin (Telegram не шлёт его).
                if path == '/telegram':
                    length = int(self.headers.get('Content-Length', '0'))
                    if length <= 0 or length > 262144:
                        raise WebError('Недопустимый размер запроса.', 413)
                    body = json.loads(self.rfile.read(length))
                    if bot is not None:
                        bot.handle_telegram(body)
                    return self.respond(200, {'ok': True})
                if path == '/telegram-health':
                    return self.respond(200, {'ok': bool(bot)})
                self.check_origin()
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 16384:
                    raise WebError('Недопустимый размер запроса.', 413)
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise WebError('Некорректный запрос.')
                if path in ('/api/auth/local', '/api/auth/telegram'):
                    result = service.authenticate(body, telegram=path.endswith('telegram'))
                elif path == '/api/hero':
                    result = service.select_hero(self.uid(), str(body.get('hero', '')))
                elif path == '/api/promo':
                    result = service.redeem_promo(self.uid(), body.get('code'))
                elif path == '/api/packs/open':
                    result = service.open_pack(self.uid(), str(body.get('id', '')))
                elif path == '/api/buy':
                    result = service.buy(self.uid(), str(body.get('card', '')))
                elif path == '/api/deck':
                    result = service.deck_mutate(self.uid(), str(body.get('op', '')),
                                                 card_id=str(body.get('card', '')),
                                                 index=body.get('index'))
                else:
                    operations = {'/api/rooms': 'create', '/api/join': 'join', '/api/action': 'action', '/api/leave': 'leave'}
                    if path not in operations:
                        raise WebError('Запрос не найден.', 404)
                    result = service.mutate(self.uid(), operations[path], body)
                self.respond(200, result)
            except WebError as error:
                self.respond(error.status, {'error': str(error)})
            except (ValueError, TypeError):
                self.respond(400, {'error': 'Некорректный запрос.'})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                print('Mini App error:', type(error).__name__, file=sys.stderr)
                self.respond(500, {'error': 'Не удалось сохранить действие. Обновите поле и повторите попытку.'})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description='Office Gwent Mini App')
    parser.add_argument('--local', action='store_true', help='Enable local test players (loopback only)')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8765')))
    parser.add_argument('--database', default=os.environ.get('MINIAPP_DATABASE_PATH', str(ROOT / 'miniapp.sqlite3')))
    args = parser.parse_args()
    token = (os.environ.get('TELEGRAM_BOT_TOKEN') or getattr(config, 'TOKEN', '') or '').strip()
    if not args.local and not token:
        raise SystemExit('TELEGRAM_BOT_TOKEN не задан. Укажите токен бота в переменных окружения.')
    service = Service(args.database, local=args.local, bot_token='' if args.local else token,
                      profiles_path=ROOT / config.FILES['users'],
                      database_url=None if args.local else os.environ.get('DATABASE_URL'))
    if service.database.postgres:
        from cloud_storage import seed_profiles
        seed_profiles(service)
    # Текстовый бот (webhook) живёт в том же процессе, если есть токен и включён.
    bot = None
    if not args.local:
        try:
            from bot_runtime import build_bot_runtime
            bot = build_bot_runtime(service)
        except Exception as error:
            if service.database.postgres:
                # Do not silently launch with a broken durable bot store.
                raise RuntimeError('Не удалось подключить хранилище бота.') from None
            print('webhook bot disabled:', type(error).__name__, file=sys.stderr)
    if bot is not None:
        bot.games.promo_service = service
    server = make_server(service, port=args.port, bot=bot)
    print(f'Office Gwent: http://0.0.0.0:{args.port}', flush=True)
    # Прописываем webhook текстового бота, если известен публичный URL.
    if bot is not None:
        public = os.environ.get('MINIAPP_PUBLIC_URL', '').rstrip('/')
        if public:
            ok, desc = bot.set_webhook(f'{public}/telegram')
            print(f'Webhook: {"OK" if ok else desc}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Checkin Bot v8 - 按钮式交互"""
import json, os, sys, time, logging, requests, random
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'checkin_config.json')
LOG_FILE = os.path.join(BASE_DIR, 'checkin.log')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json', 'Content-Type': 'application/json'}


def get_cfg():
    return json.load(open(CONFIG_FILE))

def save_cfg(cfg):
    json.dump(cfg, open(CONFIG_FILE, 'w'), indent=2, ensure_ascii=False)


def api_call(site, path, method='GET', js=None, html=False):
    b = site['url'].rstrip('/')
    h = HEADERS.copy()
    h['Origin'] = b
    h['Referer'] = b + '/console/personal'
    uid = site.get('user_id')
    if uid:
        h['New-Api-User'] = str(uid)
    ck = dict(site.get('cookies', {}))
    if html:
        h['Accept'] = 'text/html'
        h.pop('Content-Type', None)
    try:
        if method == 'GET':
            r = requests.get(b + path, headers=h, cookies=ck, timeout=15)
        else:
            r = requests.post(b + path, headers=h, cookies=ck, json=js or {}, timeout=15)
        return r if html else r.json()
    except:
        return None


def do_login(site):
    info = site.get('login')
    if not info:
        return False
    h = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json',
         'Content-Type': 'application/json', 'Origin': site['url'].rstrip('/')}
    try:
        s = requests.Session()
        r = s.post(site['url'].rstrip('/') + '/api/user/login', headers=h,
                   json={'username': info['username'], 'password': info['password']}, timeout=15)
        d = r.json()
        if d.get('success'):
            site['cookies'] = {'session': s.cookies.get('session', '')}
            site['user_id'] = d['data']['id']
            return True
    except:
        pass
    return False


def ensure_auth(site):
    cook = site.get('cookies', {}).get('session', 'TODO')
    if cook not in ('TODO', ''):
        d = api_call(site, '/api/user/self')
        if d and d.get('success'):
            return True
    if site.get('login'):
        return do_login(site)
    return False


def get_self(site):
    d = api_call(site, '/api/user/self')
    return d.get('data', {}) if d else {}

def get_checkin(site):
    ym = datetime.now().strftime('%Y-%m')
    d = api_call(site, '/api/user/checkin?month=' + ym)
    if d and d.get('success'):
        return d.get('data', {}).get('stats', {})
    return {}

def get_models(site):
    key = site.get('api_key', '')
    if not key:
        return []
    try:
        h = {'User-Agent': 'Mozilla/5.0', 'Authorization': 'Bearer ' + key}
        r = requests.get(site['url'].rstrip('/') + '/api/models', headers=h, timeout=10)
        if r.status_code == 200:
            return r.json().get('data', [])
    except:
        pass
    return []

def bal_of(quota):
    return quota / 500000 if quota else 0


# ──────────────── 定时签到 ────────────────

SCHEDULE_FILE = os.path.join(BASE_DIR, '.next_checkin')

def pick_next_time():
    """生成 8:00~20:00 之间的随机时间"""
    hour = random.randint(8, 19)
    minute = random.randint(0, 59)
    now = datetime.now()
    t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t

def load_schedule():
    try:
        with open(SCHEDULE_FILE) as f:
            return datetime.fromisoformat(f.read().strip())
    except:
        return None

def save_schedule(dt):
    os.makedirs(os.path.dirname(SCHEDULE_FILE) or '.', exist_ok=True)
    with open(SCHEDULE_FILE, 'w') as f:
        f.write(dt.isoformat())

def run_all():
    """执行全部站点签到"""
    cfg = get_cfg()
    ok = fail = 0
    for site in cfg['sites']:
        n = site['name']
        t = site.get('type', 'new_api')
        if not ensure_auth(site):
            logger.warning('[%s] No auth', n)
            fail += 1
            continue
        try:
            if t == 'login_reward':
                api_call(site, '/console/personal', html=True)
                time.sleep(2)
                logger.info('[%s] Visited', n)
                ok += 1
            elif t == 'sub2api':
                r = api_call(site, '/api/v1/check-in', method='POST', js={'turnstile_token': None})
                if r and r.get('success'):
                    logger.info('[%s] OK', n)
                    ok += 1
                else:
                    logger.warning('[%s] %s', n, str(r))
                    fail += 1
            else:
                info = get_checkin(site)
                if info.get('checked_in_today'):
                    logger.info('[%s] Already checked', n)
                    ok += 1
                    continue
                r = api_call(site, '/api/user/checkin', method='POST')
                if r and r.get('success'):
                    amt = r.get('data', {}).get('amount', '?')
                    logger.info('[%s] Checkin OK +%s', n, str(amt))
                    ok += 1
                else:
                    msg = (r.get('message', 'err')[:40] if r else 'err')
                    logger.warning('[%s] %s', n, msg)
                    fail += 1
        except Exception as e:
            logger.error('[%s] %s', n, str(e))
            fail += 1
    save_cfg(cfg)
    logger.info('Done: %s ok, %s fail', ok, fail)


# ──────────────── TG Bot ────────────────

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, CallbackContext

TG_TOKEN_FILE = os.path.join(BASE_DIR, 'tg_token.txt')

SITE_ICONS = {
    'DGB': '1\u20e3', 'Muyuan': '2\u20e3', 'CM-API': '3\u20e3',
    'Shuo': '4\u20e3', 'XiaoWei': '5\u20e3', 'NewAPI': '6\u20e3',
    'HuanAPI': '7\u20e3', '42API': '8\u20e3', 'LittleSheep': '\U0001f411',
    'Pomelo': '\U0001f34a', 'AnyRouter': '\u2699\ufe0f', 'Sub2API': '\U0001f4e1',
    'XinJianYa': '\u2728', 'AIHub': '\U0001f916', 'ChuYel': '\U0001f343',
}


def get_site_icon(name):
    return SITE_ICONS.get(name, '\u2753')

def get_site_emoji(site):
    """返回状态 emoji"""
    if not ensure_auth(site):
        return '\u274c'  # ❌
    ci = get_checkin(site)
    if ci.get('checked_in_today'):
        return '\u2705'  # ✅
    return '\u26a0\ufe0f'  # ⚠️


def build_status_buttons():
    """构建状态按钮矩阵"""
    cfg = get_cfg()
    kb = []
    row = []
    for s in cfg['sites']:
        emoji = get_site_emoji(s)
        icon = get_site_icon(s['name'])
        label = emoji + icon + ' ' + s['name']
        row.append(InlineKeyboardButton(label, callback_data='site:' + s['name']))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    # Control row
    kb.append([
        InlineKeyboardButton('\u2705 全部签到', callback_data='checkin:all'),
        InlineKeyboardButton('\U0001f504 刷新', callback_data='refresh'),
    ])
    return InlineKeyboardMarkup(kb)


def format_site_detail(name):
    cfg = get_cfg()
    site = next((s for s in cfg['sites'] if s['name'] == name), None)
    if not site:
        return '站点未找到'

    lines = []
    # Title
    icon = get_site_icon(name)
    emoji = get_site_emoji(site)
    lines.append(emoji + ' ' + icon + ' <b>' + name + '</b>')
    lines.append('\U0001f517 <code>' + site['url'] + '</code>')

    if not ensure_auth(site):
        lines.append('\u274c 未认证 / 需要手动登录')
        key = site.get('api_key', '')
        if key:
            lines.append('')
            lines.append('\U0001f511 <b>API Key:</b>')
            lines.append('<code>' + key + '</code>')
        return '\n'.join(lines)

    u = get_self(site)
    ci = get_checkin(site)

    bal = bal_of(u.get('quota', 0))
    lines.append('')
    lines.append('\U0001f4b0 <b>余额:</b> $' + format(bal, '.2f'))
    lines.append('\U0001f468 <b>用户:</b> ' + str(u.get('display_name', '?')) +
                 ' (ID: ' + str(u.get('id', '?')) + ')')

    if ci:
        ck = '\u2705 今日已签' if ci.get('checked_in_today') else '\u26a0\ufe0f 今日未签'
        lines.append('\U0001f4c5 <b>签到:</b> ' + ck)
        lines.append('\U0001f4ca 累计 ' + str(ci.get('checkin_count', 0)) + ' 天' +
                     ' | 本月 +$' + format(bal_of(ci.get('total_quota', 0)), '.2f'))

    key = site.get('api_key', '')
    if key:
        lines.append('')
        lines.append('\U0001f511 <b>API Key:</b>')
        lines.append('<code>' + key + '</code>')

    models = get_models(site)
    if models:
        lines.append('')
        lines.append('\U0001f916 <b>模型 (' + str(len(models)) + '):</b>')
        tops = [m.get('id', '?') for m in models[:8]]
        lines.append(', '.join(tops))
        if len(models) > 8:
            lines.append('  ...共 ' + str(len(models)) + ' 个')

    return '\n'.join(lines)


# ──────────────── Command Handlers ────────────────

async def cmd_start(update, context):
    await update.message.reply_text(
        '\U0001f916 <b>签到机器人 v8</b>\n\n'
        '\U0001f4ca <b>命令</b>\n'
        '/s  - 站点状态 (按钮式)\n'
        '/c  - 全部签到\n'
        '/b  - 余额汇总\n'
        '/k  - API Key 列表\n'
        '/t  - 下次签到时间\n'
        '/log - 最近日志\n'
        '/man - 手动签到 (选择站点)',
        parse_mode='HTML')

async def cmd_status(update, context):
    await update.message.reply_text(
        '\U0001f4ca 点击查看站点详情:',
        reply_markup=build_status_buttons())

async def cmd_checkin_all(update, context):
    msg = await update.message.reply_text('\U0001f3c3 执行签到...')
    run_all()
    await msg.edit_text('\u2705 签到完成！\n发 /s 查看状态')

async def cmd_balance(update, context):
    cfg = get_cfg()
    lines = ['\U0001f4b0 <b>余额汇总</b>']
    total = 0
    for s in cfg['sites']:
        if not ensure_auth(s):
            continue
        u = get_self(s)
        bal = bal_of(u.get('quota', 0))
        total += bal
        lines.append('  ' + get_site_icon(s['name']) + ' <b>' + s['name'] + '</b>: $' + format(bal, '.2f'))
    lines.append('')
    lines.append('\U0001f4b0 <b>总计: $' + format(total, '.2f') + '</b>')
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')

async def cmd_keys(update, context):
    cfg = get_cfg()
    lines = ['\U0001f511 <b>API Keys</b>']
    for s in cfg['sites']:
        key = s.get('api_key', '')
        if key:
            lines.append('')
            lines.append(get_site_icon(s['name']) + ' <b>' + s['name'] + '</b>')
            lines.append('<code>' + key + '</code>')
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')

async def cmd_time(update, context):
    scheduled = load_schedule()
    if scheduled:
        remaining = scheduled - datetime.now()
        if remaining.total_seconds() > 0:
            h = int(remaining.total_seconds() // 3600)
            m = int((remaining.total_seconds() % 3600) // 60)
            await update.message.reply_text(
                '\U0001f552 <b>下次签到:</b> ' + scheduled.strftime('%m/%d %H:%M') +
                '\n\u23f3 还剩 ' + str(h) + 'h ' + str(m) + 'm',
                parse_mode='HTML')
        else:
            await update.message.reply_text('\U0001f552 正在执行签到...')
    else:
        await update.message.reply_text('\U0001f552 未设置自动签到')

async def cmd_log(update, context):
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            logs = f.readlines()
        last = logs[-15:] if len(logs) > 15 else logs
        await update.message.reply_text(''.join(last)[:4000])
    except:
        await update.message.reply_text('\u274c 无法读取日志')

async def cmd_manual(update, context):
    """手动选择站点签到"""
    cfg = get_cfg()
    kb = []
    for s in cfg['sites']:
        emoji = get_site_emoji(s)
        icon = get_site_icon(s['name'])
        kb.append([InlineKeyboardButton(emoji + icon + ' ' + s['name'],
                                        callback_data='checkin:' + s['name'])])
    await update.message.reply_text('选择要签到的站点:', reply_markup=InlineKeyboardMarkup(kb))


async def button_callback(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == 'refresh':
        await q.message.edit_text('\U0001f4ca 点击查看站点详情:', reply_markup=build_status_buttons())
        return

    if data == 'checkin:all':
        await q.message.edit_text('\U0001f3c3 执行全部签到...')
        run_all()
        await q.message.reply_text('\u2705 签到完成！\n/s 查看状态')
        return

    if data.startswith('checkin:'):
        name = data.split(':', 1)[1]
        cfg = get_cfg()
        site = next((s for s in cfg['sites'] if s['name'] == name), None)
        if not site:
            await q.message.reply_text('站点未找到')
            return
        if not ensure_auth(site):
            await q.message.reply_text('\u274c ' + name + ': 未认证')
            return
        ci = get_checkin(site)
        if ci.get('checked_in_today'):
            await q.message.reply_text('\u2705 ' + name + ': 今日已签')
            return
        r = api_call(site, '/api/user/checkin', method='POST')
        if r and r.get('success'):
            amt = r.get('data', {}).get('amount', '?')
            await q.message.reply_text('\u2705 ' + name + ': +$' + str(amt))
        else:
            msg = (r.get('message', 'err')[:40] if r else 'err')
            await q.message.reply_text('\u274c ' + name + ': ' + msg)
        return

    if data.startswith('site:'):
        name = data.split(':', 1)[1]
        detail = format_site_detail(name)
        await q.message.reply_text(detail, parse_mode='HTML')
        return

    if data.startswith('sched:'):
        # Manual schedule - pick next time
        parts = data.split(':')
        if len(parts) == 3:
            h, m = int(parts[1]), int(parts[2])
            now = datetime.now()
            t = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if t <= now:
                t += timedelta(days=1)
            save_schedule(t)
            await q.message.reply_text('\u2705 下次签到: ' + t.strftime('%m/%d %H:%M'))
        return


# ──────────────── Cron Loop ────────────────

def cron_loop():
    """自动签到循环 - 随机时间 8:00~20:00"""
    logger.info('Cron scheduler started')
    while True:
        scheduled = load_schedule()
        if not scheduled or scheduled <= datetime.now():
            scheduled = pick_next_time()
            save_schedule(scheduled)
            logger.info('Next checkin scheduled: %s', scheduled.isoformat())

        sleep_secs = (scheduled - datetime.now()).total_seconds()
        if sleep_secs > 0:
            time.sleep(min(sleep_secs, 300))  # Check every 5 min
            continue

        logger.info('Running scheduled checkin...')
        try:
            run_all()
        except Exception as e:
            logger.error('Scheduled checkin error: %s', e)

        # Schedule next
        next_t = pick_next_time()
        save_schedule(next_t)
        logger.info('Next checkin: %s', next_t.isoformat())


# ──────────────── Main ────────────────

def main():
    import asyncio
    import threading

    # Start cron in background
    t = threading.Thread(target=cron_loop, daemon=True)
    t.start()

    # Start TG bot
    with open(TG_TOKEN_FILE) as f:
        token = f.read().strip()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler(['s', 'status'], cmd_status))
    app.add_handler(CommandHandler(['c', 'checkin'], cmd_checkin_all))
    app.add_handler(CommandHandler(['b', 'balance'], cmd_balance))
    app.add_handler(CommandHandler(['k', 'keys'], cmd_keys))
    app.add_handler(CommandHandler(['t', 'time'], cmd_time))
    app.add_handler(CommandHandler('log', cmd_log))
    app.add_handler(CommandHandler(['man', 'manual'], cmd_manual))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info('Bot v8 starting...')
    app.run_polling()


if __name__ == '__main__':
    main()

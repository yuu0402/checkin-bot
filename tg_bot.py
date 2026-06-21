#!/usr/bin/env python3
"""
Checkin Bot v9 — 设计优化版
按钮式交互 / 状态卡片 / 余额排行榜 / 分组面板
"""
import json, os, sys, time, logging, requests, random
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'checkin_config.json')
LOG_FILE = os.path.join(BASE_DIR, 'checkin.log')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json', 'Content-Type': 'application/json'}

# ─────── 站点数据 ───────
SITE_META = {
    'DGB':         {'icon': '1\u20e3', 'sort': 1},
    'Muyuan':      {'icon': '2\u20e3', 'sort': 2},
    'CM-API':      {'icon': '3\u20e3', 'sort': 3},
    'Shuo':        {'icon': '4\u20e3', 'sort': 4},
    'XiaoWei':     {'icon': '5\u20e3', 'sort': 5},
    'NewAPI':      {'icon': '6\u20e3', 'sort': 6},
    'HuanAPI':     {'icon': '7\u20e3', 'sort': 7},
    '42API':       {'icon': '8\u20e3', 'sort': 8},
    'LittleSheep': {'icon': '\U0001f411', 'sort': 9},
    'Pomelo':      {'icon': '\U0001f34a', 'sort': 10},
    'AnyRouter':   {'icon': '\u2699\ufe0f', 'sort': 11},
    'Sub2API':     {'icon': '\U0001f4e1', 'sort': 12},
    'XinJianYa':   {'icon': '\u2728', 'sort': 13},
    'AIHub':       {'icon': '\U0001f916', 'sort': 14},
    'ChuYel':      {'icon': '\U0001f343', 'sort': 15},
}

# ─────── 工具函数 ───────

def get_cfg():
    return json.load(open(CONFIG_FILE))
def save_cfg(cfg):
    json.dump(cfg, open(CONFIG_FILE, 'w'), indent=2, ensure_ascii=False)

def api_call(site, path, method='GET', js=None, html=False):
    b = site['url'].rstrip('/')
    h = HEADERS.copy()
    h['Origin'] = b; h['Referer'] = b + '/console/personal'
    uid = site.get('user_id')
    if uid: h['New-Api-User'] = str(uid)
    ck = dict(site.get('cookies', {}))
    if html:
        h['Accept'] = 'text/html'; h.pop('Content-Type', None)
    try:
        if method == 'GET':
            r = requests.get(b + path, headers=h, cookies=ck, timeout=15)
        else:
            r = requests.post(b + path, headers=h, cookies=ck, json=js or {}, timeout=15)
        return r if html else r.json()
    except: return None

def do_login(site):
    info = site.get('login')
    if not info: return False
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
    except: pass
    return False

def ensure_auth(site):
    cook = site.get('cookies', {}).get('session', 'TODO')
    if cook not in ('TODO', ''):
        d = api_call(site, '/api/user/self')
        if d and d.get('success'): return True
    if site.get('login'): return do_login(site)
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
    if not key: return []
    try:
        h = {'User-Agent': 'Mozilla/5.0', 'Authorization': 'Bearer ' + key}
        r = requests.get(site['url'].rstrip('/') + '/api/models', headers=h, timeout=10)
        if r.status_code == 200:
            return r.json().get('data', [])
    except: pass
    return []

def bal_of(quota):
    return quota / 500000 if quota else 0

def site_status(site):
    """获取站点状态数据"""
    if not ensure_auth(site):
        return {'auth': False, 'bal': 0, 'checked': None, 'models': []}
    u = get_self(site)
    ci = get_checkin(site)
    return {
        'auth': True,
        'bal': bal_of(u.get('quota', 0)),
        'checked': ci.get('checked_in_today'),
        'checkin_count': ci.get('checkin_count', 0),
        'total_quota': ci.get('total_quota', 0),
        'display_name': u.get('display_name', '?'),
        'user_id': u.get('id', '?'),
        'group': u.get('group', ''),
        'request_count': u.get('request_count', 0),
    }

# ─────── 定时签到 ───────

SCHEDULE_FILE = os.path.join(BASE_DIR, '.next_checkin')

def pick_next_time():
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
    except: return None

def save_schedule(dt):
    os.makedirs(os.path.dirname(SCHEDULE_FILE) or '.', exist_ok=True)
    with open(SCHEDULE_FILE, 'w') as f:
        f.write(dt.isoformat())

def run_all():
    cfg = get_cfg()
    ok = fail = 0
    for site in cfg['sites']:
        n = site['name']; t = site.get('type', 'new_api')
        if not ensure_auth(site):
            logger.warning('[%s] No auth', n)
            fail += 1; continue
        try:
            if t == 'login_reward':
                api_call(site, '/console/personal', html=True); time.sleep(2)
                logger.info('[%s] Visited', n); ok += 1
            elif t == 'sub2api':
                r = api_call(site, '/api/v1/check-in', method='POST', js={'turnstile_token': None})
                if r and r.get('success'):
                    logger.info('[%s] OK', n); ok += 1
                else:
                    logger.warning('[%s] %s', n, str(r)); fail += 1
            else:
                info = get_checkin(site)
                if info.get('checked_in_today'):
                    logger.info('[%s] Already checked', n); ok += 1; continue
                r = api_call(site, '/api/user/checkin', method='POST')
                if r and r.get('success'):
                    amt = r.get('data', {}).get('amount', '?')
                    logger.info('[%s] OK +%s', n, str(amt)); ok += 1
                else:
                    msg = (r.get('message', 'err')[:40] if r else 'err')
                    logger.warning('[%s] %s', n, msg); fail += 1
        except Exception as e:
            logger.error('[%s] %s', n, str(e)); fail += 1
    save_cfg(cfg)
    logger.info('Done: %s ok, %s fail', ok, fail)

# ─────── TG Bot ───────

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TG_TOKEN_FILE = os.path.join(BASE_DIR, 'tg_token.txt')

# ─── 样式常量 ───
LINE = '\u2501' * 27
LINE_S = '\u2500' * 27
EMOJI_OK = '\u2705'
EMOJI_WARN = '\u26a0\ufe0f'
EMOJI_FAIL = '\u274c'
EMOJI_COIN = '\U0001f4b0'
EMOJI_USER = '\U0001f468'
EMOJI_CAL = '\U0001f4c5'
EMOJI_KEY = '\U0001f511'
EMOJI_ROBO = '\U0001f916'
EMOJI_CLOCK = '\U0001f552'
EMOJI_ROCKET = '\U0001f680'
EMOJI_RANK = '\U0001f3c6'

# ─── 构建按钮面板 ───

def get_site_button_data(cfg):
    """获取每个站点按钮所需数据: (状态emoji, 图标, 名称, 回调)"""
    buttons = []
    for s in cfg['sites']:
        n = s['name']
        meta = SITE_META.get(n, {'icon': '\u2753', 'sort': 99})
        st = site_status(s)
        if not st['auth']:
            emoji = EMOJI_FAIL
        elif st['checked']:
            emoji = EMOJI_OK
        else:
            emoji = EMOJI_WARN
        buttons.append((emoji, meta['icon'], n, st))
    return buttons


def format_stats_banner(cfg, buttons_data):
    """生成顶部统计横幅"""
    total = 0
    ok = warn = fail = 0
    for emoji, icon, name, st in buttons_data:
        if not st['auth']:
            fail += 1
        elif st['checked']:
            ok += 1; total += st['bal']
        else:
            warn += 1; total += st['bal']
    return (
        LINE + '\n'
        '\U0001f4ca <b>\u7b7e\u5230\u9762\u677f \u00b7 '
        + datetime.now().strftime('%m/%d') + '</b>\n'
        + LINE + '\n'
        + EMOJI_OK + ' \u5df2\u7b7e\u5230  ' + str(ok)
        + '   ' + EMOJI_WARN + ' \u672a\u7b7e  ' + str(warn)
        + '   ' + EMOJI_FAIL + ' \u5f02\u5e38  ' + str(fail) + '\n'
        + EMOJI_COIN + ' \u603b\u4f59\u989d  $' + format(total, '.2f') + '\n'
        + LINE
    )


def build_button_matrix(buttons_data):
    """构建按钮矩阵（已签到 / 未签到 / 异常 分组）"""
    ok_btns = []
    warn_btns = []
    fail_btns = []
    for emoji, icon, name, st in buttons_data:
        label = emoji + ' ' + icon + ' ' + name
        cb = 'site:' + name
        btn = InlineKeyboardButton(label, callback_data=cb)
        if not st['auth']:
            fail_btns.append(btn)
        elif st['checked']:
            ok_btns.append(btn)
        else:
            warn_btns.append(btn)

    kb = []
    # 已签到组
    if ok_btns:
        # 3 per row
        for i in range(0, len(ok_btns), 3):
            kb.append(ok_btns[i:i+3])
    # 未签到组
    if warn_btns:
        for i in range(0, len(warn_btns), 3):
            kb.append(warn_btns[i:i+3])
    # 异常组
    if fail_btns:
        for i in range(0, len(fail_btns), 3):
            kb.append(fail_btns[i:i+3])

    # 控制栏
    kb.append([
        InlineKeyboardButton('\U0001f680 \u5168\u90e8\u7b7e\u5230', callback_data='checkin:all'),
        InlineKeyboardButton('\U0001f504 \u5237\u65b0', callback_data='refresh'),
    ])
    return InlineKeyboardMarkup(kb)


# ─── 格式化详情 ───

def fmt_detail(name):
    cfg = get_cfg()
    site = next((s for s in cfg['sites'] if s['name'] == name), None)
    if not site: return '\u7ad9\u70b9\u672a\u627e\u5230'
    meta = SITE_META.get(name, {'icon': '\u2753'})
    st = site_status(site)

    lines = []
    # 标题栏
    if not st['auth']:
        status_emoji = EMOJI_FAIL
        status_text = '\u672a\u8ba4\u8bc1'
    elif st['checked']:
        status_emoji = EMOJI_OK
        status_text = '\u4eca\u65e5\u5df2\u7b7e'
    else:
        status_emoji = EMOJI_WARN
        status_text = '\u4eca\u65e5\u672a\u7b7e'

    lines.append(LINE)
    lines.append(' ' + status_emoji + ' ' + meta['icon'] + ' <b>' + name + '</b>')
    lines.append(LINE)
    lines.append('\U0001f517 <code>' + site['url'] + '</code>')
    lines.append('')

    if not st['auth']:
        lines.append(EMOJI_FAIL + ' ' + status_text)
        key = site.get('api_key', '')
        if key:
            lines.append('')
            lines.append(EMOJI_KEY + ' <b>API Key</b>')
            lines.append('<code>' + key + '</code>')
        lines.append(LINE)
        return '\n'.join(lines)

    # 余额 + 用户
    lines.append(EMOJI_COIN + ' <b>\u4f59\u989d</b>        $' + format(st['bal'], '.2f'))
    lines.append(EMOJI_USER + ' <b>\u7528\u6237</b>        ' + st['display_name']
                 + ' (ID: ' + str(st['user_id']) + ')')
    if st.get('group'):
        lines.append('\U0001f4cb <b>\u5206\u7ec4</b>        ' + st['group'])
    lines.append('')

    # 签到
    cal_text = status_emoji + ' ' + status_text
    cal_text += ' \u00b7 \u7d2f\u8ba1 ' + str(st['checkin_count']) + ' \u5929'
    if st['total_quota']:
        cal_text += ' | \u672c\u6708 +$' + format(bal_of(st['total_quota']), '.2f')
    lines.append(EMOJI_CAL + ' <b>\u7b7e\u5230</b>      ' + cal_text)
    lines.append('')

    # API Key
    key = site.get('api_key', '')
    if key:
        lines.append(EMOJI_KEY + ' <b>API Key</b>')
        lines.append('<code>' + key + '</code>')
        lines.append('')

    # 模型
    models = get_models(site)
    if models:
        lines.append(EMOJI_ROBO + ' <b>\u6a21\u578b</b> (' + str(len(models)) + ' \u4e2a)')
        # 2 columns
        tops = [m.get('id', '?') for m in models]
        pairs = []
        for i in range(0, min(len(tops), 10), 2):
            pair = tops[i]
            if i+1 < len(tops):
                pair += '    ' + tops[i+1]
            pairs.append(pair)
        lines.append('<code>' + '\n'.join(pairs) + '</code>')
        if len(tops) > 10:
            lines.append('  ...\u5171 ' + str(len(tops)) + ' \u4e2a')

    lines.append(LINE)
    return '\n'.join(lines)


# ─────── 命令处理器 ───────

async def cmd_start(update, context):
    lines = [
        LINE,
        '\U0001f916 <b>\u7b7e\u5230\u673a\u5668\u4eba v9</b>',
        LINE,
        '\U0001f4ca <b>\u72b6\u6001</b>',
        '  /s - \u72b6\u6001\u9762\u677f (\u6309\u94ae)',
        '  /b - \u4f59\u989d\u6392\u884c\u699c',
        '  /k - API Key \u5217\u8868',
        '  /t - \u4e0b\u6b21\u7b7e\u5230\u65f6\u95f4',
        '',
        '\u2705 <b>\u7b7e\u5230</b>',
        '  /c - \u5168\u90e8\u7b7e\u5230',
        '  /man - \u5355\u9009\u7ad9\u70b9\u7b7e\u5230',
        '',
        '\U0001f4cb <b>\u5176\u4ed6</b>',
        '  /log - \u6700\u65b0\u65e5\u5fd7',
        '  /settime HH:MM - \u8bbe\u5b9a\u7b7e\u5230\u65f6\u95f4',
        '',
        '\u23f3 \u6bcf\u65e5 8:00~20:00 \u968f\u673a\u65f6\u95f4\u81ea\u52a8\u7b7e\u5230',
        LINE,
    ]
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')


async def cmd_status(update, context):
    cfg = get_cfg()
    btns = get_site_button_data(cfg)
    banner = format_stats_banner(cfg, btns)
    kb = build_button_matrix(btns)
    await update.message.reply_text(banner, parse_mode='HTML')
    await update.message.reply_text('\U0001f447 \u70b9\u51fb\u67e5\u770b\u8be6\u60c5:', reply_markup=kb)


async def cmd_checkin_all(update, context):
    msg = await update.message.reply_text('\U0001f680 \u6267\u884c\u5168\u90e8\u7b7e\u5230...')
    run_all()
    cfg = get_cfg()
    btns = get_site_button_data(cfg)
    banner = format_stats_banner(cfg, btns)
    kb = build_button_matrix(btns)
    await msg.edit_text(banner, parse_mode='HTML')
    await msg.reply_text('\U0001f447 \u7b7e\u5230\u5b8c\u6210\uff01', reply_markup=kb)


async def cmd_balance(update, context):
    cfg = get_cfg()
    # Collect all balances
    items = []
    for s in cfg['sites']:
        if not ensure_auth(s): continue
        u = get_self(s)
        b = bal_of(u.get('quota', 0))
        items.append((b, s['name']))
    items.sort(reverse=True)

    medals = ['\U0001f947', '\U0001f948', '\U0001f949']
    lines = [
        LINE,
        EMOJI_COIN + ' <b>\u4f59\u989d\u6392\u884c\u699c</b>',
        LINE,
    ]
    total = 0
    for i, (b, name) in enumerate(items):
        total += b
        meta = SITE_META.get(name, {'icon': '\u2753'})
        if i < 3:
            prefix = medals[i] + ' '
        else:
            prefix = (' ' if i+1 < 10 else '') + str(i+1) + '\u20e3 '
        lines.append(prefix + meta['icon'] + ' <b>' + name + '</b>  $' + format(b, '.2f'))
    lines.append('')
    lines.append(EMOJI_COIN + ' <b>\u603b\u8ba1 ' + str(len(items))
                 + ' \u7ad9: $' + format(total, '.2f') + '</b>')
    lines.append(LINE)
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')


async def cmd_keys(update, context):
    cfg = get_cfg()
    lines = [
        LINE,
        EMOJI_KEY + ' <b>API Keys</b>',
        LINE,
    ]
    for s in cfg['sites']:
        key = s.get('api_key', '')
        if key:
            meta = SITE_META.get(s['name'], {'icon': '\u2753'})
            lines.append('')
            lines.append(meta['icon'] + ' <b>' + s['name'] + '</b>')
            lines.append('<code>' + key + '</code>')
    lines.append('')
    lines.append(LINE)
    await update.message.reply_text('\n'.join(lines), parse_mode='HTML')


async def cmd_time(update, context):
    scheduled = load_schedule()
    if scheduled:
        remaining = scheduled - datetime.now()
        if remaining.total_seconds() > 0:
            h = int(remaining.total_seconds() // 3600)
            m = int((remaining.total_seconds() % 3600) // 60)
            text = (
                LINE + '\n'
                + EMOJI_CLOCK + ' <b>\u4e0b\u6b21\u7b7e\u5230</b>\n'
                + LINE + '\n'
                + '\u23f3 ' + scheduled.strftime('%m/%d %H:%M') + '\n'
                + '\u8fd8\u5269 ' + str(h) + 'h ' + str(m) + 'm\n'
                + LINE
            )
        else:
            text = EMOJI_ROCKET + ' \u6b63\u5728\u6267\u884c\u7b7e\u5230...'
    else:
        text = EMOJI_CLOCK + ' \u672a\u8bbe\u7f6e\u81ea\u52a8\u7b7e\u5230'
    await update.message.reply_text(text, parse_mode='HTML')


async def cmd_log(update, context):
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            logs = f.readlines()
        last = logs[-20:] if len(logs) > 20 else logs
        text = ''.join(last)[:4000]
        # Wrap in code block
        text = '\u2501' * 12 + '\n\u2709\ufe0f <b>\u6700\u65b0\u65e5\u5fd7</b>\n' + '\u2501' * 12 + '\n' + text
        await update.message.reply_text(text, parse_mode='HTML')
    except:
        await update.message.reply_text(EMOJI_FAIL + ' \u65e0\u6cd5\u8bfb\u53d6\u65e5\u5fd7')


async def cmd_manual(update, context):
    cfg = get_cfg()
    btns = get_site_button_data(cfg)
    kb_list = []
    for emoji, icon, name, st in btns:
        if not st['auth'] or not st['checked']:
            label = emoji + ' ' + icon + ' ' + name
            kb_list.append([InlineKeyboardButton(label, callback_data='checkin:' + name)])
    await update.message.reply_text(
        '\u9009\u62e9\u8981\u7b7e\u5230\u7684\u7ad9\u70b9:',
        reply_markup=InlineKeyboardMarkup(kb_list) if kb_list else None)


async def cmd_settime(update, context):
    args = context.args
    if not args:
        await update.message.reply_text(
            '\u7528\u6cd5: /settime HH:MM\n\u4f8b\u5982: /settime 14:30')
        return
    try:
        parts = args[0].split(':')
        h, m = int(parts[0]), int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError
        now = datetime.now()
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        save_schedule(t)
        await update.message.reply_text(
            EMOJI_OK + ' \u4e0b\u6b21\u7b7e\u5230\u65f6\u95f4\u5df2\u8bbe\u5b9a\u4e3a: '
            + t.strftime('%m/%d %H:%M'))
    except:
        await update.message.reply_text(
            '\u683c\u5f0f\u9519\u8bef\uff0c\u7528\u6cd5: /settime HH:MM')


# ─────── 按钮回调 ───────

async def button_cb(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == 'refresh':
        cfg = get_cfg()
        btns = get_site_button_data(cfg)
        banner = format_stats_banner(cfg, btns)
        kb = build_button_matrix(btns)
        # Try to edit the stats message
        try:
            await q.message.edit_text(banner, parse_mode='HTML')
        except: pass
        await q.message.reply_text('\U0001f504 \u5df2\u5237\u65b0', reply_markup=kb)
        return

    if data == 'checkin:all':
        await q.message.edit_text('\U0001f680 \u6267\u884c\u5168\u90e8\u7b7e\u5230...')
        run_all()
        cfg = get_cfg()
        btns = get_site_button_data(cfg)
        banner = format_stats_banner(cfg, btns)
        kb = build_button_matrix(btns)
        await q.message.reply_text(banner, parse_mode='HTML')
        await q.message.reply_text('\U0001f447 \u7b7e\u5230\u5b8c\u6210\uff01', reply_markup=kb)
        return

    if data.startswith('checkin:'):
        name = data.split(':', 1)[1]
        cfg = get_cfg()
        site = next((s for s in cfg['sites'] if s['name'] == name), None)
        if not site:
            await q.message.reply_text('\u7ad9\u70b9\u672a\u627e\u5230'); return
        if not ensure_auth(site):
            await q.message.reply_text(EMOJI_FAIL + ' ' + name + ': \u672a\u8ba4\u8bc1'); return
        ci = get_checkin(site)
        if ci.get('checked_in_today'):
            await q.message.reply_text(EMOJI_OK + ' ' + name + ': \u4eca\u65e5\u5df2\u7b7e'); return
        r = api_call(site, '/api/user/checkin', method='POST')
        if r and r.get('success'):
            amt = r.get('data', {}).get('amount', '?')
            await q.message.reply_text(EMOJI_OK + ' ' + name + ': +$' + str(amt))
        else:
            msg = (r.get('message', 'err')[:40] if r else 'err')
            await q.message.reply_text(EMOJI_FAIL + ' ' + name + ': ' + msg)
        return

    if data.startswith('site:'):
        name = data.split(':', 1)[1]
        detail = fmt_detail(name)
        await q.message.reply_text(detail, parse_mode='HTML')
        return


# ─────── Cron ───────

def cron_loop():
    logger.info('Cron scheduler started')
    while True:
        scheduled = load_schedule()
        if not scheduled or scheduled <= datetime.now():
            scheduled = pick_next_time()
            save_schedule(scheduled)
            logger.info('Next checkin: %s', scheduled.isoformat())
        sleep_secs = (scheduled - datetime.now()).total_seconds()
        if sleep_secs > 0:
            time.sleep(min(sleep_secs, 300))
            continue
        logger.info('Running scheduled checkin...')
        try:
            run_all()
        except Exception as e:
            logger.error('Scheduled checkin error: %s', e)
        next_t = pick_next_time()
        save_schedule(next_t)
        logger.info('Next checkin: %s', next_t.isoformat())


# ─────── Main ───────

def main():
    import threading
    t = threading.Thread(target=cron_loop, daemon=True)
    t.start()

    with open(TG_TOKEN_FILE) as f:
        token = f.read().strip()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler(['s','status'], cmd_status))
    app.add_handler(CommandHandler(['c','checkin'], cmd_checkin_all))
    app.add_handler(CommandHandler(['b','balance'], cmd_balance))
    app.add_handler(CommandHandler(['k','keys'], cmd_keys))
    app.add_handler(CommandHandler(['t','time'], cmd_time))
    app.add_handler(CommandHandler('log', cmd_log))
    app.add_handler(CommandHandler(['man','manual'], cmd_manual))
    app.add_handler(CommandHandler('settime', cmd_settime))
    app.add_handler(CallbackQueryHandler(button_cb))

    logger.info('Bot v9 starting...')
    app.run_polling()

if __name__ == '__main__':
    main()

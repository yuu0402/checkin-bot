# 🤖 公益站签到机器人

自动签到多个 NewAPI 公益站点的 Telegram Bot。

## 功能

- ✅ **自动签到** — 每天 8:00~20:00 随机时间自动签到
- 📊 **状态概览** — Telegram 内联按钮，一目了然
- 🔑 **API Key 管理** — 每个站点的 API Key 一键复制
- 🎲 **随机时间** — 避免固定时间被检测
- 📋 **模型列表** — 显示每个站点支持的模型
- 💰 **余额监控** — 实时查看各站点余额

## 命令

| 命令 | 说明 |
|------|------|
| `/s` | 站点状态 (按钮式) |
| `/c` | 全部签到 |
| `/b` | 余额汇总 |
| `/k` | API Key 列表 |
| `/t` | 下次签到时间 |
| `/man` | 手动选择站点签到 |
| `/log` | 最近日志 |

## 部署

### 环境要求
- Python 3.10+
- pip 依赖: `requests`, `python-telegram-bot`

### 安装

```bash
pip install requests python-telegram-bot
```

### 配置

编辑 `checkin_config.json`，格式:

```json
{
  "sites": [
    {
      "name": "站点名",
      "url": "https://example.com",
      "type": "new_api",
      "login": {"username": "xxx", "password": "xxx"},
      "api_key": "sk-xxxx"
    }
  ]
}
```

### 运行

```bash
python3 tg_bot.py
```

## 架构

- `tg_bot.py` — 主程序 (TG Bot + 自动签到循环)
- `cron_checkin.py` — 兼容 crontab 的外部调用入口
- `checkin_config.json` — 站点配置
- `tg_token.txt` — Telegram Bot Token

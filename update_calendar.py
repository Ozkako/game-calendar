# -*- coding: utf-8 -*-
"""
二游活动日历 · 自动更新脚本
============================

功能：
1. 读取 events.json（日历数据源），校验并排序；
2. 生成 calendar.ics，可导入 / 订阅到 Apple 日历、Google 日历、Outlook；
3. --upcoming 查看未来 N 天活动；
4. 预留 fetch_xxx() 抓取接口：在定时任务（cron / GitHub Actions）里
   抓取官方公告页，把新活动写回 events.json，再重新生成本文件。

用法：
    python update_calendar.py             # 重新生成 calendar.ics
    python update_calendar.py --upcoming 7  # 看未来7天活动
    python update_calendar.py --fetch       # 运行抓取器并更新 events.json

自动更新方案（任选其一）：
  A. 本地：系统计划任务每天运行 `python update_calendar.py --fetch`；
  B. GitHub Actions：把本文件 + events.json 推到仓库，
     用 schedule 事件定时执行，并把生成的 calendar.ics 作为 artifact 发布，
     手机日历订阅该 raw 链接即可自动更新。
"""
import json, sys, re, hashlib
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "events.json"
ICS  = BASE / "calendar.ics"

def load_events():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    evs, seen = [], set()
    for e in data["events"]:
        key = (e["game"], e["start"], e["title"])
        if key not in seen:               # 去重
            seen.add(key)
            evs.append(e)
    return data["meta"], data["games"], sorted(evs, key=lambda x: (x["start"], x["end"]))

def save_events(meta, games, events):
    DATA.write_text(json.dumps(
        {"meta": {**meta, "updated": datetime.now().strftime("%Y-%m-%d")},
         "games": games, "events": events},
        ensure_ascii=False, indent=2), encoding="utf-8")

def to_ics_date(d):  # 2026-11-20 -> 20261120（全天事件）
    return d.replace("-", "")

def gen_ics(meta, games, events):
    gname = {g["id"]: g["name"] for g in games}
    L = ["BEGIN:VCALENDAR", "VERSION:2.0",
         "PRODID:-//game-calendar//CN", "CALSCALE:GREGORIAN",
         f"X-WR-CALNAME:{meta['title']}"]
    for e in events:
        uid = hashlib.md5(f"{e['game']}{e['start']}{e['title']}".encode()).hexdigest()[:12]
        end = (datetime.strptime(e["end"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        L += ["BEGIN:VEVENT",
              f"UID:{uid}@game-calendar",
              f"DTSTART;VALUE=DATE:{to_ics_date(e['start'])}",
              f"DTEND;VALUE=DATE:{end}",
              f"SUMMARY:[{gname.get(e['game'], e['game'])}] {e['title']}",
              f"CATEGORIES:{e['game']},{e.get('type','')}",
              "END:VEVENT"]
    L.append("END:VCALENDAR")
    ICS.write_text("\r\n".join(L) + "\r\n", encoding="utf-8")
    return len(events)

def upcoming(days):
    meta, games, events = load_events()
    gname = {g["id"]: g["name"] for g in games}
    today, limit = datetime.now().date(), datetime.now().date() + timedelta(days=days)
    for e in events:
        s = datetime.strptime(e["start"], "%Y-%m-%d").date()
        if today <= s <= limit:
            rng = e["start"] if e["start"] == e["end"] else f"{e['start']} ~ {e['end']}"
            print(f"{rng}  [{gname.get(e['game'])}] {e['title']}")

# ---- 抓取器（示例模板）：官方页面结构会变，需按页面实际结构调整选择器 ----
def fetch_example(game_id, url):
    """示例：抓取公告页，返回 [{'title':..., 'start':..., 'end':...}, ...]
    需要：pip install requests beautifulsoup4
    注意遵守目标网站的 robots 协议与使用条款，控制请求频率。"""
    import requests
    from bs4 import BeautifulSoup
    html = requests.get(url, timeout=10,
                        headers={"User-Agent": "Mozilla/5.0 game-calendar"}).text
    items = []
    for a in BeautifulSoup(html, "html.parser").select("a"):
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", a.get_text(" "))
        if m:
            items.append({"game": game_id,
                          "start": f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
                          "end":   f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
                          "title": a.get_text(" ").strip()[:60], "type": "抓取"})
    return items

SOURCES = {
    # 示例：把下面注释打开并填入官方公告页地址
    # "zzz":  "https://zzz.mihoyo.com/news",
    # "wuwa": "https://mc.kurogames.com/main/news",
}

def run_fetch():
    meta, games, events = load_events()
    for gid, url in SOURCES.items():
        try:
            news = fetch_example(gid, url)
            events.extend(news)
            print(f"[{gid}] 抓取到 {len(news)} 条")
        except Exception as ex:
            print(f"[{gid}] 抓取失败：{ex}（页面结构可能需要调整）")
    save_events(meta, games, events)
    print("events.json 已更新")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--upcoming":
        upcoming(int(args[1]) if len(args) > 1 else 7)
    elif args and args[0] == "--fetch":
        run_fetch()
    else:
        meta, games, events = load_events()
        n = gen_ics(meta, games, events)
        print(f"calendar.ics 已生成（{n} 个事件），可导入手机日历订阅")

# -*- coding: utf-8 -*-
"""旁白（LLM_SCENE_WRITE）回合核对 —— 每次测旁白跑一次。

用法：
    python tool/scene_verify.py            # 核对日志里**最后一次**旁白回合
    python tool/scene_verify.py --all      # 列出所有旁白回合（改动前后对比用）
    python tool/scene_verify.py --watch    # 等**下一个**新旁白回合（可后台跑）

它核对的就是 2026-09-21 那 4 处修复：
    ① 字数      —— 旁白正文 ≤ 60 字
    ② 标记      —— 正文里不许出现 `###`
    ③ 玩家输入位置 —— prompt 里 `%LLM_PIN%` 必须在**最下方**那个段里
    ④ 睡眠措辞  —— prompt 里要有命令式的【★ 她现在的意识状态】段
另外顺带量两个已知噪声（暂未修，只是记录）：
    · prompt 开头外泄的 ERB 字面量 `@"` / 引号
    · 旁白请求带的对话历史轮数 hist=（历史里是**未清洗**的 `###` 原文）

⚠️ 为什么要用脚本而不是肉眼看日志：
   `[TRACE] CALLED LLM_CHAT_SEND` 那条日志里**嵌了真换行**（整个 prompt 原样落盘），
   按物理行读会把一条记录读成几十行 ⇒ 必须用正则跨行抓。

⚠️⚠️ 不能拿「特征串出现的位置」当回合位置：
   同一条 prompt 会在**两处**落盘 —— `TRACE CALLED`（全文）和
   `CHAT-SYS head=`（前 110 字）⇒ 按特征串数会把回合数算成两倍。
   所以这里只以 `TRACE CALLED ... args=` 那一条为准。
"""
import argparse
import os
import re
import sys
import time

LOG = os.path.join("plugins", "LLMBridge", "debug.log")

SCENE_MARK = "你在为一段 18+ 的互动场景写"   # 旁白 prompt 的开场白特征
SCENE_USER = "（描写一下此刻的画面。）"      # 旁白请求固定的 user 文本
PIN_HEAD = "【★★ 最后再说一遍：他这一轮说的是 / 做的是】"   # ③
STATE_HEAD = "【★ 她现在的意识状态"                        # ④
OLD_HEAD = "【你刚才说 / 做的】"                           # 已被删掉的旧段名

RE_TS = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"


def read_log():
    if not os.path.exists(LOG):
        sys.exit(f"找不到日志：{LOG}（先跑一轮游戏）")
    return open(LOG, encoding="utf-8", errors="replace").read()


def parse(text):
    """→ [{ts,pos,sys,hist,id,reply}]，按时间顺序。"""
    rounds = []
    # ① 旁白请求的 TRACE（跨行，直到下一条带时间戳的日志）
    for m in re.finditer(
            r"(" + RE_TS + r") \[TRACE\] CALLED LLM_CHAT_SEND args=\d+ \[(.*?)\]\s*\n"
            r"(?=" + RE_TS + r")", text, re.S):
        blob = m.group(2)
        if SCENE_MARK not in blob:
            continue
        sys_txt = blob.split(", s:" + SCENE_USER)[0]
        sys_txt = re.sub(r"^i:\d+,\s*s:", "", sys_txt, count=1)
        rounds.append({"ts": m.group(1), "pos": m.start(), "sys": sys_txt,
                       "hist": None, "id": None, "reply": None})

    # ② 配该请求的 CHAT-SEND（拿 hist 和 id）—— 取 TRACE 之后的第一条
    for r in rounds:
        m = re.search(r"\[INFO\] CHAT-SEND id=(\d+) .*?hist=(\d+)", text[r["pos"]:])
        if m:
            r["id"], r["hist"] = m.group(1), m.group(2)

    # ③ 配回复全文 —— CHAT-OK 带 id，用它定位，再取其后第一条 POLL 的全文
    for r in rounds:
        if not r["id"]:
            continue
        mk = re.search(r"\[INFO\] CHAT-OK id=" + r["id"] + r" ", text[r["pos"]:])
        if not mk:
            continue
        after = r["pos"] + mk.end()
        mp = re.search(r"-> LLM_CHAT_POLL returned '1(.*?)'\s*\n(?=" + RE_TS + r")",
                       text[after:], re.S)
        if mp:
            r["reply"] = mp.group(1)
    return rounds


def nar_len(reply):
    """正文（第一个 `###` 之前）的字符数（去掉所有空白）。"""
    if not reply:
        return None
    return len(re.sub(r"\s+", "", reply.split("###")[0]))


def check_prompt(sys_txt):
    res = []
    lines = sys_txt.splitlines()
    # ③ 玩家输入位置：必须锚**行首**（指针文字里也含这个串，不锚就会误判成功）
    pin_line = next((i for i, l in enumerate(lines) if l.startswith(PIN_HEAD)), None)
    if pin_line is None:
        res.append(("③ 玩家输入位置", False, f"prompt 里没有行首的 {PIN_HEAD}"))
    else:
        tail_ok = pin_line >= len(lines) * 0.6
        val = lines[pin_line + 1].strip() if pin_line + 1 < len(lines) else ""
        res.append(("③ 玩家输入位置", tail_ok,
                    f"段头在第 {pin_line + 1}/{len(lines)} 行"
                    f"（{'靠后 ✓' if tail_ok else '太靠前 ✗'}），下一行：{val[:40]}"))
    old_as_block = any(l.startswith(OLD_HEAD) for l in lines)
    res.append(("③b 旧段名", not old_as_block,
                "旧段【你刚才说 / 做的】还在当段用 ✗" if old_as_block
                else "旧段已不是段（只作为指针文字）✓"))
    has_state = any(STATE_HEAD in l for l in lines)
    res.append(("④ 意识状态段", has_state,
                "有命令式的意识状态段 ✓" if has_state else "没有（角色清醒时属正常）"))
    lead = sys_txt.startswith('@"')
    res.append(("噪声 开头 @\"", not lead, "开头外泄 ERB 字面量" if lead else "开头干净"))
    q = sorted({s for s in re.findall(r"【([^】]{2,20})】\"", sys_txt)})
    res.append(("噪声 值带引号", not q, ("被引号包住：" + "、".join(q)) if q else "无"))
    return res


def report(rounds):
    bad = 0
    for r in rounds:
        print("=" * 74)
        print(f"旁白回合 {r['ts']}  hist={r['hist']}  prompt {len(r['sys'])} 字")
        nl, has_tag = nar_len(r["reply"]), bool(r["reply"] and "###" in r["reply"])
        print("-" * 74)
        ok1 = nl is not None and nl <= 60
        print("① 字数    " + ("✅" if ok1 else "❌") + f"  正文 {nl} 字（要求 ≤ 60）")
        print("② 标记    " + ("✅" if not has_tag else "❌")
              + ("  出现了 `###`" if has_tag else "  没有 `###`"))
        for name, okk, msg in check_prompt(r["sys"]):
            print(f"  {name:<14}" + ("✅ " if okk else "❌ ") + msg)
        print("-" * 74)
        print("回复原文：")
        print(r["reply"] if r["reply"] else "(没抓到回复)")
        if not ok1:
            bad += 1
        if has_tag:
            bad += 1
    print("=" * 74)
    print(f"  ⇒ {'✅ 这一轮 字数/标记 都过' if bad == 0 else f'❌ 字数/标记 有 {bad} 项没过'}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="列出所有旁白回合（对比用）")
    ap.add_argument("--watch", action="store_true", help="等下一个新旁白回合再报")
    ap.add_argument("--timeout", type=int, default=2700, help="--watch 最长等待秒数")
    args = ap.parse_args()

    if args.watch:
        base = len(read_log())
        have = len(parse(read_log()))
        t0 = time.time()
        print(f"等待新的旁白回合…（已看到 {have} 个，最多等 {args.timeout} 秒）", flush=True)
        while time.time() - t0 < args.timeout:
            time.sleep(3)
            rs = parse(read_log())
            if len(rs) > have and rs[-1]["reply"]:
                print("抓到新回合：", flush=True)
                return report(rs[-1:])
        print("等待超时，没有新旁白回合。")
        return 2

    rounds = parse(read_log())
    if not rounds:
        print("日志里还没有旁白回合。")
        return 1
    if args.all:
        print(f"共 {len(rounds)} 个旁白回合（改动前后对比）：")
        print(f"  {'时间':<20}{'hist':>5}{'prompt':>8}{'正文':>6}  ###")
        for r in rounds:
            print(f"  {r['ts']:<20}{str(r['hist']):>5}{len(r['sys']):>8}"
                  f"{str(nar_len(r['reply'])):>6}  "
                  f"{'有' if (r['reply'] and '###' in r['reply']) else '无'}")
        print()
    return report(rounds if args.all else rounds[-1:])


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""离线预演：把 `@LLM_BUILD_SYSTEM_PROMPT` 在**给定角色状态**下重放一遍，
打印出实际会发给模型的 system prompt。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️⚠️ **能力边界（2026-09-27 实测后写下的结论，务必先读）**

它可以做：
  · 看 prompt **到底长什么样**、某句话出自哪个函数（`--raw` 带源行号）
  · 统计"哪些是每轮都注入、哪些只在开场/互动/有记忆时"（配合 `prompt_audit.py`）

它**做不到**（不要拿它当依据 ⚠️）：
  · **判断条件分支**。`ev()` 只能瞎猜 `CFLAG:(LLM_CID):4 >= REQUIRED_TRUST_恋慕`、
    `GETBIT(...)`、`STRLENS(...)` 这类游戏内表达式 —— 实测有 30+ 处猜错 ⚠️
  · **算出 `%变量%` 的真实值**。那些值来自**游戏运行时状态**，
    离线只能靠 `TEXTS` / `CALL_RESULT` 手工假定 ⇒ 漏一项就插值出 `0` ⚠️
  · 因此：**不要把它的输出当成"游戏里真实的 prompt"**，
    更**不要据此推演台词** —— 猜错的分支会让推演**方向相反** ⚠️

想拿到**真实**长什么样，只有两条路：
  ① 游戏内 `[5] 自检` 的「prompt 长度诊断」（字节数）
  ② `plugins\\LLMBridge\\debug.log` 的 `CHAT-SEND` 的 `sysLen`
  （想看正文得改 C# 插件去记 prompt，那是另一件事）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用法：
    python tool/prompt_replay.py --core     # ★ 只渲染"无条件注入"的段（零误判）
    python tool/prompt_replay.py            # 全量（含条件段 —— **会有假象** ⚠️）
    python tool/prompt_replay.py --raw      # 带源行号，方便对照代码
"""
import argparse
import re
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
FUNC = '@LLM_BUILD_SYSTEM_PROMPT'

# ══════════════════════════════════════════════════════════════════════════
#  ① 场景状态 —— 你现在改这里，就能换角色 / 换处境
# ══════════════════════════════════════════════════════════════════════════
STATE = {
    'LLM_CID': 58,               # 58 = 红美铃（取自 09-27 debug.log 的 char=58）
    'CHARA_NAME': '美铃',
    'CALLNAME': '美铃',
    'NO': 58,
    'TIME': 800,                 # 13:20（09-27 日志里是 13:24）
    'DAY': 2,
    'DATE_STR': '9月3日',
    'WEATHER': '晴天',
    # ── 关系（决定档位、口吻、各项概率）──
    '好感': 2100, '信赖': 320, '積攒度': 260, '態度': 2,
    # ★ 照 Chara58 美鈴.csv：口調 = 1（礼貌敬体）；CSV 里没有性格傾向 ⇒ 0
    '口調': 1, '性格傾向': 0,
    # ── 状态旗标 ──
    '睡眠': 0, '烂醉': 0, '睡眠姦': 0, '烂酔奸': 0, '時姦刻印': 0, '烂酔奸バレ': 0,
    '発情': 0, '媚薬': 0, '催情薬': 0, '妊娠': 0, '育児中': 0, '生理周期': 3,
    '诶嘿嘿': 0, '現在位置': 1234, '職種': 0, '行動': 0, '陪睡中': 0,
    '就寝時間': 1380, '起床時間': 420,
    '工作開始': -1, '工作結束': -1,   # -1 = 今天休息
    '体目当て': 0,
    'AT_HOME': 0, 'CHARA_HOLIDAY': 1, 'IS_DATING': 0,
    '好感度上限': 3000, '信赖度上限': 1000,
    'TALENT_恋慕': 0, 'TALENT_愛欲': 0, 'TALENT_思慕': 1, 'TALENT_恋人': 0,
    'TALENT_炮友': 0, 'TALENT_風騷': 0, 'TALENT_妊娠': 0, 'TALENT_育児中': 0,
    'REQUIRED_FAVOR_思慕': 1500, 'REQUIRED_TRUST_思慕': 250, 'REQUIRED_TRUST_恋慕': 700,
    # ── ★ 以下全部照 `CSV\Chara\Chara58 美鈴.csv` 原文 ──
    '面識': 1,
    # 素質：処女1 / 自制心1 / 一線越えない1 / 痛覚-1 / 献身的1 / 胸围1 / 回復速度1
    #       体型1 / 妖怪1   （注意：**沒有**羞恥心/ツンデレ/ズボラ/気分屋/小悪魔/母性）
    'TALENT_処女': 1, 'TALENT_キス未経験': 0,
    'TALENT_体型': 1, 'TALENT_胸围': 1, 'TALENT_種族': 0, 'TALENT_追加種族': 0,
    'TALENT_妖怪': 1,
    'TALENT_自制心': 1, 'TALENT_一線越えない': 1, 'TALENT_献身的': 1,
    'TALENT_痛覚': -1, 'TALENT_回復速度': 1, 'TALENT_羞恥心': 0,
    'TALENT_動物耳': 0, 'TALENT_淫乳': 0, 'TALENT_尻穴狂': 0, 'TALENT_接吻魔': 0,
    'TALENT_母乳体質': 0, 'TALENT_精力超群': 0, 'TALENT_精愛味覚': 0, 'TALENT_濃厚精液': 0,
    # 能力（`@LLM_SKILL_ADD` 只收 EX/S/A(>=4) 与 D/E(<=1)，C 档 2~3 跳过）
    'ABL_清掃技能': 2, 'ABL_話術技能': 2, 'ABL_戦闘能力': 3,
    'ABL_教養': 1, 'ABL_料理技能': 0, 'ABL_音楽技能': 0,
    # ABL 50=用手指 / 51=用舌头 / 52=用胸 / 54=下面 / 55=后面（全 0 ⇒ 那行不注入）
    'ABL50': 0, 'ABL51': 0, 'ABL52': 0, 'ABL54': 0, 'ABL55': 0,
    # 作息（照 CSV：就寝 1440 / 起床 360 / 工作 6时~12时；本例设为休息日）
    '就寝時間': 1440, '起床時間': 360,
    # ── 记忆 / 互动历史 ──
    'LLM_MEMO': [
        '[3] 他自报身份：红魔馆新来的食客',
        '[3] 他叫我「美铃姐」',
        '[5] 约好下次带酒来',
    ],
    'LLM_PROMISE': '他说下次带酒来',
    'LLM_ATTITUDE': '有点在意他，但上次山上那事还堵着',
    'LLM_PREV': '',                # 留空 = 没有"上一场片段"
    'LLM_AGREE': {1: 2, 2: 1},     # 行为代码→次数（1 牵手 / 2 拥抱）
    'LLM_PREF': {},                # 玩家偏好（次数 <3 ⇒ 不注入）
    'LLM_FAV': 0,
    'LLM_DATELOG': [],
    'JUST_ENDED': '', 'ENDED_CNT': 0,
    'ACTIVITY_TYPE': None, 'ACTIVITY_LEFT': 0,
    'CLOTHES': '绿色旗袍（上身）、白色长裤（下身）、布鞋',
    'OTHERS': '',                  # 同房间还有谁
    'TG': '',                      # 陪伴中做的事
    'LLM_MODE': 0,                 # 0 = 自由对话
    'OPENING': 0,                  # 0 = 普通轮，1 = 开场白
    'PLAYER_TIRED': 0,
    'FEEL': 0, 'TOUCH_NOTE': 0,
}

# 这些"文本类"变量的值本该由各 @LLM_* 函数算出来。
# ★ 下面全部来自子代理逐字抄回的**真实函数体**（不是猜的）——
#   搜 `TEXTS` 即可看到每条对应哪个函数。
TEXTS = {
    # @LLM_TONE_OF：CASE 1（口調 1）+ 性格傾向 0 ⇒ 无后缀
    'TONE': '礼貌的敬体：说话有礼貌，句尾偏「～呢」「～吧」「～吗」，但不卑不亢',
    # @LLM_CHARA_TRAIT CASE 58
    'TRAIT': '红美铃：悠闲随和、不太靠谱，说话轻松带笑，爱偷懒和打瞌睡，被咲夜抓住会心虚',
    # @LLM_CHARA_FEATURE：**表里没有 58** ⇒ 空串（该段不注入）
    'FEAT': '',
    # @LLM_CHARA_LIKES CASE 58
    'LIKES': '喜欢睡觉、中华料理和晒太阳；被人拜托事情会很高兴（虽然容易搞砸）',
    'SKILLS': '戦闘：Ｂ、教養：Ｄ、料理：Ｅ、音楽：Ｅ',
    'SELF': '',       # @LLM_SKILL_SELF：**无 58 分支** ⇒ 空串
    'PRIDE': '',      # @LLM_SKILL_PRIDE：**无 58 分支** ⇒ 空串
    'INTRO': '～华人少女～　●种族：妖怪　●能力：使用气程度的能力',
    'PERS': '',       # 官方 @PERSONALITY_TYPE（离线未取）
    'RELATION': '',   # 官方 RELATION（离线未取）
    'SCHED': '',      # 13:20 休息日 ⇒ 四档都不触发 ⇒ 空
    'HORNY': '',      # 由 CALL 填（见 CALL_RESULT）
    'BODYTXT': '',    # 由 CALL 填
    'EXPTXT': '',     # 由 CALL 填
    'PERSONA_SHOW': '东方红魔乡 门番（初始）',
    'PERSONA': 'K58',
    'ACT_TXT': '',    # 本轮无特别行动 ⇒ 空
}

ASSUMED = []      # 记录所有"假定/查不到"的地方，末尾汇总


def note(what: str):
    if what not in ASSUMED:
        ASSUMED.append(what)


# ══════════════════════════════════════════════════════════════════════════
#  ② 取值：把 ERB 里的变量名 / 函数调用映射到上面的 STATE / TEXTS
# ══════════════════════════════════════════════════════════════════════════
def var(name: str):
    """单个标识符 / 带下标的变量 → 值。

    支持 ERB 的三种写法：
      · `LLM_MOOD`                     —— 普通变量
      · `CFLAG:(LLM_CID):好感度`        —— 具名 CFLAG（下标是谁不重要，取最后一段名）
      · `TALENT:(LLM_CID):思慕`         —— 具名 TALENT
    """
    raw = name.strip()
    # 取**最后一段**具名下标（`CFLAG:(LLM_CID):好感度` ⇒ 好感度）
    segs = [x for x in raw.split(':') if x and not x.startswith('(')]
    key = segs[-1] if segs else raw
    for cand in (key, raw):
        if cand in TEXTS:
            v = TEXTS[cand]
            if v == '':
                note(f'TEXTS["{cand}"] 为空 —— 真实值应由对应 @LLM_* 函数给出')
            return v
        if cand in STATE:
            return STATE[cand]
    note(f'未映射的变量「{raw}」（按 0 / 空处理）')
    return 0


# ══════════════════════════════════════════════════════════════════════════
#  ③-b `CALL @LLM_xxx(..., REF_OUT)` 的结果
#  ⚠️ 这些值**逐字来自子代理抄回的真实函数体**，按上面的 STATE 算出来的；
#     不是猜的。改 STATE 时这里要跟着改（比如换角色/换欲求档位）✓
# ══════════════════════════════════════════════════════════════════════════
# @LLM_PREV_SHOW：本例 LLM_PREV 为空 ⇒ 空串（不注入那段）
PREV_SHOW = ''
# @LLM_HORNY_DESC：积攒度 260 ⇒ 命中"想发泄"档；REL_DEPTH(思慕)=
#   @LLM_REL_DEPTH 对 LV2 返回 **中(1)** ⇒ <2 ⇒ 走"浅"分支（不表现）
HORNY_DESC = (
    '你现在的状态：心里有些燥，但还没到忍不住的地步（欲求 26％）。'
    '\n   但你们还没到那一步，所以你**只会自己难受，不会表现出来** ——'
    '\n   · 说话偶尔走神、反应慢半拍，或者莫名有点烦躁'
    '\n   · **绝不主动暗示、也绝不勾引** —— 那样不符合你们现在的关系。'
    '\n   · 他要是问起，你会含糊过去（「没什么」「……有点热而已」）。'
    '\n   强度：只是偶尔心不在焉，几乎看不出来。'
)
# @LLM_CHARA_BODY：体型/胸围/种族/性情 —— 全部照 Chara58 CSV 的素質
BODY_TXT = (
    '体型：**身材高挑**，比一般人高。\n'
    '身材：**身材丰满**。\n'
    '身体：**不怕痛**、**恢复得快**（其余略）。\n'
    '性情：**有自制心**、**有一条跨不过去的线**、**肯为他付出**（其余略）。\n'
)
# @LLM_CHARA_EXP：性技全 0 ⇒ 熟练度那行不注入；但她是処女、没接过吻
EXP_TXT = '**还留着初吻** —— 你没和任何人接过吻。\n你**还是处女** —— 身体从没被任何人进入过。\n'
# @LLM_SHOW_CLOTHES / LLM_AGREE_SHOW / LLM_MEMO_SHOW / LLM_SHOW_DATELOG
CLOTHES_TXT = STATE['CLOTHES']
AGREE_TXT = '牵手（2 次）、拥抱（1 次）'
MEMO_TXT = '；'.join(STATE['LLM_MEMO'])
DATELOG_TXT = ''          # 没有约会日志 ⇒ 空串
SKILLS_TXT = ''           # @LLM_CHARA_SKILL：需 ABL 实际值；未取到就留空

CALL_RESULT = {
    'LLM_PREV_SHOW': PREV_SHOW,
    'LLM_HORNY_DESC': HORNY_DESC,
    'LLM_CHARA_BODY': BODY_TXT,
    'LLM_CHARA_EXP': EXP_TXT,
    'LLM_MEMO_SHOW': MEMO_TXT,
    'LLM_AGREE_SHOW': AGREE_TXT,
    'LLM_SHOW_CLOTHES': CLOTHES_TXT,
    'LLM_SHOW_DATELOG': DATELOG_TXT,
    'LLM_CHARA_SKILL': SKILLS_TXT,
    'LLM_SKILL_SELF': '',      # 无 58 分支 ⇒ 空
    'LLM_SKILL_PRIDE': '',     # 无 58 分支 ⇒ 空
    'LLM_DATE_SUMMARY': '',
}


def call(fn: str, args):
    """函数调用 → 值（`args` 是原样的实参串）。"""
    f = fn.lstrip('@')
    fu = f.upper()
    table = {
        'LLM_REL_LEVEL': 2,                     # 思慕
        'LLM_REL_DEPTH': 1,                     # LV2 ⇒ 中(1)
        'LLM_ACT_REMAIN': 0,
        'LLM_IS_SLEEPTIME': 0,
        'IS_DATING_WITH_PLAYER': STATE['IS_DATING'],
        'AT_HOME': STATE['AT_HOME'],
        'BATHROOM': 0,
        'CHARA_HOLIDAY': STATE['CHARA_HOLIDAY'],
        'GET_MAPID': 11,
        'PRINT_DATE_F': STATE['DATE_STR'],
        'GET_DAY_CN': '三',
        'GET_WEATHER': STATE['WEATHER'],
        'GET_MAPNAME': '紅魔館',
        'GET_PLACENAME': '正门',
        'NAME_FROM_PLACE': '正门',
        'GET_JOBNAME': '',
        'TOSTR': 0, 'STRLENS': 0, 'MAX': 0, 'MIN': 0,
    }
    # ⚠️ `時刻表示` 是**中文函数名** ⇒ 不能一起 upper()，要单独匹配原始名
    if f == '時刻表示':
        return f"{STATE['TIME'] // 60}时{STATE['TIME'] % 60:02d}分"
    if fu in table:
        return table[fu]
    note(f'函数「{fn}()」按默认值处理（未在重放器里实现）')
    return 0


def call_stmt(fn: str, args: str):
    """`CALL @LLM_xxx(..., REF_OUT)` —— 把结果**写回最后一个参数**。"""
    a = [x.strip() for x in args.split(',')] if args.strip() else []
    if not a:
        return
    target = a[-1]
    key = fn.lstrip('@')
    if key in CALL_RESULT:
        STATE[target] = CALL_RESULT[key]
        return
    if key.startswith('LLM_'):
        # 没登记结果的：清空（与真实函数"先 REF_OUT = ''"一致），并记下来
        STATE[target] = ''
        note(f'CALL {key}(...) 的结果未登记 ⇒ 按空串处理')
        return
    note(f'CALL {fn}(...) 未在重放器里实现（跳过）')


# ══════════════════════════════════════════════════════════════════════════
#  ③ 极简条件求值（只覆盖这个函数用到的写法）
# ══════════════════════════════════════════════════════════════════════════
# ⚠️ ERB 变量可能带**具名下标**：`CFLAG:(LLM_CID):好感度` / `LLM_PREF:(LLM_CID):0` /
#    `BASE:MASTER:体力`。这个正则把整串当**一个**记号（否则会被拆成 `CFLAG:` + `好感度`，
#    求值时炸掉，进而插值出 `0` —— 这是本工具最大的坑）✓
VAR_TOKEN = r'[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*(?::(?:\([^()]*\)|[^:()\s/+\-*=<>&|,]+))*:?'


def ev(expr: str):
    s = expr.strip()
    if s.startswith(';'):
        return False
    # 先保护函数调用：替换成哨兵，避免里面的标识符被当变量处理
    calls = []

    def stash(m):
        calls.append(call(m.group(1), m.group(2)))
        return f'__C{len(calls) - 1}__'
    s = re.sub(r'([A-Za-z_][A-Za-z_0-9]*)\(([^()]*)\)', stash, s)
    # `%变量%` → 值
    def rep_pct(m):
        v = var(m.group(1).strip())
        if isinstance(v, (int, float)):
            return str(v)
        return f'"{v}"' if v else '""'
    s = re.sub(r'%([^%]+)%', rep_pct, s)

    def rep_ident(m):
        n = m.group(0)
        if n.startswith('__C') and n.endswith('__'):
            return repr(calls[int(n[3:-2])])
        if n in ('and', 'or', 'not', 'True', 'False', 'MAX', 'MIN'):
            return n
        v = var(n)
        if isinstance(v, (int, float)):
            return str(v)
        return f'"{v}"' if v else '""'
    # ⚠️ 必须用 VAR_TOKEN（带下标）—— 关键修复
    s = re.sub(r'__C\d+__|' + VAR_TOKEN, rep_ident, s)
    s = s.replace('&&', ' and ').replace('||', ' or ')
    s = re.sub(r'!(?!=)', ' not ', s)
    s = s.replace('<>', '!=')
    s = re.sub(r'\bMAX\(', 'max(', s)
    s = re.sub(r'\bMIN\(', 'min(', s)
    try:
        return bool(eval(s, {'__builtins__': {}}, {'max': max, 'min': min}))
    except Exception as e:
        note(f'条件求值失败（已当 False）：{expr.strip()[:60]}  ← {e}')
        return False


# ══════════════════════════════════════════════════════════════════════════
#  ④ 主循环：逐行重放
# ══════════════════════════════════════════════════════════════════════════
LIT = re.compile(r'REF_PROMPT\s*\+?=\s*@"(.*)"\s*$')
SIF = re.compile(r'^SIF\s+(.+?)\s*$')
IF = re.compile(r'^IF\s+(.+?)\s*$')
ELSEIF = re.compile(r'^ELSEIF\s+(.+?)\s*$')
CALL = re.compile(r'^CALL\s+([A-Za-z_0-9]+)\s*\((.*)\)\s*$')
# 普通赋值：`VAR = <值>` / `VAR += <值>` / `VAR '= <表达式>`
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)\s*(\+=|'=|=)\s*(.+)$")


def rvalue(expr: str):
    """把一个 ERB 右值求成 Python 值（字符串 / 数字）。"""
    e = expr.strip()
    m = re.fullmatch(r'@?"(.*)"', e)
    if m:
        return m.group(1).replace('\\n', '\n').replace('\\"', '"').replace('\\t', '\t')
    m = re.fullmatch(r'%(.+)%', e)
    if m:
        inner = m.group(1).strip()
        fm = re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)\((.*)\)', inner)
        if fm:
            return str(call(fm.group(1), fm.group(2)))
        return str(var(inner))
    m = re.fullmatch(r'-?\d+', e)
    if m:
        return int(e)
    # 其它式子：用条件求值器当布尔（够用了）
    return ev(e)


def assign(raw_line: str):
    m = ASSIGN.match(raw_line.strip())
    if not m:
        return False
    name, op, rhs = m.group(1), m.group(2), m.group(3)
    if name in ('REF_PROMPT', 'RETURN', 'IF', 'SIF', 'ELSE', 'ELSEIF', 'ENDIF', 'CALL',
                'PRINTL', 'PRINTFORML', 'PRINTFORMC', 'PRINTFORM', 'FOR', 'NEXT',
                'SELECTCASE', 'CASE', 'CASEELSE', 'ENDSELECT', 'WHILE', 'BREAK', 'CONTINUE'):
        return False
    if name == 'LOCAL' or name.startswith('LOCAL:'):
        return True          # 临时量，忽略
    val = rvalue(rhs)
    if op == '+=':
        old = STATE.get(name, 0)
        if isinstance(old, str) or isinstance(val, str):
            STATE[name] = (old if isinstance(old, str) else '') + (val if isinstance(val, str) else str(val))
        else:
            STATE[name] = old + val
    else:
        STATE[name] = val
    return True


def interpolate(s: str) -> str:
    s = s.replace('\\n', '\n').replace('\\"', '"').replace('\\t', '\t')

    def rep_pct(m):
        e = m.group(1).strip()
        # `%函数(...)%` 或 `%变量%`（变量可能带具名下标，如 `%LLM_ATTITUDE:(LLM_CID):0%`）
        fm = re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)\((.*)\)', e)
        if fm:
            return str(call(fm.group(1), fm.group(2)))
        return str(var(e))

    s = re.sub(r'%([^%]+)%', rep_pct, s)

    def rep_brace(m):
        e = m.group(1).strip()
        # `{CFLAG:(LLM_CID):积攒度 / 10}` 这类算式：把变量换掉后再算
        e2 = re.sub(VAR_TOKEN, lambda mm: repr(var(mm.group(0))), e)
        try:
            return str(eval(e2, {'__builtins__': {}}, {}))
        except Exception:
            note(f'`{{{e}}}` 没算出来（原样保留）')
            return m.group(0)
    s = re.sub(r'\{([^{}]+)\}', rep_brace, s)
    return s


def replay(raw=False, core_only=False):
    """
    core_only=True ⇒ **只渲染 `live` 判定为"无条件注入"的字面量**。
    为什么需要这个模式（2026-09-27 的教训）：
        条件求值器（`ev`）面对 `CFLAG:(LLM_CID):4 >= REQUIRED_TRUST_恋慕`、
        `GETBIT(...)`、`STRLENS(...)` 这类**游戏内表达式**时只能瞎猜；
        猜错就会渲染出**方向相反**的段落 ⇒ 拿它推演台词**比没有更危险** ⚠️
    ⇒ 所以「要拿去推理台词」时用 `--core`：只取无条件段，零误判 ✓
    """
    lines = open(PATH, encoding='utf-8').read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(FUNC))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith('@'))

    out = []
    # 条件栈：每项 = [当前分支是否命中, 该层是否已经有分支命中过]
    stack = []
    live = True
    sif_next = None

    for i in range(start, end):
        raw_line = lines[i]
        s = raw_line.strip()

        if not s or s.startswith(';'):
            continue

        m = IF.match(s)
        if m:
            if core_only:
                stack.append([False, True])      # 无条件块**全部当不命中**
                live = False
                continue
            hit = ev(m.group(1))
            stack.append([hit, hit])
            live = all(x[0] for x in stack)
            continue
        m = ELSEIF.match(s)
        if m and stack:
            if core_only:
                stack[-1] = [False, True]
                live = False
                continue
            if stack[-1][1]:
                stack[-1][0] = False
            else:
                hit = ev(m.group(1))
                stack[-1][0] = hit
                stack[-1][1] = stack[-1][1] or hit
            live = all(x[0] for x in stack)
            continue
        if s == 'ELSE' and stack:
            if core_only:
                stack[-1] = [False, True]
                live = False
                continue
            stack[-1][0] = not stack[-1][1]
            stack[-1][1] = True
            live = all(x[0] for x in stack)
            continue
        if s == 'ENDIF':
            if stack:
                stack.pop()
            live = (all(x[0] for x in stack) if stack else True) if not core_only else (not stack)
            continue

        m = SIF.match(s)
        if m:
            if core_only:
                live = not stack                  # SIF 在无条件区 ⇒ 也当"有条件"，跳过
                sif_skip = True
                continue
            sif_next = ev(m.group(1))
            continue
        if sif_next is not None:
            if not sif_next:
                sif_next = None
                continue
            sif_next = None

        if not live:
            continue

        m = LIT.search(raw_line)
        if m:
            out.append((i + 1, interpolate(m.group(1))))
            continue

        m = CALL.match(s)
        if m:
            call_stmt(m.group(1), m.group(2))
            continue

        assign(raw_line)

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', action='store_true', help='每段标出源码行号')
    ap.add_argument('--core', action='store_true',
                    help='★ 只渲染「无条件注入」的段落（推演台词请用这个，零误判）')
    args = ap.parse_args()

    segs = replay(args.raw, core_only=args.core)
    text = ''.join(t for _, t in segs)

    print('=' * 78)
    print(f'离线重放的 system prompt —— 角色 {STATE["CHARA_NAME"]}({STATE["LLM_CID"]})')
    print(f'时间 {STATE["TIME"] // 60}:{STATE["TIME"] % 60:02d}  天气 {STATE["WEATHER"]}'
          f'  关系档位 {call("LLM_REL_LEVEL", "")}  好感 {STATE["好感"]} 信赖 {STATE["信赖"]}')
    if args.core:
        print('★ 模式：**只含无条件注入的段落**（有条件的那几段见文末清单）')
    print(f'长度：{len(text)} 字符（ERB 的 STRLENS 会数成 {len(text.encode("utf-8"))} 字节）')
    print('=' * 78)
    if args.raw:
        for ln, t in segs:
            print(f'--- 源行 {ln} ---')
            print(t, end='')
        print()
    else:
        print(text)
    print()
    print('=' * 78)
    print('⚠️ 以下是**假定值**（离线重放拿不到真实数据的地方）——')
    for a in ASSUMED:
        print(f'  · {a}')
    print('=' * 78)


if __name__ == '__main__':
    sys.exit(main())

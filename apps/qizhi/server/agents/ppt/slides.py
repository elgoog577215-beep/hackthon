"""从【教案】（Markdown 文本）生成可上课的 PPT。

改编自 video-analyze 的 slides_steps：保留两段式生成（大纲 + 并发填充）、结构化 schema、
以及自包含 HTML 渲染；但输入从「视频字幕 + 知识树 + 时间轴」改为「教案正文 + 用户要求」，
不再依赖任何时间信息。产物：
    deck(dict)   —— 结构化讲稿（HTML 与 pptx 共用同一份数据）
    slides.html  —— 自包含、可键盘翻页、可投影、可打印成 PDF 的 HTML PPT
    slides.pptx  —— 由 pptx_render.build_pptx 用 python-pptx 生成（无需 Node）
"""
from __future__ import annotations

import re
from typing import List, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 结构化输出 schema（与 video-analyze 保持一致，字段用 ASCII）
# ---------------------------------------------------------------------------

SlideLayout = Literal["cover", "agenda", "section", "content", "qa", "summary"]


class SlidePlan(BaseModel):
    layout: SlideLayout = Field(description="页型：cover封面/agenda提纲/section章节分隔/content内容/qa课堂思考/summary小结")
    title: str = Field(description="该页标题，精炼，≤20字")
    subtitle: str = Field(default="", description="副标题/一句话导语，可空")


class DeckPlan(BaseModel):
    title: str = Field(description="整套 PPT 的标题（通常即本节课主题）")
    subtitle: str = Field(default="", description="副标题，可空")
    slides: List[SlidePlan] = Field(description="按讲授顺序排列的页序")


class Bullet(BaseModel):
    text: str = Field(description="一条要点，书面化、信息密度高，≤28字")
    children: List[str] = Field(default_factory=list, description="0-3 条子要点（展开/举例），可空")


class SlideFill(BaseModel):
    bullets: List[Bullet] = Field(description="3-5 条要点")
    notes: str = Field(default="", description="教师讲稿/演讲者备注，口语化，120-200字")
    key_terms: List[str] = Field(default_factory=list, description="2-5 个关键术语")


# ---------------------------------------------------------------------------
# Prompt（面向教案文本）
# ---------------------------------------------------------------------------

_ROLE = ("你是一名资深大学教师兼课程 PPT 设计专家。注意：这是要做【用于课堂讲授的 PPT】，"
         "面向学生讲解知识，不是教学评价或督导分析。")

OUTLINE_PROMPT = (
    _ROLE + "\n"
    "下面给你一份【教案】正文（Markdown），以及可选的【用户额外要求】。请据此设计一整套课堂讲授 PPT 的页序，输出 JSON。\n"
    "要求：\n"
    "1) 第 1 页 layout=cover（封面）；第 2 页 layout=agenda（本节提纲）。\n"
    "2) 依据教案的章节/知识结构，每个大主题前放一页 layout=section（章节分隔，title=该主题名）；"
    "其下拆成若干 layout=content 内容页，每页只聚焦一个小主题。\n"
    "3) 在讲完重要内容后、或教案中的提问/讨论环节处，插入 1-2 页 layout=qa（课堂思考/讨论题）。\n"
    "4) 最后一页 layout=summary（本节小结）。\n"
    "5) 总页数控制在 {min}-{max} 页。\n"
    "6) title 精炼（≤20字）；本步只排页序与标题，不要写正文要点。\n"
)

CONTENT_FILL_PROMPT = (
    _ROLE + "\n"
    "正在制作课堂讲授 PPT 的一页，本页标题：「{title}」。\n"
    "下面是完整【教案】正文。请聚焦与本页标题相关的内容，提炼成适合放上 PPT 的讲解要点，输出 JSON：\n"
    "- bullets：3-5 条要点，书面化、精炼、信息密度高（不是逐字稿），每条 ≤28 字；"
    "必要时每条可带 1-3 个 children 子要点（更细的展开或例子）。\n"
    "- notes：教师讲稿（口语自然、120-200 字），放进演讲者备注，让老师能照着把这页讲清楚。\n"
    "- key_terms：2-5 个本页关键术语/概念。\n"
    "务必忠于教案内容，不要编造教案里没有的事实或数据。\n\n"
    "教案正文：\n{content}\n"
)

SUMMARY_FILL_PROMPT = (
    _ROLE + "\n"
    "正在制作课堂讲授 PPT 的【本节小结】页。请基于下面的【教案正文】与【本节讲过的主题】，"
    "凝练面向学生的核心收获，输出 JSON：\n"
    "- bullets：3-6 条「关键收获 / take-away」，每条 ≤28 字，可带 children；\n"
    "- notes：收尾讲稿（120-180 字），帮助老师做课堂总结与升华；\n"
    "- key_terms：3-6 个本节核心术语。\n"
    "只讲知识内容本身，不要点评教师的讲课表现或教学优缺点。\n\n"
    "本节主题：{topics}\n\n教案正文：\n{content}\n"
)

QA_FILL_PROMPT = (
    _ROLE + "\n"
    "正在制作课堂讲授 PPT 的【课堂思考/讨论】页，主题：「{title}」。请紧扣下面的【教案正文】，"
    "设计能引发学生思考的问题，输出 JSON：\n"
    "- bullets：3-5 个由浅入深、紧扣本页主题的思考/讨论题，每条为一个完整问句，≤30 字；\n"
    "- notes：组织讨论的引导语与预期答题方向（100-160 字），放进演讲者备注；\n"
    "- key_terms：2-4 个相关概念。\n"
    "问题应贴合教案内容，避免与其它思考页重复。\n\n"
    "教案正文：\n{content}\n"
)

_OUTLINE_CHARS = 16000   # 大纲阶段送入教案的最大字符数
_FILL_CHARS = 6000       # 每页填充阶段送入教案的最大字符数


# ---------------------------------------------------------------------------
# 大纲（Stage 1）
# ---------------------------------------------------------------------------

def _clip(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n]


def _md_headings(content: str) -> list:
    """从教案 Markdown 抽取标题行（# / ## / 数字编号），作为兜底页序。"""
    titles = []
    for line in (content or "").splitlines():
        s = line.strip()
        m = re.match(r"^#{1,6}\s+(.+)$", s)
        if m:
            titles.append(m.group(1).strip()[:20])
            continue
        m = re.match(r"^(?:第[一二三四五六七八九十0-9]+[章节、.]|[0-9]+[、.])\s*(.+)$", s)
        if m and len(s) <= 40:
            titles.append(m.group(1).strip()[:20] or s[:20])
    # 去重保序
    seen, out = set(), []
    for t in titles:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _make_outline(runner, content, course, sub, user_prompt, min_slides, max_slides, log=None) -> dict:
    prompt = OUTLINE_PROMPT.format(min=min_slides, max=max_slides)
    if user_prompt:
        prompt += f"\n【用户额外要求】：{user_prompt}\n"
    prompt += "\n===== 教案正文开始 =====\n" + _clip(content, _OUTLINE_CHARS) + "\n===== 教案正文结束 ====="
    if log:
        log.info("[ppt] 生成 PPT 大纲 ...")
    budget = min(8192, max(4096, max_slides * 220))
    try:
        plan = runner.run("ppt-outline", [prompt], DeckPlan, max_output_tokens=budget)
    except Exception as e:  # noqa: BLE001
        if log:
            log.warning(f"[ppt] 大纲生成失败，回退到按教案标题自动排版：{str(e)[:120]}")
        plan = _fallback_plan(content, course, sub)
    plan = _normalize_plan(plan, course, sub, max_slides)
    if log:
        log.info(f"[ppt] 大纲共 {len(plan['slides'])} 页")
    return plan


def _fallback_plan(content, course, sub) -> dict:
    """模型大纲失败时，用教案标题兜底排出页序。"""
    slides = [{"layout": "cover", "title": course, "subtitle": sub},
              {"layout": "agenda", "title": "本节提纲"}]
    titles = _md_headings(content) or ["课程内容"]
    slides.append({"layout": "section", "title": titles[0]})
    for t in titles[: max(1, min(len(titles), 12))]:
        slides.append({"layout": "content", "title": t})
    slides.append({"layout": "qa", "title": "课堂思考"})
    slides.append({"layout": "summary", "title": "本节小结"})
    return {"title": course, "subtitle": sub, "slides": slides}


def _normalize_plan(plan: dict, course: str, sub: str, max_slides: int) -> dict:
    valid = ("cover", "agenda", "section", "content", "qa", "summary")
    slides = [s for s in (plan.get("slides") or []) if s.get("layout") in valid]
    cover = next((s for s in slides if s.get("layout") == "cover"), None) or \
        {"layout": "cover", "title": plan.get("title") or course, "subtitle": plan.get("subtitle") or sub}
    agenda = next((s for s in slides if s.get("layout") == "agenda"), None) or \
        {"layout": "agenda", "title": "本节提纲"}
    body = [s for s in slides if s.get("layout") not in ("cover", "agenda")]
    # 小结：只保留最后一个置于结尾，其余降级为 content
    summaries = [s for s in body if s.get("layout") == "summary"]
    if summaries:
        keep = summaries[-1]
        for s in body:
            if s.get("layout") == "summary" and s is not keep:
                s["layout"] = "content"
        body = [s for s in body if s is not keep] + [keep]
    else:
        body = body + [{"layout": "summary", "title": "本节小结"}]
    slides = [cover, agenda] + body
    # 超出 max_slides：裁掉多余的 content/qa（保留封面/提纲/章节分隔/小结），优先裁 qa、靠后优先
    if max_slides and len(slides) > max_slides:
        over = len(slides) - max_slides
        removable = [i for i, s in enumerate(slides) if s.get("layout") in ("content", "qa")]
        order = sorted(removable, key=lambda i: (slides[i].get("layout") != "qa", -i))
        drop = set(order[:over])
        slides = [s for i, s in enumerate(slides) if i not in drop]
    plan["slides"] = slides
    plan["title"] = plan.get("title") or course
    plan["subtitle"] = plan.get("subtitle") or sub
    return plan


# ---------------------------------------------------------------------------
# 填充（Stage 2，并发）
# ---------------------------------------------------------------------------

def _cap(lst, n):
    return list(lst or [])[:n]


def _fill_slides(runner, plan, content, course, log=None, progress=None) -> list:
    clipped = _clip(content, _FILL_CHARS)
    section_titles = [s["title"] for s in plan["slides"] if s.get("layout") == "section" and s.get("title")]
    content_titles = [s["title"] for s in plan["slides"] if s.get("layout") == "content" and s.get("title")]
    agenda_items = (section_titles or content_titles)[:10]
    topics = ", ".join(content_titles[:40])

    out, jobs, sec_no = [], [], 0
    for sp in plan["slides"]:
        layout = sp.get("layout")
        s = {"layout": layout, "title": sp.get("title", ""), "subtitle": sp.get("subtitle", ""),
             "bullets": [], "notes": "", "key_terms": [], "time_ref": ""}
        if layout == "cover":
            s["title"] = s["title"] or course
            s["subtitle"] = s["subtitle"] or plan.get("subtitle", "")
        elif layout == "agenda":
            s["bullets"] = [{"text": t, "children": []} for t in agenda_items]
            s["title"] = s["title"] or "本节提纲"
        elif layout == "section":
            sec_no += 1
            s["index"] = sec_no
        elif layout == "content":
            jobs.append((len(out), "content", {"title": sp.get("title", "")}))
        elif layout == "qa":
            jobs.append((len(out), "qa", {"title": sp.get("title", "")}))
        elif layout == "summary":
            s["title"] = s["title"] or "本节小结"
            jobs.append((len(out), "summary", {}))
        out.append(s)

    if log:
        log.info(f"[ppt] 填充 {len(jobs)} 页正文（并发）...")
    total = len(jobs)
    done_counter = {"n": 0}

    def do(job):
        idx, kind, info = job
        if kind == "content":
            prompt = CONTENT_FILL_PROMPT.format(title=info.get("title", ""), content=clipped)
        elif kind == "qa":
            prompt = QA_FILL_PROMPT.format(title=info.get("title", "") or "课堂思考", content=clipped)
        else:  # summary
            prompt = SUMMARY_FILL_PROMPT.format(topics=topics or "（见教案）", content=clipped)
        try:
            fill = runner.run(f"ppt-{kind}-{idx}", [prompt], SlideFill, max_output_tokens=2048)
        except Exception as e:  # noqa: BLE001  单页失败不拖垮整套
            if log:
                log.warning(f"[ppt] 第 {idx + 1} 页填充失败：{str(e)[:120]}")
            fill = {"bullets": [], "notes": "", "key_terms": []}
        done_counter["n"] += 1
        if progress:
            progress(f"正在生成第 {done_counter['n']}/{total} 页内容…")
        return idx, fill

    for idx, fill in runner.map_parallel(do, jobs):
        bullets = []
        for b in _cap(fill.get("bullets"), 6):
            if isinstance(b, str):
                b = {"text": b, "children": []}
            bullets.append({"text": b.get("text", ""), "children": _cap(b.get("children"), 3)})
        out[idx]["bullets"] = bullets
        out[idx]["notes"] = fill.get("notes", "") or ""
        out[idx]["key_terms"] = _cap(fill.get("key_terms"), 6)
    return out


# ---------------------------------------------------------------------------
# 对外：组装整套 deck
# ---------------------------------------------------------------------------

def build_deck_from_text(runner, *, content: str, meta: dict | None = None,
                         user_prompt: str = "", min_slides: int = 12, max_slides: int = 24,
                         log=None, progress=None) -> dict:
    meta = meta or {}
    course = meta.get("courseName") or "课程"
    sub = meta.get("subTitle") or ""
    if not (content or "").strip():
        raise ValueError("教案内容为空，无法生成 PPT。")
    if progress:
        progress("正在规划 PPT 大纲…")
    plan = _make_outline(runner, content, course, sub, user_prompt, min_slides, max_slides, log)
    slides = _fill_slides(runner, plan, content, course, log, progress)
    return {
        "title": plan.get("title") or course,
        "subtitle": plan.get("subtitle") or sub,
        "course": course,
        "footer": course,
        "model": getattr(runner, "model", ""),
        "duration": "",
        "slides": slides,
    }


# ---------------------------------------------------------------------------
# HTML PPT 渲染（自包含；键盘翻页 / 演讲者备注 / 缩略图总览 / 打印成 PDF）
# 直接移植自 video-analyze/slides_steps.py
# ---------------------------------------------------------------------------

def _esc(s) -> str:
    return (str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _bullets_html(bullets) -> str:
    if not bullets:
        return ""
    items = []
    for b in bullets:
        if isinstance(b, str):
            b = {"text": b, "children": []}
        kids = b.get("children") or []
        sub = ("<ul class=\"sub\">" + "".join(f"<li>{_esc(c)}</li>" for c in kids) + "</ul>") if kids else ""
        items.append(f"<li>{_esc(b.get('text', ''))}{sub}</li>")
    return "<ul class=\"bul\">" + "".join(items) + "</ul>"


def _chips_html(terms) -> str:
    if not terms:
        return ""
    return "<div class=\"chips\">" + "".join(f"<span>{_esc(t)}</span>" for t in terms) + "</div>"


def _slide_inner(s: dict, total_sections: int) -> str:
    layout = s.get("layout", "content")
    title, subtitle = _esc(s.get("title", "")), _esc(s.get("subtitle", ""))
    notes = s.get("notes", "")
    note_block = f"<div class=\"snotes\" hidden>{_esc(notes)}</div>" if notes else ""

    if layout == "cover":
        meta_bits = " · ".join(x for x in [s.get("_course", ""), s.get("_duration", ""), s.get("_model", "")] if x)
        return (f"<div class=\"stage cover\"><div class=\"inner\">"
                f"<div class=\"kicker\">{_esc(s.get('_course', ''))}</div>"
                f"<h1>{title}</h1><div class=\"csub\">{subtitle}</div>"
                f"<div class=\"cmeta\">{_esc(meta_bits)}</div></div>{note_block}</div>")

    if layout == "agenda":
        lis = "".join(f"<li><span class=\"n\">{i + 1:02d}</span>{_esc((b.get('text') if isinstance(b, dict) else b))}</li>"
                      for i, b in enumerate(s.get("bullets", [])))
        return (f"<div class=\"stage\"><div class=\"inner\"><div class=\"head\"><span class=\"bar\"></span>"
                f"<h2>{title or '本节提纲'}</h2></div><ol class=\"agenda\">{lis}</ol></div>{note_block}</div>")

    if layout == "section":
        num = f"{s.get('index', 0):02d}"
        return (f"<div class=\"stage section\"><div class=\"inner\">"
                f"<div class=\"bignum\">{num}<span>/ {total_sections:02d}</span></div>"
                f"<h1>{title}</h1><div class=\"csub\">{subtitle}</div></div>{note_block}</div>")

    if layout == "qa":
        cards = "".join(f"<div class=\"qcard\"><span class=\"qq\">Q{i + 1}</span><p>{_esc((b.get('text') if isinstance(b, dict) else b))}</p></div>"
                        for i, b in enumerate(s.get("bullets", [])))
        return (f"<div class=\"stage qa\"><div class=\"inner\"><div class=\"head\"><span class=\"bar\"></span>"
                f"<h2>{title or '课堂思考'}</h2></div><div class=\"qwrap\">{cards}</div>"
                f"{_chips_html(s.get('key_terms'))}</div>{note_block}</div>")

    # content / summary
    tag = "本节小结" if layout == "summary" else ""
    badge = f"<span class=\"tbadge\">{_esc(s.get('time_ref', ''))}</span>" if s.get("time_ref") and layout == "content" else ""
    kicker = f"<div class=\"slabel\">{tag}</div>" if tag else ""
    cls = "stage summary" if layout == "summary" else "stage"
    sub_html = f"<div class=\"csub small\">{subtitle}</div>" if subtitle else ""
    bul_html = _bullets_html(s.get("bullets", []))
    chips_html = _chips_html(s.get("key_terms"))
    return (f"<div class=\"{cls}\"><div class=\"inner\">{kicker}"
            f"<div class=\"head\"><span class=\"bar\"></span><h2>{title}</h2>{badge}</div>"
            f"{sub_html}{bul_html}{chips_html}</div>{note_block}</div>")


_HTML_CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#1f2733;--accent:#4e4376;--accent2:#2b5876;--muted:#8a93a2;--line:#e7eaf2}
html,body{height:100%;background:#0b1020;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);overflow:hidden}
#deck{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
.slide{position:absolute;inset:0;display:none;align-items:center;justify-content:center;padding:2vmin}
.slide.active{display:flex}
.stage{position:relative;width:min(100vw,177.78vh);height:min(56.25vw,100vh);background:#fff;border-radius:10px;
  overflow:hidden;container-type:size;box-shadow:0 12px 50px rgba(0,0,0,.5)}
.stage .inner{position:absolute;inset:0;padding:7cqh 8cqw;display:flex;flex-direction:column;gap:2.4cqh}
.head{display:flex;align-items:center;gap:2cqw}
.head .bar{width:1.1cqw;height:6.2cqh;background:linear-gradient(var(--accent2),var(--accent));border-radius:2px;flex:none}
.stage h1{font-size:8cqh;line-height:1.15;color:var(--ink);font-weight:800;letter-spacing:.5px}
.stage h2{font-size:5.6cqh;line-height:1.2;color:var(--ink);font-weight:750}
.tbadge{margin-left:auto;font:600 2.6cqh/1 monospace;color:#fff;background:var(--accent);padding:1.1cqh 1.6cqw;border-radius:99px}
.slabel{font-size:2.6cqh;color:var(--accent);font-weight:700;letter-spacing:2px}
.csub{font-size:3.6cqh;color:var(--muted);font-weight:500}
.csub.small{font-size:3cqh;margin-top:-1cqh}
ul.bul{list-style:none;display:flex;flex-direction:column;gap:1.9cqh;margin-top:.6cqh}
ul.bul>li{position:relative;padding-left:3.4cqw;font-size:3.7cqh;line-height:1.42;color:#2b3445}
ul.bul>li::before{content:"";position:absolute;left:.4cqw;top:1.7cqh;width:1.3cqw;height:1.3cqw;border-radius:50%;
  background:linear-gradient(135deg,var(--accent2),var(--accent))}
ul.sub{list-style:none;margin:.8cqh 0 0;display:flex;flex-direction:column;gap:.7cqh}
ul.sub>li{position:relative;padding-left:3cqw;font-size:2.85cqh;line-height:1.35;color:#5a6472}
ul.sub>li::before{content:"–";position:absolute;left:.6cqw;color:var(--accent)}
.chips{margin-top:auto;display:flex;flex-wrap:wrap;gap:1.2cqw;padding-top:2cqh}
.chips span{font-size:2.5cqh;color:var(--accent);background:#eef0fb;border:1px solid #e0e3f6;border-radius:99px;padding:.7cqh 1.6cqw}
.stage.cover{background:radial-gradient(120% 120% at 80% 10%,#3a4a8a 0%,var(--accent2) 45%,#1c2440 100%);color:#fff}
.stage.cover .inner{justify-content:center;gap:3cqh}
.stage.cover .kicker{font-size:3cqh;letter-spacing:4px;color:#aeb8e6;text-transform:uppercase}
.stage.cover h1{font-size:9.5cqh;color:#fff;max-width:84%}
.stage.cover .csub{font-size:4cqh;color:#dfe5ff}
.stage.cover .cmeta{position:absolute;left:8cqw;bottom:6cqh;font-size:2.4cqh;color:#9fb0e8;font-family:monospace}
.stage.section{background:linear-gradient(125deg,var(--accent),var(--accent2));color:#fff}
.stage.section .inner{justify-content:center;gap:2cqh}
.stage.section .bignum{font:800 22cqh/1 monospace;color:rgba(255,255,255,.28)}
.stage.section .bignum span{font-size:5cqh;margin-left:1cqw;color:rgba(255,255,255,.5)}
.stage.section h1{color:#fff;font-size:8.5cqh;max-width:86%}
.stage.section .csub{color:#e6ebff}
.agenda{list-style:none;display:grid;grid-template-columns:1fr 1fr;gap:2.2cqh 5cqw;margin-top:1cqh}
.agenda li{display:flex;align-items:baseline;gap:1.6cqw;font-size:3.5cqh;color:#2b3445;line-height:1.3}
.agenda .n{font:800 3.2cqh/1 monospace;color:var(--accent);flex:none}
.stage.qa{background:#fbfbfe}
.qwrap{display:flex;flex-direction:column;gap:1.8cqh;margin-top:.5cqh}
.qcard{display:flex;gap:2cqw;align-items:flex-start;background:#fff;border:1px solid var(--line);border-left:.9cqw solid var(--accent);
  border-radius:8px;padding:2.2cqh 2.4cqw}
.qcard .qq{font:800 3cqh/1 monospace;color:var(--accent);flex:none}
.qcard p{font-size:3.4cqh;line-height:1.35;color:#2b3445}
.stage.summary{background:linear-gradient(180deg,#fff,#f5f7fd)}
#bar{position:fixed;left:0;bottom:0;height:4px;background:var(--accent);width:0;transition:width .25s;z-index:30}
#counter{position:fixed;right:14px;bottom:12px;color:#cfd6ea;font:600 13px/1 monospace;background:rgba(0,0,0,.35);
  padding:6px 10px;border-radius:99px;z-index:30}
#notes{position:fixed;left:0;right:0;bottom:0;max-height:34vh;overflow:auto;background:rgba(12,16,32,.96);color:#dfe4f5;
  padding:16px 22px;font-size:15px;line-height:1.6;border-top:2px solid var(--accent);transform:translateY(100%);
  transition:transform .25s;z-index:40}
#notes.show{transform:none}
#notes b{color:#aeb8e6;display:block;margin-bottom:6px;font-size:12px;letter-spacing:1px}
#grid{position:fixed;inset:0;background:rgba(8,11,22,.97);display:none;grid-template-columns:repeat(4,1fr);gap:14px;
  padding:28px;overflow:auto;z-index:50}
#grid.show{display:grid}
#grid .gthumb{background:#fff;border-radius:6px;aspect-ratio:16/9;padding:10px;cursor:pointer;overflow:hidden;position:relative;
  border:2px solid transparent;font-size:12px;color:#33415c}
#grid .gthumb:hover{border-color:var(--accent)}
#grid .gthumb .gi{position:absolute;top:4px;right:6px;font:700 10px/1 monospace;color:var(--muted)}
#grid .gthumb b{font-size:12px;color:var(--ink);display:block}
#grid .gthumb small{color:var(--muted)}
#help{position:fixed;left:14px;bottom:12px;color:#9aa3bd;font-size:12px;z-index:30;background:rgba(0,0,0,.3);
  padding:6px 10px;border-radius:8px}
#help b{color:#cfd6ea}
@media print{
  @page{size:1280px 720px;margin:0}
  html,body{overflow:visible;background:#fff}
  #deck{position:static}
  .slide{display:block!important;position:relative;page-break-after:always;padding:0}
  .stage{width:1280px;height:720px;border-radius:0;box-shadow:none}
  .stage .snotes{display:block!important;position:absolute;left:8cqw;right:8cqw;bottom:1.5cqh;font-size:1.9cqh;
    color:#8a93a2;border-top:1px dashed #ccc;padding-top:1cqh}
  #bar,#counter,#notes,#grid,#help{display:none!important}
}
@supports not (width:1cqw){
  .stage .inner{padding:6.5vh 7.5vw;gap:2.2vh}
  .stage h1{font-size:7.4vh}.stage h2{font-size:5.2vh}
  .csub{font-size:3.3vh}.csub.small{font-size:2.8vh}
  .tbadge{font-size:2.4vh}.slabel{font-size:2.4vh}
  ul.bul>li{font-size:3.4vh;padding-left:3.2vw}
  ul.bul>li::before{width:1.2vw;height:1.2vw;top:1.6vh}
  ul.sub>li{font-size:2.7vh;padding-left:2.8vw}
  .chips span{font-size:2.3vh}.agenda li{font-size:3.2vh}.agenda .n{font-size:3vh}
  .qcard p{font-size:3.1vh}.qcard .qq{font-size:2.8vh}
  .stage.cover h1{font-size:8.8vh}.stage.cover .kicker{font-size:2.8vh}.stage.cover .csub{font-size:3.7vh}
  .stage.section .bignum{font-size:20vh}.stage.section .bignum span{font-size:4.6vh}.stage.section h1{font-size:7.9vh}
}
"""

_HTML_JS = r"""
const slides=[...document.querySelectorAll('.slide')];
const N=slides.length; let cur=0;
const bar=document.getElementById('bar'), counter=document.getElementById('counter'),
      notes=document.getElementById('notes'), grid=document.getElementById('grid');
function clamp(i){return Math.max(0,Math.min(N-1,i));}
function show(i){
  cur=clamp(i);
  slides.forEach((s,k)=>s.classList.toggle('active',k===cur));
  bar.style.width=((cur+1)/N*100)+'%';
  counter.textContent=(cur+1)+' / '+N;
  const nd=slides[cur].querySelector('.snotes');
  notes.querySelector('.ni').innerHTML='<b>演讲者备注</b>'+(nd?nd.innerHTML:'（无）');
  if(location.hash!=='#'+(cur+1)) history.replaceState(null,'','#'+(cur+1));
}
function next(){show(cur+1);} function prev(){show(cur-1);}
addEventListener('keydown',e=>{
  if(grid.classList.contains('show')){const k=e.key.toLowerCase();if(k!=='g'&&k!=='o'&&k!=='escape')return;}
  switch(e.key){
    case 'ArrowRight':case ' ':case 'PageDown':case 'ArrowDown':next();break;
    case 'ArrowLeft':case 'PageUp':case 'ArrowUp':prev();break;
    case 'Home':show(0);break; case 'End':show(N-1);break;
    case 'f':case 'F':document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();break;
    case 's':case 'S':notes.classList.toggle('show');break;
    case 'g':case 'G':case 'o':case 'O':grid.classList.toggle('show');break;
    case 'p':case 'P':print();break;
    case 'Escape':grid.classList.remove('show');notes.classList.remove('show');break;
  }
});
addEventListener('click',e=>{
  if(e.target.closest('#notes,#grid,#help,a'))return;
  (e.clientX < innerWidth*0.32)?prev():next();
});
let tx=0; addEventListener('touchstart',e=>tx=e.changedTouches[0].clientX,{passive:true});
addEventListener('touchend',e=>{const dx=e.changedTouches[0].clientX-tx; if(Math.abs(dx)>40)(dx<0?next():prev());},{passive:true});
addEventListener('hashchange',()=>{const n=parseInt(location.hash.slice(1)); if(n>=1&&n<=N&&n-1!==cur)show(n-1);});
slides.forEach((s,k)=>{
  const st=s.querySelector('.stage'); const h=st.querySelector('h1,h2');
  const sub=st.querySelector('.csub'); const lay=st.className.replace('stage','').trim()||'content';
  const d=document.createElement('div'); d.className='gthumb';
  const gi=document.createElement('span'); gi.className='gi'; gi.textContent=(k+1);
  const tb=document.createElement('b'); tb.textContent=h?h.textContent:'';
  const sm=document.createElement('small'); sm.textContent=lay+(sub?' · '+sub.textContent:'');
  d.append(gi,tb,sm);
  d.onclick=()=>{grid.classList.remove('show');show(k);};
  grid.appendChild(d);
});
const start=parseInt((location.hash||'#1').slice(1))||1;
show(start-1);
"""


def render_slides_html(deck: dict) -> str:
    """返回自包含的 HTML PPT 字符串。"""
    course = deck.get("course", "")
    sections = [s for s in deck.get("slides", []) if s.get("layout") == "section"]
    total_sections = len(sections)
    parts = []
    for s in deck.get("slides", []):
        if s.get("layout") == "cover":
            s = {**s, "_course": course, "_duration": deck.get("duration", ""), "_model": deck.get("model", "")}
        parts.append(f"<div class=\"slide\">{_slide_inner(s, total_sections)}</div>")
    title = _esc(deck.get("title", "课堂 PPT"))
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>"
        f"<title>{title}</title><style>{_HTML_CSS}</style></head><body>"
        f"<div id=\"deck\">{''.join(parts)}</div>"
        "<div id=\"bar\"></div><div id=\"counter\"></div>"
        "<div id=\"notes\"><div class=\"ni\"></div></div><div id=\"grid\"></div>"
        "<div id=\"help\"><b>←/→</b> 翻页 · <b>S</b> 备注 · <b>G</b> 总览 · <b>F</b> 全屏 · <b>P</b> 打印</div>"
        f"<script>{_HTML_JS}</script></body></html>"
    )

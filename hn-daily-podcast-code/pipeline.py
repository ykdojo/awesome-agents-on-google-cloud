"""Hacker News Digest — daily HN-to-podcast pipeline on an ADK 2 graph.

Graph spine = function nodes passing a state dict; every LLM step is a
dynamic ctx.run_node call to an Agent. Code owns fetching, scoring,
pruning, the ledger, routing, TTS, and publishing; models own curation,
digests, script-writing, claim extraction, and fact-check verdicts.

Env:
  GEMINI_API_KEY        key for the TTS call (free tier works)
  GOOGLE_GENAI_USE_ENTERPRISE=TRUE + ADC   for text models (billed project)
  GOOGLE_CLOUD_LOCATION=global
  PUBLISH_BUCKET        GCS bucket name; unset = write to ./out locally
  PUBLIC_BASE_URL       public URL prefix for the bucket (for RSS links)
  WINDOW_HOURS          lookback window (default 26)
"""

import asyncio
import base64
import datetime
import zoneinfo
import html
import json
import os
import re
import subprocess
import wave

import requests
from pydantic import BaseModel

from google.adk import Agent, Context, Event, Runner, Workflow
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import RetryConfig, node
from google import genai

MODEL_PRO = os.environ.get("MODEL_PRO", "gemini-3.1-pro-preview")
MODEL_FLASH = os.environ.get("MODEL_FLASH", "gemini-3.6-flash")
TTS_MODEL = "gemini-3.1-flash-tts-preview"
WINDOW_HOURS = int(os.environ.get("WINDOW_HOURS", "26"))
WORD_BUDGET = 1300          # ~9 min at speaking pace, one TTS call
MAX_REWRITES = int(os.environ.get("MAX_REWRITES", "2"))
MAX_CUTS = 2                # cut passes are re-verified; abort if still dirty
MAX_DIGEST_REPAIRS = int(os.environ.get("MAX_DIGEST_REPAIRS", "2"))
MAX_PICKS = int(os.environ.get("MAX_PICKS", "10"))
VOICES = {"Hacker": "Despina", "News": "Charon"}
TTS_STYLE = ("TTS the following conversation between Hacker and News, "
             "spoken naturally at a relaxed, conversational pace:\n")

ALGOLIA = "https://hn.algolia.com/api/v1"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


# ---------- structured outputs ----------

class Pick(BaseModel):
    story_id: int
    tier: str            # "main" | "quick"
    reason: str


class Curation(BaseModel):
    picks: list[Pick]


class CommentTheme(BaseModel):
    theme: str
    evidence_quotes: list[str]


class Digest(BaseModel):
    story_id: int
    article_key_points: list[str]
    comment_themes: list[CommentTheme]
    standout_quote: str


class Line(BaseModel):
    speaker: str         # "Hacker" | "News"
    text: str


class Script(BaseModel):
    lines: list[Line]


class Claim(BaseModel):
    claim_id: int
    story_id: int
    text: str
    kind: str            # "article_fact" | "thread_characterization" | "quantified"


class ClaimList(BaseModel):
    claims: list[Claim]


class Verdict(BaseModel):
    claim_id: int
    verdict: str         # "verified" | "failed"
    note: str


class DigestAudit(BaseModel):
    ok: bool
    unsupported: list[str]   # digest statements the sources do not support


# ---------- agents ----------

CLAIM_RULES = """Claim rules (strict):
- Story metadata numbers (points, comment counts) are provided and safe to state.
- Characterize the discussion ONLY with evidence quoted in the digest; prefer
  attributed forms ("one commenter said...", "several people pointed out...").
- NEVER fuse a number with a characterization ("N comments of people doing X")
  unless the digest states it verbatim.
- Assert only what appears in the digests (closed world)."""

curator = Agent(
    name="curator", model=MODEL_PRO, output_schema=Curation,
    instruction="""You are the editor of a short daily Hacker News podcast.
From the candidate stories (JSON metadata), pick 7-10 for today's episode:
3-4 as tier "main" (worth a real discussion) and the rest tier "quick"
(one-line mentions). Optimize for variety of topics and how interesting the
story is to talk about, not just points. Avoid picking near-duplicates.""")

digester = Agent(
    name="digester", model=MODEL_PRO, output_schema=Digest,
    instruction="""Digest this Hacker News story for podcast hosts.
You get story metadata, article text (may be missing), and top comment threads.
Return: 3-6 key points from the article (or from the thread if no article);
2-4 comment themes, each with 1-2 short evidence quotes copied verbatim from
actual comments; one standout quote. Only report what is actually present.""")

scriptwriter = Agent(
    name="scriptwriter", model=MODEL_PRO, output_schema=Script,
    instruction=f"""Write today's episode of "Hacker News Digest", a two-host
podcast. Hosts are openly robots named Hacker and News. Open with exactly this
gag: Hacker says "Good morning. I'm Hacker." News says "And I'm News. This is
Hacker News Digest for <weekday, month day>." Then cover the MAIN stories with
genuine back-and-forth discussion grounded in the digests, and the QUICK
stories as brief mentions near the end. Close with a short sign-off.
Tone: brisk, natural, a sports-broadcast feel; light humor welcome; no
over-the-top enthusiasm. HARD LIMIT: at most {WORD_BUDGET} words total.
If REWRITE FEEDBACK is present: prefer DELETING or neutrally softening each
flagged claim over rephrasing it, keep every other line as close to unchanged
as possible, and add NO new factual material anywhere in the script.
{CLAIM_RULES}""")

extractor = Agent(
    name="extractor", model=MODEL_FLASH, output_schema=ClaimList,
    instruction="""From this podcast script, extract every checkable claim:
facts attributed to an article (kind=article_fact), characterizations of the
comment thread (kind=thread_characterization), and any quantified claims
(kind=quantified). Skip pure opinions, jokes, and the intro/outro. Assign
sequential claim_ids and the story_id each claim belongs to.""")

digest_checker = Agent(
    name="digest_checker", model=MODEL_PRO, output_schema=DigestAudit,
    instruction="""Audit this story digest against the raw sources (article
excerpt + comment threads). List every digest statement the sources do not
support as written: wrong facts, merged commenters, overstated prevalence
("many users" when sources show one or two), or anything not present at all.
ok=true only if every statement is supported.""")

checker = Agent(
    name="checker", model=MODEL_PRO, output_schema=Verdict,
    instruction="""Fact-check one claim from a podcast script against the
provided digest and raw source excerpts for its story. verdict="verified" only
if the sources support the claim as stated; otherwise "failed" with a note
saying what is wrong (wrong number, unsupported characterization, not in
sources). Be strict about quantified characterizations of the thread.""")


# ---------- deterministic helpers ----------

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def now_show():
    """Show-facing clock: episode dates/titles use Pacific time (YK's call),
    configurable via SHOW_TZ. Epoch math for the fetch window is tz-agnostic."""
    tz = zoneinfo.ZoneInfo(os.environ.get("SHOW_TZ", "America/Los_Angeles"))
    return datetime.datetime.now(tz)


def fetch_candidates_algolia():
    ts = int(now_utc().timestamp()) - WINDOW_HOURS * 3600
    r = requests.get(
        f"{ALGOLIA}/search_by_date",
        params={"tags": "story", "hitsPerPage": 200,
                "numericFilters": f"created_at_i>{ts},points>10"},
        timeout=30)
    r.raise_for_status()
    hits = r.json()["hits"]
    seen_urls, out = set(), []
    for h in sorted(hits, key=lambda h: -(h["points"] + 1.5 * (h["num_comments"] or 0))):
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        out.append({
            "story_id": int(h["objectID"]), "title": h["title"],
            "url": h.get("url"), "points": h["points"],
            "num_comments": h["num_comments"] or 0,
            "age_h": round((now_utc().timestamp() - h["created_at_i"]) / 3600, 1),
        })
    return out[:20]


def strip_tags(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def prune_comments(tree, max_threads, max_depth, per_comment=1200, total_cap=60000):
    lines, size = [], 0

    def walk(c, depth):
        nonlocal size
        if depth > max_depth or size > total_cap:
            return
        text = strip_tags(c.get("text"))[:per_comment]
        if text:
            lines.append(f"{'  ' * depth}[{c.get('author', '?')}] {text}")
            size += len(text)
        for child in (c.get("children") or []):
            walk(child, depth + 1)

    for top in (tree.get("children") or [])[:max_threads]:
        walk(top, 0)
    return "\n".join(lines)


def fetch_article(url, comment_text):
    """Deterministic cascade: direct -> alt UA -> archive link in comments -> Wayback."""
    if not url:
        return None, "no_url"

    def get(u, headers):
        try:
            r = requests.get(u, headers=headers, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                text = strip_tags(re.sub(
                    r"<(script|style)[^>]*>.*?</\1>", "", r.text, flags=re.S))
                if len(text.split()) > 150:
                    return text[:40000]
        except requests.RequestException:
            pass
        return None

    text = get(url, UA)
    if text:
        return text, "direct"
    text = get(url, {"User-Agent": "curl/8.0"})
    if text:
        return text, "alt_ua"
    m = re.search(r"https?://archive\.(?:org|ph|today)/\S+", comment_text or "")
    if m:
        text = get(m.group(0).rstrip('.,)"'), UA)
        if text:
            return text, "archive_link_from_comments"
    try:
        r = requests.get("https://archive.org/wayback/available",
                         params={"url": url}, timeout=15).json()
        snap = (r.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available"):
            text = get(snap["url"], UA)
            if text:
                return text, "wayback"
    except requests.RequestException:
        pass
    return None, "unfetchable"


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def verify_digest_quotes(digest, story):
    """Deterministic digest verification: every evidence quote must actually
    appear in the pruned sources. Fabricated quotes are dropped in code, and
    themes that lose all their evidence are dropped with them, BEFORE the
    scriptwriter ever sees the digest. No model call needed."""
    sources = norm((story.get("article_text") or "") + " " + story["comments_text"])
    dropped = 0
    kept_themes = []
    for t in digest.comment_themes:
        good = [q for q in t.evidence_quotes if norm(q) and norm(q) in sources]
        dropped += len(t.evidence_quotes) - len(good)
        if good:
            t.evidence_quotes = good
            kept_themes.append(t)
        else:
            dropped += 1
    digest.comment_themes = kept_themes
    if digest.standout_quote and norm(digest.standout_quote) not in sources:
        digest.standout_quote = ""
        dropped += 1
    if dropped:
        print(f"  digest {digest.story_id}: dropped {dropped} unverifiable quote(s)/theme(s)")
    return digest


def deep_fetch_story(story, light=False):
    r = requests.get(f"{ALGOLIA}/items/{story['story_id']}", timeout=30)
    r.raise_for_status()
    tree = r.json()
    comments = prune_comments(
        tree, max_threads=5 if light else 12, max_depth=1 if light else 3)
    article, how = (None, "skipped_quick_tier") if light else \
        fetch_article(story.get("url"), comments)
    return {**story, "article_text": article, "article_via": how,
            "comments_text": comments}


_llm_sem = asyncio.Semaphore(int(os.environ.get("MAX_CONCURRENCY", "3")))

# Free-trial Vertex quotas are low QPM/TPM; retry 429s at the NODE level
# (a failed child node aborts the whole workflow before the parent can catch).
_RETRY = RetryConfig(max_attempts=6, initial_delay=20, max_delay=120,
                     backoff_factor=1.5)
_retrying = {}


async def run_agent(ctx, agent, prompt, schema):
    """Run an agent as a retrying, concurrency-capped dynamic node."""
    if agent.name not in _retrying:
        _retrying[agent.name] = node(agent, retry_config=_RETRY)
    async with _llm_sem:
        result = await ctx.run_node(_retrying[agent.name], prompt)
    return schema.model_validate(result)


# ---------- graph nodes ----------

@node
def fetch_candidates(node_input) -> dict:
    cands = fetch_candidates_algolia()
    print(f"fetch_candidates: {len(cands)} candidates")
    return {"candidates": cands}


@node(rerun_on_resume=True)
async def curate(ctx: Context, node_input: dict) -> dict:
    cur = await run_agent(ctx, curator, json.dumps(node_input["candidates"]), Curation)
    by_id = {c["story_id"]: c for c in node_input["candidates"]}
    picks = [p for p in cur.picks if p.story_id in by_id][:MAX_PICKS]
    mains = [p for p in picks if p.tier == "main"][:4]
    quicks = [p for p in picks if p.tier == "quick"][:max(0, MAX_PICKS - len(mains))]
    print(f"curate: {len(mains)} main + {len(quicks)} quick")
    return {**node_input, "picks": mains + quicks, "by_id": by_id}


@node(rerun_on_resume=True)
async def digest_stories(ctx: Context, node_input: dict) -> dict:
    picks, by_id = node_input["picks"], node_input["by_id"]

    story_check = os.environ.get("STORY_CHECK") == "1"

    async def digest_story(p):
        story = await asyncio.to_thread(
            deep_fetch_story, by_id[p.story_id], p.tier == "quick")
        prompt = (f"METADATA: {json.dumps({k: story[k] for k in ('story_id', 'title', 'url', 'points', 'num_comments')})}\n"
                  f"ARTICLE ({story['article_via']}):\n{story['article_text'] or '(none)'}\n\n"
                  f"TOP COMMENT THREADS:\n{story['comments_text']}")
        d = verify_digest_quotes(await run_agent(ctx, digester, prompt, Digest), story)
        if story_check:
            src_txt = (f"ARTICLE EXCERPT: {story['article_text'] or '(none)'}"[:12000]
                       + f"\nCOMMENTS: {story['comments_text'][:8000]}")
            # audit -> repair -> re-audit, same loop shape as the script level;
            # anything that survives the cap is still covered by the
            # script-level claim checks downstream
            for round_ in range(MAX_DIGEST_REPAIRS + 1):
                audit = await run_agent(
                    ctx, digest_checker,
                    f"DIGEST: {d.model_dump_json()}\n\n{src_txt}", DigestAudit)
                if audit.ok or not audit.unsupported:
                    break
                if round_ == MAX_DIGEST_REPAIRS:
                    print(f"  story {p.story_id}: still {len(audit.unsupported)} "
                          f"unsupported after {MAX_DIGEST_REPAIRS} repairs; "
                          f"script-level checks will catch the rest")
                    break
                print(f"  story {p.story_id}: {len(audit.unsupported)} unsupported "
                      f"digest statement(s), repair round {round_ + 1}")
                d = verify_digest_quotes(await run_agent(
                    ctx, digester,
                    prompt + "\n\nA fact audit found these statements "
                    "unsupported by the sources. Remove or fix them, change "
                    "nothing else:\n" + json.dumps(audit.unsupported), Digest), story)
        return p.story_id, story, d

    results = await asyncio.gather(*[digest_story(p) for p in picks])
    stories = {sid: s for sid, s, _ in results}
    digests = {sid: d for sid, _, d in results}
    fetched = sum(1 for s in stories.values() if s["article_text"])
    print(f"digest_stories: {len(digests)} digests, {fetched} articles fetched")
    return {**node_input, "stories": stories, "digests": digests,
            "rewrites": 0, "cuts": 0, "verdict_cache": {}, "feedback": ""}


def script_prompt(state):
    today = now_show().strftime("%A, %B %-d")
    parts = [f"Today is {today}.", "MAIN STORIES:"]
    for p in state["picks"]:
        meta = state["by_id"][p.story_id]
        d = state["digests"][p.story_id]
        block = (f"[{p.tier.upper()}] {meta['title']} "
                 f"({meta['points']} points, {meta['num_comments']} comments)\n"
                 f"editor's note: {p.reason}\n"
                 f"digest: {d.model_dump_json()}")
        parts.append(block)
    if state["feedback"]:
        parts.append("REWRITE FEEDBACK — fix or remove these failed claims, "
                     "keep everything else:\n" + state["feedback"])
    return "\n\n".join(parts)


@node(rerun_on_resume=True)
async def write_script(ctx: Context, node_input: dict) -> dict:
    script = await run_agent(ctx, scriptwriter, script_prompt(node_input), Script)
    words = sum(len(l.text.split()) for l in script.lines)
    print(f"write_script: {len(script.lines)} lines, {words} words")
    return {**node_input, "script": script, "script_words": words}


@node(rerun_on_resume=True)
async def fact_check(ctx: Context, node_input: dict) -> dict:
    transcript = "\n".join(f"{l.speaker}: {l.text}" for l in node_input["script"].lines)
    story_index = json.dumps([
        {"story_id": p.story_id, "title": node_input["by_id"][p.story_id]["title"]}
        for p in node_input["picks"]])
    claims = (await run_agent(
        ctx, extractor,
        f"STORIES (use these exact story_ids):\n{story_index}\n\nSCRIPT:\n{transcript}",
        ClaimList)).claims

    async def check(c):
        story = node_input["stories"].get(c.story_id)
        digest = node_input["digests"].get(c.story_id)
        meta = ({k: story[k] for k in ("title", "points", "num_comments", "url")}
                if story else None)
        src = (f"STORY METADATA (from the HN API, authoritative): {json.dumps(meta)}\n"
               f"DIGEST: {digest.model_dump_json() if digest else '(none)'}\n"
               f"ARTICLE EXCERPT: {(story or {}).get('article_text') or '(none)'}"[:12000]
               + f"\nCOMMENTS: {(story or {}).get('comments_text', '')[:8000]}")
        v = await run_agent(ctx, checker, f"CLAIM: {c.text}\nKIND: {c.kind}\n\n{src}", Verdict)
        return c, v

    cache = node_input["verdict_cache"]

    def key(c):
        return f"{c.story_id}|{re.sub(r'[^a-z0-9 ]', '', c.text.lower()).strip()}"

    new_claims = [c for c in claims if key(c) not in cache]
    results = await asyncio.gather(*[check(c) for c in new_claims])
    for c, v in results:
        cache[key(c)] = {"status": v.verdict.strip().lower(), "note": v.note}
    print(f"fact_check: {len(new_claims)} checked, {len(claims) - len(new_claims)} from cache")
    ledger = [{"claim_id": c.claim_id, "story_id": c.story_id, "claim": c.text,
               "kind": c.kind, **cache[key(c)]} for c in claims]
    failed = [row for row in ledger if row["status"] != "verified"]
    print(f"fact_check: {len(ledger)} claims, {len(failed)} failed")
    for row in failed[:3]:
        print(f"  sample fail: [{row['kind']}] {row['claim'][:80]} -- {row['note'][:100]}")
    return {**node_input, "ledger": ledger, "failed": failed}


@node
def review_router(node_input: dict) -> Event:
    if not node_input["failed"]:
        print("review_router: all verified -> RENDER")
        return Event(route="RENDER", output=node_input)
    if node_input["rewrites"] < MAX_REWRITES:
        state = {**node_input, "rewrites": node_input["rewrites"] + 1,
                 "feedback": json.dumps(node_input["failed"], indent=1)}
        print(f"review_router: {len(node_input['failed'])} failed -> "
              f"REWRITE #{state['rewrites']}")
        return Event(route="REWRITE", output=state)
    if node_input["cuts"] < MAX_CUTS:
        state = {**node_input, "cuts": node_input["cuts"] + 1}
        print(f"review_router: rewrite cap hit -> CUT #{state['cuts']}")
        return Event(route="CUT", output=state)
    raise RuntimeError(
        "unverified claims survived rewrites and cut passes; refusing to publish: "
        + json.dumps(node_input["failed"]))


cutter = Agent(
    name="cutter", model=MODEL_FLASH, output_schema=Script,
    instruction="Remove or neutrally soften ONLY the listed failed claims from "
                "this script. Change nothing else. Return the full edited script.")


@node(rerun_on_resume=True)
async def cut_failed(ctx: Context, node_input: dict) -> dict:
    transcript = "\n".join(f"{l.speaker}: {l.text}" for l in node_input["script"].lines)
    script = await run_agent(
        ctx, cutter, f"FAILED CLAIMS:\n{json.dumps(node_input['failed'])}\n\n"
                    f"SCRIPT:\n{transcript}", Script)
    return {**node_input, "script": script, "cut_applied": True}


SEGMENT_WORDS = int(os.environ.get("SEGMENT_WORDS", "260"))  # ~1.5-2 min


def chunk_lines(lines):
    """Split the script at speaker-turn boundaries into ~SEGMENT_WORDS chunks.
    TTS quality degrades on outputs longer than a few minutes, so each chunk
    renders separately and the PCM is concatenated."""
    chunks, cur, words = [], [], 0
    for l in lines:
        cur.append(l)
        words += len(l.text.split())
        if words >= SEGMENT_WORDS:
            chunks.append(cur)
            cur, words = [], 0
    if cur:
        chunks.append(cur)
    return chunks


def tts_chunk(client, chunk):
    transcript = "\n".join(f"{l.speaker}: {l.text}" for l in chunk)
    for attempt in range(5):
        try:
            interaction = client.interactions.create(
                model=TTS_MODEL,
                input=TTS_STYLE + transcript,
                response_format={"type": "audio"},
                generation_config={"speech_config": [
                    {"speaker": s, "voice": v} for s, v in VOICES.items()]},
            )
            return base64.b64decode(interaction.output_audio.data)
        except Exception as e:
            if ("429" in str(e) or "too_many_requests" in str(e)) and attempt < 4:
                print(f"  tts chunk: 429, retrying in 90s (attempt {attempt + 1})")
                import time
                time.sleep(90)
                continue
            raise


def render_transcript(lines):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], enterprise=False)
    gap = b"\x00" * (int(24000 * 0.35) * 2)   # 350ms silence between segments
    parts = []
    chunks = chunk_lines(lines)
    for i, chunk in enumerate(chunks):
        print(f"  tts segment {i + 1}/{len(chunks)} "
              f"({sum(len(l.text.split()) for l in chunk)} words)")
        parts.append(tts_chunk(client, chunk))
    return gap.join(parts)


@node
def render_tts(node_input: dict) -> dict:
    stamp = now_show().strftime("%Y-%m-%d")
    if os.environ.get("DRY_RUN") == "1":
        print("render_tts: DRY_RUN, skipping TTS")
        return {**node_input, "mp3": None, "duration_s": 0, "date": stamp}
    pcm = render_transcript(node_input["script"].lines)
    os.makedirs("out", exist_ok=True)
    stamp = now_show().strftime("%Y-%m-%d")
    wav_path, mp3_path = f"out/{stamp}.wav", f"out/{stamp}.mp3"
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000)
        wf.writeframes(pcm)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
                    "-b:a", "128k", mp3_path], check=True)
    dur = len(pcm) // (24000 * 2)
    print(f"render_tts: {dur}s episode, {len(chunk_lines(node_input['script'].lines))} segments -> {mp3_path}")
    return {**node_input, "mp3": mp3_path, "duration_s": dur, "date": stamp}


def build_feed(episodes, base_url):
    items = ""
    for ep in sorted(episodes, key=lambda e: e["date"], reverse=True):
        items += f"""
  <item>
    <title>{html.escape(ep['title'])}</title>
    <description>{html.escape(ep['description'])}</description>
    <enclosure url="{base_url}/episodes/{ep['date']}.mp3" length="{ep['bytes']}" type="audio/mpeg"/>
    <guid isPermaLink="false">hn-digest-{ep['date']}</guid>
    <pubDate>{ep['pub_rfc822']}</pubDate>
    <itunes:duration>{ep['duration_s']}</itunes:duration>
  </item>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Hacker News Digest</title>
  <link>{base_url}/feed.xml</link>
  <description>A short daily Hacker News briefing by two robots named Hacker and News. Fully automated with ADK and Cloud Run.</description>
  <language>en</language>
  <itunes:author>Hacker and News</itunes:author>
  <itunes:image href="{base_url}/cover.png"/>
  <itunes:category text="Technology"/>
  <itunes:explicit>false</itunes:explicit>{items}
</channel>
</rss>
"""


@node
def publish(node_input: dict) -> dict:
    stamp = node_input["date"]
    if not node_input["mp3"]:
        with open(f"out/{stamp}-ledger.json", "w") as f:
            json.dump(node_input["ledger"], f, indent=1)
        with open(f"out/{stamp}-script.txt", "w") as f:
            f.write("\n".join(f"{l.speaker}: {l.text}"
                              for l in node_input["script"].lines))
        print("publish: dry run, wrote script + ledger only")
        return {"published": "dry-run"}
    top = node_input["by_id"][node_input["picks"][0].story_id]["title"]
    ep = {"date": stamp, "title": f"HN Digest {stamp}: {top}",
          "description": "Today's stories: " + "; ".join(
              node_input["by_id"][p.story_id]["title"] for p in node_input["picks"]),
          "duration_s": node_input["duration_s"],
          "bytes": os.path.getsize(node_input["mp3"]),
          "pub_rfc822": now_show().strftime("%a, %d %b %Y %H:%M:%S %z")}
    with open(f"out/{stamp}-ledger.json", "w") as f:
        json.dump(node_input["ledger"], f, indent=1)
    with open(f"out/{stamp}-script.txt", "w") as f:
        f.write("\n".join(f"{l.speaker}: {l.text}"
                          for l in node_input["script"].lines))

    bucket_name = os.environ.get("PUBLISH_BUCKET")
    if not node_input["mp3"] or not bucket_name:
        with open("out/feed.xml", "w") as f:
            f.write(build_feed([ep], "http://localhost"))
        print("publish: local mode -> out/")
        return {"published": "local", "episode": ep}

    from google.cloud import storage
    base_url = os.environ.get(
        "PUBLIC_BASE_URL", f"https://storage.googleapis.com/{bucket_name}")
    bucket = storage.Client().bucket(bucket_name)
    manifest_blob = bucket.blob("manifest.json")
    episodes = (json.loads(manifest_blob.download_as_text())
                if manifest_blob.exists() else [])
    episodes = [e for e in episodes if e["date"] != stamp] + [ep]
    bucket.blob(f"episodes/{stamp}.mp3").upload_from_filename(
        node_input["mp3"], content_type="audio/mpeg")
    bucket.blob(f"episodes/{stamp}-ledger.json").upload_from_filename(
        f"out/{stamp}-ledger.json", content_type="application/json")
    bucket.blob(f"episodes/{stamp}-script.txt").upload_from_filename(
        f"out/{stamp}-script.txt", content_type="text/plain")
    manifest_blob.upload_from_string(json.dumps(episodes), content_type="application/json")
    bucket.blob("feed.xml").upload_from_string(
        build_feed(episodes, base_url), content_type="application/rss+xml")
    print(f"publish: {base_url}/feed.xml")
    return {"published": f"{base_url}/feed.xml", "episode": ep}


workflow = Workflow(
    name="hn_digest",
    edges=[
        ("START", fetch_candidates, curate, digest_stories, write_script,
         fact_check, review_router),
        (review_router, {"REWRITE": write_script,
                         "CUT": cut_failed,
                         "RENDER": render_tts}),
        (cut_failed, fact_check),
        (render_tts, publish),
    ],
)


async def main():
    runner = Runner(app_name="hn_digest", node=workflow,
                    session_service=InMemorySessionService(),
                    auto_create_session=True)
    events = await runner.run_debug("run", quiet=True)
    outputs = [e.output for e in events if getattr(e, "output", None) is not None]
    print("RESULT:", outputs[-1] if outputs else "no output")


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for env_name in ("NO_PROXY", "no_proxy"):
    current_no_proxy = os.environ.get(env_name, "")
    entries = {item.strip() for item in current_no_proxy.split(",") if item.strip()}
    entries.add("open.feishu.cn")
    os.environ[env_name] = ",".join(sorted(entries))

from shopops.config import load_settings
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient, PlatformTableSpec, text_field


TABLE_NAME = "达人筛选表"
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

TABLE_FIELDS = [
    "unique_key",
    "搜索关键词",
    "平台",
    "来源",
    "搜索排名",
    "达人名称",
    "抖音号",
    "粉丝数",
    "获赞数",
    "关注数",
    "认证/身份",
    "简介",
    "主页链接",
    "主页截图",
    "视频1封面截图",
    "视频1获赞/热度",
    "视频1封面URL",
    "视频2封面截图",
    "视频2获赞/热度",
    "视频2封面URL",
    "视频3封面截图",
    "视频3获赞/热度",
    "视频3封面URL",
    "视频1标题/可见文案",
    "视频2标题/可见文案",
    "视频3标题/可见文案",
    "评论来源作品ID",
    "评论来源作品标题",
    "评论接口状态",
    "评论抓取时间",
    "评论抓取失败原因",
    "真实评论条数",
    "评论接口返回总数",
    "评论原始数据JSON",
    "评论原始数据范围",
    "评论采样方式",
    "评论采样状态",
    "评论首屏截图1",
    "评论首屏截图2",
    "评论首屏截图3",
    "评论样本数",
    "有效评论数",
    "购买意图评论数",
    "使用问题评论数",
    "质疑评论数",
    "无效评论比例",
    "重复话术比例",
    "高频问题摘要",
    "购买意向样例3条",
    "质疑样例3条",
    "评论风险结论",
    "评论证据等级",
    "评论评分依据",
    "评论采样限制",
    "内容相关评分",
    "商业匹配评分",
    "评论有效性评分",
    "风险评分",
    "综合评分",
    "评分依据",
    "评分公式版本",
    "评分结论",
    "AI初筛等级",
    "AI初筛原因",
    "人工确认状态",
    "采集时间",
    "原始搜索卡片",
    "原始主页文本",
]


@dataclass
class SearchCandidate:
    name: str
    followers: str
    douyin_id: str
    rank: int
    raw_card: str
    source_page: str = "user"
    index_on_page: int = 0
    aweme_id: str = ""
    source_video_title: str = ""


def screening_table_spec() -> PlatformTableSpec:
    return PlatformTableSpec(
        env_name="FEISHU_TABLE_CREATOR_SCREENING",
        key="creator_screening",
        name=TABLE_NAME,
        fields=[text_field(name) for name in TABLE_FIELDS],
    )


class CreatorScreeningFeishuClient:
    def __init__(self) -> None:
        settings = load_settings()
        self.app_token = settings.feishu_app_token
        if not self.app_token:
            raise RuntimeError("FEISHU_APP_TOKEN is required")
        self.client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)

    def ensure_table(self) -> tuple[str, bool]:
        existing = self.client.list_tables(self.app_token)
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        table = self.client.ensure_table(self.app_token, screening_table_spec(), existing_by_name)
        table_id = str(table.get("table_id") or "")
        if not table_id:
            raise RuntimeError("Feishu create/reuse table did not return table_id")
        self.ensure_fields(table_id)
        return table_id, bool(table.get("reused"))

    def list_fields(self, table_id: str) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                params=params,
            )
            fields.extend(data.get("items", []) or [])
            page_token = data.get("page_token")
            if not data.get("has_more") or not page_token:
                break
        return fields

    def ensure_fields(self, table_id: str) -> list[str]:
        existing = {str(field.get("field_name")) for field in self.list_fields(table_id) if field.get("field_name")}
        created: list[str] = []
        for field_name in TABLE_FIELDS:
            if field_name in existing:
                continue
            self._request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                {"field_name": field_name, "type": 1},
            )
            created.append(field_name)
        return created

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{FEISHU_BASE_URL}{path}",
            headers=self.client.headers(),
            json=payload,
            params=params,
            timeout=30,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Feishu API returned non-JSON response: HTTP {response.status_code}") from exc
        if response.status_code >= 400:
            raise RuntimeError(f"Feishu API HTTP {response.status_code}: {body}")
        if body.get("code") != 0:
            raise RuntimeError(f"Feishu API error {body.get('code')}: {body.get('msg')}")
        return body.get("data") or {}

    def create_records(self, table_id: str, rows: list[dict[str, Any]]) -> list[str]:
        record_ids: list[str] = []
        for offset in range(0, len(rows), 500):
            chunk = rows[offset : offset + 500]
            data = self._request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create",
                {"records": [{"fields": row} for row in chunk]},
            )
            record_ids.extend(str(item.get("record_id") or "") for item in data.get("records", []) or [])
        return record_ids

    def readback_by_unique_keys(self, table_id: str, keys: set[str]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
                params=params,
            )
            for item in data.get("items", []) or []:
                fields = item.get("fields") or {}
                if fields.get("unique_key") in keys:
                    found.append(item)
            if not data.get("has_more"):
                return found
            page_token = data.get("page_token")


def normalize_user_card(text: str) -> SearchCandidate | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    if "你可能想找" in lines:
        return None
    name = lines[0]
    followers = ""
    douyin_id = ""
    for line in lines[1:]:
        if line.startswith("粉丝"):
            followers = line.replace("粉丝：", "").replace("粉丝:", "").strip()
        elif line.startswith("抖音号"):
            douyin_id = line.replace("抖音号：", "").replace("抖音号:", "").strip()
        elif not douyin_id and ("账号" in line or "官方号" in line or "授权号" in line):
            douyin_id = line
    if not name or not followers:
        return None
    return SearchCandidate(name=name, followers=followers, douyin_id=douyin_id, rank=0, raw_card=text, source_page="user")


def normalize_video_card(text: str) -> SearchCandidate | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return None
    name = lines[0]
    if name in {"商品·", "大家还在搜"} or "广告" in name:
        return None
    if not any(term in text for term in ("洗面奶", "洁面", "护肤", "控油", "祛痘", "毛孔", "黑头")):
        return None
    title = "\n".join(lines[1:4])
    return SearchCandidate(name=name, followers="", douyin_id="", rank=0, raw_card=text, source_page="general", source_video_title=title)


def parse_aweme_id(card_extra: str) -> str:
    try:
        payload = json.loads(card_extra or "{}")
    except json.JSONDecodeError:
        return ""
    return str(payload.get("search_result_id") or payload.get("aweme_id") or "")


def profile_stat(lines: list[str], label: str) -> str:
    for idx, line in enumerate(lines):
        if line == label and idx + 1 < len(lines):
            return lines[idx + 1]
    return ""


def profile_identity(lines: list[str], name: str, douyin_id: str) -> str:
    skip = {"获赞", "关注", "粉丝", name, f"抖音号\xa0{douyin_id}", f"抖音号 {douyin_id}"}
    for line in lines:
        if line in skip or re.match(r"^\d", line) or line.startswith("进入橱窗"):
            continue
        if "创作者" in line or "账号" in line or "官方" in line or "达人" in line:
            return line
    return ""


def profile_signature(lines: list[str], name: str, douyin_id: str) -> str:
    chunks: list[str] = []
    after_id = False
    for line in lines:
        normalized = line.replace("\xa0", " ")
        if normalized.startswith("抖音号"):
            after_id = True
            continue
        if not after_id:
            continue
        if line in {"进入橱窗", "作品", "喜欢"} or line.endswith("件好物"):
            break
        if "创作者" in line or line == name:
            continue
        chunks.append(line)
    return "\n".join(chunks[:4]).strip()


def parse_count(value: str) -> float:
    text = (value or "").replace("+", "").replace(",", "").strip().lower()
    if not text:
        return 0.0
    multiplier = 1.0
    if "亿" in text:
        multiplier = 100_000_000
    elif "万" in text or "w" in text:
        multiplier = 10_000
    elif "k" in text:
        multiplier = 1_000
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    return float(match.group(1)) * multiplier


def clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def ai_screen(keyword: str, name: str, signature: str, identity: str, videos: list[dict[str, str]]) -> tuple[str, str]:
    text = "\n".join([keyword, name, signature, identity, *[v.get("heat", "") for v in videos]])
    strong_terms = ["洗面奶", "洁面", "护肤", "美妆", "祛痘", "控油", "毛孔", "黑头", "旗舰店"]
    hits = [term for term in strong_terms if term in text]
    if any(term in text for term in ["洗面奶", "洁面"]) and len(hits) >= 2:
        return "A", "搜索词和主页/身份/作品信息高度命中：" + "、".join(hits[:5])
    if hits:
        return "B", "存在相关护肤/美妆关键词：" + "、".join(hits[:5])
    return "C", "公开可见信息未体现明显产品相关性"


def comment_signal_summary(keyword: str, text: str) -> dict[str, str]:
    purchase_terms = ["怎么买", "求链接", "链接", "同款", "在哪里买", "多少钱", "已下单", "想买", "种草"]
    question_terms = ["好用吗", "适合", "敏感肌", "油皮", "干皮", "痘痘", "黑头", "毛孔", "刺痛", "会不会"]
    doubt_terms = ["广告", "智商税", "踩雷", "没用", "假", "贵", "翻车", "不值", "骗人"]
    relevant_terms = [keyword, "洁面", "洗脸", "护肤", "控油", "毛孔", "黑头", "痘", "敏感肌", "油皮"]

    purchase_hits = [term for term in purchase_terms if term in text]
    question_hits = [term for term in question_terms if term in text]
    doubt_hits = [term for term in doubt_terms if term in text]
    relevant_hits = [term for term in relevant_terms if term in text]
    effective = len(set(purchase_hits + question_hits + doubt_hits + relevant_hits))
    sample_count = "首屏可见文本近似抽样" if text else "0"
    risk = "低" if doubt_hits == [] else "中"
    if len(doubt_hits) >= 3:
        risk = "高"
    evidence_level = "L1-弱证据"
    scoring_basis = "未直接采集评论区正文；仅用搜索卡片、公开视频页/主页首屏可见文本做弱信号判断，评论维度必须降权。"
    if purchase_hits or question_hits or doubt_hits:
        evidence_level = "L2-可见文本信号"
        scoring_basis = "公开首屏文本中出现购买/使用/质疑相关词，作为评论近似信号；未采评论用户身份，未做深翻页。"
    return {
        "评论采样方式": "第一阶段低风险采样：仅首屏可见评论/视频页文本信号，不滚动深挖，不采评论用户ID/头像/主页；授权后再做全量评论。",
        "评论采样状态": "已采公开首屏近似信号" if text else "未发现可采样公开评论文本",
        "评论样本数": sample_count,
        "有效评论数": str(effective),
        "购买意图评论数": str(len(purchase_hits)),
        "使用问题评论数": str(len(question_hits)),
        "质疑评论数": str(len(doubt_hits)),
        "无效评论比例": "无法可靠估算（未做批量评论抓取）",
        "重复话术比例": "无法可靠估算（未做批量评论抓取）",
        "高频问题摘要": "、".join((question_hits + relevant_hits)[:8]),
        "购买意向样例3条": "、".join(purchase_hits[:3]),
        "质疑样例3条": "、".join(doubt_hits[:3]),
        "评论风险结论": risk,
        "评论证据等级": evidence_level,
        "评论评分依据": scoring_basis,
        "评论采样限制": "非授权阶段不批量抓取评论，不进入评论用户主页，不采集评论用户ID/头像；当前只用于筛选排序，不能替代授权后的完整评论审计。",
    }


def score_creator(
    keyword: str,
    name: str,
    signature: str,
    identity: str,
    followers: str,
    likes: str,
    comment_summary: dict[str, str],
    videos: list[dict[str, str]],
) -> dict[str, str]:
    text = "\n".join([keyword, name, signature, identity, *[v.get("heat", "") for v in videos]])
    related_terms = ["洗面奶", "洁面", "洗脸", "护肤", "美妆", "控油", "油皮", "毛孔", "黑头", "祛痘", "旗舰店"]
    related_hits = [term for term in related_terms if term in text]
    fans = parse_count(followers)
    like_count = parse_count(likes)
    content_score = clamp_score(35 + len(set(related_hits)) * 9)
    business_score = clamp_score(35 + min(fans / 20_000, 25) + min(like_count / 200_000, 25))
    comment_effective = parse_count(comment_summary.get("有效评论数", "0"))
    evidence_level = comment_summary.get("评论证据等级", "")
    if evidence_level.startswith("L2") or evidence_level.startswith("L3"):
        comment_score = clamp_score(35 + min(comment_effective * 8, 30))
    else:
        comment_score = clamp_score(20 + min(comment_effective * 5, 15))
    risk_score = 85
    if comment_summary.get("评论风险结论") == "中":
        risk_score = 70
    elif comment_summary.get("评论风险结论") == "高":
        risk_score = 45
    if fans == 0:
        risk_score -= 15
    total = clamp_score(content_score * 0.35 + business_score * 0.25 + comment_score * 0.2 + risk_score * 0.2)
    conclusion = "A类候选-建议人工确认" if total >= 70 and content_score >= 65 else "B类候选-可复核" if total >= 55 else "C类候选-暂缓"
    return {
        "内容相关评分": str(content_score),
        "商业匹配评分": str(business_score),
        "评论有效性评分": str(comment_score),
        "风险评分": str(max(0, risk_score)),
        "综合评分": str(total),
        "评分依据": f"公式=内容35%+商业25%+评论20%+风险20%；相关词={','.join(related_hits[:8]) or '无'}；粉丝={followers or '未知'}；获赞={likes or '未知'}；评论证据={evidence_level or '未知'}；评论风险={comment_summary.get('评论风险结论', '')}",
        "评分公式版本": "creator-screening-v2-comment-evidence-weighted",
        "评分结论": conclusion,
    }


def format_comment_time(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def sanitize_comment(raw: dict[str, Any]) -> dict[str, Any]:
    user = raw.get("user") or {}
    return {
        "cid": str(raw.get("cid") or ""),
        "text": str(raw.get("text") or ""),
        "create_time": raw.get("create_time") or 0,
        "create_time_text": format_comment_time(raw.get("create_time")),
        "digg_count": raw.get("digg_count") or 0,
        "reply_comment_total": raw.get("reply_comment_total") or 0,
        "commenter_nickname": str(user.get("nickname") or ""),
    }


async def fetch_real_comments(page: Any, aweme_id: str, count: int = 20) -> dict[str, Any]:
    if not aweme_id:
        return {
            "status": "no_aweme_id",
            "comments": [],
            "total": 0,
            "has_more": False,
            "cursor": 0,
            "error": "candidate has no source aweme id",
        }
    try:
        data = await page.evaluate(
            """async ({awemeId, count}) => {
                const params = new URLSearchParams({
                    aid: '581610',
                    channel: 'channel_pc_web',
                    aweme_id: awemeId,
                    item_type: '0',
                    cursor: '0',
                    count: String(count),
                    platform: 'PC',
                    device_platform: 'webapp',
                    device_brand: 'Chrome'
                });
                const url = 'https://so.douyin.com/aweme/v1/web/comment/list/?' + params.toString();
                const response = await fetch(url, { method: 'GET' });
                const text = await response.text();
                try {
                    return { http_status: response.status, url, body: JSON.parse(text) };
                } catch (error) {
                    return { http_status: response.status, url, parse_error: String(error), raw_text: text.slice(0, 1000) };
                }
            }""",
            {"awemeId": aweme_id, "count": count},
        )
    except Exception as exc:
        return {
            "status": "fetch_failed",
            "comments": [],
            "total": 0,
            "has_more": False,
            "cursor": 0,
            "error": repr(exc),
        }
    body = data.get("body") or {}
    if data.get("http_status") != 200:
        return {
            "status": "http_error",
            "comments": [],
            "total": 0,
            "has_more": False,
            "cursor": 0,
            "error": json.dumps(data, ensure_ascii=False)[:800],
        }
    if body.get("status_code") != 0:
        return {
            "status": f"api_error_{body.get('status_code')}",
            "comments": [],
            "total": body.get("total") or 0,
            "has_more": bool(body.get("has_more")),
            "cursor": body.get("cursor") or 0,
            "error": str(body.get("status_msg") or body.get("prompts") or "")[:800],
        }
    comments = [sanitize_comment(item) for item in (body.get("comments") or []) if str(item.get("text") or "").strip()]
    return {
        "status": "success",
        "comments": comments,
        "total": body.get("total") or len(comments),
        "has_more": bool(body.get("has_more")),
        "cursor": body.get("cursor") or 0,
        "error": "",
        "url": data.get("url") or "",
    }


async def collect_search_candidates(page: Any, keyword: str, target: int, evidence_dir: Path) -> list[SearchCandidate]:
    seen: dict[str, SearchCandidate] = {}
    encoded = quote(keyword)
    pool_target = target
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for round_index in range(1, 5):
        general_url = f"https://so.douyin.com/s?keyword={encoded}&pd=general&source=normal_search&traffic_source=ZY1112&round={round_index}"
        await page.goto(general_url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(8_000)
        stale_scrolls = 0
        for scroll_index in range(12):
            before_count = len(seen)
            if scroll_index % 5 == 0:
                await page.screenshot(path=str(evidence_dir / f"general-{round_index:02d}-{scroll_index + 1:02d}.png"), full_page=False)
                try:
                    visible_text = await page.locator("body").inner_text(timeout=5_000)
                    (evidence_dir / f"general-{round_index:02d}-{scroll_index + 1:02d}.txt").write_text(
                        visible_text[:20000],
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            raw_video_cards: list[dict[str, str]] = await page.locator(
                '.SEARCH_CARD_CONTAINER[data-card-type-name="general_single_video"]'
            ).evaluate_all(
                """els => els.map(e => ({
                    text: (e.innerText || '').trim(),
                    extra: e.getAttribute('data-test-extra') || ''
                })).filter(item => item.text)"""
            )
            for index, item in enumerate(raw_video_cards):
                text = item.get("text") or ""
                candidate = normalize_video_card(text)
                if not candidate:
                    continue
                candidate.aweme_id = parse_aweme_id(item.get("extra") or "")
                if not candidate.aweme_id:
                    continue
                key = candidate.name
                if key not in seen:
                    candidate.rank = len(seen) + 1
                    candidate.index_on_page = index
                    seen[key] = candidate
            if len(seen) >= pool_target:
                break
            if len(seen) == before_count:
                stale_scrolls += 1
            else:
                stale_scrolls = 0
            if stale_scrolls >= 4:
                break
            await page.mouse.wheel(0, 1400)
            await page.wait_for_timeout(3_000)
            write_json(evidence_dir / "candidates.progress.json", {"candidate_count": len(seen), "pool_target": pool_target})
        if len(seen) >= pool_target:
            break

    for attempt in range(1, 11):
        if len(seen) >= pool_target:
            break
        url = f"https://so.douyin.com/s?keyword={encoded}&pd=user&source=normal_search&traffic_source=ZY1112"
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(8_000)
        await page.screenshot(path=str(evidence_dir / f"search-{attempt:02d}.png"), full_page=False)
        try:
            visible_text = await page.locator("body").inner_text(timeout=5_000)
            (evidence_dir / f"search-{attempt:02d}.txt").write_text(visible_text[:20000], encoding="utf-8")
        except Exception:
            pass
        raw_cards: list[str] = await page.locator(".card-item").evaluate_all(
            "els => els.map(e => (e.innerText || '').trim()).filter(Boolean)"
        )
        for index, text in enumerate(raw_cards):
            candidate = normalize_user_card(text)
            if not candidate:
                continue
            key = candidate.douyin_id or candidate.name
            if key not in seen:
                candidate.rank = len(seen) + 1
                candidate.index_on_page = index
                seen[key] = candidate
        await page.wait_for_timeout(2_000 + attempt * 500)
    candidates = list(seen.values())
    write_json(evidence_dir / "candidates.json", {"candidates": [candidate.__dict__ for candidate in candidates]})
    return candidates


async def open_candidate_profile(page: Any, candidate: SearchCandidate) -> bool:
    if candidate.source_page == "general":
        cards = page.locator('.SEARCH_CARD_CONTAINER[data-card-type-name="general_single_video"]')
        matched_by_aweme = False
        if candidate.aweme_id:
            card_selector = (
                '.SEARCH_CARD_CONTAINER[data-card-type-name="general_single_video"]'
                f'[data-test-extra*="{candidate.aweme_id}"]'
            )
            for _ in range(24):
                matched = page.locator(card_selector)
                if await matched.count():
                    cards = matched
                    matched_by_aweme = True
                    break
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(1_000)
            if not matched_by_aweme:
                return False
        if await cards.count() <= 0:
            return False
        card = cards.first if candidate.aweme_id else cards.nth(candidate.index_on_page)
        click_target = card.locator(".authorInfoContainer_f6b01")
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
                await click_target.click(timeout=5_000)
        except Exception:
            try:
                await click_target.click(timeout=5_000)
                await page.wait_for_timeout(8_000)
            except Exception:
                return False
        await page.wait_for_timeout(8_000)
        return True

    cards = page.locator(".card-item")
    if await cards.count() <= candidate.index_on_page:
        return False
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
            await cards.nth(candidate.index_on_page).click(timeout=5_000)
    except Exception:
        try:
            await cards.nth(candidate.index_on_page).click(timeout=5_000)
            await page.wait_for_timeout(8_000)
        except Exception:
            return False
    await page.wait_for_timeout(8_000)
    return True


async def collect_profile(page: Any, keyword: str, candidate: SearchCandidate, evidence_dir: Path) -> dict[str, Any] | None:
    encoded = quote(keyword)
    source_pd = "general" if candidate.source_page == "general" else "user"
    await page.goto(f"https://so.douyin.com/s?keyword={encoded}&pd={source_pd}&source=normal_search&traffic_source=ZY1112", wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(8_000)
    if candidate.source_page == "general":
        for _ in range(max(candidate.index_on_page // 5, 0)):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(1_500)
    try:
        real_comments = await asyncio.wait_for(fetch_real_comments(page, candidate.aweme_id, 20), timeout=15)
    except Exception as exc:
        real_comments = {
            "status": "comment_fetch_timeout",
            "comments": [],
            "total": 0,
            "has_more": False,
            "cursor": 0,
            "error": repr(exc),
        }
    if not await open_candidate_profile(page, candidate):
        return None

    profile_url = page.url
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", candidate.douyin_id or candidate.name)[:40] or f"creator_{candidate.rank}"
    profile_screenshot = evidence_dir / f"profile-{candidate.rank:02d}-{safe}.png"
    profile_screenshot_value = ""
    try:
        await page.screenshot(path=str(profile_screenshot), full_page=False, timeout=10_000)
        profile_screenshot_value = str(profile_screenshot)
    except Exception:
        profile_screenshot_value = ""
    body_text = await page.locator("body").inner_text(timeout=10_000)
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    likes = profile_stat(lines, "获赞")
    following = profile_stat(lines, "关注")
    followers = profile_stat(lines, "粉丝") or candidate.followers
    name = ""
    try:
        name = (await page.locator(".name").first.inner_text(timeout=2_000)).strip()
    except Exception:
        name = candidate.name
    douyin_id = candidate.douyin_id
    try:
        raw_id = (await page.locator(".aweme-id").first.inner_text(timeout=2_000)).strip()
        if raw_id:
            douyin_id = raw_id.replace("抖音号", "").replace("\xa0", " ").strip()
    except Exception:
        pass
    identity = profile_identity(lines, name, douyin_id)
    signature = profile_signature(lines, name, douyin_id)

    videos: list[dict[str, str]] = []
    covers = page.locator("img.user-post-cover_img")
    cover_count = min(await covers.count(), 3)
    for idx in range(cover_count):
        cover = covers.nth(idx)
        src = await cover.get_attribute("src") or ""
        box = await cover.bounding_box()
        shot_path = evidence_dir / f"profile-{candidate.rank:02d}-{safe}-video-{idx + 1}.png"
        try:
            await cover.screenshot(path=str(shot_path))
        except Exception:
            await page.screenshot(path=str(shot_path), full_page=False)
        heat = ""
        if box:
            heat = await page.evaluate(
                """({x, y}) => {
                    const elements = Array.from(document.elementsFromPoint(x + 18, y + 152));
                    const texts = elements.map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean);
                    return texts[0] || '';
                }""",
                {"x": box["x"], "y": box["y"]},
            )
        videos.append({"cover_url": src, "screenshot": str(shot_path), "heat": heat, "title": heat})

    level, reason = ai_screen(keyword, name, signature, identity, videos)
    comment_text_blob = "\n".join([str(item.get("text") or "") for item in real_comments.get("comments", [])])
    comment_summary = comment_signal_summary(keyword, "\n".join([candidate.raw_card, body_text, comment_text_blob]))
    real_comment_count = len(real_comments.get("comments") or [])
    if real_comments.get("status") == "success" and real_comment_count:
        comment_summary["评论采样状态"] = "已抓取真实公开评论"
        comment_summary["评论证据等级"] = "L3-真实评论接口抽样"
        comment_summary["评论样本数"] = str(real_comment_count)
        comment_summary["评论评分依据"] = "已通过 so.douyin.com 公开评论接口抓取真实评论文本抽样；评分按评论文本中的购买意图、使用问题、质疑风险和无效比例信号计算。"
        comment_summary["评论采样限制"] = "当前为公开接口首批评论抽样，不翻评论用户主页，不保存用户UID/头像；授权后可扩大到多页评论和回复链。"
    scoring = score_creator(keyword, name, signature, identity, followers, likes, comment_summary, videos)
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    unique_source = f"{keyword}|{douyin_id or name}|{collected_at}"
    unique_key = "creator_screening_" + hashlib.sha1(unique_source.encode("utf-8")).hexdigest()[:16]
    row = {
        "unique_key": unique_key,
        "搜索关键词": keyword,
        "平台": "抖音",
        "来源": "so.douyin.com 移动端用户搜索可见结果"
        if candidate.source_page == "user"
        else "so.douyin.com 移动端综合搜索视频作者可见结果",
        "搜索排名": str(candidate.rank),
        "达人名称": name,
        "抖音号": douyin_id,
        "粉丝数": followers,
        "获赞数": likes,
        "关注数": following,
        "认证/身份": identity,
        "简介": signature,
        "主页链接": profile_url,
        "主页截图": profile_screenshot_value,
        "评论来源作品ID": candidate.aweme_id,
        "评论来源作品标题": candidate.source_video_title,
        "评论接口状态": str(real_comments.get("status") or ""),
        "评论抓取时间": collected_at,
        "评论抓取失败原因": str(real_comments.get("error") or ""),
        "真实评论条数": str(real_comment_count),
        "评论接口返回总数": str(real_comments.get("total") or real_comment_count),
        "评论原始数据JSON": json.dumps(real_comments.get("comments") or [], ensure_ascii=False, separators=(",", ":")),
        "评论原始数据范围": "so.douyin.com 评论接口首批公开评论；字段保留 cid/text/create_time/digg_count/reply_comment_total/commenter_nickname，不保存用户UID/头像/主页。",
        **comment_summary,
        **scoring,
        "AI初筛等级": level,
        "AI初筛原因": reason,
        "人工确认状态": "待确认",
        "采集时间": collected_at,
        "原始搜索卡片": candidate.raw_card,
        "原始主页文本": body_text[:1800],
    }
    for idx in range(3):
        video = videos[idx] if idx < len(videos) else {}
        row[f"视频{idx + 1}封面截图"] = video.get("screenshot", "")
        row[f"视频{idx + 1}获赞/热度"] = video.get("heat", "")
        row[f"视频{idx + 1}封面URL"] = video.get("cover_url", "")
        row[f"视频{idx + 1}标题/可见文案"] = video.get("title", "")
        row[f"评论首屏截图{idx + 1}"] = ""
    return row


def row_profile_key(row: dict[str, Any]) -> str:
    return str(row.get("主页链接") or row.get("抖音号") or row.get("达人名称") or "")


async def crawl(
    keyword: str,
    target: int,
    evidence_dir: Path,
    exclude_profiles: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from playwright.async_api import async_playwright

    evidence_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page(viewport={"width": 390, "height": 844}, user_agent=MOBILE_USER_AGENT)
        candidates = await collect_search_candidates(page, keyword, target, evidence_dir)
        rows: list[dict[str, Any]] = []
        seen_profiles: set[str] = set(exclude_profiles or set())
        for candidate in candidates:
            if len(rows) >= target:
                break
            try:
                row = await collect_profile(page, keyword, candidate, evidence_dir)
            except Exception as exc:
                write_json(
                    evidence_dir / f"error-candidate-{candidate.rank:02d}.json",
                    {"candidate": candidate.__dict__, "error": repr(exc)},
                )
                row = None
            if row:
                profile_key = row_profile_key(row)
                if profile_key in seen_profiles:
                    await page.wait_for_timeout(1_500)
                    continue
                seen_profiles.add(profile_key)
                rows.append(row)
                write_json(evidence_dir / "rows.partial.json", {"rows": rows})
            await page.wait_for_timeout(1_500)
        await browser.close()
    return rows, {"candidate_count": len(candidates), "saved_screenshots_dir": str(evidence_dir)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def async_main(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.evidence_dir) / f"creator-screening-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    seed_rows: list[dict[str, Any]] = []
    if args.seed_rows:
        seed_payload = json.loads(Path(args.seed_rows).read_text(encoding="utf-8"))
        seed_rows = list(seed_payload.get("rows") or [])
    seed_keys = {row_profile_key(row) for row in seed_rows if row_profile_key(row)}
    missing_target = max(args.target - len(seed_rows), 0)
    new_rows: list[dict[str, Any]] = []
    crawl_meta: dict[str, Any] = {"candidate_count": 0, "saved_screenshots_dir": str(evidence_dir)}
    if missing_target:
        new_rows, crawl_meta = await crawl(args.keyword, missing_target, evidence_dir, seed_keys)
    rows = seed_rows + new_rows
    write_json(evidence_dir / "rows.json", {"rows": rows})
    if len(rows) < args.target:
        summary = {
            "status": "blocked_insufficient_visible_creators",
            "keyword": args.keyword,
            "target": args.target,
            "collected": len(rows),
            "seeded": len(seed_rows),
            "new_collected": len(new_rows),
            "crawl_meta": crawl_meta,
            "rows_path": str(evidence_dir / "rows.json"),
            "reason": "Douyin mobile user search exposed fewer clickable creator profiles than requested in the visible public result set.",
        }
        write_json(evidence_dir / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 3

    feishu = CreatorScreeningFeishuClient()
    table_id, reused = feishu.ensure_table()
    record_ids = feishu.create_records(table_id, rows)
    keys = {row["unique_key"] for row in rows}
    readback = feishu.readback_by_unique_keys(table_id, keys)
    readback_keys = {(item.get("fields") or {}).get("unique_key") for item in readback}
    missing = sorted(keys - readback_keys)
    summary = {
        "status": "success" if not missing and len(rows) == args.target else "readback_failed",
        "keyword": args.keyword,
        "target": args.target,
        "collected": len(rows),
        "seeded": len(seed_rows),
        "new_collected": len(new_rows),
        "feishu": {
            "table_name": TABLE_NAME,
            "table_id": table_id,
            "table_reused": reused,
            "created_record_ids": record_ids,
            "created_count": len(record_ids),
            "readback_count": len(readback),
            "missing_unique_keys": missing,
        },
        "crawl_meta": crawl_meta,
        "rows_path": str(evidence_dir / "rows.json"),
    }
    write_json(evidence_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "success" else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl Douyin creator candidates and write them to Feishu Bitable.")
    parser.add_argument("--keyword", default="洗面奶")
    parser.add_argument("--target", type=int, default=20)
    parser.add_argument("--evidence-dir", default="docs/live-evidence")
    parser.add_argument("--seed-rows", default="")
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())

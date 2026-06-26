from __future__ import annotations

import argparse
import base64
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
import urllib.request

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
DEFAULT_CREATOR_CDP_URL = "http://127.0.0.1:9224"
DEFAULT_CREATOR_CDP_PROFILE_ROOT = Path(os.environ.get("SHOPOPS_CREATOR_CDP_PROFILE_ROOT", str(ROOT / ".tmp" / "ShopOpsCdpProfiles")))
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
    "内容相关度",
    "普通视频互动情况",
    "评论原始样本",
    "评论分析",
    "评论可信度评分",
    "评论可信度等级",
    "最终结论",
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
    "普通视频样本数",
    "普通视频样本JSON",
    "普通视频采样说明",
    "普通视频平均热度",
    "普通视频中位热度",
    "粉赞互动诊断",
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
    "ROI筛选分",
    "ROI分层",
    "互动稳定性评分",
    "注水风险评分",
    "粉赞错配风险",
    "首测建议",
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


def parse_video_id_from_url(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/(?:video|note)/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"(?:aweme_id|modal_id|vid)=(\d+)", url)
    return match.group(1) if match else ""

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


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def video_heat_summary(videos: list[dict[str, str]]) -> tuple[str, str]:
    heats = [parse_count(video.get("heat", "")) for video in videos]
    heats = [value for value in heats if value > 0]
    if not heats:
        return "", ""
    return str(int(round(sum(heats) / len(heats)))), str(int(round(median(heats))))


def follower_like_diagnosis(followers: str, videos: list[dict[str, str]]) -> str:
    follower_count = parse_count(followers)
    heats = [parse_count(video.get("heat", "")) for video in videos]
    heats = [value for value in heats if value > 0]
    if not follower_count or not heats:
        return "缺粉丝或普通视频热度，暂不能判断粉赞错配"
    median_heat = median(heats)
    ratio = follower_count / max(median_heat, 1)
    if follower_count >= 100_000 and median_heat < 100:
        return f"高风险：粉丝{int(follower_count)}，普通视频中位热度仅{int(median_heat)}"
    if ratio >= 1000:
        return f"高风险：粉丝/普通视频中位热度比约{ratio:.0f}，疑似粉丝质量弱或互动断层"
    if ratio >= 500:
        return f"中风险：粉丝/普通视频中位热度比约{ratio:.0f}，需人工复核近30条视频"
    return f"暂未发现明显粉赞错配：粉丝/普通视频中位热度比约{ratio:.0f}"


async def collect_profile_videos(page: Any, evidence_dir: Path, safe: str, rank: int, limit: int) -> list[dict[str, str]]:
    videos: list[dict[str, str]] = []
    seen_src: set[str] = set()
    stale_scrolls = 0
    target = max(1, min(limit, 30))
    for _ in range(10):
        before = len(videos)
        covers = page.locator("img.user-post-cover_img")
        cover_count = await covers.count()
        for idx in range(cover_count):
            if len(videos) >= target:
                break
            cover = covers.nth(idx)
            src = await cover.get_attribute("src") or ""
            if not src or src in seen_src:
                continue
            card_text = ""
            try:
                card_text = await cover.evaluate(
                    """el => {
                        let node = el;
                        for (let depth = 0; depth < 7 && node; depth += 1, node = node.parentElement) {
                            const text = (node.innerText || node.textContent || '').trim();
                            if (text) return text;
                        }
                        return '';
                    }"""
                )
            except Exception:
                card_text = ""
            video_url = ""
            try:
                video_url = await cover.evaluate(
                    """el => {
                        let node = el;
                        for (let depth = 0; depth < 8 && node; depth += 1, node = node.parentElement) {
                            const direct = node.matches && node.matches('a[href]') ? node.href : '';
                            const nested = node.querySelector ? (node.querySelector('a[href*="/video/"],a[href*="/note/"]') || {}).href || '' : '';
                            const href = direct || nested;
                            if (href) return href;
                        }
                        return '';
                    }"""
                )
            except Exception:
                video_url = ""
            aweme_id = parse_video_id_from_url(video_url)
            is_pinned = "置顶" in card_text
            seen_src.add(src)
            if is_pinned:
                continue
            box = await cover.bounding_box()
            heat = ""
            if box:
                try:
                    heat = await page.evaluate(
                        """({x, y}) => {
                            const elements = Array.from(document.elementsFromPoint(x + 18, y + 152));
                            const texts = elements.map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean);
                            return texts[0] || '';
                        }""",
                        {"x": box["x"], "y": box["y"]},
                    )
                except Exception:
                    heat = ""
            shot_value = ""
            if len(videos) < 3:
                shot_path = evidence_dir / f"profile-{rank:02d}-{safe}-video-{len(videos) + 1}.png"
                try:
                    await cover.screenshot(path=str(shot_path))
                    shot_value = str(shot_path)
                except Exception:
                    shot_value = ""
            videos.append(
                {
                    "sample_rank": str(len(videos) + 1),
                    "cover_url": src,
                    "video_url": video_url,
                    "aweme_id": aweme_id,
                    "screenshot": shot_value,
                    "heat": heat,
                    "title": card_text[:160],
                    "is_pinned": "false",
                    "sample_scope": "profile_normal_video_excluding_visible_pinned",
                }
            )
        if len(videos) >= target:
            break
        stale_scrolls = stale_scrolls + 1 if len(videos) == before else 0
        if stale_scrolls >= 3:
            break
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(1_500)
    return videos


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


COMMENT_USAGE_TERMS = [
    "\u6cb9\u76ae", "\u5e72\u76ae", "\u654f\u611f\u808c", "\u75d8\u808c", "\u9ed1\u5934", "\u6bdb\u5b54", "\u95ed\u53e3", "\u51fa\u6cb9", "\u62d4\u5e72", "\u7d27\u7ef7", "\u6e29\u548c", "\u63a7\u6cb9", "\u6e05\u6d01\u529b", "\u523a\u75db", "\u5c4f\u969c"
]
COMMENT_PURCHASE_TERMS = ["\u591a\u5c11\u94b1", "\u54ea\u91cc\u4e70", "\u94fe\u63a5", "\u600e\u4e48\u4e70", "\u6709\u5238\u5417", "\u540c\u6b3e", "\u5e97\u94fa", "\u6c42\u94fe\u63a5", "\u5165\u624b", "\u4e0b\u5355"]
COMMENT_QUESTION_TERMS = ["\u5417", "\uff1f", "?", "\u9002\u5408", "\u80fd\u4e0d\u80fd", "\u4f1a\u4e0d\u4f1a", "\u53ef\u4ee5", "\u600e\u4e48\u9009", "\u63a8\u8350"]
COMMENT_DOUBT_TERMS = ["\u5e7f\u544a", "\u667a\u5546\u7a0e", "\u6c34\u519b", "\u6ca1\u7528", "\u771f\u7684\u5047\u7684", "\u592a\u8d35", "\u8e29\u96f7", "\u7ffb\u8f66", "\u9a97\u4eba", "\u4e0d\u503c"]
COMMENT_LOW_VALUE_TERMS = {"\u597d\u7528", "\u4e0d\u9519", "\u79cd\u8349", "\u79cd\u8349\u4e86", "666", "\u6765\u4e86", "\u652f\u6301", "\u54c8\u54c8", "\u54c8\u54c8\u54c8"}
COMMENT_RELEVANT_TERMS = ["\u6d17\u9762\u5976", "\u6d01\u9762", "\u6d17\u8138", "\u62a4\u80a4", "\u63a7\u6cb9", "\u6bdb\u5b54", "\u9ed1\u5934", "\u75d8", "\u654f\u611f\u808c", "\u6cb9\u76ae", "\u6e05\u6d01"]


def normalize_comment_text(text: str) -> str:
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub("[\uFF0C\u3002\uFF01\uFF1F\u3001,.!?:\uFF1A\uFF1B;~\uFF5E\\-\u2014_\uFF08\uFF09()\u3010\u3011\\[\\]{}]", "", text)
    return text.lower()


def comment_texts(raw_comments: list[dict[str, Any]], limit: int = 80) -> list[str]:
    texts: list[str] = []
    for item in raw_comments:
        text = str(item.get("text") or "").strip()
        if text:
            texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def is_low_value_comment(text: str) -> bool:
    normalized = normalize_comment_text(text)
    if len(normalized) <= 1:
        return True
    if normalized in COMMENT_LOW_VALUE_TERMS:
        return True
    if re.fullmatch("(6+|\u54c8+|\u652f\u6301|\u6765\u4e86|\u6253\u5361)", normalized):
        return True
    return False


def count_text_hits(texts: list[str], terms: list[str]) -> list[str]:
    return [text for text in texts if any(term in text for term in terms)]


def comment_credibility_fields(keyword: str, raw_comments: list[dict[str, Any]], context_text: str = "") -> dict[str, str]:
    texts = comment_texts(raw_comments)
    sample_count = len(texts)
    if not texts and context_text:
        texts = [line.strip() for line in context_text.splitlines() if line.strip()][:20]
        sample_count = 0
    meaningful = [text for text in texts if not is_low_value_comment(text)]
    normalized = [normalize_comment_text(text) for text in meaningful if normalize_comment_text(text)]
    duplicate_rate = (len(normalized) - len(set(normalized))) / len(normalized) if normalized else 0.0
    low_value_rate = (len(texts) - len(meaningful)) / len(texts) if texts else 1.0
    usage_hits = count_text_hits(meaningful, COMMENT_USAGE_TERMS)
    purchase_hits = count_text_hits(meaningful, COMMENT_PURCHASE_TERMS)
    question_hits = count_text_hits(meaningful, COMMENT_QUESTION_TERMS)
    doubt_hits = count_text_hits(meaningful, COMMENT_DOUBT_TERMS)
    relevant_terms = list(dict.fromkeys([keyword, *COMMENT_RELEVANT_TERMS]))
    relevant_hits = count_text_hits(meaningful, relevant_terms)
    relevant_rate = len(relevant_hits) / len(texts) if texts else 0.0

    score = 0
    score += 25 if len(usage_hits) >= 5 else 15 if len(usage_hits) >= 2 else 8 if usage_hits else 0
    score += 20 if len(purchase_hits) >= 3 else 10 if purchase_hits else 0
    score += 20 if len(question_hits) >= 5 else 10 if len(question_hits) >= 2 else 0
    if 0 < len(doubt_hits) <= max(1, len(texts) * 0.2):
        score += 15
    score += 10 if relevant_rate >= 0.35 else 5 if relevant_rate >= 0.15 else 0
    score += 10 if sample_count >= 30 else 5 if sample_count >= 10 else 0
    if low_value_rate > 0.5:
        score -= 20
    elif low_value_rate > 0.3:
        score -= 10
    if duplicate_rate > 0.3:
        score -= 20
    elif duplicate_rate > 0.15:
        score -= 10
    if relevant_rate < 0.12 and texts:
        score -= 15
    score = clamp_score(score)
    if sample_count < 10:
        score = min(score, 39)
        level = "\u6837\u672c\u4e0d\u8db3"
    elif score >= 80:
        level = "\u9ad8"
    elif score >= 60:
        level = "\u4e2d"
    elif score >= 40:
        level = "\u4f4e"
    else:
        level = "\u5dee"

    analysis_parts = [f"\u91c7\u6837{sample_count}\u6761\u771f\u5b9e\u8bc4\u8bba" if sample_count else "\u672a\u83b7\u5f97\u8db3\u91cf\u771f\u5b9e\u8bc4\u8bba\u6837\u672c"]
    if usage_hits:
        analysis_parts.append(f"\u6709{len(usage_hits)}\u6761\u63d0\u5230\u80a4\u8d28/\u6e05\u6d01/\u63a7\u6cb9\u7b49\u4f7f\u7528\u573a\u666f")
    if purchase_hits:
        analysis_parts.append(f"\u6709{len(purchase_hits)}\u6761\u8d2d\u4e70\u610f\u5411")
    if question_hits:
        analysis_parts.append(f"\u6709{len(question_hits)}\u6761\u5177\u4f53\u95ee\u9898/\u54a8\u8be2")
    if doubt_hits:
        analysis_parts.append(f"\u6709{len(doubt_hits)}\u6761\u8d28\u7591\u6216\u8d1f\u9762\u53cd\u9988")
    analysis_parts.append(f"\u65e0\u610f\u4e49\u8bc4\u8bba\u7ea6{low_value_rate:.0%}\uff0c\u91cd\u590d\u8bdd\u672f\u7ea6{duplicate_rate:.0%}")
    if level == "\u9ad8":
        analysis_parts.append("\u6574\u4f53\u8bc4\u8bba\u8ba8\u8bba\u5177\u4f53\uff0c\u53ef\u4fe1\u5ea6\u9ad8")
    elif level == "\u4e2d":
        analysis_parts.append("\u8bc4\u8bba\u6709\u4e00\u5b9a\u6709\u6548\u8ba8\u8bba\uff0c\u5efa\u8bae\u4eba\u5de5\u590d\u6838")
    elif level == "\u6837\u672c\u4e0d\u8db3":
        analysis_parts.append("\u6837\u672c\u4e0d\u8db3\uff0c\u4e0d\u4f5c\u4e3a\u9ad8\u4f18\u5148\u5224\u65ad\u4f9d\u636e")
    else:
        analysis_parts.append("\u6709\u6548\u8ba8\u8bba\u504f\u5f31\u6216\u6c34\u8bc4\u98ce\u9669\u504f\u9ad8")

    return {
        "\u8bc4\u8bba\u539f\u59cb\u6837\u672c": "\n".join(texts[:80])[:6000],
        "\u8bc4\u8bba\u5206\u6790": "\uff1b".join(analysis_parts),
        "\u8bc4\u8bba\u53ef\u4fe1\u5ea6\u8bc4\u5206": str(score),
        "\u8bc4\u8bba\u53ef\u4fe1\u5ea6\u7b49\u7ea7": level,
    }


def content_relevance_level(score: Any) -> str:
    value = parse_count(score)
    if value >= 60:
        return "\u9ad8"
    if value >= 45:
        return "\u4e2d"
    return "\u4f4e"


def interaction_level(scoring: dict[str, str], videos: list[dict[str, str]]) -> str:
    interaction = parse_count(scoring.get("\u4e92\u52a8\u7a33\u5b9a\u6027\u8bc4\u5206", "0"))
    water_risk = parse_count(scoring.get("\u6ce8\u6c34\u98ce\u9669\u8bc4\u5206", "0"))
    if water_risk >= 65 or interaction < 45:
        return "\u5f02\u5e38"
    if interaction >= 70 and len(videos) >= 10:
        return "\u7a33\u5b9a"
    return "\u4e00\u822c"


def final_creator_decision(content_level: str, interaction: str, comment_score: str, comment_level: str) -> str:
    score = parse_count(comment_score)
    if content_level == "\u9ad8" and interaction in {"\u7a33\u5b9a", "\u4e00\u822c"} and score >= 75 and comment_level != "\u6837\u672c\u4e0d\u8db3":
        return "A\u7c7b\uff1a\u4f18\u5148\u8054\u7cfb"
    if content_level in {"\u9ad8", "\u4e2d"} and interaction != "\u5f02\u5e38" and score >= 60 and comment_level != "\u6837\u672c\u4e0d\u8db3":
        return "B\u7c7b\uff1a\u4eba\u5de5\u590d\u6838"
    if content_level == "\u4f4e" or interaction == "\u5f02\u5e38" or score < 40:
        return "D\u7c7b\uff1a\u6dd8\u6c70"
    return "C\u7c7b\uff1a\u6682\u4e0d\u4f18\u5148"


def concise_decision_fields(scoring: dict[str, str], comment_fields: dict[str, str], videos: list[dict[str, str]]) -> dict[str, str]:
    relevance = content_relevance_level(scoring.get("\u5185\u5bb9\u76f8\u5173\u8bc4\u5206", "0"))
    interaction = interaction_level(scoring, videos)
    final = final_creator_decision(relevance, interaction, comment_fields.get("\u8bc4\u8bba\u53ef\u4fe1\u5ea6\u8bc4\u5206", "0"), comment_fields.get("\u8bc4\u8bba\u53ef\u4fe1\u5ea6\u7b49\u7ea7", ""))
    return {
        "\u5185\u5bb9\u76f8\u5173\u5ea6": relevance,
        "\u666e\u901a\u89c6\u9891\u4e92\u52a8\u60c5\u51b5": interaction,
        **comment_fields,
        "\u6700\u7ec8\u7ed3\u8bba": final,
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
    video_heats = [parse_count(video.get("heat", "")) for video in videos]
    video_heats = [value for value in video_heats if value > 0]
    median_heat = median(video_heats) if video_heats else 0.0
    avg_heat = sum(video_heats) / len(video_heats) if video_heats else 0.0
    low_video_rate = len([value for value in video_heats if value < 100]) / len(video_heats) if video_heats else 1.0
    follower_heat_ratio = fans / max(median_heat, 1) if fans else 0.0

    content_score = clamp_score(35 + len(set(related_hits)) * 9)
    business_score = clamp_score(35 + min(fans / 20_000, 25) + min(like_count / 200_000, 25))
    comment_effective = parse_count(comment_summary.get("有效评论数", "0"))
    evidence_level = comment_summary.get("评论证据等级", "")
    if evidence_level.startswith("L2") or evidence_level.startswith("L3"):
        comment_score = clamp_score(35 + min(comment_effective * 8, 30))
    else:
        comment_score = clamp_score(20 + min(comment_effective * 5, 15))

    interaction_score = clamp_score(
        25
        + min(len(video_heats), 30) * 1.2
        + min(median_heat / 40, 18)
        + min(avg_heat / 80, 14)
        + min(comment_effective * 2, 8)
        - low_video_rate * 10
    )

    water_risk = 10
    mismatch_labels: list[str] = []
    if not video_heats:
        water_risk += 25
        mismatch_labels.append("缺普通视频互动样本")
    if fans >= 100_000 and median_heat < 100:
        water_risk += 35
        mismatch_labels.append("粉丝高但普通视频中位热度低")
    elif follower_heat_ratio >= 1000:
        water_risk += 30
        mismatch_labels.append("粉丝/普通视频中位热度比过高")
    elif follower_heat_ratio >= 500:
        water_risk += 18
        mismatch_labels.append("粉赞互动偏弱，需复核")
    if low_video_rate >= 0.7 and len(video_heats) >= 5:
        water_risk += 15
        mismatch_labels.append("多数普通视频热度偏低")
    if comment_summary.get("评论风险结论") == "中":
        water_risk += 12
    elif comment_summary.get("评论风险结论") == "高":
        water_risk += 25
    if any(term in text for term in ["官方", "旗舰店", "直播间", "专场", "商家"]):
        water_risk += 18
        mismatch_labels.append("疑似品牌/商家/直播间账号")
    water_risk = clamp_score(water_risk)

    risk_score = clamp_score(100 - water_risk)
    total = clamp_score(content_score * 0.35 + business_score * 0.2 + comment_score * 0.2 + risk_score * 0.15 + interaction_score * 0.1)
    roi_score = clamp_score(content_score * 0.3 + comment_score * 0.2 + interaction_score * 0.25 + risk_score * 0.25)

    if roi_score >= 82 and water_risk <= 35 and content_score >= 65:
        roi_tier = "S-优先联系"
        first_test = "优先报价；建议寄样+低基础费+佣金，首测预算500-700元"
    elif roi_score >= 70 and water_risk <= 50 and content_score >= 55:
        roi_tier = "A-可联系报价"
        first_test = "联系报价；先要近30条普通视频数据，首测控制在500元左右"
    elif roi_score >= 58:
        roi_tier = "B-待补采复核"
        first_test = "暂不付款；补采评论、普通视频和报价后再定"
    elif any(term in text for term in ["官方", "旗舰店", "直播间", "专场", "商家"]):
        roi_tier = "D-非达人池"
        first_test = "移出达人池；品牌/商家/直播间账号另行评估"
    else:
        roi_tier = "C-暂缓投放"
        first_test = "首轮不投；除非报价极低且人工复核通过"

    conclusion = "A类候选-建议人工确认" if total >= 70 and content_score >= 65 else "B类候选-可复核" if total >= 55 else "C类候选-暂缓"
    mismatch_text = "；".join(mismatch_labels) if mismatch_labels else "暂未发现明显粉赞错配"
    return {
        "内容相关评分": str(content_score),
        "商业匹配评分": str(business_score),
        "评论有效性评分": str(comment_score),
        "风险评分": str(max(0, risk_score)),
        "综合评分": str(total),
        "评分依据": f"公式=内容35%+商业20%+评论20%+风险15%+互动10%；相关词={','.join(related_hits[:8]) or '无'}；粉丝={followers or '未知'}；获赞={likes or '未知'}；评论证据={evidence_level or '未知'}；评论风险={comment_summary.get('评论风险结论', '')}；普通视频样本={len(video_heats)}；中位热度={int(median_heat)}",
        "评分公式版本": "creator-screening-v3-roi-water-risk",
        "评分结论": conclusion,
        "ROI筛选分": str(roi_score),
        "ROI分层": roi_tier,
        "互动稳定性评分": str(interaction_score),
        "注水风险评分": str(water_risk),
        "粉赞错配风险": mismatch_text,
        "首测建议": first_test,
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
                const target = Math.max(1, Math.min(Number(count) || 20, 100));
                const pageSize = Math.min(50, target);
                const comments = [];
                const pages = [];
                let cursor = 0;
                let hasMore = true;
                let total = 0;
                let lastUrl = '';
                for (let pageIndex = 0; pageIndex < 5 && comments.length < target && hasMore; pageIndex += 1) {
                    const params = new URLSearchParams({
                        aid: '581610',
                        channel: 'channel_pc_web',
                        aweme_id: awemeId,
                        item_type: '0',
                        cursor: String(cursor),
                        count: String(pageSize),
                        platform: 'PC',
                        device_platform: 'webapp',
                        device_brand: 'Chrome'
                    });
                    const url = 'https://so.douyin.com/aweme/v1/web/comment/list/?' + params.toString();
                    lastUrl = url;
                    const response = await fetch(url, { method: 'GET' });
                    const text = await response.text();
                    let body;
                    try {
                        body = JSON.parse(text);
                    } catch (error) {
                        return { http_status: response.status, url, parse_error: String(error), raw_text: text.slice(0, 1000), pages };
                    }
                    pages.push({ http_status: response.status, status_code: body.status_code, cursor, returned: (body.comments || []).length });
                    if (response.status !== 200 || body.status_code !== 0) {
                        return { http_status: response.status, url, body, pages, partial_comments: comments, partial_total: total };
                    }
                    total = body.total || total || 0;
                    for (const item of (body.comments || [])) {
                        if ((item.text || '').trim()) comments.push(item);
                        if (comments.length >= target) break;
                    }
                    hasMore = Boolean(body.has_more);
                    cursor = body.cursor || 0;
                    if (!cursor) break;
                }
                return { http_status: 200, url: lastUrl, body: { status_code: 0, comments, total, has_more: hasMore, cursor }, pages };
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
            "comments": [sanitize_comment(item) for item in (data.get("partial_comments") or []) if str(item.get("text") or "").strip()],
            "total": body.get("total") or data.get("partial_total") or 0,
            "has_more": bool(body.get("has_more")),
            "cursor": body.get("cursor") or 0,
            "error": str(body.get("status_msg") or body.get("prompts") or "")[:800],
            "pages": data.get("pages") or [],
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
        "pages": data.get("pages") or [],
    }


def comment_dedupe_key(item: dict[str, Any]) -> str:
    cid = str(item.get("cid") or "").strip()
    if cid:
        return "cid:" + cid
    text = normalize_comment_text(str(item.get("text") or ""))
    return "text:" + text[:80]


def merge_comment_batches(batches: list[tuple[str, dict[str, Any]]], count: int) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    errors: list[str] = []
    statuses: list[str] = []
    total = 0
    has_more = False
    for aweme_id, payload in batches:
        statuses.append(str(payload.get("status") or ""))
        total += int(payload.get("total") or 0)
        has_more = has_more or bool(payload.get("has_more"))
        if payload.get("error"):
            errors.append(f"{aweme_id}:{payload.get('error')}")
        for page_info in payload.get("pages") or []:
            if isinstance(page_info, dict):
                page_copy = dict(page_info)
                page_copy["source_aweme_id"] = aweme_id
                pages.append(page_copy)
        for item in payload.get("comments") or []:
            if len(merged) >= count:
                break
            key = comment_dedupe_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            comment = dict(item)
            comment["source_aweme_id"] = aweme_id
            merged.append(comment)
        if len(merged) >= count:
            break
    success = bool(merged)
    return {
        "status": "success" if success else (statuses[0] if statuses else "no_comments"),
        "comments": merged,
        "total": total or len(merged),
        "has_more": has_more,
        "cursor": 0,
        "error": "; ".join(errors)[:800],
        "pages": pages,
        "source_count": len([item for item in batches if item[0]]),
        "source_statuses": statuses,
    }


async def fetch_comments_from_multiple_videos(
    page: Any,
    primary_aweme_id: str,
    videos: list[dict[str, str]],
    count: int,
    max_sources: int = 6,
) -> dict[str, Any]:
    aweme_ids: list[str] = []
    for aweme_id in [primary_aweme_id, *[video.get("aweme_id", "") for video in videos]]:
        aweme_id = str(aweme_id or "").strip()
        if aweme_id and aweme_id not in aweme_ids:
            aweme_ids.append(aweme_id)
        if len(aweme_ids) >= max_sources:
            break
    batches: list[tuple[str, dict[str, Any]]] = []
    for index, aweme_id in enumerate(aweme_ids):
        remaining = max(1, count - sum(len(batch.get("comments") or []) for _, batch in batches))
        request_count = count if index == 0 else min(count, max(20, remaining))
        try:
            payload = await asyncio.wait_for(fetch_real_comments(page, aweme_id, request_count), timeout=25)
        except Exception as exc:
            payload = {
                "status": "comment_fetch_timeout",
                "comments": [],
                "total": 0,
                "has_more": False,
                "cursor": 0,
                "error": repr(exc),
            }
        batches.append((aweme_id, payload))
        if len(merge_comment_batches(batches, count).get("comments") or []) >= count:
            break
        if index + 1 < len(aweme_ids):
            await page.wait_for_timeout(700)
    return merge_comment_batches(batches, count)

async def collect_search_candidates(page: Any, keyword: str, target: int, evidence_dir: Path) -> list[SearchCandidate]:
    seen: dict[str, SearchCandidate] = {}
    encoded = quote(keyword)
    pool_target = max(target, min(target * 3, target + 80))
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


async def collect_profile(page: Any, keyword: str, candidate: SearchCandidate, evidence_dir: Path, comments_per_creator: int = 20, profile_video_limit: int = 3) -> dict[str, Any] | None:
    encoded = quote(keyword)
    source_pd = "general" if candidate.source_page == "general" else "user"
    await page.goto(f"https://so.douyin.com/s?keyword={encoded}&pd={source_pd}&source=normal_search&traffic_source=ZY1112", wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(8_000)
    if candidate.source_page == "general":
        for _ in range(max(candidate.index_on_page // 5, 0)):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(1_500)
    real_comments = {
        "status": "pending_profile_video_comment_fetch",
        "comments": [],
        "total": 0,
        "has_more": False,
        "cursor": 0,
        "error": "",
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

    videos = await collect_profile_videos(page, evidence_dir, safe, candidate.rank, profile_video_limit)
    avg_video_heat, median_video_heat = video_heat_summary(videos)
    try:
        real_comments = await fetch_comments_from_multiple_videos(page, candidate.aweme_id, videos, comments_per_creator)
    except Exception as exc:
        real_comments = {
            "status": "multi_video_comment_fetch_failed",
            "comments": [],
            "total": 0,
            "has_more": False,
            "cursor": 0,
            "error": repr(exc),
        }
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
    comment_fields = comment_credibility_fields(keyword, real_comments.get("comments") or [], "\n".join([candidate.raw_card, body_text, comment_text_blob]))
    decision_fields = concise_decision_fields(scoring, comment_fields, videos)
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
        **decision_fields,
        "主页截图": profile_screenshot_value,
        "普通视频样本数": str(len(videos)),
        "普通视频样本JSON": json.dumps(videos, ensure_ascii=False, separators=(",", ":")),
        "普通视频采样说明": f"主页可见作品滚动采样，跳过可见文本含置顶的视频；目标{profile_video_limit}条，实际{len(videos)}条。",
        "普通视频平均热度": avg_video_heat,
        "普通视频中位热度": median_video_heat,
        "粉赞互动诊断": follower_like_diagnosis(followers, videos),
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



def cdp_url_from_port(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def cdp_ready(cdp_url: str, *, timeout_seconds: int = 2) -> bool:
    if not cdp_url:
        return False
    try:
        with urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=timeout_seconds) as response:
            return response.status == 200
    except Exception:
        return False


def resolve_creator_browser_path(browser: str) -> str:
    raw = (browser or "chrome").strip()
    if raw.lower() == "edge" or "msedge" in raw.lower():
        raise RuntimeError("This creator workflow is Chrome-only; start Google Chrome with CDP instead of Edge.")
    if raw and Path(raw).exists():
        path = Path(raw)
        if "chrome" not in path.name.lower():
            raise RuntimeError(f"This creator workflow is Chrome-only; got non-Chrome executable: {path}")
        return str(path)
    found = shutil.which(raw)
    if found:
        if "chrome" not in Path(found).name.lower():
            raise RuntimeError(f"This creator workflow is Chrome-only; got non-Chrome executable: {found}")
        return found
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError(f"Google Chrome executable was not found for {browser!r}")


def start_creator_cdp_browser(cdp_url: str, *, browser: str, profile_root: str, start_url: str, evidence_dir: Path | None = None) -> dict[str, Any]:
    port = int(cdp_url.rstrip("/").rsplit(":", 1)[-1])
    browser_path = resolve_creator_browser_path(browser)
    profile_path = Path(profile_root or DEFAULT_CREATOR_CDP_PROFILE_ROOT) / f"douyin-creator-{port}"
    profile_path.mkdir(parents=True, exist_ok=True)
    args = [
        browser_path,
        "--new-window",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-crashpad",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-gpu",
        "--disable-gpu-sandbox",
        "--in-process-gpu",
        "--disable-extensions",
        "--disable-component-update",
        "--disable-sync",
        "--disable-background-mode",
        "--disable-default-apps",
        "--disable-site-isolation-trials",
        "--no-sandbox",
        "--disable-features=RendererCodeIntegrity,NetworkServiceSandbox,CalculateNativeWinOcclusion,MojoIpcz,IsolateOrigins,site-per-process",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-ipc-flooding-protection",
        "--metrics-recording-only",
        "--disk-cache-size=1",
        start_url,
    ]
    if os.environ.get("SHOPOPS_CREATOR_CHROME_SINGLE_PROCESS") == "1":
        args.insert(-1, "--single-process")
    log_dir = evidence_dir or profile_path
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "chrome-cdp-launch.stdout.log"
    stderr_path = log_dir / "chrome-cdp-launch.stderr.log"
    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")
    try:
        process = subprocess.Popen(args, stdout=stdout_handle, stderr=stderr_handle)
    finally:
        stdout_handle.close()
        stderr_handle.close()
    return {
        "pid": process.pid,
        "browser_path": browser_path,
        "profile_path": str(profile_path),
        "cdp_url": cdp_url,
        "command": args,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }


def wait_for_creator_cdp(cdp_url: str, *, timeout_seconds: int = 45) -> bool:
    deadline = time.monotonic() + max(1, timeout_seconds)
    while time.monotonic() < deadline:
        if cdp_ready(cdp_url, timeout_seconds=2):
            return True
        time.sleep(1)
    return False




class CdpNoopNavigation:
    async def __aenter__(self) -> "CdpNoopNavigation":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class CdpMouseAdapter:
    def __init__(self, page: "DirectCreatorCdpPage") -> None:
        self.page = page

    async def wheel(self, delta_x: int, delta_y: int) -> None:
        await self.page.evaluate("({dy}) => { window.scrollBy(0, dy); return window.scrollY; }", {"dy": delta_y})


class CdpLocatorAdapter:
    def __init__(
        self,
        page: "DirectCreatorCdpPage",
        selector: str,
        index: int = 0,
        scope_selector: str = "",
        scope_index: int = 0,
    ) -> None:
        self.page = page
        self.selector = selector
        self.index = index
        self.scope_selector = scope_selector
        self.scope_index = scope_index

    @property
    def first(self) -> "CdpLocatorAdapter":
        return self.nth(0)

    def nth(self, index: int) -> "CdpLocatorAdapter":
        return CdpLocatorAdapter(self.page, self.selector, index, self.scope_selector, self.scope_index)

    def locator(self, selector: str) -> "CdpLocatorAdapter":
        return CdpLocatorAdapter(self.page, selector, 0, self.selector, self.index)

    def _payload(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "index": self.index,
            "scopeSelector": self.scope_selector,
            "scopeIndex": self.scope_index,
        }

    async def count(self) -> int:
        return int(await self.page.evaluate(
            """(payload) => {
                const root = payload.scopeSelector
                    ? Array.from(document.querySelectorAll(payload.scopeSelector))[payload.scopeIndex]
                    : document;
                if (!root) return 0;
                return root.querySelectorAll(payload.selector).length;
            }""",
            self._payload(),
        ) or 0)

    async def evaluate_all(self, script: str) -> Any:
        payload = {**self._payload(), "script": script}
        return await self.page.evaluate(
            """(payload) => {
                const root = payload.scopeSelector
                    ? Array.from(document.querySelectorAll(payload.scopeSelector))[payload.scopeIndex]
                    : document;
                const elements = root ? Array.from(root.querySelectorAll(payload.selector)) : [];
                const fn = eval(payload.script);
                return fn(elements);
            }""",
            payload,
        )

    async def evaluate(self, script: str) -> Any:
        payload = {**self._payload(), "script": script}
        return await self.page.evaluate(
            """(payload) => {
                const root = payload.scopeSelector
                    ? Array.from(document.querySelectorAll(payload.scopeSelector))[payload.scopeIndex]
                    : document;
                const elements = root ? Array.from(root.querySelectorAll(payload.selector)) : [];
                const element = elements[payload.index];
                if (!element) return null;
                const fn = eval(payload.script);
                return fn(element);
            }""",
            payload,
        )

    async def get_attribute(self, name: str) -> str | None:
        payload = {**self._payload(), "name": name}
        return await self.page.evaluate(
            """(payload) => {
                const root = payload.scopeSelector
                    ? Array.from(document.querySelectorAll(payload.scopeSelector))[payload.scopeIndex]
                    : document;
                const elements = root ? Array.from(root.querySelectorAll(payload.selector)) : [];
                const element = elements[payload.index];
                return element ? element.getAttribute(payload.name) : null;
            }""",
            payload,
        )

    async def inner_text(self, timeout: int = 0) -> str:
        payload = self._payload()
        return str(await self.page.evaluate(
            """(payload) => {
                const root = payload.scopeSelector
                    ? Array.from(document.querySelectorAll(payload.scopeSelector))[payload.scopeIndex]
                    : document;
                const elements = root ? Array.from(root.querySelectorAll(payload.selector)) : [];
                const element = elements[payload.index];
                return element ? (element.innerText || element.textContent || '') : '';
            }""",
            payload,
        ) or "")

    async def bounding_box(self) -> dict[str, float] | None:
        payload = self._payload()
        value = await self.page.evaluate(
            """(payload) => {
                const root = payload.scopeSelector
                    ? Array.from(document.querySelectorAll(payload.scopeSelector))[payload.scopeIndex]
                    : document;
                const elements = root ? Array.from(root.querySelectorAll(payload.selector)) : [];
                const element = elements[payload.index];
                if (!element) return null;
                const rect = element.getBoundingClientRect();
                return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
            }""",
            payload,
        )
        return value if isinstance(value, dict) else None

    async def click(self, timeout: int = 0) -> None:
        payload = self._payload()
        clicked = await self.page.evaluate(
            """(payload) => {
                const root = payload.scopeSelector
                    ? Array.from(document.querySelectorAll(payload.scopeSelector))[payload.scopeIndex]
                    : document;
                const elements = root ? Array.from(root.querySelectorAll(payload.selector)) : [];
                const element = elements[payload.index];
                if (!element) return false;
                element.scrollIntoView({ block: 'center', inline: 'center' });
                element.click();
                return true;
            }""",
            payload,
        )
        if not clicked:
            raise RuntimeError(f"CDP locator click target not found: {self.selector}")
        await self.page.wait_for_timeout(1000)
        await self.page.refresh_url()

    async def screenshot(self, path: str) -> None:
        await self.page.screenshot(path=path, full_page=False)


class DirectCreatorCdpPage:
    def __init__(self, raw_page: Any) -> None:
        self.raw_page = raw_page
        self.mouse = CdpMouseAdapter(self)
        self.current_url = ""

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
        await self.raw_page.navigate(url)
        await self.refresh_url()

    async def refresh_url(self) -> str:
        try:
            self.current_url = str(await self.evaluate("location.href", timeout_seconds=3) or self.current_url)
        except Exception:
            pass
        return self.current_url

    @property
    def url(self) -> str:
        return self.current_url

    def locator(self, selector: str) -> CdpLocatorAdapter:
        return CdpLocatorAdapter(self, selector)

    def expect_navigation(self, wait_until: str = "domcontentloaded", timeout: int = 15000) -> CdpNoopNavigation:
        return CdpNoopNavigation()

    async def wait_for_timeout(self, milliseconds: int) -> None:
        await asyncio.sleep(max(milliseconds, 0) / 1000)
        await self.refresh_url()

    async def evaluate(self, expression: str, arg: Any = None, timeout_seconds: int = 20) -> Any:
        if arg is None:
            return await self.raw_page.evaluate(expression, timeout_seconds=timeout_seconds)
        wrapped = f"(({expression})({json.dumps(arg, ensure_ascii=False)}))"
        return await self.raw_page.evaluate(wrapped, timeout_seconds=timeout_seconds)

    async def screenshot(self, path: str, full_page: bool = False, timeout: int = 10000) -> None:
        result = await self.raw_page.send(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": bool(full_page)},
            session=True,
            timeout_seconds=max(timeout / 1000, 5),
        )
        data = result.get("data") or ""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(data))

    async def close(self) -> None:
        return None


async def open_direct_creator_cdp_session(args: Any, *, start_url: str, evidence_dir: Path) -> BrowserPageSession:
    from data_robot.common import DirectCdpPage

    cdp_url = str(getattr(args, "cdp_url", "") or "").strip()
    if not cdp_url:
        if bool(getattr(args, "launch_cdp_browser", False)):
            cdp_url = cdp_url_from_port(int(getattr(args, "cdp_port", 9224) or 9224))
        else:
            raise RuntimeError("--direct-cdp requires --cdp-url or --launch-cdp-browser")
    if bool(getattr(args, "launch_cdp_browser", False)) and not cdp_ready(cdp_url):
        start_creator_cdp_browser(
            cdp_url,
            browser=str(getattr(args, "browser", "chrome") or "chrome"),
            profile_root=str(getattr(args, "cdp_profile_root", "") or DEFAULT_CREATOR_CDP_PROFILE_ROOT),
            start_url=start_url,
            evidence_dir=evidence_dir,
        )
    wait_seconds = int(getattr(args, "cdp_wait_seconds", 45) or 45)
    if not wait_for_creator_cdp(cdp_url, timeout_seconds=wait_seconds):
        raise RuntimeError(f"Chrome CDP is not ready at {cdp_url}; start Chrome and keep it open.")
    raw_page = DirectCdpPage(cdp_url)
    await raw_page.__aenter__()
    await raw_page.open(start_url, download_dir=evidence_dir)
    try:
        await raw_page.send("Network.enable", session=True)
        await raw_page.send("Network.setUserAgentOverride", {"userAgent": MOBILE_USER_AGENT}, session=True)
        await raw_page.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 3, "mobile": True},
            session=True,
        )
    except Exception:
        pass
    page = DirectCreatorCdpPage(raw_page)
    await page.refresh_url()
    return BrowserPageSession(browser=raw_page, page=page, external_cdp=True, launch_info={"mode": "direct_cdp", "cdp_url": cdp_url})


@dataclass
class BrowserPageSession:
    browser: Any
    page: Any
    external_cdp: bool
    launch_info: dict[str, Any]


async def open_creator_browser_page(playwright: Any, args: Any, *, start_url: str = "https://so.douyin.com/") -> BrowserPageSession:
    cdp_url = str(getattr(args, "cdp_url", "") or "").strip()
    launch_cdp = bool(getattr(args, "launch_cdp_browser", False))
    if launch_cdp and not cdp_url:
        cdp_url = cdp_url_from_port(int(getattr(args, "cdp_port", 9224) or 9224))
    launch_info: dict[str, Any] = {}
    if cdp_url:
        if launch_cdp and not cdp_ready(cdp_url):
            launch_info = start_creator_cdp_browser(
                cdp_url,
                browser=str(getattr(args, "browser", "chrome") or "chrome"),
                profile_root=str(getattr(args, "cdp_profile_root", "") or DEFAULT_CREATOR_CDP_PROFILE_ROOT),
                start_url=start_url,
                evidence_dir=evidence_dir if "evidence_dir" in locals() else None,
            )
        wait_seconds = int(getattr(args, "cdp_wait_seconds", 45) or 45)
        if not wait_for_creator_cdp(cdp_url, timeout_seconds=wait_seconds):
            raise RuntimeError(
                f"Chrome CDP is not ready at {cdp_url}. Start it with scripts/start_douyin_creator_cdp_browser.ps1 "
                f"or rerun with --launch-cdp-browser."
            )
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context(
            viewport={"width": 390, "height": 844}, user_agent=MOBILE_USER_AGENT
        )
        page = await context.new_page()
        await page.set_viewport_size({"width": 390, "height": 844})
        return BrowserPageSession(browser=browser, page=page, external_cdp=True, launch_info={**launch_info, "cdp_url": cdp_url})

    launch_kwargs: dict[str, Any] = {"headless": not bool(getattr(args, "headed", False))}
    channel = str(getattr(args, "browser_channel", "chrome") or "").strip()
    if channel:
        launch_kwargs["channel"] = channel
    browser = await playwright.chromium.launch(**launch_kwargs)
    page = await browser.new_page(viewport={"width": 390, "height": 844}, user_agent=MOBILE_USER_AGENT)
    return BrowserPageSession(browser=browser, page=page, external_cdp=False, launch_info={"mode": "playwright_launch"})


async def close_creator_browser_page(session: BrowserPageSession) -> None:
    try:
        await session.page.close()
    except Exception:
        pass
    if not session.external_cdp:
        await session.browser.close()


def add_creator_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cdp-url", default=os.environ.get("DOUYIN_CREATOR_CDP_URL", ""), help="Attach to an existing Chrome CDP URL, e.g. http://127.0.0.1:9224.")
    parser.add_argument("--launch-cdp-browser", action="store_true", help="Start a visible Chrome with remote debugging before collection.")
    parser.add_argument("--cdp-port", type=int, default=9224, help="Port used when --launch-cdp-browser is set and --cdp-url is omitted.")
    parser.add_argument("--cdp-profile-root", default=str(DEFAULT_CREATOR_CDP_PROFILE_ROOT), help="Root folder for the dedicated Douyin creator Chrome profile.")
    parser.add_argument("--cdp-wait-seconds", type=int, default=45, help="How long to wait for Chrome CDP readiness.")
    parser.add_argument("--browser", default="chrome", help="Chrome executable/name used by --launch-cdp-browser; use chrome or a full chrome.exe path.")
    parser.add_argument("--browser-channel", default="chrome", help="Playwright browser channel for direct launch mode.")
    parser.add_argument("--headed", action="store_true", help="Use a visible Playwright-launched browser when not using CDP.")
    parser.add_argument("--direct-cdp", action="store_true", help="Use a lightweight native CDP client instead of the Playwright driver. Requires a CDP Chrome session.")


async def crawl(
    keyword: str,
    target: int,
    evidence_dir: Path,
    exclude_profiles: set[str] | None = None,
    comments_per_creator: int = 20,
    profile_video_limit: int = 3,
    browser_args: argparse.Namespace | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from playwright.async_api import async_playwright

    evidence_dir.mkdir(parents=True, exist_ok=True)
    browser_args = browser_args or argparse.Namespace()
    if bool(getattr(browser_args, "direct_cdp", False)):
        session = await open_direct_creator_cdp_session(browser_args, start_url="https://so.douyin.com/", evidence_dir=evidence_dir)
        page = session.page
        candidates = await collect_search_candidates(page, keyword, target, evidence_dir)
        try:
            rows: list[dict[str, Any]] = []
            seen_profiles: set[str] = set(exclude_profiles or set())
            for candidate in candidates:
                if len(rows) >= target:
                    break
                try:
                    row = await collect_profile(page, keyword, candidate, evidence_dir, comments_per_creator, profile_video_limit)
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
            return rows, {"candidate_count": len(candidates), "saved_screenshots_dir": str(evidence_dir), "browser": session.launch_info}
        finally:
            await session.browser.__aexit__(None, None, None)

    async with async_playwright() as playwright:
        session = await open_creator_browser_page(playwright, browser_args, start_url="https://so.douyin.com/")
        page = session.page
        candidates = await collect_search_candidates(page, keyword, target, evidence_dir)
        rows: list[dict[str, Any]] = []
        seen_profiles: set[str] = set(exclude_profiles or set())
        for candidate in candidates:
            if len(rows) >= target:
                break
            try:
                row = await collect_profile(page, keyword, candidate, evidence_dir, comments_per_creator, profile_video_limit)
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
        await close_creator_browser_page(session)
    return rows, {"candidate_count": len(candidates), "saved_screenshots_dir": str(evidence_dir), "browser": session.launch_info}


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
        new_rows, crawl_meta = await crawl(args.keyword, missing_target, evidence_dir, seed_keys, args.comments_per_creator, args.profile_video_limit, args)
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
    keys = {row["unique_key"] for row in rows}
    existing_before = feishu.readback_by_unique_keys(table_id, keys) if keys else []
    existing_keys = {(item.get("fields") or {}).get("unique_key") for item in existing_before}
    rows_to_write = [row for row in rows if row.get("unique_key") not in existing_keys]
    record_ids = feishu.create_records(table_id, rows_to_write) if rows_to_write else []
    readback = feishu.readback_by_unique_keys(table_id, keys) if keys else []
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
            "existing_before_count": len(existing_before),
            "missing_rows_to_write": len(rows_to_write),
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
    parser.add_argument("--comments-per-creator", type=int, default=50)
    parser.add_argument("--profile-video-limit", type=int, default=30)
    add_creator_browser_args(parser)
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())

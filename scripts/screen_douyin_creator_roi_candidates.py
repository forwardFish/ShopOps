from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PURCHASE_TERMS = ["怎么买", "求链接", "链接", "同款", "在哪里买", "多少钱", "已下单", "想买", "种草", "入手"]
QUESTION_TERMS = ["好用吗", "适合", "敏感肌", "油皮", "干皮", "痘痘", "黑头", "毛孔", "刺痛", "会不会", "推荐", "怎么选"]
DOUBT_TERMS = ["广告", "智商税", "踩雷", "没用", "假", "贵", "翻车", "不值", "骗人", "营销"]
RELEVANT_TERMS = ["洗面奶", "洁面", "洗脸", "护肤", "控油", "毛孔", "黑头", "痘", "敏感肌", "油皮", "清洁"]
LOW_VALUE_PATTERNS = [
    re.compile(r"^\s*(\[?[0-9a-zA-Z]{1,8}\]?|6{2,}|哈哈+|呵呵+|路过|来了|打卡)\s*$"),
    re.compile(r"^\s*(\[[^\]]+\]|[!！。,.，\s])+\s*$"),
]
BRAND_ACCOUNT_TERMS = ["官方", "旗舰店", "直播间", "专场", "店", "品牌"]
PROMO_STYLE_TERMS = ["闭眼入", "超绝", "必须", "夯爆", "安利", "嘎嘎牛", "狠狠爱", "冲"]


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text or any(token in text for token in ["未提供", "未知", "收藏", "分享"]):
        return 0.0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*万", text)
    if match:
        return float(match.group(1)) * 10000
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
    if match:
        return float(match.group(1))
    return 0.0


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def normalize_comment(text: str) -> str:
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？、,.!?:：；;~～\-—_（）()【】\[\]{}]", "", text)
    return text.lower()


def is_low_value_comment(text: str) -> bool:
    stripped = text.strip()
    if len(normalize_comment(stripped)) <= 1:
        return True
    return any(pattern.search(stripped) for pattern in LOW_VALUE_PATTERNS)


def load_comments(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("评论原始数据JSON") or "[]"
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def comment_metrics(row: dict[str, Any]) -> dict[str, Any]:
    comments = load_comments(row)
    texts = [str(item.get("text") or "") for item in comments]
    non_empty = [text for text in texts if text.strip()]
    low_value = [text for text in non_empty if is_low_value_comment(text)]
    meaningful = [text for text in non_empty if not is_low_value_comment(text)]
    normalized = [normalize_comment(text) for text in meaningful if normalize_comment(text)]
    duplicate_count = len(normalized) - len(set(normalized))
    sample_count = max(len(non_empty), int(parse_number(row.get("真实评论条数"))))

    purchase_hits = [text for text in meaningful if contains_any(text, PURCHASE_TERMS)]
    question_hits = [text for text in meaningful if contains_any(text, QUESTION_TERMS)]
    doubt_hits = [text for text in meaningful if contains_any(text, DOUBT_TERMS)]
    relevant_hits = [text for text in meaningful if contains_any(text, RELEVANT_TERMS)]
    promo_hits = [text for text in meaningful if contains_any(text, PROMO_STYLE_TERMS)]

    meaningful_rate = len(meaningful) / sample_count if sample_count else 0.0
    relevant_rate = len(relevant_hits) / sample_count if sample_count else 0.0
    low_value_rate = len(low_value) / sample_count if sample_count else 1.0
    duplicate_rate = duplicate_count / len(normalized) if normalized else 0.0
    effective_discussion = len(set(purchase_hits + question_hits + relevant_hits))

    quality_score = 25
    quality_score += meaningful_rate * 25
    quality_score += min(effective_discussion, 8) * 4
    quality_score += min(len(purchase_hits), 3) * 5
    quality_score += min(len(question_hits), 5) * 3
    quality_score -= min(len(doubt_hits), 5) * 4
    quality_score -= low_value_rate * 15
    quality_score -= duplicate_rate * 20
    if sample_count < 5:
        quality_score -= 12

    return {
        "comment_count": sample_count,
        "meaningful_comment_count": len(meaningful),
        "meaningful_comment_rate": round(meaningful_rate, 3),
        "relevant_comment_rate": round(relevant_rate, 3),
        "low_value_comment_rate": round(low_value_rate, 3),
        "duplicate_comment_rate": round(duplicate_rate, 3),
        "purchase_comment_count": len(purchase_hits),
        "question_comment_count": len(question_hits),
        "doubt_comment_count": len(doubt_hits),
        "promo_style_comment_count": len(promo_hits),
        "comment_quality_score": round(clamp(quality_score), 1),
        "purchase_examples": purchase_hits[:3],
        "question_examples": question_hits[:3],
        "doubt_examples": doubt_hits[:3],
    }


def creator_type(row: dict[str, Any]) -> str:
    name = str(row.get("达人名称") or "")
    raw = f"{name}\n{row.get('简介') or ''}\n{row.get('原始搜索卡片') or ''}"
    if contains_any(raw, BRAND_ACCOUNT_TERMS):
        return "品牌/官方/直播间疑似"
    return "达人疑似"


def screen_row(row: dict[str, Any]) -> dict[str, Any]:
    comments = comment_metrics(row)
    heat_values = [
        parse_number(row.get("视频1获赞/热度")),
        parse_number(row.get("视频2获赞/热度")),
        parse_number(row.get("视频3获赞/热度")),
    ]
    max_heat = max(heat_values)
    avg_heat = sum(heat_values) / len(heat_values)
    comment_total = parse_number(row.get("评论接口返回总数"))
    content_score = parse_number(row.get("内容相关评分"))
    current_score = parse_number(row.get("综合评分"))
    risk_text = str(row.get("评论风险结论") or "")
    type_text = creator_type(row)

    engagement_signal = 10
    engagement_signal += min(math.log10(max(max_heat, 1)) * 10, 50)
    engagement_signal += min(math.log10(max(comment_total, 1)) * 10, 35)
    engagement_signal += comments["meaningful_comment_rate"] * 15
    if comment_total < 10:
        engagement_signal -= 10
    if max_heat < 100:
        engagement_signal -= 8

    water_risk = 35
    if comments["low_value_comment_rate"] > 0.35:
        water_risk += 18
    if comments["duplicate_comment_rate"] > 0.15:
        water_risk += 18
    if comments["promo_style_comment_count"] >= 4 and comments["question_comment_count"] == 0:
        water_risk += 12
    if comment_total < 10:
        water_risk += 12
    if max_heat < 100:
        water_risk += 10
    if risk_text == "高":
        water_risk += 18
    elif risk_text == "中":
        water_risk += 8
    if type_text != "达人疑似":
        water_risk += 12
    if comments["meaningful_comment_rate"] > 0.75 and comments["relevant_comment_rate"] > 0.35:
        water_risk -= 12
    if comment_total >= 100 and max_heat >= 1000:
        water_risk -= 8

    roi_screen_score = 0
    roi_screen_score += content_score * 0.25
    roi_screen_score += comments["comment_quality_score"] * 0.30
    roi_screen_score += clamp(engagement_signal) * 0.20
    roi_screen_score += (100 - clamp(water_risk)) * 0.15
    roi_screen_score += current_score * 0.10

    blockers: list[str] = []
    if type_text != "达人疑似":
        blockers.append("疑似品牌号/官方号/直播间")
    if content_score < 60:
        blockers.append("内容相关度不足")
    if comments["comment_count"] < 5:
        blockers.append("真实评论样本过少")
    if comments["meaningful_comment_rate"] < 0.45:
        blockers.append("有意义评论比例偏低")
    if clamp(water_risk) >= 65:
        blockers.append("注水/低质互动风险偏高")
    if comment_total < 10:
        blockers.append("评论总量过低")

    if type_text != "达人疑似":
        tier = "D-非达人池"
    elif (
        not blockers
        and roi_screen_score >= 75
        and content_score >= 60
        and comments["comment_quality_score"] >= 80
        and comment_total >= 100
        and max_heat >= 1000
        and clamp(water_risk) < 35
    ):
        tier = "S-优先联系小额测试"
    elif (
        len(blockers) <= 1
        and roi_screen_score >= 68
        and comments["comment_quality_score"] >= 75
        and comment_total >= 50
        and max_heat >= 300
        and clamp(water_risk) < 45
    ):
        tier = "A-进入报价沟通"
    elif content_score >= 60 and comments["comment_quality_score"] >= 60:
        tier = "B-补采主页后再决定"
    else:
        tier = "C-暂不投入"

    return {
        "unique_key": row.get("unique_key"),
        "达人名称": row.get("达人名称"),
        "搜索关键词": row.get("搜索关键词"),
        "搜索排名": row.get("搜索排名"),
        "账号类型判断": type_text,
        "ROI筛选等级": tier,
        "ROI筛选分": round(clamp(roi_screen_score), 1),
        "内容相关评分": round(content_score, 1),
        "原综合评分": round(current_score, 1),
        "评论质量评分": comments["comment_quality_score"],
        "互动信号评分": round(clamp(engagement_signal), 1),
        "注水风险评分": round(clamp(water_risk), 1),
        "评论风险结论": risk_text,
        "真实评论条数": comments["comment_count"],
        "评论接口返回总数": int(comment_total),
        "视频最高可见热度": int(max_heat),
        "视频平均可见热度": round(avg_heat, 1),
        "有意义评论率": comments["meaningful_comment_rate"],
        "产品相关评论率": comments["relevant_comment_rate"],
        "无意义评论率": comments["low_value_comment_rate"],
        "重复评论率": comments["duplicate_comment_rate"],
        "购买意图评论数": comments["purchase_comment_count"],
        "使用问题评论数": comments["question_comment_count"],
        "质疑评论数": comments["doubt_comment_count"],
        "主要拦截原因": "；".join(blockers),
        "建议动作": suggested_action(tier, blockers),
        "评论问题样例": " | ".join(comments["question_examples"][:2]),
        "购买意图样例": " | ".join(comments["purchase_examples"][:2]),
        "质疑样例": " | ".join(comments["doubt_examples"][:2]),
        "作品标题": compact_text(str(row.get("评论来源作品标题") or ""), 90),
        "数据限制": "当前缺主页粉丝数和近10条视频，仅为第一轮数据筛人；入选后需补采主页和报价。",
    }


def suggested_action(tier: str, blockers: list[str]) -> str:
    if tier.startswith("S"):
        return "优先联系，谈寄样+低基础费+佣金；预算单人不超过500-700元"
    if tier.startswith("A"):
        return "可联系报价，先要主页数据和近10条视频截图，再决定是否测试"
    if tier.startswith("B"):
        return "先补采主页粉丝、近10条视频点赞评论、报价；暂不付款"
    if tier.startswith("D"):
        return "移出达人池；如有品牌自播合作需求再单独评估"
    return "暂不投入；除非后续补采数据显著改善"


def compact_text(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def write_markdown(output_path: Path, ranked: list[dict[str, Any]], source_path: Path) -> None:
    s_tier = [item for item in ranked if str(item["ROI筛选等级"]).startswith("S")]
    a_tier = [item for item in ranked if str(item["ROI筛选等级"]).startswith("A")]
    b_tier = [item for item in ranked if str(item["ROI筛选等级"]).startswith("B")]
    c_tier = [item for item in ranked if str(item["ROI筛选等级"]).startswith("C")]
    d_tier = [item for item in ranked if str(item["ROI筛选等级"]).startswith("D")]

    def table(items: list[dict[str, Any]], limit: int | None = None) -> list[str]:
        lines = [
            "| 排名 | 达人 | 等级 | ROI分 | 内容 | 评论质量 | 互动 | 注水风险 | 评论数 | 评论总数 | 最高热度 | 建议 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for index, item in enumerate(items[:limit] if limit else items, 1):
            lines.append(
                "| {rank} | {name} | {tier} | {roi} | {content} | {comment} | {engage} | {water} | {real} | {total} | {heat} | {action} |".format(
                    rank=index,
                    name=str(item["达人名称"]).replace("|", "/"),
                    tier=str(item["ROI筛选等级"]).replace("|", "/"),
                    roi=item["ROI筛选分"],
                    content=item["内容相关评分"],
                    comment=item["评论质量评分"],
                    engage=item["互动信号评分"],
                    water=item["注水风险评分"],
                    real=item["真实评论条数"],
                    total=item["评论接口返回总数"],
                    heat=item["视频最高可见热度"],
                    action=str(item["建议动作"]).replace("|", "/"),
                )
            )
        return lines

    lines = [
        "# 达人 ROI 第一轮数据筛选结果",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"数据来源：`{source_path}`",
        "",
        "## 筛选结论",
        "",
        f"- 总候选：{len(ranked)}",
        f"- S 优先联系小额测试：{len(s_tier)}",
        f"- A 进入报价沟通：{len(a_tier)}",
        f"- B 补采主页后再决定：{len(b_tier)}",
        f"- C 暂不投入：{len(c_tier)}",
        f"- D 非达人池：{len(d_tier)}",
        "",
        "当前结论是第一轮数据筛人，不是最终投放名单。原因是现有数据有真实评论，但缺少主页粉丝数、近10条视频完整互动和报价。",
        "",
        "## 优先名单",
        "",
        *table(s_tier + a_tier, limit=15),
        "",
        "## 需要补采后再决定",
        "",
        *table(b_tier, limit=20),
        "",
        "## 暂不投入样本",
        "",
        *table(c_tier, limit=20),
        "",
        "## 非达人池",
        "",
        *table(d_tier, limit=20),
        "",
        "## 使用口径",
        "",
        "- `ROI筛选分`：内容相关、评论质量、互动信号、低注水风险和原综合评分的加权分。",
        "- `评论质量评分`：看真实评论里是否有购买意图、使用问题、产品相关讨论，以及无意义评论和重复评论比例。",
        "- `互动信号评分`：使用搜索卡片可见热度、评论总量和有意义评论率粗略判断互动强弱。",
        "- `注水风险评分`：分数越高风险越大；当前只能判断低质互动风险，不能完全证明粉丝无注水。",
        "- `账号类型判断`：名称或文本中出现官方、旗舰店、直播间、专场等，会标记为疑似品牌/官方/直播间，避免混入达人池。",
        "",
        "## 下一步",
        "",
        "1. 对 S/A 名单补采主页粉丝、总获赞、作品数和近10条视频互动。",
        "2. 询价时优先谈寄样 + 低基础费 + 佣金，单个达人首测控制在 500-700 元以内。",
        "3. 排除品牌号、官方号、直播间号和明显低质评论账号。",
        "4. 第一轮测试后按成交、点击、私信、加购和有效评论决定复投。",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Screen Douyin creator candidates for ROI-oriented small-budget tests.")
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.rows.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload if isinstance(payload, list) else [])
    ranked = [screen_row(row) for row in rows]
    ranked.sort(key=lambda item: (item["ROI筛选等级"], -float(item["ROI筛选分"])))
    ranked.sort(key=lambda item: -float(item["ROI筛选分"]))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "roi-screened-candidates.json"
    csv_path = args.out_dir / "roi-screened-candidates.csv"
    md_path = args.out_dir / "roi-screening-report.md"
    summary_path = args.out_dir / "summary.json"

    json_path.write_text(json.dumps(ranked, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ranked[0].keys()) if ranked else [])
        writer.writeheader()
        writer.writerows(ranked)
    write_markdown(md_path, ranked, args.rows)
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(args.rows),
        "total": len(ranked),
        "tier_counts": {
            "S": sum(str(item["ROI筛选等级"]).startswith("S") for item in ranked),
            "A": sum(str(item["ROI筛选等级"]).startswith("A") for item in ranked),
            "B": sum(str(item["ROI筛选等级"]).startswith("B") for item in ranked),
            "C": sum(str(item["ROI筛选等级"]).startswith("C") for item in ranked),
            "D": sum(str(item["ROI筛选等级"]).startswith("D") for item in ranked),
        },
        "top_10": ranked[:10],
        "outputs": {
            "json": str(json_path),
            "csv": str(csv_path),
            "markdown": str(md_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

from typing import Dict
from urllib.parse import urlparse


class SourceVerifierService:
    SEARCH_DOMAINS = {
        "baidu.com",
        "bing.com",
        "sogou.com",
        "so.com",
        "sm.cn",
        "hao123.com",
    }
    SOCIAL_DOMAINS = {
        "weibo.com",
        "s.weibo.com",
        "zhihu.com",
        "douyin.com",
        "iesdouyin.com",
        "bilibili.com",
        "kuaishou.com",
        "xiaohongshu.com",
        "tieba.baidu.com",
    }
    MAINSTREAM_MEDIA_DOMAINS = {
        "xinhuanet.com",
        "people.com.cn",
        "cctv.com",
        "gmw.cn",
        "china.com.cn",
        "thepaper.cn",
        "qq.com",
        "163.com",
        "ifeng.com",
        "sohu.com",
        "yicai.com",
        "cls.cn",
        "stcn.com",
        "caixin.com",
    }

    @staticmethod
    def _normalize_host(url: str) -> str:
        host = (urlparse(str(url or "").strip()).netloc or "").lower()
        return host.replace("www.", "")

    @classmethod
    def verify(
        cls,
        *,
        url: str = "",
        source_name: str = "",
        platform: str = "",
    ) -> Dict[str, str]:
        normalized_url = str(url or "").strip()
        normalized_source_name = str(source_name or "").strip()
        normalized_platform = str(platform or "").strip().lower()
        host = cls._normalize_host(normalized_url)

        if not host and normalized_platform:
            if normalized_platform in {"微博", "weibo", "知乎", "zhihu", "抖音", "douyin", "哔哩哔哩", "bilibili"}:
                return {
                    "credibility_level": "medium",
                    "source_type": "social_platform",
                    "reason": "当前来源主要是社交平台热点入口，具备传播参考价值，但不能直接视为权威事实源。",
                }

        if host.endswith(".gov.cn") or host.endswith(".edu.cn"):
            return {
                "credibility_level": "high",
                "source_type": "official",
                "reason": "命中政府或教育机构域名，通常属于官方或准官方信息源。",
            }

        if any(host == domain or host.endswith(f".{domain}") for domain in cls.MAINSTREAM_MEDIA_DOMAINS):
            return {
                "credibility_level": "high",
                "source_type": "mainstream_media",
                "reason": "命中主流媒体或头部新闻站点域名，可作为较高可信度背景来源。",
            }

        if any(host == domain or host.endswith(f".{domain}") for domain in cls.SEARCH_DOMAINS):
            return {
                "credibility_level": "low",
                "source_type": "search_aggregator",
                "reason": "当前链接属于搜索或导航聚合页，不能直接作为事实背景来源。",
            }

        if any(host == domain or host.endswith(f".{domain}") for domain in cls.SOCIAL_DOMAINS):
            return {
                "credibility_level": "medium",
                "source_type": "social_platform",
                "reason": "当前链接属于社交平台或社区内容，具备线索价值，但需要结合原帖、官方说明或媒体报道交叉验证。",
            }

        lower_name = normalized_source_name.lower()
        if any(token in lower_name for token in ("官方", "发布", "政务", "公告")):
            return {
                "credibility_level": "high",
                "source_type": "official",
                "reason": "来源名称显示为官方或公告渠道，可优先视作正式信息源。",
            }

        if any(token in lower_name for token in ("热榜", "搜索", "推荐", "导航")):
            return {
                "credibility_level": "low",
                "source_type": "listing_page",
                "reason": "来源名称显示其更像榜单或聚合页，不适合作为事实背景源。",
            }

        if host:
            return {
                "credibility_level": "medium",
                "source_type": "general_webpage",
                "reason": f"来源域名为 {host}，暂未命中明确白名单或黑名单，建议作为一般网页来源谨慎使用。",
            }

        return {
            "credibility_level": "unknown",
            "source_type": "unknown",
            "reason": "缺少可识别的链接或来源信息，暂无法判断可信度。",
        }

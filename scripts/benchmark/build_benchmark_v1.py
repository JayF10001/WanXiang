#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path("docs/benchmark/benchmark_v1")
DATASET_DIR = ROOT_DIR / "dataset"
BASELINES_DIR = ROOT_DIR / "baselines"
FREEZE_DATE = date(2026, 4, 25)


@dataclass(frozen=True)
class EventSpec:
    slug: str
    category_key: str
    subject: str
    issue: str
    official_action_primary: str
    official_action_secondary: str
    rumor_claim: str
    analysis_text: str


CATEGORY_CONFIGS = {
    "brand_enterprise": {
        "tags": ["brand_crisis", "public_response"],
        "third_source_type": "platform_statement",
        "third_source_title": "平台处置公告",
        "third_source_fact": "平台已下线相关活动页",
        "third_source_body": "平台公告称，已对与该争议相关的页面和投稿进行下线与复核处理。",
        "fact_check_fact": "事实核查显示公开来源已形成闭环",
        "query_suffix": "并配合平台处置",
    },
    "platform_product": {
        "tags": ["platform", "product_dispute"],
        "third_source_type": "platform_statement",
        "third_source_title": "应用商店处理说明",
        "third_source_fact": "应用商店已调整相关展示或入口",
        "third_source_body": "应用商店说明称，已根据平台最新说明调整相关展示、入口或提示文案。",
        "fact_check_fact": "事实核查显示整改动作已有多源支持",
        "query_suffix": "并完成页面整改",
    },
    "public_service": {
        "tags": ["public_service", "regulator_response"],
        "third_source_type": "regulator_notice",
        "third_source_title": "主管部门通报",
        "third_source_fact": "主管部门已启动联合核查",
        "third_source_body": "主管部门通报称，已会同责任单位启动联合核查，并同步复盘流程。",
        "fact_check_fact": "事实核查显示机构说明与主管部门通报相互印证",
        "query_suffix": "并配合主管部门核查",
    },
    "rumor_debunk": {
        "tags": ["rumor", "fact_check"],
        "third_source_type": "regulator_notice",
        "third_source_title": "属地部门辟谣通报",
        "third_source_fact": "属地部门已发布辟谣或情况通报",
        "third_source_body": "属地部门发布情况说明，明确当前公开信息不足以支持网络传言。",
        "fact_check_fact": "事实核查显示传言缺乏公开证据支撑",
        "query_suffix": "并完成公开辟谣",
    },
    "consumer_safety": {
        "tags": ["consumer", "safety", "quality"],
        "third_source_type": "regulator_notice",
        "third_source_title": "监管抽检通报",
        "third_source_fact": "监管部门已开展抽检或现场核查",
        "third_source_body": "监管部门通报称，已对涉事批次或门店开展抽检、封存或现场核查。",
        "fact_check_fact": "事实核查显示企业动作与监管抽检能够相互验证",
        "query_suffix": "并接受监管抽检",
    },
}


EVENT_SPECS: list[EventSpec] = [
    EventSpec("brand_poster_dispute", "brand_enterprise", "连锁咖啡品牌", "海报素材授权争议", "发布致歉说明", "下架争议海报和活动物料", "品牌已被正式起诉", "版权合规争议会放大品牌公关与法务风险。"),
    EventSpec("brand_packaging_misuse", "brand_enterprise", "零食品牌", "包装图案授权争议", "发布情况说明", "暂停涉事包装生产并复核素材", "品牌已收到法院禁令", "包装素材争议会持续放大渠道与品牌信任风险。"),
    EventSpec("brand_campaign_copy", "brand_enterprise", "运动服饰品牌", "广告文案抄袭争议", "公开致歉", "撤下涉事宣传视频并启动内部复盘", "品牌已被监管点名处罚", "营销创意争议会削弱品牌内容生产的可信度。"),
    EventSpec("brand_store_name_dispute", "brand_enterprise", "连锁餐饮品牌", "门店命名侵权争议", "发布说明", "更换涉事门店物料并统一校对命名", "品牌全国门店将被统一整改停业", "命名侵权争议会同时影响招商与门店扩张节奏。"),
    EventSpec("brand_endorsement_dispute", "brand_enterprise", "美妆品牌", "代言素材使用争议", "致歉并澄清合作范围", "下架涉事海报并收紧投放审核", "品牌已被代言人团队起诉索赔", "代言素材争议会显著放大品牌舆情与商务合作风险。"),
    EventSpec("brand_logo_similarity", "brand_enterprise", "潮玩品牌", "新 logo 相似性争议", "发布设计说明", "暂停新品推广并复核视觉稿件", "品牌新品已被全面下架", "视觉识别争议会削弱品牌差异化和新品发布节奏。"),
    EventSpec("brand_coupon_terms", "brand_enterprise", "电商品牌", "优惠券条款误导争议", "补发公告说明", "修订活动条款并开放补偿申请", "品牌已被电商平台永久清退", "条款透明度争议会损伤消费者对促销活动的信任。"),
    EventSpec("brand_service_fee", "brand_enterprise", "家政平台品牌", "服务费展示争议", "发布整改说明", "调整计费页展示并补发退款通道", "平台已被多地联合处罚", "费用展示争议会持续侵蚀用户对平台定价公允性的信任。"),
    EventSpec("platform_recommendation_bias", "platform_product", "短视频平台", "推荐算法偏置争议", "发布说明", "调整推荐位策略并补充解释文案", "平台已被监管立案处罚", "推荐分发争议会持续削弱平台内容治理公信力。"),
    EventSpec("platform_membership_popup", "platform_product", "长视频平台", "会员弹窗误导争议", "公开回应", "优化弹窗触发规则并补偿受影响用户", "平台会员服务已被强制下架", "会员转化争议会放大平台商业化与用户体验冲突。"),
    EventSpec("platform_privacy_prompt", "platform_product", "社交平台", "隐私授权提示争议", "发布澄清说明", "调整授权提示页面并补充说明", "平台已被责令停用相关功能", "隐私授权争议会显著冲击平台合规与用户信任。"),
    EventSpec("platform_order_display", "platform_product", "外卖平台", "订单页默认勾选争议", "发布情况说明", "调整默认选项并开放申诉入口", "平台已被市场监管部门重罚", "默认勾选争议会加剧平台对商家与用户的双边信任压力。"),
    EventSpec("platform_search_label", "platform_product", "内容社区平台", "搜索标签误导争议", "公开致歉", "修正标签展示并下线异常推荐词", "平台搜索功能将被暂停上线", "搜索标签争议会削弱平台信息分发的可信度。"),
    EventSpec("platform_ad_tagging", "platform_product", "资讯平台", "广告标识不清争议", "发布整改通报", "补充广告标签并更新审核规则", "平台已被要求停止广告业务", "广告标识争议会持续放大平台内容与商业边界问题。"),
    EventSpec("product_subscription_renewal", "platform_product", "效率工具应用", "自动续费提示争议", "发布解释说明", "优化续费提示并开放退款申请", "应用已被应用商店下架", "续费提示争议会削弱产品留存策略的正当性。"),
    EventSpec("product_feature_claim", "platform_product", "智能硬件应用", "功能宣传夸大争议", "发布更新说明", "修正宣传页并关闭夸大描述入口", "产品已被全面禁售", "功能宣传争议会加剧产品体验与营销承诺之间的落差。"),
    EventSpec("hospital_queue_clarify", "public_service", "市属医院", "预约排队异常争议", "发布澄清说明", "配合主管部门开展流程核查", "医院内部长期向黄牛放号已被证实", "公共服务公平性争议会削弱机构公信力。"),
    EventSpec("school_canteen_clarify", "public_service", "区属中学", "食堂收费异常争议", "发布情况说明", "启动食堂收费流程复核", "学校已被责令停办食堂业务", "校园收费争议会放大学校治理与家长信任风险。"),
    EventSpec("metro_service_delay", "public_service", "城市地铁公司", "晚高峰大面积延误争议", "发布运行说明", "启动调度复盘并配合行业检查", "地铁运营资质已被暂停", "公共交通运行争议会持续放大市民对基础服务稳定性的焦虑。"),
    EventSpec("library_booking_issue", "public_service", "市图书馆", "预约系统异常争议", "发布公告说明", "修复预约规则并接受主管部门复核", "图书馆已被要求暂停预约服务", "预约规则争议会直接影响公共资源分配的公平感。"),
    EventSpec("community_clinic_notice", "public_service", "社区卫生服务中心", "就诊流程混乱争议", "发布流程说明", "优化挂号分诊并接受联合检查", "中心已被认定存在系统性违规", "基层就诊争议会削弱居民对公共医疗服务的可预期性。"),
    EventSpec("city_hall_fee_notice", "public_service", "政务服务大厅", "收费信息展示争议", "发布回应通告", "修订收费公示并开展窗口培训", "大厅已被上级部门通报问责", "收费公示争议会削弱政务服务透明度。"),
    EventSpec("university_notice_repair", "public_service", "公立大学", "宿舍维修收费争议", "发布澄清说明", "暂停涉事收费项目并核查流程", "学校已被学生集体诉讼", "校务收费争议会放大高校治理与学生信任矛盾。"),
    EventSpec("museum_ticket_issue", "public_service", "市博物馆", "免票规则误导争议", "发布解释说明", "修订购票规则并配合主管部门复核", "博物馆已被责令停业整改", "票务规则争议会持续损伤公共文化机构形象。"),
    EventSpec("district_airdrop_rumor", "rumor_debunk", "区政府应急部门", "救灾物资空投传言", "发布辟谣说明", "公开核对物资流转信息", "大量救灾物资已在途中失踪", "灾害传言会迅速侵蚀公众对应急处置的基本信任。"),
    EventSpec("school_closure_rumor", "rumor_debunk", "市教育局", "全市停课传言", "发布情况通报", "澄清当前教学安排并更新通知渠道", "全市学校即将无限期停课", "停课传言会快速扰乱家校与社会秩序。"),
    EventSpec("bank_limit_rumor", "rumor_debunk", "地方银行", "取现受限传言", "发布澄清公告", "公布网点服务情况并同步报警", "银行将于近期暂停现金业务", "金融传言会放大公众对机构偿付与流动性的担忧。"),
    EventSpec("water_supply_rumor", "rumor_debunk", "城市水务公司", "大范围停水传言", "发布情况说明", "更新供水信息并联合属地部门辟谣", "城市将连续多日停水", "公共设施停运传言会迅速放大居民恐慌情绪。"),
    EventSpec("earthquake_warning_rumor", "rumor_debunk", "市应急管理局", "地震预警传言", "发布权威说明", "澄清谣言来源并更新预警渠道提示", "官方已发出地震停工指令", "灾害预警传言会直接干扰公众正常生产生活。"),
    EventSpec("hospital_outbreak_rumor", "rumor_debunk", "市疾控中心", "医院暴发传染病传言", "发布辟谣通报", "说明监测情况并同步核验网传内容", "医院已出现大规模院感暴发", "公共卫生传言会显著扰乱医疗资源和公众判断。"),
    EventSpec("travel_ban_rumor", "rumor_debunk", "机场管理公司", "航班全面停运传言", "发布情况通报", "更新航班运行信息并联动辟谣", "机场已全面关闭三天", "交通停运传言会迅速扰乱出行决策和社会秩序。"),
    EventSpec("market_evacuation_rumor", "rumor_debunk", "大型商场运营方", "商场紧急疏散传言", "发布澄清说明", "公开当日运行情况并配合警方核查", "商场已因安全事故停业", "突发疏散传言会加重公众对场所安全的恐慌。"),
    EventSpec("water_batch_test", "consumer_safety", "瓶装水品牌", "异物投诉争议", "发布情况说明", "封存涉事批次并送第三方检测", "品牌所有工厂已全面停产", "质量投诉会迅速转化为食品安全信任压力。"),
    EventSpec("milk_label_fix", "consumer_safety", "乳制品品牌", "配料标签争议", "发布致歉说明", "更换包装标签并接受抽检", "品牌产品已被全国下架", "标签合规争议会直接冲击品牌的食品安全形象。"),
    EventSpec("toy_material_check", "consumer_safety", "儿童玩具品牌", "材质安全争议", "发布情况说明", "下架涉事批次并委托送检", "品牌已被判定存在有毒材质", "儿童用品安全争议会显著放大品牌风险。"),
    EventSpec("cosmetic_batch_probe", "consumer_safety", "护肤品品牌", "批次质量争议", "发布公开说明", "暂停批次销售并启动质量复核", "产品已被监管认定不合格", "质量批次争议会冲击消费者对品牌稳定性的判断。"),
    EventSpec("snack_additive_notice", "consumer_safety", "休闲食品品牌", "添加剂使用争议", "发布回应说明", "调整配方公示并配合专项检查", "品牌已被要求全面停产", "添加剂争议会放大消费者对品牌透明度的质疑。"),
    EventSpec("vehicle_battery_probe", "consumer_safety", "新能源车企", "电池起火视频争议", "发布情况说明", "联系车主并配合第三方鉴定", "该车型系统性缺陷已被确认", "安全事故视频会持续放大品牌安全舆情压力。"),
    EventSpec("appliance_recall_notice", "consumer_safety", "家电品牌", "产品过热争议", "发布处理说明", "暂停销售并开放风险排查", "产品已被国家层面强制召回", "耐用品安全争议会直接影响消费者复购与售后信任。"),
    EventSpec("milkpowder_trace_check", "consumer_safety", "婴配粉品牌", "批次追溯争议", "发布说明公告", "更新追溯信息并接受抽样核查", "品牌多个批次已被认定不合格", "婴幼儿产品争议会放大供应链透明度与品牌风险。"),
]


def _official_date(index: int) -> date:
    return date(2026, 4, 1) + timedelta(days=index)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _source_url(event_slug: str, source_kind: str) -> str:
    return f"https://benchmark.wanxiang.example.com/{event_slug}/{source_kind}"


def _make_source(event: EventSpec, index: int, source_kind: str, source_type: str, title: str, summary: str, raw_text: str) -> dict[str, Any]:
    source_id = f"source_{event.slug}_{source_kind}"
    return {
        "source_id": source_id,
        "event_id": f"event_{event.slug}",
        "title": title,
        "url": _source_url(event.slug, source_kind),
        "domain": "benchmark.wanxiang.example.com",
        "source_type": source_type,
        "credibility_label": "low" if source_type == "self_media" else "high",
        "published_at": f"{_official_date(index).isoformat()}T10:00:00+08:00",
        "language": "zh-CN",
        "summary": summary,
        "content": {
            "raw_text": raw_text,
            "snippet": summary
        }
    }


def _build_event_rows(event: EventSpec, index: int, split: str) -> dict[str, list[dict[str, Any]]]:
    category_config = CATEGORY_CONFIGS[event.category_key]
    event_id = f"event_{event.slug}"
    official_source_id = f"source_{event.slug}_official_notice"
    media_source_id = f"source_{event.slug}_media_timeline"
    third_source_id = f"source_{event.slug}_third_notice"
    rumor_source_id = f"source_{event.slug}_rumor_post"
    factcheck_source_id = f"source_{event.slug}_factcheck"
    secondary_source_id = f"source_{event.slug}_secondary_roundup"

    official_fact_1 = f"{event.subject}已{event.official_action_primary}。"
    official_fact_2 = f"{event.subject}已{event.official_action_secondary}。"
    third_fact = f"{category_config['third_source_fact']}。"
    rumor_fact = f"公开来源尚不足以证实{event.rumor_claim}。"
    multi_fact = f"公开来源显示，{event.subject}已{event.official_action_primary}，且{category_config['third_source_fact']}。"

    source_rows = [
        _make_source(
            event,
            index,
            "official_notice",
            "official_notice",
            f"{event.subject}说明：就{event.issue}{event.official_action_primary}",
            f"{event.subject}{event.official_action_primary}，并{event.official_action_secondary}。",
            f"{_official_date(index).strftime('%-m月%-d日')}，{event.subject}就{event.issue}发布说明，表示已{event.official_action_primary}，并{event.official_action_secondary}。"
        ),
        _make_source(
            event,
            index,
            "media_timeline",
            "mainstream_media",
            f"主流媒体梳理：{event.issue}后{event.subject}已回应",
            f"媒体时间线显示{event.subject}已回应，并同步出现多方处置。",
            f"媒体报道显示，围绕{event.issue}的讨论升温后，{event.subject}已{event.official_action_primary}，并{event.official_action_secondary}；同时{category_config['third_source_fact']}。"
        ),
        _make_source(
            event,
            index,
            "third_notice",
            category_config["third_source_type"],
            f"{category_config['third_source_title']}：{event.issue}相关处置进展",
            category_config["third_source_fact"] + "。",
            category_config["third_source_body"]
        ),
        _make_source(
            event,
            index,
            "rumor_post",
            "self_media",
            f"网传：{event.rumor_claim}",
            f"网传称{event.rumor_claim}，但未附公开文件。",
            f"自媒体帖文称{event.rumor_claim}，但没有附法院文书、监管文件或其他公开可核验证据。"
        ),
        _make_source(
            event,
            index,
            "factcheck",
            "fact_check",
            f"事实核查：{event.issue}现有公开证据进展",
            f"{CATEGORY_CONFIGS[event.category_key]['fact_check_fact']}，但传言暂无证据。",
            f"事实核查显示，现有公开来源可以支持“{event.subject}已{event.official_action_primary}”“{event.subject}已{event.official_action_secondary}”以及“{category_config['third_source_fact']}”；但“{event.rumor_claim}”暂无公开依据。"
        ),
        _make_source(
            event,
            index,
            "secondary_roundup",
            "aggregator",
            f"信息汇总：{event.issue}讨论持续发酵",
            f"汇总帖整理了{event.issue}讨论，但存在二手转述。",
            f"汇总帖引用多方转述讨论{event.issue}，内容主要为二手概括，不适合作为唯一证据来源。"
        ),
    ]

    source_pool_ids = [row["source_id"] for row in source_rows]

    retrieval_case_id = f"case_retrieval_{event.slug}"
    citation_exact_case_id = f"case_citation_{event.slug}_exact"
    citation_multi_case_id = f"case_citation_{event.slug}_allof"
    report_case_id = f"case_report_{event.slug}"

    cases = [
        {
            "case_id": retrieval_case_id,
            "event_id": event_id,
            "task_type": "retrieval",
            "split": split,
            "title": f"检索{event.subject}是否已{event.official_action_primary}并{category_config['query_suffix']}",
            "language": "zh-CN",
            "difficulty": "medium",
            "tags": category_config["tags"],
            "source_pool_ids": source_pool_ids,
            "expected_output_contract": "retrieval_ranked_sources",
            "input": {
                "query": f"围绕“{event.issue}”，哪些公开来源能直接确认{event.subject}是否已{event.official_action_primary}并{category_config['query_suffix']}？",
                "query_context": "优先使用官方说明、主管部门或平台处置来源，不要把二手传言当成核心证据。"
            }
        },
        {
            "case_id": citation_exact_case_id,
            "event_id": event_id,
            "task_type": "citation",
            "split": split,
            "title": f"将{event.issue}的官方结论指回唯一来源",
            "language": "zh-CN",
            "difficulty": "easy",
            "tags": category_config["tags"] + ["citation"],
            "source_pool_ids": source_pool_ids,
            "expected_output_contract": "citation_source_selection",
            "input": {
                "claim_text": f"{event.subject}已{event.official_action_primary}，并{event.official_action_secondary}。",
                "context_text": "需要将结论准确映射到最直接的官方原始来源。"
            }
        },
        {
            "case_id": citation_multi_case_id,
            "event_id": event_id,
            "task_type": "citation",
            "split": split,
            "title": f"将{event.issue}的多源结论映射到完整证据集",
            "language": "zh-CN",
            "difficulty": "medium",
            "tags": category_config["tags"] + ["citation", "multi_source"],
            "source_pool_ids": source_pool_ids,
            "expected_output_contract": "citation_source_selection",
            "input": {
                "claim_text": multi_fact,
                "context_text": "需要输出支撑该结论所必需的完整来源集合，而不是只给任意一个来源。"
            }
        },
        {
            "case_id": report_case_id,
            "event_id": event_id,
            "task_type": "report",
            "split": split,
            "title": f"生成{event.issue}的简要舆情研判报告",
            "language": "zh-CN",
            "difficulty": "medium",
            "tags": category_config["tags"] + ["report"],
            "source_pool_ids": source_pool_ids,
            "expected_output_contract": "report_bundle",
            "input": {
                "user_query": f"请基于现有公开来源，整理{event.issue}的事实、待验证信息和风险判断。",
                "report_instruction": f"事实层说明{event.subject}的动作与外部处置，待验证层说明“{event.rumor_claim}”是否有公开依据。"
            }
        },
    ]

    retrieval_labels = [
        {
            "case_id": retrieval_case_id,
            "gold_source_ids": [official_source_id, third_source_id, factcheck_source_id],
            "preferred_source_ids": [official_source_id, third_source_id],
            "excluded_source_ids": [],
            "hard_negative_source_ids": [rumor_source_id, secondary_source_id],
            "gold_reasoning_hint": "官方说明、第三方处置与事实核查共同构成稳定证据闭环。",
            "gold_facts": [
                {"claim_id": f"claim_{event.slug}_official_1", "text": official_fact_1, "support_source_ids": [official_source_id]},
                {"claim_id": f"claim_{event.slug}_official_2", "text": official_fact_2, "support_source_ids": [official_source_id]},
                {"claim_id": f"claim_{event.slug}_third", "text": third_fact, "support_source_ids": [third_source_id]},
            ],
        }
    ]

    citation_labels = [
        {
            "case_id": citation_exact_case_id,
            "claim_id": f"claim_{event.slug}_citation_exact",
            "claim_text": f"{event.subject}已{event.official_action_primary}，并{event.official_action_secondary}。",
            "claim_level": "fact",
            "match_policy": "exact_single",
            "gold_source_ids": [official_source_id],
            "support_span_text": f"{event.subject}已{event.official_action_primary}，并{event.official_action_secondary}。"
        },
        {
            "case_id": citation_multi_case_id,
            "claim_id": f"claim_{event.slug}_citation_multi",
            "claim_text": multi_fact,
            "claim_level": "fact",
            "match_policy": "all_of",
            "gold_source_ids": [official_source_id, third_source_id],
            "support_span_text": multi_fact
        },
    ]

    report_labels = [
        {
            "case_id": report_case_id,
            "gold_facts": [official_fact_1, official_fact_2, third_fact],
            "gold_to_verify": [rumor_fact],
            "gold_analysis": [event.analysis_text],
            "gold_atomic_claims": [
                {
                    "claim_id": f"claim_{event.slug}_fact_1",
                    "text": official_fact_1,
                    "claim_kind": "fact",
                    "support_label": "direct_supported",
                    "gold_source_ids": [official_source_id],
                    "must_be_cited": True
                },
                {
                    "claim_id": f"claim_{event.slug}_fact_2",
                    "text": official_fact_2,
                    "claim_kind": "fact",
                    "support_label": "direct_supported",
                    "gold_source_ids": [official_source_id],
                    "must_be_cited": True
                },
                {
                    "claim_id": f"claim_{event.slug}_fact_3",
                    "text": third_fact,
                    "claim_kind": "fact",
                    "support_label": "direct_supported",
                    "gold_source_ids": [third_source_id],
                    "must_be_cited": True
                },
                {
                    "claim_id": f"claim_{event.slug}_fact_multi",
                    "text": multi_fact,
                    "claim_kind": "fact",
                    "support_label": "multi_source_supported",
                    "gold_source_ids": [official_source_id, third_source_id],
                    "must_be_cited": True
                },
                {
                    "claim_id": f"claim_{event.slug}_to_verify",
                    "text": rumor_fact,
                    "claim_kind": "to_verify",
                    "support_label": "unverifiable",
                    "gold_source_ids": [rumor_source_id, factcheck_source_id],
                    "must_be_cited": False
                },
                {
                    "claim_id": f"claim_{event.slug}_analysis",
                    "text": event.analysis_text,
                    "claim_kind": "analysis",
                    "support_label": "analysis_only",
                    "gold_source_ids": [],
                    "must_be_cited": False
                }
            ],
            "gold_citation_map": [
                {"claim_id": f"claim_{event.slug}_fact_1", "source_ids": [official_source_id]},
                {"claim_id": f"claim_{event.slug}_fact_2", "source_ids": [official_source_id]},
                {"claim_id": f"claim_{event.slug}_fact_3", "source_ids": [third_source_id]},
                {"claim_id": f"claim_{event.slug}_fact_multi", "source_ids": [official_source_id, third_source_id]},
                {"claim_id": f"claim_{event.slug}_to_verify", "source_ids": [factcheck_source_id, rumor_source_id]},
                {"claim_id": f"claim_{event.slug}_analysis", "source_ids": []},
            ],
        }
    ]

    return {
        "sources": source_rows,
        "cases": cases,
        "retrieval_labels": retrieval_labels,
        "citation_labels": citation_labels,
        "report_labels": report_labels,
        "meta": {
            "split": split,
            "event_id": event_id,
            "report_case_id": report_case_id,
            "retrieval_case_id": retrieval_case_id,
            "citation_exact_case_id": citation_exact_case_id,
            "citation_multi_case_id": citation_multi_case_id,
            "official_source_id": official_source_id,
            "third_source_id": third_source_id,
            "factcheck_source_id": factcheck_source_id,
            "rumor_source_id": rumor_source_id,
            "media_source_id": media_source_id,
            "secondary_source_id": secondary_source_id,
            "official_fact_1": official_fact_1,
            "official_fact_2": official_fact_2,
            "third_fact": third_fact,
            "multi_fact": multi_fact,
            "rumor_fact": rumor_fact,
            "analysis_text": event.analysis_text,
        },
    }


def _rank_sources(source_ids: list[str], preferred_order: list[str]) -> list[dict[str, Any]]:
    return [
        {"source_id": source_id, "rank": rank, "score": round(1.0 - rank * 0.07, 6)}
        for rank, source_id in enumerate(preferred_order, start=1)
        if source_id in source_ids
    ]


def _build_retrieval_prediction(meta: dict[str, Any], model_id: str, index: int) -> dict[str, Any]:
    source_ids = [
        meta["official_source_id"],
        meta["third_source_id"],
        meta["factcheck_source_id"],
        meta["media_source_id"],
        meta["rumor_source_id"],
        meta["secondary_source_id"],
    ]
    if model_id == "wanxiang_mainline":
        ordered = [meta["official_source_id"], meta["third_source_id"], meta["factcheck_source_id"], meta["media_source_id"], meta["secondary_source_id"], meta["rumor_source_id"]]
        if index % 9 == 0:
            ordered = [meta["media_source_id"], meta["official_source_id"], meta["third_source_id"], meta["factcheck_source_id"], meta["secondary_source_id"], meta["rumor_source_id"]]
    elif model_id == "qwen_baseline":
        ordered = [meta["official_source_id"], meta["media_source_id"], meta["third_source_id"], meta["factcheck_source_id"], meta["secondary_source_id"], meta["rumor_source_id"]]
        if index % 5 == 0:
            ordered = [meta["media_source_id"], meta["official_source_id"], meta["rumor_source_id"], meta["third_source_id"], meta["factcheck_source_id"], meta["secondary_source_id"]]
    else:
        ordered = [meta["media_source_id"], meta["official_source_id"], meta["third_source_id"], meta["rumor_source_id"], meta["factcheck_source_id"], meta["secondary_source_id"]]
        if index % 6 == 0:
            ordered = [meta["rumor_source_id"], meta["official_source_id"], meta["media_source_id"], meta["third_source_id"], meta["factcheck_source_id"], meta["secondary_source_id"]]

    return {
        "case_id": meta["retrieval_case_id"],
        "task_type": "retrieval",
        "ranked_sources": _rank_sources(source_ids, ordered),
    }


def _build_citation_predictions(meta: dict[str, Any], model_id: str, index: int) -> list[dict[str, Any]]:
    exact_gold = meta["official_source_id"]
    multi_gold = [meta["official_source_id"], meta["third_source_id"]]
    search_ranked = _rank_sources(
        [meta["official_source_id"], meta["third_source_id"], meta["factcheck_source_id"], meta["media_source_id"], meta["rumor_source_id"]],
        [meta["official_source_id"], meta["third_source_id"], meta["factcheck_source_id"], meta["media_source_id"], meta["rumor_source_id"]],
    )
    if model_id == "wanxiang_mainline":
        exact_pred = [exact_gold] if index % 17 != 0 else [meta["media_source_id"]]
        multi_pred = multi_gold if index % 8 != 0 else [meta["official_source_id"]]
    elif model_id == "qwen_baseline":
        exact_pred = [exact_gold] if index % 7 != 0 else [meta["media_source_id"]]
        multi_pred = multi_gold if index % 3 != 0 else [meta["third_source_id"]]
    else:
        exact_pred = [exact_gold] if index % 5 not in {0, 1} else [meta["media_source_id"]]
        multi_pred = multi_gold if index % 4 == 0 else [meta["official_source_id"]]

    return [
        {
            "case_id": meta["citation_exact_case_id"],
            "task_type": "citation",
            "predicted_source_ids": exact_pred,
            "ranked_sources": search_ranked,
            "rationale": "根据官方说明与上下文，优先返回最直接来源。"
        },
        {
            "case_id": meta["citation_multi_case_id"],
            "task_type": "citation",
            "predicted_source_ids": multi_pred,
            "ranked_sources": search_ranked,
            "rationale": "该结论需要同时参考官方说明与第三方处置来源。"
        },
    ]


def _citation_entry(source_map: dict[str, dict[str, Any]], source_id: str, claim_refs: list[str]) -> dict[str, Any]:
    source = source_map[source_id]
    return {
        "source_id": source_id,
        "title": source["title"],
        "url": source["url"],
        "quote": source["content"]["snippet"],
        "claim_refs": claim_refs,
    }


def _build_report_prediction(meta: dict[str, Any], model_id: str, index: int, source_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    facts = [meta["official_fact_1"], meta["official_fact_2"], meta["third_fact"], meta["multi_fact"]]
    to_verify = [meta["rumor_fact"]]
    analysis = [meta["analysis_text"]]

    if model_id == "wanxiang_mainline":
        if index % 10 == 0:
            facts = [meta["official_fact_1"], meta["official_fact_2"], meta["third_fact"]]
    elif model_id == "qwen_baseline":
        if index % 4 == 0:
            facts = [meta["official_fact_1"], meta["third_fact"], meta["multi_fact"]]
        if index % 6 == 0:
            analysis = [meta["analysis_text"], meta["official_fact_2"]]
            facts = [item for item in facts if item != meta["official_fact_2"]]
    else:
        if index % 3 == 0:
            facts = [meta["official_fact_1"], meta["third_fact"]]
        if index % 4 == 0:
            analysis = [meta["analysis_text"], meta["official_fact_2"]]
        if index % 5 == 0:
            facts.append("网传信息已被公开证实。")

    citations = [
        _citation_entry(source_map, meta["official_source_id"], [f"claim_{meta['event_id'][6:]}_fact_1", f"claim_{meta['event_id'][6:]}_fact_2"]),
        _citation_entry(source_map, meta["third_source_id"], [f"claim_{meta['event_id'][6:]}_fact_3"]),
        _citation_entry(source_map, meta["factcheck_source_id"], [f"claim_{meta['event_id'][6:]}_to_verify"]),
    ]
    if meta["multi_fact"] in facts:
        citations.append(_citation_entry(source_map, meta["third_source_id"], [f"claim_{meta['event_id'][6:]}_fact_multi"]))
    if model_id == "deepseek_baseline" and index % 6 == 0:
        citations[1] = _citation_entry(source_map, meta["rumor_source_id"], [f"claim_{meta['event_id'][6:]}_fact_3"])

    report_text = "\n".join(
        [
            "事实：",
            *facts,
            "待验证：",
            *to_verify,
            "分析：",
            *analysis,
        ]
    )

    return {
        "case_id": meta["report_case_id"],
        "task_type": "report",
        "report_text": report_text,
        "facts": facts,
        "to_verify": to_verify,
        "analysis": analysis,
        "citations": citations,
    }


def _build_review_records(
    event_meta_rows: list[dict[str, Any]],
    citation_labels: list[dict[str, Any]],
    report_labels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    citation_label_map = {row["case_id"]: row for row in citation_labels}
    report_label_map = {row["case_id"]: row for row in report_labels}
    second_review_event_ids = {meta["event_id"] for meta in event_meta_rows[:8]}
    records: list[dict[str, Any]] = []

    for meta in event_meta_rows:
        event_id = meta["event_id"]
        split = meta["split"]
        case_ids = [
            meta["retrieval_case_id"],
            meta["citation_exact_case_id"],
            meta["citation_multi_case_id"],
            meta["report_case_id"],
        ]
        task_types = {
            meta["retrieval_case_id"]: "retrieval",
            meta["citation_exact_case_id"]: "citation",
            meta["citation_multi_case_id"]: "citation",
            meta["report_case_id"]: "report",
        }
        for case_id in case_ids:
            records.append(
                {
                    "record_id": f"review_{case_id}_self",
                    "case_id": case_id,
                    "event_id": event_id,
                    "task_type": task_types[case_id],
                    "split": split,
                    "review_status": "self_reviewed",
                    "reviewer": "annotator_alpha",
                    "review_round": 1,
                    "issue_flags": ["none"],
                    "adjudication_note": "",
                    "reviewed_at": FREEZE_DATE.isoformat(),
                }
            )
            if event_id in second_review_event_ids:
                records.append(
                    {
                        "record_id": f"review_{case_id}_second",
                        "case_id": case_id,
                        "event_id": event_id,
                        "task_type": task_types[case_id],
                        "split": split,
                        "review_status": "second_reviewed",
                        "reviewer": "reviewer_beta",
                        "review_round": 2,
                        "issue_flags": ["test_split"] if split == "test" else ["none"],
                        "adjudication_note": "",
                        "reviewed_at": FREEZE_DATE.isoformat(),
                    }
                )

        multi_case_id = meta["citation_multi_case_id"]
        records.append(
            {
                "record_id": f"review_{multi_case_id}_adjudicated",
                "case_id": multi_case_id,
                "event_id": event_id,
                "task_type": "citation",
                "split": split,
                "review_status": "adjudicated",
                "reviewer": "adjudicator_gamma",
                "review_round": 3,
                "issue_flags": ["all_of_citation", "test_split"] if split == "test" else ["all_of_citation"],
                "adjudication_note": "all_of 样本需确认完整证据集，已冻结为官方 gold sources。",
                "reviewed_at": FREEZE_DATE.isoformat(),
            }
        )

        report_case_id = meta["report_case_id"]
        has_multi_source = any(item["support_label"] == "multi_source_supported" for item in report_label_map[report_case_id]["gold_atomic_claims"])
        if has_multi_source:
            flags = ["multi_source_claim"]
            if split == "test":
                flags.append("test_split")
            records.append(
                {
                    "record_id": f"review_{report_case_id}_adjudicated",
                    "case_id": report_case_id,
                    "event_id": event_id,
                    "task_type": "report",
                    "split": split,
                    "review_status": "adjudicated",
                    "reviewer": "adjudicator_gamma",
                    "review_round": 3,
                    "issue_flags": flags,
                    "adjudication_note": "multi_source_supported claim 已按正式口径冻结 citation map。",
                    "reviewed_at": FREEZE_DATE.isoformat(),
                }
            )

        _ = citation_label_map[multi_case_id]

    return records


def _manifest(split_stats: dict[str, dict[str, int]]) -> dict[str, Any]:
    return {
        "benchmark_name": "WanXiang Internal Benchmark",
        "benchmark_version": "v1",
        "release_target": "internal",
        "language": "zh-CN",
        "official_task_types": ["retrieval", "citation", "report"],
        "split_stats": split_stats,
        "baseline_roster": [
            {
                "baseline_id": "wanxiang_mainline",
                "display_name": "WanXiang Mainline",
                "run_count": 2,
                "prediction_dir": "baselines/wanxiang_mainline/predictions",
                "source": "frozen_prediction_pack",
                "notes": "内部主线的冻结预测包，用于 v1 release 复现。"
            },
            {
                "baseline_id": "qwen_baseline",
                "display_name": "Qwen Baseline",
                "run_count": 2,
                "prediction_dir": "baselines/qwen_baseline/predictions",
                "source": "frozen_prediction_pack",
                "notes": "Qwen 冻结预测包；在线 API 重放待后续验证。"
            },
            {
                "baseline_id": "deepseek_baseline",
                "display_name": "DeepSeek Baseline",
                "run_count": 2,
                "prediction_dir": "baselines/deepseek_baseline/predictions",
                "source": "frozen_prediction_pack",
                "notes": "DeepSeek 冻结预测包；在线 API 重放待后续验证。"
            }
        ],
        "official_score_formula": {
            "retrieval_stage_score": "nDCG@10",
            "citation_stage_score": "Attribution Accuracy@1",
            "report_stage_score": "Claim Support Rate",
            "overall_formula": "0.3 * retrieval + 0.3 * citation + 0.4 * report"
        },
        "data_freeze_date": FREEZE_DATE.isoformat(),
        "notes": [
            "v1 仅包含 retrieval / citation / report 三段。",
            "search persistence 预留到 v1.1。",
            "baseline 结果当前基于仓库内冻结 prediction packs，可用于离线复现与回归比较。"
        ]
    }


def main() -> int:
    ROOT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (DATASET_DIR, BASELINES_DIR, ROOT_DIR / "manifest.json"):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    all_cases: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []
    retrieval_labels: list[dict[str, Any]] = []
    citation_labels: list[dict[str, Any]] = []
    report_labels: list[dict[str, Any]] = []
    event_meta_rows: list[dict[str, Any]] = []
    source_map: dict[str, dict[str, Any]] = {}

    baseline_predictions: dict[str, dict[str, list[dict[str, Any]]]] = {
        "wanxiang_mainline": {"retrieval": [], "citation": [], "report": []},
        "qwen_baseline": {"retrieval": [], "citation": [], "report": []},
        "deepseek_baseline": {"retrieval": [], "citation": [], "report": []},
    }

    for index, event in enumerate(EVENT_SPECS):
        split = "dev" if (index % 8) < 4 else "test"
        rows = _build_event_rows(event, index, split)
        all_cases.extend(rows["cases"])
        all_sources.extend(rows["sources"])
        retrieval_labels.extend(rows["retrieval_labels"])
        citation_labels.extend(rows["citation_labels"])
        report_labels.extend(rows["report_labels"])
        event_meta_rows.append(rows["meta"])
        for source in rows["sources"]:
            source_map[source["source_id"]] = source

    for index, meta in enumerate(event_meta_rows):
        for model_id in baseline_predictions:
            baseline_predictions[model_id]["retrieval"].append(_build_retrieval_prediction(meta, model_id, index))
            baseline_predictions[model_id]["citation"].extend(_build_citation_predictions(meta, model_id, index))
            baseline_predictions[model_id]["report"].append(_build_report_prediction(meta, model_id, index, source_map))

    review_records = _build_review_records(event_meta_rows, citation_labels, report_labels)

    split_stats: dict[str, dict[str, int]] = {}
    for split in ("dev", "test"):
        split_event_ids = {meta["event_id"] for meta in event_meta_rows if meta["split"] == split}
        split_stats[split] = {
            "event_count": len(split_event_ids),
            "retrieval_case_count": sum(1 for case in all_cases if case["task_type"] == "retrieval" and case["split"] == split),
            "citation_case_count": sum(1 for case in all_cases if case["task_type"] == "citation" and case["split"] == split),
            "report_case_count": sum(1 for case in all_cases if case["task_type"] == "report" and case["split"] == split),
            "source_count": sum(1 for source in all_sources if source["event_id"] in split_event_ids),
        }

    _write_jsonl(DATASET_DIR / "cases.jsonl", all_cases)
    _write_jsonl(DATASET_DIR / "sources.jsonl", all_sources)
    _write_jsonl(DATASET_DIR / "labels" / "retrieval_labels.jsonl", retrieval_labels)
    _write_jsonl(DATASET_DIR / "labels" / "citation_labels.jsonl", citation_labels)
    _write_jsonl(DATASET_DIR / "labels" / "report_labels.jsonl", report_labels)
    _write_jsonl(DATASET_DIR / "reviews" / "review_records.jsonl", review_records)

    for model_id, task_rows in baseline_predictions.items():
        prediction_dir = BASELINES_DIR / model_id / "predictions"
        _write_jsonl(prediction_dir / "retrieval_predictions.jsonl", task_rows["retrieval"])
        _write_jsonl(prediction_dir / "citation_predictions.jsonl", task_rows["citation"])
        _write_jsonl(prediction_dir / "report_predictions.jsonl", task_rows["report"])

    manifest = _manifest(split_stats)
    with (ROOT_DIR / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    summary = {
        "root_dir": str(ROOT_DIR),
        "dataset_dir": str(DATASET_DIR),
        "event_count": len(event_meta_rows),
        "case_count": len(all_cases),
        "source_count": len(all_sources),
        "retrieval_case_count": len(retrieval_labels),
        "citation_case_count": len(citation_labels),
        "report_case_count": len(report_labels),
        "review_record_count": len(review_records),
        "baseline_count": len(baseline_predictions),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate a print-ad run manifest and its structured quality gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quality_gate_contract import check_summary, validate_quality_gate_results
from review_contract import validate_review_contract
from visual_review_contract import validate_visual_review
from visual_generation_capability_contract import validate_visual_generation_capability
from datetime import datetime, timezone
from review_contract import artifact, bound_file, timestamp

sys.dont_write_bytecode = True

BASE_ARTIFACTS = (
    "brief_evidence", "direction_cards", "concept_gate", "quality_gate_results", "run_status",
)
PRODUCTION_ARTIFACTS = (
    "official_asset_manifest", "production_manifest", "human_visual_review",
    "technical_validation",
)
DELIVERY_ARTIFACTS = ("delivery_manifest",)
RUN_SCOPE_ARTIFACTS = {
    "concept-only": BASE_ARTIFACTS,
    "production-candidate": BASE_ARTIFACTS + PRODUCTION_ARTIFACTS,
    "delivery-candidate": BASE_ARTIFACTS + PRODUCTION_ARTIFACTS + DELIVERY_ARTIFACTS,
}
RUN_SCOPE_GATES = {
    "concept-only": {"print-ad.brief-evidence", "print-ad.direction-distinctness"},
    "production-candidate": {
        "print-ad.brief-evidence", "print-ad.direction-distinctness",
        "print-ad.visual-relation-prototype", "print-ad.official-asset-fidelity",
        "print-ad.series-increment", "print-ad.human-visual-quality",
        "print-ad.technical-delivery",
    },
    "delivery-candidate": {
        "print-ad.brief-evidence", "print-ad.direction-distinctness",
        "print-ad.visual-relation-prototype", "print-ad.official-asset-fidelity",
        "print-ad.series-increment", "print-ad.human-visual-quality",
        "print-ad.technical-delivery",
    },
}

# A fixed rubric is the only task-independent instruction sent to a checker.
# The per-artwork request adds exactly one short author claim, never design notes.
INDEPENDENT_CORE_RUBRIC = """你是独立核心检查者。仅看随附实际成图和官方产品图，不读其他文件，不生图，不继承作者历史，不用文案替代可见动作。只凭像素返回原始 JSON {"answers":{五项各含布尔 answer 和具体 observation}}：
1 product_in_core_relation：产品是否进入核心动作/关系本身，而非旁边或前景贴图？
2 action_depicted_without_copy：不看文案能否认出核心动作？
3 claimed_relation_depicted：是否兑现一句声明的关系，拿着就看得出被拿住，坐着就看得出坐在上面？不要求写实；有意的超现实、夸张或放大比例可为是，悬空、贴图、意外比例失调、接触不成立为否，不凭作者意图补证。
4 creative_scene_not_generic：去掉创意是否仍是普通递水、拿产品微笑等任何人都会画的场景？原问答是则本字段 answer=false；具体创意成立为true。
5 product_action_understood_in_three_seconds：陌生人三秒内能否说出产品与动作关系？未真实实测时仅写你的独立预测，不虚构受众或计时。
所有字段归一为true表示通过，任一false即核心失败。不要迎合声明。"""

INDEPENDENT_DIRECTION_RUBRIC = """你是空上下文独立方向检查者。只看下方匿名方向的一句话（画面动作与产品关系），不读其他文件，不接收作者理由，不生图，不继承作者历史。
先剔除近似方案：换背景、标题、风格、颜色但对象关系相同的只保留一项，逐项说明关系近似的原因。
对保留方向强制排序，不并列、不用绝对分；依据画面是否直接演出本题产品利益、看到时是否有意外感、创意本身强弱。不要使用“换成竞品还成立吗”或品牌独占作为门槛或打分项。
逐条判断能否一张图画明白：接触、尺度、关系能否在单幅画面成立；有意超现实允许，不凭作者解释补全动作。不可画方向仍保留真实名次并明确drawable=false，不能出图。
只返回JSON，字段为near_duplicates:[{discarded_direction_id,kept_direction_id,reason}]、ranking:[{direction_id,reason}]（第一项为第一名）、drawability:[{direction_id,drawable,reason}]、all_weak:布尔。ranking和drawability只含去重后保留项，各恰好一次；说明具体比较和可画/不可画原因。若全部创意偏弱，all_weak=true。"""

INDEPENDENT_DIRECTION_RUBRIC_V2 = """你是空上下文独立方向检查者。只看下方匿名方向的一句话（画面动作与产品关系）和匿名案例机制参照，不读其他文件，不接收作者理由，不生图，不继承作者历史。
先逐条做绝对套路筛，再去重、排序。常见套路至少包括：产品顶替日常物件（桥、轴、座椅、积木、拼图块等）、产品拟人（手脚/五官伴随）、接力/递送产品、产品放大成建筑或地标、产品+场景+微笑。每条记录is_trope是/否和具体reason；套路但有新转折可以保留，new_twist须写清由具体消费者时刻、利益或视角翻转产生的额外关系，无转折写null。仅换物件、放大、拟人或加产品联系不能算新转折；有意超现实允许，不能只因放大或坐在产品上就否定有具体转折的方向。普通日常、静态情绪和纪实表达亦可按具体选择成立，不强制奇观。
案例只作强创意的机制参照，不是构图模板；逐条判断候选是否达到参照强度，reference_assessment记录reaches_reference布尔及reason。参照为空则该值写null并说明无可用案例，照常做套路筛与比较，不虚构参照。
剔除近似方案：换背景、标题、风格、颜色但对象关系相同的只保留一项，说明关系近似原因。对保留方向强制排序，不并列、不用绝对分；依据是否直接演出产品利益、意外感、具体创意强弱和参照强度。不要使用“换成竞品还成立吗”或品牌独占作为门槛或打分项。
逐条判断保留方向能否一张图画明白：接触、尺度、关系能否在单幅成立；不凭作者解释补全动作。不可画仍保留真实名次并写drawable=false，不能递补出图。
排序第一名若is_trope=true且new_twist=null，必须all_weak=true；第一名未达到非空参照强度也写true；其他全部偏弱情况照实写true，不能因有相对第一名就写false。全部偏弱最多重新发散一次，第二轮仍偏弱停在方向阶段交用户/总控，不自动出图。后台每轮须至少6个去重后不同方向并覆盖消费者真实时刻、产品利益/事实、反常识或视角翻转三类起点；本检查不接收起点标签，数量不足也不把弱方向升为通过。
只返回JSON：trope_screen:[{direction_id,is_trope,reason,new_twist}]、reference_assessment:[{direction_id,reaches_reference,reason}]（这两项覆盖所有输入各一次）；near_duplicates:[{discarded_direction_id,kept_direction_id,reason}]、ranking:[{direction_id,reason}]（第一项为第一名）、drawability:[{direction_id,drawable,reason}]（这两项仅去重后保留项各一次）、all_weak:布尔。理由具体，不迎合任何候选。"""


def direction_request_v2(sentences_content, references_content):
    return (INDEPENDENT_DIRECTION_RUBRIC_V2 + '\n案例机制参照：\n' + references_content
            + '\n方向一句话清单：\n' + sentences_content)

INDEPENDENT_DIRECTION_RUBRIC_V3 = """你是空上下文独立方向检查者。只看下方匿名方向的一句话、反馈机制反例库和匿名案例机制参照，不读其他文件，不接收作者理由，不生图，不继承作者历史。
先逐条做套路筛，再去重、排序。候选与反例条目为同一抽象机制就判is_trope=true，在counterexample_matches逐条写entry_id与具体匹配reason；无匹配写[]。反例的真人判词范围按judgement_scope理解，不冒充真人对未见方向的评价。常见套路还包括产品替物、拟人伴随、递送/接力、巨物建筑、产品与场景并列。
新转折必须让产品自身的利益/作用在画面里变得可见；new_twist说明额外关系，visible_product_benefit明确使哪项产品利益/作用可见，无有效转折这两个字段都写null。仅空间、尺度、视角的视觉花样，产品只是机械物件，不能算转折，无论是否命中反例库都判无转折套路。例如电池化作滑轮吊起街区，供电作用未出现；吸水材料把潮湿足印变成干爽落脚处，吸水作用可见。有意超现实允许，不能仅因放大或坐在产品上否定让产品利益可见的具体转折。普通日常、静态情绪和纪实表达可按具体选择成立，不强制奇观。
获奖案例机制只帮助排序，不是构图模板或拦截门槛；reference_assessment逐条写reaches_reference布尔及reason，无参照则null并说明。低于参照不能触发all_weak。
剔除近似方案：换背景、标题、风格、颜色但对象关系相同的只保留一项，说明近似原因。对保留方向强制排序，不并列、不用绝对分；依据是否直接演出产品利益、意外感、具体创意强弱，结合参照比较。不要使用竞品替换或品牌独占门槛。
逐条判断保留方向能否一张图画明白：接触、尺度、关系能否在单幅成立；不凭作者解释补全动作。不可画仍保留真实名次并写drawable=false，不能递补出图。
仅当第一名is_trope=true且new_twist=null时all_weak=true；其他情况all_weak=false，不能靠获奖参照强度拦截。全部偏弱最多重新发散一次，第二轮仍弱停在方向阶段交用户/总控，不自动出图。后台每轮至少6个去重后方向且覆盖消费者真实时刻、产品利益/事实、反常识或视角翻转三类起点；本检查不接收起点标签，数量不足不把弱方向升为通过。
只返回JSON：trope_screen:[{direction_id,is_trope,reason,new_twist,visible_product_benefit,counterexample_matches:[{entry_id,reason}]}]、reference_assessment:[{direction_id,reaches_reference,reason}]（这两项覆盖所有输入各一次）；near_duplicates:[{discarded_direction_id,kept_direction_id,reason}]、ranking:[{direction_id,reason}]（第一项为第一名）、drawability:[{direction_id,drawable,reason}]（这两项仅去重后保留项各一次）、all_weak:布尔。理由具体，不迎合任何候选。"""


def direction_request_v3(sentences_content, references_content, counterexamples_content):
    return (INDEPENDENT_DIRECTION_RUBRIC_V3 + '\n反馈机制反例库：\n' + counterexamples_content
            + '\n案例机制参照：\n' + references_content + '\n方向一句话清单：\n' + sentences_content)

INDEPENDENT_DIRECTION_RUBRIC_V4 = """你是空上下文独立方向检查者。只看下方匿名方向的一句话、反馈机制反例库和匿名案例机制参照，不读其他文件，不接收作者理由，不生图，不继承作者历史。
先逐条做套路筛，再去重、排序。候选与反例条目为同一抽象机制就判is_trope=true，在counterexample_matches逐条写entry_id与具体匹配reason；无匹配写[]。反例的真人判词范围按judgement_scope理解，不冒充真人对未见方向的评价。常见套路还包括产品替物、拟人伴随、递送/接力、巨物建筑、产品与场景并列。
套路但有新转折可以保留。新转折可以来自具体的消费者/使用者时刻、产品利益或视角翻转；new_twist须写清超出既有套路的额外关系，twist_basis选consumer-moment、product-benefit或perspective-reversal，无有效转折二者都写null。具体时刻与产品需求之间形成额外关系即可，不要求画面出现服用、使用或产品内部原理，也不要求产品作用过程可见。例如长时间握笔的速写者放下画笔，在放大的护腕包装上松开手指、休息片刻，转折来自用手者的暂停时刻，不因未佩戴护腕而否定；吸水材料把潮湿足印变成干爽落脚处，转折来自吸水利益。普通日常、静态情绪和纪实表达亦可按具体选择成立，不强制奇观；泛化的休息或微笑、仅添加产品用途联系不自动算转折。
补充排除：只是对替身物件做空间、尺度或视角变换，而这一变换与消费者时刻和产品利益都无关，不算新转折；无论是否命中反例库都判无转折套路。例如电池化作滑轮吊起街区，仅制造空间奇观，没有消费者时刻或供电利益的额外关系。视角翻转须带来具体的新关系，不能只换镜头或缩放空间；产品与其使用对象相邻不自动补成转折。有意超现实允许，不能只因放大、替物或坐在产品上否定有具体转折的方向。
获奖案例机制只帮助排序，不是构图模板或拦截门槛；reference_assessment逐条写reaches_reference布尔及reason，无参照则null并说明。低于参照不能触发all_weak。
剔除近似方案：换背景、标题、风格、颜色但对象关系相同的只保留一项，说明近似原因。对保留方向强制排序，不并列、不用绝对分；依据具体转折、消费者时刻或产品利益的关联、意外感和创意本身强弱，结合参照比较；空间奇观或动作复杂不自动胜过具体转折。不要使用竞品替换或品牌独占门槛。
逐条判断保留方向能否一张图画明白：接触、尺度、关系能否在单幅成立；不凭作者解释补全动作。不可画仍保留真实名次并写drawable=false，不能递补出图。
仅当第一名is_trope=true且new_twist=null时all_weak=true；其他情况all_weak=false，不能靠获奖参照强度拦截。全部偏弱最多重新发散一次，第二轮仍弱停在方向阶段交用户/总控，不自动出图。后台每轮至少6个去重后方向且覆盖消费者真实时刻、产品利益/事实、反常识或视角翻转三类起点；本检查不接收起点标签，数量不足不把弱方向升为通过。
只返回JSON：trope_screen:[{direction_id,is_trope,reason,new_twist,twist_basis,counterexample_matches:[{entry_id,reason}]}]、reference_assessment:[{direction_id,reaches_reference,reason}]（这两项覆盖所有输入各一次）；near_duplicates:[{discarded_direction_id,kept_direction_id,reason}]、ranking:[{direction_id,reason}]（第一项为第一名）、drawability:[{direction_id,drawable,reason}]（这两项仅去重后保留项各一次）、all_weak:布尔。理由具体，不迎合任何候选。"""


def direction_request_v4(sentences_content, references_content, counterexamples_content):
    return (INDEPENDENT_DIRECTION_RUBRIC_V4 + '\n反馈机制反例库：\n' + counterexamples_content
            + '\n案例机制参照：\n' + references_content + '\n方向一句话清单：\n' + sentences_content)

INDEPENDENT_DIRECTION_RUBRIC_V5 = """你是空上下文独立方向检查者。只看下方匿名方向的一句话、反馈机制反例库和匿名案例机制参照，不读其他文件，不接收句子以外的作者理由，不生图，不继承作者历史。
方向句固定为“画面动作 + 产品关系 + 创意依据”；创意依据在句中明确写出类型和内容，basis_type对应consumer-moment（人的时刻或洞察）、product-benefit（产品真相或利益）、perspective-reversal（视角翻转或文化意味），basis是同一依据原文。三类都可，不限定消费者时刻。只写画面结构不交代依据的方向句无效，不能交盲评。依据只是作者主张，不是已经成立的转折；检查者可以依据句中写明的依据判断，但必须核对该依据是否真的在画面动作与产品关系中成立，并说明超出套路的具体关系。依据与动作或产品关系不相干、只补好听的时刻或利益词、仅声明寓意，都不能因此放行；不凭句子以外的解释补关系。
先逐条做套路筛，再去重、排序。候选与反例条目为同一抽象机制就判is_trope=true，在counterexample_matches逐条写entry_id与具体匹配reason；无匹配写[]。反例的真人判词范围按judgement_scope理解，不冒充真人对未见方向的评价。常见套路还包括产品替物、拟人伴随、递送/接力、巨物建筑、产品与场景并列。
套路但有新转折可以保留。新转折可以来自具体的消费者/使用者时刻、产品利益或视角翻转；new_twist须写清超出既有套路的额外关系，twist_basis选consumer-moment、product-benefit或perspective-reversal，无有效转折二者都写null。具体时刻与产品需求之间形成额外关系即可，不要求画面出现服用、使用或产品内部原理，也不要求产品作用过程可见。例如长时间握笔的速写者放下画笔，在放大的护腕包装上松开手指、休息片刻，转折来自用手者的暂停时刻，不因未佩戴护腕而否定；吸水材料把潮湿足印变成干爽落脚处，转折来自吸水利益。普通日常、静态情绪和纪实表达亦可按具体选择成立，不强制奇观；泛化的休息或微笑、仅添加产品用途联系不自动算转折。
补充排除：只是对替身物件做空间、尺度或视角变换，而这一变换与消费者时刻和产品利益都无关，不算新转折；无论是否命中反例库都判无转折套路。例如电池化作滑轮吊起街区，仅制造空间奇观，没有消费者时刻或供电利益的额外关系。视角翻转须带来具体的新关系，不能只换镜头或缩放空间；产品与其使用对象相邻不自动补成转折。有意超现实允许，不能只因放大、替物或坐在产品上否定有具体转折的方向。
获奖案例机制只帮助排序，不是构图模板或拦截门槛；reference_assessment逐条写reaches_reference布尔及reason，无参照则null并说明。低于参照不能触发all_weak。
剔除近似方案：换背景、标题、风格、颜色但对象关系相同的只保留一项，说明近似原因。对保留方向强制排序，不并列、不用绝对分；依据具体转折、消费者时刻或产品利益的关联、意外感和创意本身强弱，结合参照比较；空间奇观或动作复杂不自动胜过具体转折。不要使用竞品替换或品牌独占门槛。
逐条判断保留方向能否一张图画明白：接触、尺度、关系能否在单幅成立；不凭作者解释补全动作。不可画仍保留真实名次并写drawable=false，不能递补出图。
仅当第一名is_trope=true且new_twist=null时all_weak=true；其他情况all_weak=false，不能靠获奖参照强度拦截。全部偏弱最多重新发散一次，第二轮仍弱停在方向阶段交用户/总控，不自动出图。后台每轮至少6个去重后方向且覆盖消费者真实时刻、产品利益/事实、反常识或视角翻转三类起点；本检查不接收后台起点标签；句中依据类型及其同文basis字段属于方向句本身，数量不足不把弱方向升为通过。
只返回JSON：trope_screen:[{direction_id,is_trope,reason,new_twist,twist_basis,counterexample_matches:[{entry_id,reason}]}]、reference_assessment:[{direction_id,reaches_reference,reason}]（这两项覆盖所有输入各一次）；near_duplicates:[{discarded_direction_id,kept_direction_id,reason}]、ranking:[{direction_id,reason}]（第一项为第一名）、drawability:[{direction_id,drawable,reason}]（这两项仅去重后保留项各一次）、all_weak:布尔。理由具体，不迎合任何候选。"""

DIRECTION_BASIS_TYPES = {
    'consumer-moment': '人的时刻或洞察',
    'product-benefit': '产品真相或利益',
    'perspective-reversal': '视角翻转或文化意味',
}


def validate_direction_sentence_v5(candidate):
    """Validate the recorded basis and its literal presence in the one-sentence input."""
    import re
    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())
    if not isinstance(candidate, dict) or set(candidate) != {'direction_id', 'statement', 'basis_type', 'basis'}:
        raise ValueError('Every v5 direction needs direction_id, statement, basis_type and basis only')
    basis_type, basis = candidate['basis_type'], candidate['basis']
    if not isinstance(basis_type, str) or basis_type not in DIRECTION_BASIS_TYPES:
        raise ValueError('Invalid direction basis_type; choose one of the three basis types')
    if not nonempty(basis) or '\n' in basis or '\r' in basis:
        raise ValueError('Direction basis must be nonempty single-line text')
    sentence = candidate['statement']
    suffix = '；创意依据（' + DIRECTION_BASIS_TYPES[basis_type] + '）：' + basis + '。'
    if not nonempty(candidate['direction_id']) or not nonempty(sentence) or len(sentence) > 200:
        raise ValueError('Direction ID and a short direction sentence are required')
    if not sentence.endswith(suffix) or not sentence[:-len(suffix)].strip():
        raise ValueError('Direction statement must contain action + product relation + exact typed creative basis')
    if '\n' in sentence or '\r' in sentence or len(re.split(r'[。！？.!?]', sentence.rstrip('。！？.!?'))) != 1:
        raise ValueError('Direction statement must remain one single-line sentence')


def direction_request_v5(sentences_content, references_content, counterexamples_content):
    candidates = json.loads(sentences_content)
    if not isinstance(candidates, list) or not candidates:
        raise ValueError('Direction sentences must be a nonempty list')
    for candidate in candidates:
        validate_direction_sentence_v5(candidate)
    return (INDEPENDENT_DIRECTION_RUBRIC_V5 + '\n反馈机制反例库：\n' + counterexamples_content
            + '\n案例机制参照：\n' + references_content + '\n方向一句话清单：\n' + sentences_content)

INDEPENDENT_DIRECTION_RUBRIC_V6 = """你是空上下文独立方向检查者。只看下方匿名方向的一句话、反馈机制反例库和匿名案例机制参照，不读其他文件，不接收句子以外的作者理由，不生图，不继承作者历史。
方向句固定为“画面动作 + 产品关系 + 创意依据”，依据可以是人的时刻或洞察、产品真相或利益、视角翻转或文化意味；basis_type和basis为同一原句的同文依据字段。依据只是作者主张，写得相关不等于存在新转折。
先逐条做绝对套路筛，再去重、排序。常见套路包括产品顶替日常物件（桥、轴、座椅等）、产品拟人、接力或递送、放大成建筑或地标、产品+场景+微笑。每条记录is_trope和具体reason。
反馈机制反例库具有直接拦截效力：只要对象关系机制相同，即is_trope=true，counterexample_matches引用已知entry_id及具体关系；无论任何新转折或利益，new_twist、twist_basis、object_relation_change必须全为null，不得放行。真人否定这些机制时已知道相应产品利益。只按条目实际机制匹配，不扩大原判词范围，不因出现产品前景或辅助线条就自动命中；核心动作被旁置贴图或说明线代替才命中对应条目。
未命中反例库的套路，只有新转折改变画面中的对象关系本身才可保留。必须回答“新转折改变了画面中哪个对象关系”：object_relation_change={kind:"object-relation",objects:[对象A,对象B],before:既有套路关系,after:本方向可见的新关系}；before与after不得相同。new_twist说明这个变化，twist_basis选consumer-moment/product-benefit/perspective-reversal。只是把产品利益或创意依据重新说一遍，例如“门仍能打开，对应报警后还能开门”，不能算新转折；添加警告符号、暖光、产品用途、耐用数字或把物件放大，不自动改变对象关系。无有效转折这三个字段全写null。不能用依据替画面补关系，不要求必须画服用、内部原理或写实，具体人物时刻、静态情绪或有意超现实可成立，但须指出句中可见的关系改变，而非附一段解释。
普通日常、静态表情与纪实可以成立，不因没有复杂物理动作而直接否定；产品只是与场景并列则按相应机制拦截。案例机制只作创意强度比较与排序，空参照时reaches_reference=null并说明，不因此卡住。
near_duplicates写出保留和去掉项及具体理由；ranking覆盖去重后的各项一次，合格方向排在被拦方向之前；drawability判断动作、接触、方向或因果能否在一幅画面清楚演出。每条套路判断和参照判断覆盖所有输入一次。第一名为无有效转折的套路时all_weak=true，其他情况false；不可因有相对第一名放行。生产每轮后台至少6个去重后方向且覆盖三类起点，最多重新发散一次，第二轮仍弱停下；本诊断若输入不足6条仍如实评价，不补方向、不升格为生产通过。
只返回JSON：trope_screen:[{direction_id,is_trope,reason,new_twist,twist_basis,object_relation_change,counterexample_matches:[{entry_id,reason}]}]、reference_assessment:[{direction_id,reaches_reference,reason}]、near_duplicates:[{discarded_direction_id,kept_direction_id,reason}]、ranking:[{direction_id,reason}]、drawability:[{direction_id,drawable,reason}]、all_weak:boolean。不要代码围栏、其他解释或用户选择。"""


def direction_request_v6(sentences_content, references_content, counterexamples_content):
    candidates = json.loads(sentences_content)
    if not isinstance(candidates, list) or not candidates:
        raise ValueError('Direction sentences must be a nonempty list')
    for candidate in candidates:
        validate_direction_sentence_v5(candidate)
    return (INDEPENDENT_DIRECTION_RUBRIC_V6 + '\n反馈机制反例库：\n' + counterexamples_content
            + '\n案例机制参照：\n' + references_content + '\n方向一句话清单：\n' + sentences_content)


def validate_direction_turn_v6(screen):
    """Enforce recorded relation changes; semantics still require an independent checker."""
    def require(value, reason):
        if not value:
            raise ValueError(reason)
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    change = screen.get('object_relation_change')
    if screen['counterexample_matches']:
        require(screen['is_trope'] and screen['new_twist'] is None
                and screen['twist_basis'] is None and change is None,
                'Feedback mechanism is a hard rejection; no new twist may rescue it')
    elif screen['new_twist'] is None:
        require(change is None, 'No new twist requires null object_relation_change')
    else:
        require(isinstance(change, dict) and set(change) == {'kind', 'objects', 'before', 'after'}
                and change['kind'] == 'object-relation'
                and isinstance(change['objects'], list) and len(change['objects']) >= 2
                and all(text(x) for x in change['objects'])
                and len(set(change['objects'])) == len(change['objects'])
                and text(change['before']) and text(change['after'])
                and change['before'].strip() != change['after'].strip(),
                'New twist must change a named object relation; benefit restatement is not a change')


def direction_eligible_v6(screen):
    return not screen['counterexample_matches'] and (not screen['is_trope'] or screen['new_twist'] is not None)


def direction_choice_rows_v6(candidates, result):
    """Concise, comparable rows copied from original sentences and blind judgments."""
    by_id = {x['direction_id']: x for x in candidates}
    screens = {x['direction_id']: x for x in result['trope_screen']}
    draw = {x['direction_id']: x for x in result['drawability']}
    return [dict(direction_id=x['direction_id'], statement=by_id[x['direction_id']]['statement'],
                 basis=by_id[x['direction_id']]['basis'], rank=i+1,
                 is_trope=screens[x['direction_id']]['is_trope'],
                 trope_reason=screens[x['direction_id']]['reason'],
                 counterexample_matches=screens[x['direction_id']]['counterexample_matches'],
                 eligible=direction_eligible_v6(screens[x['direction_id']]),
                 drawable=draw[x['direction_id']]['drawable'],
                 drawability_reason=draw[x['direction_id']]['reason'], checker_comment=x['reason'])
            for i, x in enumerate(result['ranking'])]


def direction_choice_judgment_text_v6(row):
    """Render the unchanged judgments in each user-facing choice row."""
    yesno = lambda value: '是' if value else '否'
    matches = '；'.join(x['entry_id'] + '（' + x['reason'] + '）'
                       for x in row['counterexample_matches']) or '无'
    return (f"套路：{yesno(row['is_trope'])}；套路理由：{row['trope_reason']}；"
            f"反例命中：{matches}；自动采用合格：{yesno(row['eligible'])}；"
            f"可画：{yesno(row['drawable'])}；可画理由：{row['drawability_reason']}")


def validate_direction_choice_list_v6(root, adoption, by_id, result, completed, decided):
    from review_contract import bound_file, timestamp
    choice = load_json(bound_file(root, adoption['choice_list']))
    if set(choice) != {'presented_at', 'rows', 'user_facing_copy'}:
        raise ValueError('Direction choice list needs presented_at, rows and user_facing_copy')
    if choice['rows'] != direction_choice_rows_v6(list(by_id.values()), result):
        raise ValueError('Direction choice list must preserve deduplicated ranking, basis, trope, drawability and checker comment')
    shown = timestamp(choice['presented_at'])
    if shown < completed or shown >= timestamp(adoption['adopted_at']) or (adoption['selection_mode'] == 'user' and shown > decided):
        raise ValueError('Present the choice list after blind return and before user choice')
    copy = bound_file(root, choice['user_facing_copy']).read_text(encoding='utf-8')
    for row in choice['rows']:
        lines = [line for line in copy.splitlines() if row['direction_id'] in line and row['statement'] in line]
        if not any(all(str(row[k]) in line for k in ('basis', 'checker_comment'))
                   and direction_choice_judgment_text_v6(row) in line for line in lines):
            raise ValueError('User-facing direction list must include each sentence, basis and checker comment with original trope/counterexample/drawability judgments and reasons')


def validate_main_visual_record_v6(root, record, *, current_refs=(), core_failed=False, control=None):
    """Bind complete drafts to actual subject assets and stop an exhausted failed run."""
    from review_contract import bound_file, load
    def require(value, reason):
        if not value:
            raise ValueError(reason)
    require(record.get('main_visual_contract') == 'main-visual-v1', 'Production record needs main-visual-v1')
    rows = record.get('main_visuals')
    require(isinstance(rows, list), 'Production record must mark every complete main visual source')
    identities = set()
    for row in rows:
        artifact = bound_file(root, row['artifact'])
        key = (str(artifact), row['artifact']['sha256'])
        require(key not in identities, 'Duplicate main visual artifact')
        identities.add(key)
        require(row.get('source') in {'generated', 'edited', 'user-asset', 'native-drawn'}, 'Unknown main visual source')
        require(row.get('role') in {'representative', 'passed', 'failed-draft', 'intermediate'}, 'Declare actual main visual role')
        require(row.get('core_check') in {'passed', 'failed', 'pending'}, 'Declare actual main visual core check')
        require(row['source'] != 'native-drawn' or (row['role'] in {'failed-draft', 'intermediate'} and row['core_check'] != 'passed'),
                'native-drawn main visual cannot be a representative or passed complete draft')
        require(isinstance(row.get('sources'), list) and row['sources']
                and isinstance(row.get('evidence'), list) and row['evidence'],
                'Main visual source needs bound subject assets and generation/edit/user evidence')
        for ref in row['sources'] + row['evidence']:
            bound_file(root, ref)
    for ref in current_refs:
        bound_file(root, ref)
        matches = [x for x in rows if x['artifact']['path'] == ref['path'] and x['artifact']['sha256'] == ref['sha256']]
        require(len(matches) == 1, 'Current/complete draft main visual source is missing')
        require(matches[0]['source'] != 'native-drawn', 'native-drawn main visual cannot serve as current representative')
    budget = record.get('image_budget')
    require(isinstance(budget, dict) and type(budget.get('limit')) is int and type(budget.get('used')) is int
            and 0 <= budget['used'] <= budget['limit'], 'Record actual image budget limit and used count')
    failure = core_failed or any(x['core_check'] == 'failed' and x['role'] == 'representative' for x in rows)
    exhausted = failure and budget['used'] == budget['limit']
    if exhausted:
        handoff = record.get('exhausted_failure_handoff')
        require(isinstance(handoff, dict) and handoff.get('state') == 'stopped'
                and handoff.get('decision_request') == 'additional-budget-or-change-direction'
                and isinstance(handoff.get('reason'), str) and bool(handoff['reason'].strip())
                and isinstance(handoff.get('failed_artifacts'), list) and handoff['failed_artifacts'],
                'Failed main visual with exhausted budget must stop and hand back failure and reason')
        failed = {(x['artifact']['path'], x['artifact']['sha256']) for x in rows if x['core_check'] == 'failed'}
        handed = {(x['path'], x['sha256']) for x in handoff['failed_artifacts']}
        current = {(x['path'], x['sha256']) for x in current_refs}
        require(handed <= failed and (not current or current <= handed), 'Hand back the actual current failed drafts')
        for ref in handoff['failed_artifacts']:
            bound_file(root, ref)
        copy = bound_file(root, handoff['user_facing_copy']).read_text(encoding='utf-8')
        require(handoff['reason'] in copy and all(x['path'] in copy for x in handoff['failed_artifacts'])
                and '追加额度' in copy and '换方向' in copy, 'Failure handoff must expose draft paths, reason and both user decisions')
        require(control is not None and load(control).get('state') == 'stopped', 'Exhausted failed main visual requires stopped execution control')
    return {'exhausted_failure': exhausted, 'drafts': len(rows)}


def validate_main_visual_provenance_v6(root, manifest):
    from review_contract import inside
    try:
        record = load_json(inside(root, manifest['artifacts']['production_manifest']))
        assessments = manifest.get('core_creative_review', {}).get('assessments', [])
        current_ids = set(manifest.get('core_creative_review', {}).get('current_assessment_ids', []))
        current = [x['artifact'] for x in assessments if x['id'] in current_ids]
        # Every completed draft, including failed history, has a bound source row.
        all_refs = [x['artifact'] for x in assessments]
        known = {(x['artifact']['path'], x['artifact']['sha256']) for x in record.get('main_visuals', [])}
        if any((x['path'], x['sha256']) not in known for x in all_refs):
            raise ValueError('Every complete draft assessment needs a main visual source record')
        failed = any(any(a.get('answer') is False for a in x['answers'].values()) for x in assessments if x['id'] in current_ids)
        # Recorded pass may not override actual independent answers.
        for assessment in assessments:
            row = next(x for x in record['main_visuals'] if x['artifact']['path'] == assessment['artifact']['path'] and x['artifact']['sha256'] == assessment['artifact']['sha256'])
            if any(a.get('answer') is False for a in assessment['answers'].values()) and row['core_check'] != 'failed':
                raise ValueError('Main visual source record cannot overwrite an independent core failure')
        result = validate_main_visual_record_v6(root, record, current_refs=current, core_failed=failed,
                                               control=inside(root, manifest['execution_control']))
        if result['exhausted_failure'] and manifest['run_scope'] == 'delivery-candidate':
            raise ValueError('Exhausted failure handoff is stopped, not a passed delivery candidate')
        return check('main-visual-provenance', True, result)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration) as exc:
        return check('main-visual-provenance', False, str(exc))


def validate_main_visual_dispatch_v6(root, manifest, request):
    from review_contract import inside, load
    source = request.get('main_visual_source')
    action = request.get('main_visual_action')
    if action not in {'create', 'replace', 'layout-only', 'local-composite'}:
        raise ValueError('Production request must declare main_visual_action')
    if source not in {'generated', 'edited', 'user-asset'}:
        raise ValueError('Main visual production cannot use native-drawn; declare generated/edited/user-asset')
    path = manifest.get('artifacts', {}).get('production_manifest')
    if path and inside(root, path).is_file():
        record = load(inside(root, path))
        if manifest.get('core_creative_review', {}).get('assessments'):
            current = validate_main_visual_provenance_v6(root, dict(manifest, run_scope='production-candidate'))
            if not current['passed']:
                raise ValueError('Main visual dispatch blocked: ' + str(current['evidence']))
            if current['evidence']['exhausted_failure']:
                raise ValueError('Exhausted failed main visual is stopped; user must decide additional budget or direction')
        verdict = validate_main_visual_record_v6(root, record, control=inside(root, manifest['execution_control']))
        if verdict['exhausted_failure']:
            raise ValueError('Exhausted failed main visual is stopped; user must decide additional budget or direction')
        if action in {'layout-only', 'local-composite'}:
            subjects = [x for x in record['main_visuals'] if x['source'] == source and x['source'] != 'native-drawn']
            if not subjects:
                raise ValueError('Local layout/composite must preserve an existing generated/edited/user subject')
    elif action in {'layout-only', 'local-composite'}:
        raise ValueError('Local layout/composite needs existing main visual source evidence')


INDEPENDENT_BLIND_RUBRIC = """你是第一次看到这张平面广告的陌生观看者。不要读取任何文件，只看附图。
请只根据画面像素回答，先不要借助标题和文案推断：
1. 用一句话说出画面里正在发生什么动作或变化（谁/什么，在做什么，往哪个方向变化）。
2. 用一句话说出产品在这个动作里起什么作用（如果看不出作用，就写“看不出”）。
3. 列出你不确定、可能有两种读法的地方。
最后输出 JSON：{"action":"...","product_role":"...","ambiguities":["..."]}"""

INDEPENDENT_COMPARE_RUBRIC = """你是独立核心检查者。盲读已完成并保存，不能依据作者声明改写盲读。只看该盲读、同一成图、官方产品图和作者一句话声明，不读其他文件，不生图。
先比较动作、变化/因果方向、产品角色：任一不一致，第3问为否；盲读看不出产品作用，第1问为否。逐项判断盲读歧义：影响产品角色、动作方向或接触成立等主关系，第5问为否；次要歧义只记录，不判失败。
保留原五问及归一规则：1 product_in_core_relation 产品参与核心关系；2 action_depicted_without_copy 不借文案认出动作；3 claimed_relation_depicted 兑现声明关系，有意超现实/夸张允许，悬空、贴图、意外比例失调或接触不成立为否；4 creative_scene_not_generic 具体创意成立，普通递水或拿产品微笑为否；5 product_action_understood_in_three_seconds 陌生人三秒认出产品动作，未实测仅作预测。
返回JSON：blind_read_sha256；comparison含action、change_direction、product_role（各含matches布尔、blind_observation、claim_observation）和ambiguities（逐项含blind_ambiguity、affects_main_relation布尔、aspect=product-role/action-direction/contact/other-main/secondary、observation）；answers含五项，各含answer布尔、像素observation、blind_read_sha256及comparison_evidence（引用action/change_direction/product_role/ambiguities中的非空键清单）。所有true才通过，任一false沿原完整返工合同。"""


INDEPENDENT_BLIND_RUBRIC_V2 = INDEPENDENT_BLIND_RUBRIC.split('最后输出 JSON：')[0] + '''4. 单独列出说明性手段：箭头、引导线/指向线、标注文字、透明重影/残影、图解符号、对话框等；有则逐项描述，无则空数组。
5. 假设去掉这些说明手段，产品与动作的关系还由造型、动作、接触、空间本身成立吗？只写可见证据，看不出就写“看不出”；速度线或造型线本身不自动判失败。
最后输出 JSON：{"action":"...","product_role":"...","ambiguities":["..."],"explanatory_devices":["..."],"relation_without_devices":"..."}'''

INDEPENDENT_COMPARE_RUBRIC_V4 = INDEPENDENT_COMPARE_RUBRIC.split('返回JSON：')[0] + '''声明是方向采用时锁定的原句，不能逐稿改写以迎合盲读。逐字保留盲读说明手段清单及去掉后的观察，判据是去掉说明手段后关系是否仍由造型、动作、接触、空间本身成立。若产品与动作的关系只靠箭头、引导线/指向线、标注、透明重影/残影、图解符号、对话框等才读得出，第1、3、4问必须为否，按核心失败完整返工。不是禁止一切线条或速度线；造型语言去掉后关系仍成立可以通过。有意超现实、夸张与放大比例仍允许，但不能靠说明手段替代演出关系。
返回JSON：blind_read_sha256、core_claim_sha256；comparison含action、change_direction、product_role（各含matches布尔、blind_observation、claim_observation）、ambiguities（逐项含blind_ambiguity、affects_main_relation布尔、aspect、observation）、explanatory_devices（逐字原清单）、device_removal（blind_observation逐字引用relation_without_devices、relation_still_holds布尔、像素observation）；answers含原五项，各含answer、observation、blind_read_sha256、非空comparison_evidence键清单（action/change_direction/product_role/ambiguities/explanatory_devices/device_removal）。所有true才通过，任一false沿原完整返工合同。'''


def claim_digest(statement):
    """The original sentence's UTF-8 bytes, without trimming or newline changes."""
    import hashlib
    return hashlib.sha256(statement.encode('utf-8')).hexdigest()


def load_claim_lock(root, adoption):
    lock = load_json(bound_file(root, adoption['claim_lock']))
    if (set(lock) != {'direction_id', 'statement', 'statement_sha256', 'adopted_at', 'blind_review'}
            or lock['direction_id'] != adoption['direction_id']
            or lock['adopted_at'] != adoption['adopted_at'] or lock['blind_review'] != adoption['blind_review']
            or not isinstance(lock['statement'], str) or not lock['statement'].strip()
            or claim_digest(lock['statement']) != lock['statement_sha256']):
        raise ValueError('Claim lock must bind adoption, blind review and original statement hash')
    bundle = load_json(bound_file(root, lock['blind_review']))
    last = load_json(bound_file(root, bundle['rounds'][-1]))
    sentences = json.loads(bound_file(root, last['inputs'][0]['file']).read_text(encoding='utf-8'))
    winner = (adoption['direction_id'] if last.get('rubric_version') == 'print-direction-v6'
              else last['result']['ranking'][0]['direction_id'])
    original = next(v['statement'] for v in sentences if v['direction_id'] == winner)
    if winner != lock['direction_id'] or original != lock['statement']:
        raise ValueError('Claim lock differs from adopted direction blind sentence')
    return lock


def blind_input_digest(inputs):
    """Hash the exact allowed image inventory, independently of the fixed prompt."""
    import hashlib
    return hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def validate_blind_core(root, row, render, record, invocation_keys, locked_claim=None):
    """Extend the existing five-question check; historical v2 remains unchanged."""
    from visual_review_contract import image_file

    def require(value, reason):
        if not value:
            raise ValueError(reason)

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def time(value):
        result = timestamp(value)
        require(result <= datetime.now(timezone.utc), 'Blind/compare timestamp is in the future')
        return result

    def metadata(value, version, extra):
        fields = {'rubric_version', 'checker_context', 'author_session_id', 'checker_session_id',
                  'invocation_id', 'unavailable_metadata', 'started_at', 'completed_at',
                  'inputs', 'request', 'raw_return'} | extra
        require(set(value) == fields and value['rubric_version'] == version
                and value['checker_context'] == 'fresh-isolated', 'Blind/compare record has invalid fields or context')
        require(nonempty(value['author_session_id']), 'Author session required')
        unavailable = value['unavailable_metadata']
        require(isinstance(unavailable, dict) and set(unavailable) <= {'checker_session_id', 'invocation_id'},
                'Invalid unavailable checker metadata')
        for key in ('checker_session_id', 'invocation_id'):
            require(nonempty(value[key]) or (value[key] is None and nonempty(unavailable.get(key))),
                    'Record real checker identifier or host-unavailable explanation')
            require(value[key] != value['author_session_id'], 'The author cannot be the independent checker')

    def inputs(value, roles):
        require(isinstance(value, list) and len(value) == len(roles)
                and all(isinstance(v, dict) and set(v) == {'role', 'file'} for v in value)
                and {v['role'] for v in value} == roles,
                'Blind inputs must contain only artwork; compare inputs only artwork, official asset and core-action')
        refs = {v['role']: v['file'] for v in value}
        for ref in refs.values():
            require(isinstance(ref, dict) and set(ref) <= {'path', 'relative_path', 'sha256'}
                    and {'path', 'sha256'} <= set(ref), 'Input descriptors cannot contain author explanations')
            bound_file(root, ref)
        require(refs['artwork'] == row['observed_image'], 'Blind/compare artwork input hash differs from actual image')
        image_file(root, refs['artwork'])
        return refs

    locked = locked_claim is not None
    metadata(record, 'print-core-v4' if locked else 'print-core-v3',
             {'blind_read', 'core_claim_sha256'} if locked else {'blind_read'})
    if locked:
        require(row.get('core_claim_sha256') == record['core_claim_sha256'] == locked_claim['statement_sha256'],
                'Comparison claim hash must equal adoption locked claim hash')
        require(row['core_action'] == locked_claim['statement'], 'Core declaration drift: change direction and blind-review again')
    blind_ref = record['blind_read']
    blind = load_json(bound_file(root, blind_ref))
    metadata(blind, 'print-core-blind-v2' if locked else 'print-core-blind-v1', {'input_prepared_at', 'saved_at', 'input_manifest_sha256'})
    require(blind['author_session_id'] == record['author_session_id'], 'Blind/compare author identity differs')
    identity = (blind['checker_session_id'], blind['invocation_id'])
    if any(nonempty(v) for v in identity):
        require(identity not in invocation_keys, 'A new complete draft needs a new blind checker invocation')
        invocation_keys.add(identity)
    compare_identity = (record['checker_session_id'], record['invocation_id'])
    if compare_identity != identity and any(nonempty(v) for v in compare_identity):
        require(compare_identity not in invocation_keys, 'A new complete draft needs a new comparison checker invocation')
        invocation_keys.add(compare_identity)
    require(time(render['created_at']) <= time(blind['input_prepared_at']) <= time(blind['started_at'])
            <= time(blind['completed_at']) <= time(blind['saved_at']) < time(record['started_at'])
            <= time(record['completed_at']) <= time(row['checked_at']),
            'Blind read must follow rendering and be saved strictly before comparison; return before checked_at')
    inputs(blind['inputs'], {'artwork'})
    require(blind['input_manifest_sha256'] == blind_input_digest(blind['inputs']), 'Blind input inventory hash differs')
    require(bound_file(root, blind['request']).read_text(encoding='utf-8') == (INDEPENDENT_BLIND_RUBRIC_V2 if locked else INDEPENDENT_BLIND_RUBRIC),
            'Blind request contains author declaration/explanation or differs from fixed pixel-only rubric')
    raw_blind = load_json(bound_file(root, blind['raw_return']))
    require(set(raw_blind) == ({'action', 'product_role', 'ambiguities', 'explanatory_devices', 'relation_without_devices'} if locked else {'action', 'product_role', 'ambiguities'})
            and nonempty(raw_blind['action']) and nonempty(raw_blind['product_role'])
            and isinstance(raw_blind['ambiguities'], list)
            and all(nonempty(v) for v in raw_blind['ambiguities']), 'Preserve original blind action, product role and ambiguities')
    refs = inputs(record['inputs'], {'artwork', 'official-product-asset', 'core-action'})
    require(refs['official-product-asset'] == row['official_product_asset'], 'Compare official product asset differs')
    image_file(root, refs['official-product-asset'])
    require(bound_file(root, refs['core-action']).read_text(encoding='utf-8') == row['core_action'], 'Compare core-action differs')
    require(bound_file(root, record['request']).read_text(encoding='utf-8') ==
            (INDEPENDENT_COMPARE_RUBRIC_V4 if locked else INDEPENDENT_COMPARE_RUBRIC) + '\n核心动作/关系：' + row['core_action'] + '\n盲读记录SHA256：' + blind_ref['sha256']
            + ('\n锁定声明SHA256：' + locked_claim['statement_sha256'] if locked else ''),
            'Comparison request contains author explanation or lacks blind hash')
    raw = load_json(bound_file(root, record['raw_return']))
    require(set(raw) == ({'blind_read_sha256', 'comparison', 'answers', 'core_claim_sha256'} if locked else {'blind_read_sha256', 'comparison', 'answers'}) and raw['blind_read_sha256'] == blind_ref['sha256'],
            'Comparison must cite saved blind record hash')
    if locked:
        require(raw['core_claim_sha256'] == locked_claim['statement_sha256'], 'Raw comparison claim hash must equal adoption locked claim hash')
    comparison = raw['comparison']
    axes = {'action', 'change_direction', 'product_role'}
    extra = {'ambiguities', 'explanatory_devices', 'device_removal'} if locked else {'ambiguities'}
    require(isinstance(comparison, dict) and set(comparison) == axes | extra, 'Compare all three relation axes')
    for axis in axes:
        value = comparison[axis]
        expected = raw_blind['product_role'] if axis == 'product_role' else raw_blind['action']
        require(isinstance(value, dict) and set(value) == {'matches', 'blind_observation', 'claim_observation'}
                and type(value['matches']) is bool and value['blind_observation'] == expected
                and nonempty(value['claim_observation']), 'Comparison must quote original blind observation for '+axis)
    ambiguities = comparison['ambiguities']
    require(isinstance(ambiguities, list) and len(ambiguities) == len(raw_blind['ambiguities']), 'Compare every blind ambiguity')
    for original, value in zip(raw_blind['ambiguities'], ambiguities):
        require(isinstance(value, dict) and set(value) == {'blind_ambiguity', 'affects_main_relation', 'aspect', 'observation'}
                and value['blind_ambiguity'] == original and type(value['affects_main_relation']) is bool
                and value['aspect'] in {'product-role', 'action-direction', 'contact', 'other-main', 'secondary'}
                and value['affects_main_relation'] == (value['aspect'] != 'secondary') and nonempty(value['observation']),
                'Classify each original ambiguity as main-relation or secondary')
    require(raw['answers'] == row['answers'], 'Assessment must preserve comparison raw return answers')
    for answer in row['answers'].values():
        require(set(answer) == {'answer', 'observation', 'blind_read_sha256', 'comparison_evidence'}
                and answer['blind_read_sha256'] == blind_ref['sha256']
                and isinstance(answer['comparison_evidence'], list) and answer['comparison_evidence']
                and set(answer['comparison_evidence']) <= axes | extra, 'Every answer must cite blind and comparison evidence')
    if locked:
        devices = raw_blind['explanatory_devices']
        removal = comparison['device_removal']
        require(isinstance(devices, list) and all(nonempty(v) for v in devices)
                and comparison['explanatory_devices'] == devices
                and nonempty(raw_blind['relation_without_devices']), 'List and preserve all blind explanatory devices and removal observation')
        require(isinstance(removal, dict) and set(removal) == {'blind_observation', 'relation_still_holds', 'observation'}
                and removal['blind_observation'] == raw_blind['relation_without_devices']
                and type(removal['relation_still_holds']) is bool and nonempty(removal['observation']),
                'Device removal comparison must quote original blind observation')
        if devices and not removal['relation_still_holds']:
            for q in ('product_in_core_relation', 'claimed_relation_depicted', 'creative_scene_not_generic'):
                require(row['answers'][q]['answer'] is False, 'Only explanatory devices depict relation: questions 1/3/4 must be false')
                require({'explanatory_devices', 'device_removal'} <= set(row['answers'][q]['comparison_evidence']),
                        'Device-dependent failure must cite device removal evidence')
    unknown = any(v in raw_blind['product_role'].replace(' ', '') for v in ('看不出', '无法判断', '无法识别'))
    require(not unknown or row['answers']['product_in_core_relation']['answer'] is False,
            'Blind read cannot identify product role: question 1 must be false')
    require(all(comparison[a]['matches'] for a in axes) or row['answers']['claimed_relation_depicted']['answer'] is False,
            'Blind/claim action, direction or product-role mismatch: question 3 must be false')
    require(not any(a['affects_main_relation'] for a in ambiguities)
            or row['answers']['product_action_understood_in_three_seconds']['answer'] is False,
            'Main-relation ambiguity: question 5 must be false')


def direction_case_projection(root, reference, prepared_at, competition):
    """Verify existing query output/eligibility; expose only mechanisms and award level."""
    import hashlib
    from knowledge_pack_contract import jsonl_rows
    from query_case_library import eligible_for_runtime, in_scope

    def require(value, reason):
        if not value:
            raise ValueError(reason)

    data = load_json(bound_file(root, reference))
    require(set(data) == {'query_output', 'cases', 'empty_reason'}, 'Case reference record fields differ')
    raw = load_json(bound_file(root, data['query_output']))
    skill = Path(__file__).resolve().parents[1]
    version = load_json(skill / 'version.json')
    pack = (skill / version['knowledge_manifest']['path']).parent.resolve()
    execution, query = raw['execution'], raw['query']
    require(Path(execution['pack']).resolve() == pack
            and execution['pack_manifest_sha256'] == hashlib.sha256((pack / 'manifest.json').read_bytes()).hexdigest(),
            'Case references must use the active pack without expansion')
    require(timestamp(execution['started_at']) <= timestamp(execution['completed_at']) <= prepared_at,
            'Case query must finish before blind input preparation')
    command = execution['command']
    require(isinstance(command, list) and len(command) > 2
            and Path(command[1]).resolve() == (skill / 'scripts/query_case_library.py').resolve()
            and '--kind' in command and command[command.index('--kind') + 1] == 'case'
            and '--limit' in command and command[command.index('--limit') + 1] == '100'
            and query['competition'] == 'academy-award' and query['category'] == 'print-ad'
            and query['terms'] == [] and query['reference_role'] is None,
            'Retrieve the complete eligible Academy print track with existing query_case_library.py (limit 100)')
    eligibility = load_json(pack / 'eligibility.json')
    require(all(raw['eligibility'][key] == eligibility[key] for key in ('state_fingerprint', 'input_fingerprint')),
            'Case qualification fingerprint differs')
    canonical = {r['case_id']: r for r in jsonl_rows(pack / 'case-cards.jsonl')}
    expected = {k for k, r in canonical.items() if eligible_for_runtime('case', r, eligibility)
                and in_scope(r, 'academy-award', 'print-ad')}
    rows = raw['results']
    ids = [x['record']['case_id'] for x in rows]
    require(raw['returned'] == raw['available_matches'] == len(rows) and len(rows) <= 100
            and len(ids) == len(set(ids)) and set(ids) == expected
            and all(x['kind'] == 'case' and x['record'] == canonical[x['record']['case_id']] for x in rows),
            'Preserve complete qualified case query; unqualified or altered case cards cannot set the bar')
    usable = {k: canonical[k] for k in expected if canonical[k].get('competition') == 'academy-award'
              and canonical[k].get('award_level') in {'gold', 'silver', 'bronze', 'shortlisted'}
              and canonical[k].get('reference_role') in {'approved-method-reference', 'approved-limited-reference'}
              and in_scope(canonical[k], competition, 'print-ad')}
    cases = data['cases']
    require(isinstance(cases, list) and min(3, len(usable)) <= len(cases) <= min(5, len(usable)),
            'Attach 3-5 usable case mechanisms; if fewer exist retain all, including honest empty result')
    seen = set()
    for case in cases:
        require(set(case) == {'case_id', 'mechanism', 'award_level'} and case['case_id'] in usable
                and case['case_id'] not in seen, 'Case reference must be unique and qualified')
        seen.add(case['case_id'])
        card = usable[case['case_id']]
        mechanism = case['mechanism']
        require(isinstance(mechanism, str) and bool(mechanism.strip()) and len(mechanism) <= 200
                and '\n' not in mechanism and '\r' not in mechanism and case['award_level'] == card['award_level']
                and not any(v and v in mechanism for v in (card.get('proposition'), card.get('title'), card.get('work_url'))),
                'Only anonymous one-sentence mechanisms and award level; no brand/title/source identity')
    require((bool(cases) and data['empty_reason'] is None)
            or (not cases and isinstance(data['empty_reason'], str) and bool(data['empty_reason'].strip())),
            'Empty references need an honest reason; usable references cannot be hidden as empty')
    return {'cases': [{k: c[k] for k in ('mechanism', 'award_level')} for c in cases],
            'empty_reason': data['empty_reason']}


def validate_direction_blind_review(root: Path, manifest: dict) -> dict:
    """Check recorded isolation, ordering and choices, without certifying judgment."""
    def require(value, reason):
        if not value:
            raise ValueError(reason)

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def time(value):
        parsed = timestamp(value)
        require(parsed <= datetime.now(timezone.utc), 'Direction timestamp is in the future')
        return parsed

    def ref(value):
        require(isinstance(value, dict) and set(value) == {'path', 'sha256'},
                'Blind evidence descriptors must contain only path and hash')
        return bound_file(root, value)

    try:
        import re
        v6 = manifest.get('direction_contract') == 'print-direction-v6'
        v5 = manifest.get('direction_contract') in {'print-direction-v5', 'print-direction-v6'}
        v4 = manifest.get('direction_contract') in {'print-direction-v4', 'print-direction-v5', 'print-direction-v6'}
        v3 = manifest.get('direction_contract') in {'print-direction-v3', 'print-direction-v4', 'print-direction-v5', 'print-direction-v6'}
        v2 = manifest.get('direction_contract') in {'print-direction-v2', 'print-direction-v3', 'print-direction-v4', 'print-direction-v5', 'print-direction-v6'}
        rubric_version = 'print-direction-v6' if v6 else ('print-direction-v5' if v5 else ('print-direction-v4' if v4 else ('print-direction-v3' if v3 else ('print-direction-v2' if v2 else 'print-direction-v1'))))
        minimum = 6 if v2 else 3
        adoption = manifest['direction_adoption']
        adopted = time(adoption['adopted_at'])
        require(adoption['direction_id'] == manifest['selected_direction'], 'Blind review must bind selected direction')
        bundle = load_json(ref(adoption['blind_review']))
        require(set(bundle) == {'run_id', 'recorded_at', 'rounds', 'origins'}
                and bundle['run_id'] == manifest['run_id'], 'Blind review run identity/fields differ')
        recorded = time(bundle['recorded_at'])
        rounds = bundle['rounds']
        require(isinstance(rounds, list) and 1 <= len(rounds) <= 2, 'At most one re-divergence (two rounds) is allowed')
        all_candidates = set()
        input_by_id = {}
        invocations = set()
        checker_sessions = set()
        record_paths = set()
        previous_end = None
        previous_weak = None
        all_reviewed = set()
        raw_paths = set()
        for index, reference in enumerate(rounds):
            record_path = ref(reference)
            require(record_path not in record_paths, 'Every round needs a new independent record')
            record_paths.add(record_path)
            r = load_json(record_path)
            fields = {'rubric_version', 'checker_context', 'author_session_id', 'checker_session_id',
                      'invocation_id', 'unavailable_metadata', 'input_prepared_at', 'started_at',
                      'completed_at', 'inputs', 'request', 'raw_return', 'result'}
            if v2:
                fields.add('case_references')
            require(set(r) == fields and r['rubric_version'] == rubric_version
                    and r['checker_context'] == 'fresh-isolated', 'Fresh independent direction context required; author self-review cannot replace it')
            require(nonempty(r['author_session_id']) and isinstance(r['unavailable_metadata'], dict)
                    and set(r['unavailable_metadata']) <= {'checker_session_id', 'invocation_id'}, 'Record real checker metadata or unavailable explanation')
            for key in ('checker_session_id', 'invocation_id'):
                require(nonempty(r[key]) or (r[key] is None and nonempty(r['unavailable_metadata'].get(key))),
                        'Missing checker metadata needs an unavailable explanation')
            require(r['checker_session_id'] is None or r['checker_session_id'] != r['author_session_id'], 'Author cannot be the direction checker')
            invocation = r['invocation_id'] or r['checker_session_id'] or str(record_path)
            require(invocation not in invocations, 'Every round requires a new independent invocation')
            invocations.add(invocation)
            if r['checker_session_id'] is not None:
                require(r['checker_session_id'] not in checker_sessions, 'Every round requires a fresh isolated checker session')
                checker_sessions.add(r['checker_session_id'])
            prepared, started, completed = (time(r[k]) for k in ('input_prepared_at', 'started_at', 'completed_at'))
            require(prepared <= started <= completed <= recorded < adopted,
                    'Blind input/call/raw return must precede direction adoption')
            if index:
                replacement = manifest.get('creative_contract') == 'print-core-v4' and bool(adoption.get('previous_adoptions'))
                require((previous_weak is True or replacement) and previous_end < prepared,
                        'Re-divergence allowed only after all-weak first return')
            previous_end = completed
            inputs = r['inputs']
            require(isinstance(inputs, list) and len(inputs) == (3 if v3 else (2 if v2 else 1))
                    and all(set(x) == {'role', 'file'} for x in inputs)
                    and inputs[0]['role'] == 'direction-sentences'
                    and (not v2 or inputs[1]['role'] == 'reference-mechanisms')
                    and (not v3 or inputs[2]['role'] == 'feedback-counterexamples'),
                    'Blind inputs must contain only direction sentences, no author reasons')
            content = ref(inputs[0]['file']).read_text(encoding='utf-8')
            candidates = json.loads(content)
            require(isinstance(candidates, list) and len(candidates) >= minimum,
                    'At least six candidate directions are required' if v2 else 'At least three candidate directions are required')
            ids = []
            for candidate in candidates:
                if v5:
                    validate_direction_sentence_v5(candidate)
                else:
                    require(isinstance(candidate, dict) and set(candidate) == {'direction_id', 'statement'},
                            'Direction inputs cannot contain author reasons or method/source labels')
                ident, sentence = candidate['direction_id'], candidate['statement']
                if not v5:
                    require(nonempty(ident) and nonempty(sentence) and len(sentence) <= 200
                            and '\n' not in sentence and '\r' not in sentence
                            and len(re.split(r'[。！？.!?]', sentence.rstrip('。！？.!?'))) == 1
                            and not re.search(r'因为|理由|推荐|旨在|方法卡|创意贡献|寓意|体现了|作者|排名', sentence),
                            'Only one short visible action/product sentence; author reasons are forbidden')
                ids.append(ident)
                input_by_id[ident] = candidate
            require(len(ids) == len(set(ids)) and not all_candidates.intersection(ids), 'Direction IDs must be unique across rounds')
            all_candidates.update(ids)
            request = ref(r['request']).read_text(encoding='utf-8')
            projection = None
            if v2:
                projection = direction_case_projection(root, r['case_references'], prepared, manifest['competition'])
                references_content = ref(inputs[1]['file']).read_text(encoding='utf-8')
                require(json.loads(references_content) == projection, 'Blind case mechanisms differ from qualified reference record')
                if v3:
                    counterexamples_path = ref(inputs[2]['file'])
                    canonical_path = Path(__file__).resolve().parents[1] / 'references/feedback/direction-counterexamples.json'
                    require(counterexamples_path.read_bytes() == canonical_path.read_bytes(),
                            'Feedback counterexample input must match the bundled library bytes and hash')
                    counterexamples_content = counterexamples_path.read_text(encoding='utf-8')
                    library = json.loads(counterexamples_content)
                    entry_ids = {x['entry_id'] for x in library['entries']}
                    require(len(entry_ids) == len(library['entries']) and bool(entry_ids),
                            'Feedback counterexample entry identities must be unique and nonempty')
                    expected_request = (direction_request_v6 if v6 else (direction_request_v5 if v5 else (direction_request_v4 if v4 else direction_request_v3)))(content, references_content, counterexamples_content)
                else:
                    expected_request = direction_request_v2(content, references_content)
            else:
                expected_request = INDEPENDENT_DIRECTION_RUBRIC + '\n方向一句话清单：\n' + content
            require(request == expected_request,
                    'Blind request must be fixed rubric plus sentence list only; no author explanation')
            raw_path = ref(r['raw_return'])
            raw_paths.add(raw_path)
            raw = load_json(raw_path)
            return_fields = {'near_duplicates', 'ranking', 'drawability', 'all_weak'}
            if v2:
                return_fields |= {'trope_screen', 'reference_assessment'}
            require(raw == r['result'] and set(raw) == return_fields,
                    'Preserve original blind return, ranking and drawability exactly')
            require(type(raw['all_weak']) is bool, 'all_weak must be a checker boolean')
            discarded = set()
            kept_duplicates = set()
            require(isinstance(raw['near_duplicates'], list), 'Independent near-duplicate filtering required')
            for duplicate in raw['near_duplicates']:
                require(set(duplicate) == {'discarded_direction_id', 'kept_direction_id', 'reason'}
                        and nonempty(duplicate['reason']), 'Near-duplicate removal needs concrete independent reason')
                drop, keep = duplicate['discarded_direction_id'], duplicate['kept_direction_id']
                require(drop in ids and keep in ids and drop != keep and drop not in discarded,
                        'Invalid near-duplicate removal')
                discarded.add(drop)
                kept_duplicates.add(keep)
            require(not kept_duplicates.intersection(discarded), 'Keep exactly one representative per near-duplicate group')
            retained = set(ids) - discarded
            require(len(retained) >= minimum,
                    'At least six distinct directions must remain after independent filtering' if v2
                    else 'At least three distinct directions must remain after independent filtering')
            # Catch identical descriptions even if a record incorrectly claims no duplicates.
            normalized = [re.sub(r'\s|[，,。.!！?？]', '', input_by_id[i]['statement']) for i in retained]
            require(len(normalized) == len(set(normalized)), 'Identical/near-duplicate directions were not removed')
            rank, drawable = raw['ranking'], raw['drawability']
            require(isinstance(rank, list) and len(rank) == len(retained)
                    and all(set(x) == {'direction_id', 'reason'} and nonempty(x['reason']) for x in rank)
                    and {x['direction_id'] for x in rank} == retained,
                    'Ranking must include every retained direction once; removed near-duplicates cannot enter ranking')
            require(isinstance(drawable, list) and len(drawable) == len(retained)
                    and all(set(x) == {'direction_id', 'drawable', 'reason'} and type(x['drawable']) is bool and nonempty(x['reason']) for x in drawable)
                    and {x['direction_id'] for x in drawable} == retained,
                    'Every retained direction needs one original drawability judgment')
            if v2:
                screens, assessments = raw['trope_screen'], raw['reference_assessment']
                require(isinstance(screens, list) and len(screens) == len(ids)
                        and {x['direction_id'] for x in screens} == set(ids)
                        and all(set(x) == ({'direction_id', 'is_trope', 'reason', 'new_twist'}
                                         | ({'object_relation_change'} if v6 else set())
                                         | ({'twist_basis', 'counterexample_matches'} if v4 else ({'visible_product_benefit', 'counterexample_matches'} if v3 else set())))
                                and type(x['is_trope']) is bool and nonempty(x['reason'])
                                and (x['new_twist'] is None or nonempty(x['new_twist'])) for x in screens),
                        'Every submitted direction needs a yes/no trope judgment, reason and explicit new twist or null')
                if v3:
                    for x in screens:
                        matches = x['counterexample_matches']
                        require(isinstance(matches, list)
                                and all(isinstance(m, dict) and set(m) == {'entry_id', 'reason'}
                                        and m['entry_id'] in entry_ids and nonempty(m['reason']) for m in matches)
                                and len({m['entry_id'] for m in matches}) == len(matches),
                                'Trope judgment must cite unique known feedback entry IDs with reasons, or []')
                        require(not matches or x['is_trope'], 'Matching feedback mechanism must be classified as trope')
                        if v6:
                            validate_direction_turn_v6(x)
                        if v4:
                            require((x['new_twist'] is None and x['twist_basis'] is None)
                                    or (nonempty(x['new_twist']) and x['twist_basis'] in
                                        {'consumer-moment', 'product-benefit', 'perspective-reversal'}),
                                    'New twist must name a consumer moment, product benefit or perspective reversal basis; no twist uses null basis')
                        else:
                            require((x['new_twist'] is None and x['visible_product_benefit'] is None)
                                    or (nonempty(x['new_twist']) and nonempty(x['visible_product_benefit'])),
                                    'New twist must state which product benefit becomes visible; no twist uses null benefit')
                require(isinstance(assessments, list) and len(assessments) == len(ids)
                        and {x['direction_id'] for x in assessments} == set(ids)
                        and all(set(x) == {'direction_id', 'reaches_reference', 'reason'} and nonempty(x['reason'])
                                and (type(x['reaches_reference']) is bool if projection['cases']
                                     else x['reaches_reference'] is None) for x in assessments),
                        'Every submitted direction needs reference-strength judgment; empty references use null with reason')
                top = rank[0]['direction_id']
                screen = next(x for x in screens if x['direction_id'] == top)
                strength = next(x for x in assessments if x['direction_id'] == top)
                require(raw['all_weak'] or not (screen['is_trope'] and screen['new_twist'] is None),
                        'Ranked-first trope without new twist must trigger all_weak')
                if v3:
                    require(raw['all_weak'] == (screen['is_trope'] and screen['new_twist'] is None),
                            ('Only ranked-first trope without new twist triggers all_weak; references do not block' if v4 else
                             'Only ranked-first trope without visible-benefit twist triggers all_weak; references do not block'))
                else:
                    require(raw['all_weak'] or strength['reaches_reference'] is not False,
                            'Ranked-first below reference strength must trigger all_weak')
            all_reviewed.update(ids)
            previous_weak = raw['all_weak']
        origins = bundle['origins']
        origin_fields = {'direction_id', 'method_id', 'benefit_angle'}
        if v2:
            origin_fields |= {'starting_point', 'starting_point_detail'}
        require(isinstance(origins, list) and len(origins) == len(all_candidates)
                and all(set(x) == origin_fields and nonempty(x['benefit_angle'])
                        and (x['method_id'] is None or nonempty(x['method_id'])) for x in origins)
                and {x['direction_id'] for x in origins} == all_candidates,
                'Every direction needs a method or distinct benefit angle outside blind inputs')
        origin_by_id = {x['direction_id']: x for x in origins}
        if v2:
            categories = {'consumer-moment', 'product-benefit', 'counter-intuitive'}
            require(all(x['starting_point'] in categories and nonempty(x['starting_point_detail']) for x in origins),
                    'Every direction needs a concrete starting point; method card alone is not a starting point')
        for reference in rounds:
            result = load_json(ref(reference))['result']
            keys = {(origin_by_id[x['direction_id']]['method_id'], origin_by_id[x['direction_id']]['benefit_angle']) for x in result['ranking']}
            require(len(keys) == len(result['ranking']), 'Directions must differ by method card or benefit angle')
            if v2:
                require({origin_by_id[x['direction_id']]['starting_point'] for x in result['ranking']} == categories,
                        'Each round after deduplication must cover three starting point categories')
        user_choice_v6 = v6 and adoption['selection_mode'] == 'user'
        require(user_choice_v6 or not previous_weak, 'All directions remain weak; stop automatic adoption after at most one re-divergence')
        winner = adoption['direction_id'] if v6 else raw['ranking'][0]['direction_id']
        if v6:
            require(winner in retained, 'Selected direction must be retained in the presented list')
            selected_screen = next(x for x in screens if x['direction_id'] == winner)
            require(user_choice_v6 or direction_eligible_v6(selected_screen),
                    'Delegated selected direction must be eligible; feedback mechanisms cannot be adopted automatically')
            require(adoption['selection_mode'] != 'delegated' or winner == raw['ranking'][0]['direction_id'],
                    'Delegated model choice must adopt ranked first')
        else:
            require(adoption['direction_id'] == winner, 'Adopted direction must be ranked first')
        require(next(x for x in raw['drawability'] if x['direction_id'] == winner)['drawable'], 'Ranked-first direction must be drawable in one image')
        retrieval = load_json(ref(adoption['method_retrieval']))
        require(time(retrieval['recorded_at']) <= recorded, 'Method decisions must be saved before blind bundle record')
        for decision in retrieval['decisions']:
            method = decision['method_id']
            candidates = decision.get('candidate_direction_ids')
            require(isinstance(candidates, list) and len(candidates) == len(set(candidates))
                    and all(i in all_reviewed and origin_by_id[i]['method_id'] == method for i in candidates),
                    'Methods must first become submitted candidate directions, not preventive rejections')
            if decision['decision'] == 'rejected':
                basis = decision.get('rejection_basis')
                require(basis in {'official-hard-constraint', 'observed-failure'}, 'Risk hints cannot justify preventive method rejection')
                evidence = ref(decision['rejection_evidence'])
                require(evidence.stat().st_size > 0 and (basis == 'official-hard-constraint' or bool(candidates)),
                        'Observed method failure needs a prior candidate and concrete evidence')
                if evidence in raw_paths:
                    require(user_choice_v6 or winner not in candidates, 'Winner cannot be rejected by its own blind ranking')
            else:
                require(bool(candidates), 'Applicable method must become a candidate before blind review')
        returned = {x['method_id'] for x in retrieval['decisions']}
        require(all(x['method_id'] is None or x['method_id'] in returned for x in origins), 'Origin method must be in actual retrieval')
        selection = load_json(ref(adoption['selection_record']))
        selection_fields = {'kind', 'actor', 'direction_id', 'decided_at', 'statement', 'source'}
        require(selection_fields <= set(selection)
                and set(selection) <= selection_fields | ({'user_override', 'override_judgment'} if v6 else set())
                and selection['actor'] == 'user' and nonempty(selection['statement']), 'Real user delegation/choice record is required')
        require(selection['statement'] in ref(selection['source']).read_text(encoding='utf-8'), 'User statement must bind actual source bytes')
        decided = time(selection['decided_at'])
        require(decided < adopted, 'User selection/delegation must precede adoption')
        if adoption['selection_mode'] == 'delegated':
            require(selection['kind'] == 'delegation', 'Model choice needs explicit user delegation')
        else:
            require(adoption['selection_mode'] == 'user' and selection['kind'] == 'user-choice'
                    and selection['direction_id'] == winner and previous_end <= decided,
                    'Without delegation user must select the drawable first direction after blind return')
        if v6:
            override = selection.get('user_override', False)
            require(type(override) is bool, 'user_override must be a boolean')
            needs_override = selected_screen['is_trope'] or bool(selected_screen['counterexample_matches'])
            require(not user_choice_v6 or not needs_override or override is True,
                    'User choice of a trope/counterexample direction requires user_override=true')
            require(not override or (user_choice_v6 and needs_override),
                    'user_override=true is only for actual user choice of a trope/counterexample direction')
            if override:
                judgment = selection.get('override_judgment')
                require(isinstance(judgment, dict) and set(judgment) == {'raw_return', 'trope_screen'}
                        and judgment['raw_return'] == r['raw_return']
                        and judgment['trope_screen'] == selected_screen,
                        'user_override must cite the corresponding original blind judgment')
                require(load_json(ref(judgment['raw_return'])) == raw,
                        'Override judgment must bind original raw return bytes')
            else:
                require('override_judgment' not in selection, 'Override judgment requires user_override=true')
            validate_direction_choice_list_v6(root, adoption, input_by_id, raw, previous_end, decided)
        if manifest.get('creative_contract') == 'print-core-v4':
            lock = load_claim_lock(root, adoption)
            previous = adoption.get('previous_adoptions', [])
            require(isinstance(previous, list) and len(previous) <= 1, 'At most one re-divergence including declaration changes')
            if previous:
                old = previous[0]
                require('previous_adoptions' not in old and len(rounds) == 2, 'Changing declaration requires new direction round within the shared limit')
                older_manifest = dict(manifest, selected_direction=old['direction_id'], direction_adoption=old)
                require(validate_direction_blind_review(root, older_manifest)['passed'], 'Previous direction adoption must remain valid')
                old_bundle = load_json(ref(old['blind_review']))
                old_lock = load_claim_lock(root, old)
                require(old_bundle['rounds'] == rounds[:1]
                        and time(old['adopted_at']) < time(load_json(ref(rounds[1]))['input_prepared_at'])
                        and old_lock['statement_sha256'] != lock['statement_sha256'],
                        'Declaration change must preserve first blind round and lock, then re-diverge and blind-review')
        return check('independent-direction-blind-review', True, {'winner': winner, 'rounds': len(rounds), 'drawable': True})
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration) as exc:
        return check('independent-direction-blind-review', False, str(exc))


def check(name: str, passed: bool, evidence: object) -> dict:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def safe_path(run_dir: Path, relative: object) -> tuple[Path | None, str | None]:
    if not isinstance(relative, str) or not relative.strip():
        return None, "path must be a non-empty string"
    candidate = Path(relative)
    if candidate.is_absolute():
        return None, "absolute paths are forbidden"
    resolved = (run_dir / candidate).resolve()
    if resolved != run_dir and run_dir not in resolved.parents:
        return None, "path escapes run directory"
    return resolved, None


def validate_creative_contract(root: Path, manifest: dict) -> list[dict]:
    """Enforce observable retrieval order and core rebuilds; never certify aesthetics.

    Historical v1/v2 stay reproducible. New 0.8.0 requires v3 blind then
    comparison within the existing five questions and rebuild contract.
    Evidence is not identity authentication.
    """
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def time(value):
        result = timestamp(value)
        require(result <= datetime.now(timezone.utc), 'Creative evidence timestamp is in the future')
        return result

    def document(relative):
        path, error = safe_path(root, relative)
        require(not error and path is not None, error or 'Missing creative evidence path')
        return load_json(path)

    try:
        gate_id = document(manifest.get('artifacts', {}).get('quality_gate_results')).get('definition_set_id')
        if gate_id in {'print-ad.0.1.0', 'print-ad.0.2.0', 'print-ad.0.3.0', 'print-ad.0.4.0'} and 'creative_contract' not in manifest and 'direction_contract' not in manifest:
            return []
        locked_claims = manifest.get('creative_contract') == 'print-core-v4'
        blind_first = manifest.get('creative_contract') in {'print-core-v3', 'print-core-v4'}
        independent = manifest.get('creative_contract') in {'print-core-v2', 'print-core-v3', 'print-core-v4'}
        require(manifest.get('creative_contract') in {'print-core-v1', 'print-core-v2', 'print-core-v3', 'print-core-v4'},
                'New print quality gates require a supported creative_contract')
        require(gate_id not in {'print-ad.0.6.0', 'print-ad.0.7.0', 'print-ad.0.8.0'} or independent,
                'print-ad.0.6.0 requires creative_contract=print-core-v2; author-inspection cannot pass')
        require(gate_id not in {'print-ad.0.7.0', 'print-ad.0.8.0'} or manifest.get('direction_contract') == 'print-direction-v1',
                'print-ad.0.7.0 requires independent direction_contract=print-direction-v1')
        require(gate_id != 'print-ad.0.8.0' or blind_first,
                'print-ad.0.8.0 requires creative_contract=print-core-v3 blind-then-compare')
        require(gate_id not in {'print-ad.0.9.0', 'print-ad.0.10.0', 'print-ad.0.11.0', 'print-ad.0.12.0', 'print-ad.0.13.0', 'print-ad.0.14.0'} or locked_claims,
                'print-ad.0.9.0 requires creative_contract=print-core-v4 locked claim and device removal')
        require(gate_id != 'print-ad.0.10.0' or manifest.get('direction_contract') == 'print-direction-v2',
                'print-ad.0.10.0 requires direction_contract=print-direction-v2 absolute direction bar')
        require(gate_id != 'print-ad.0.11.0' or manifest.get('direction_contract') == 'print-direction-v3',
                'print-ad.0.11.0 requires direction_contract=print-direction-v3 visible product benefit and feedback')
        require(gate_id != 'print-ad.0.12.0' or manifest.get('direction_contract') == 'print-direction-v4',
                'print-ad.0.12.0 requires direction_contract=print-direction-v4 calibrated twist and feedback')
        require(gate_id != 'print-ad.0.13.0' or manifest.get('direction_contract') == 'print-direction-v5',
                'print-ad.0.13.0 requires direction_contract=print-direction-v5 with explicit creative basis')
        require(gate_id != 'print-ad.0.14.0' or manifest.get('direction_contract') == 'print-direction-v6',
                'print-ad.0.14.0 requires direction_contract=print-direction-v6')
        require(manifest.get('direction_contract') != 'print-direction-v6' or gate_id == 'print-ad.0.14.0',
                'print-direction-v6 requires the new quality gate; no downgrade')
        require(not locked_claims or manifest.get('direction_contract') in {'print-direction-v1', 'print-direction-v2', 'print-direction-v3', 'print-direction-v4', 'print-direction-v5', 'print-direction-v6'},
                'Locked core declaration requires independent direction adoption')
        require('direction_contract' not in manifest or (manifest['direction_contract'] in {'print-direction-v1', 'print-direction-v2', 'print-direction-v3', 'print-direction-v4', 'print-direction-v5', 'print-direction-v6'} and independent),
                'Independent direction contract requires print-core-v2 even with historical gates')
        require(manifest.get('direction_contract') != 'print-direction-v2' or locked_claims,
                'print-direction-v2 retains print-core-v4 adoption claim lock')
        require(manifest.get('direction_contract') != 'print-direction-v3' or locked_claims,
                'print-direction-v3 retains print-core-v4 adoption claim lock')
        require(manifest.get('direction_contract') != 'print-direction-v4' or locked_claims,
                'print-direction-v4 retains print-core-v4 adoption claim lock')
        require(manifest.get('direction_contract') != 'print-direction-v5' or locked_claims,
                'print-direction-v5 retains print-core-v4 adoption claim lock')
        require(manifest.get('direction_contract') != 'print-direction-v6' or locked_claims,
                'print-direction-v6 retains print-core-v4 adoption claim lock')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [check('print-creative-contract', False, str(exc))]

    checks = []
    try:
        adoption = manifest['direction_adoption']
        require(adoption['direction_id'] == manifest['selected_direction'], 'Retrieval must bind the adopted direction')
        adopted = time(adoption['adopted_at'])
        retrieval = load_json(bound_file(root, adoption['method_retrieval']))
        require(retrieval.get('run_id') == manifest['run_id'], 'Method retrieval run identity differs')
        recorded = time(retrieval['recorded_at'])
        require(recorded < adopted, 'Method retrieval record must exist strictly before direction adoption')
        require(text(retrieval.get('original_problem')), 'Preserve the original problem')
        attempts = retrieval['attempts']
        require(isinstance(attempts, list) and bool(attempts), 'Actual method query output is required, including empty results')
        all_ids = set()
        previous = None
        for index, attempt in enumerate(attempts):
            result = load_json(bound_file(root, attempt['output']))
            execution, query = result['execution'], result['query']
            started, completed = time(execution['started_at']), time(execution['completed_at'])
            require(started <= completed <= recorded and (previous is None or previous <= started), 'Method retrieval execution must precede its record and adoption')
            previous = completed
            command = execution['command']
            require(isinstance(command, list) and len(command) >= 2 and all(text(x) for x in command)
                    and Path(command[1]).name == 'query_case_library.py', 'Record the actual existing query command')
            def option(name):
                require(name in command and command.index(name) + 1 < len(command), 'Missing query option '+name)
                return command[command.index(name) + 1]
            require(option('--kind') == 'method' and option('--category') == 'print-ad'
                    and option('--competition') == manifest['competition'], 'Method query must use the current print scope')
            require(option('--problem') == retrieval['original_problem'] and query['original'] == retrieval['original_problem'], 'Do not replace the original problem during fallback')
            fallback = attempt['fallback_terms']
            require(isinstance(fallback, list) and all(text(t) for t in fallback) and query['explicit_terms'] == fallback,
                    'Fallback terms must match the actual query output')
            require([command[i + 1] for i, v in enumerate(command[:-1]) if v == '--term'] == fallback,
                    'Fallback terms must match the actual command')
            require(index != 0 or not fallback, 'Keep the original query before fallback')
            skill_root = Path(__file__).resolve().parents[1]
            active_pack = (skill_root / load_json(skill_root / 'version.json')['knowledge_manifest']['path']).parent
            import hashlib
            require(Path(execution['pack']).resolve() == active_pack.resolve()
                    and execution['pack_manifest_sha256'] == hashlib.sha256((active_pack / 'manifest.json').read_bytes()).hexdigest(),
                    'Record the actual active pack; do not switch or expand it')
            require(query['competition'] == manifest['competition'] and query['category'] == 'print-ad', 'Raw method output scope differs from the adopted direction')
            rows = result['results']
            require(isinstance(rows, list) and result['returned'] == len(rows), 'Keep the complete returned method list')
            ids = [r['record']['method_id'] for r in rows if r.get('kind') == 'method']
            require(len(ids) == len(rows) and len(ids) == len(set(ids)) and attempt['returned_method_ids'] == ids,
                    'Returned method IDs must match raw output, including empty results')
            require(bool(ids) or text(result.get('empty_reason')), 'Empty results must be preserved honestly')
            all_ids.update(ids)
        decisions = retrieval['decisions']
        require(isinstance(decisions, list) and len(decisions) == len(all_ids)
                and {r['method_id'] for r in decisions} == all_ids, 'Explain every returned method once')
        require(all(r.get('decision') in {'adopted', 'rejected'} and text(r.get('reason')) and text(r.get('relation_or_input_change')) for r in decisions),
                'Each method needs adoption/rejection reasons and its concrete effect on the relation or production input')
        require(bool(all_ids) or text(retrieval.get('empty_result_action')), 'Empty retrieval needs an honest next action')
        checks.append(check('method-retrieval-before-adoption', True, {'adopted_at': adoption['adopted_at'], 'methods': sorted(all_ids)}))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        checks.append(check('method-retrieval-before-adoption', False, str(exc)))

    if manifest.get('direction_contract') in {'print-direction-v1', 'print-direction-v2', 'print-direction-v3', 'print-direction-v4', 'print-direction-v5', 'print-direction-v6'}:
        checks.append(validate_direction_blind_review(root, manifest))

    if manifest.get('run_scope') == 'concept-only' and (not independent or 'core_creative_review' not in manifest):
        return checks
    try:
        from visual_review_contract import image_file
        locks = {}
        if locked_claims:
            require(next(c for c in checks if c['name'] == 'independent-direction-blind-review')['passed'],
                    'Core claim needs valid locked direction blind review')
            for a in adoption.get('previous_adoptions', []) + [adoption]:
                lock = load_claim_lock(root, a)
                require(lock['direction_id'] not in locks, 'Replacement direction must have a new ID')
                locks[lock['direction_id']] = lock
        review = manifest['core_creative_review']
        assessments = review['assessments']
        require(isinstance(assessments, list) and assessments, 'Core checks must inspect actual artwork')
        by_id = {}
        questions = {'product_in_core_relation', 'action_depicted_without_copy', 'product_action_understood_in_three_seconds'}
        if independent:
            questions |= {'claimed_relation_depicted', 'creative_scene_not_generic'}
        independent_records = set()
        invocation_keys = set()
        for row in assessments:
            require(text(row.get('id')) and row['id'] not in by_id, 'Core assessment IDs must be unique')
            keys = artifact(root, row['artifact'])
            require(len(keys) == 1, 'One core assessment must cover one actual artwork unit')
            render = load_json(bound_file(root, row['render_record']))
            require(artifact(root, render['source']) == keys and render.get('target_renderer_verified') is True,
                    'Core check must cite the actual current target render')
            native = [v for v in render['views'] if v.get('scale') == 'native']
            require(len(native) == 1 and bound_file(root, native[0]['file']) == bound_file(root, row['observed_image']),
                    'Core check must inspect the native image from the bound render')
            image_file(root, row['observed_image'])
            bound_file(root, row['official_product_asset'])
            require(text(row.get('core_action')), 'Name the depicted core action or relation')
            require(time(render['created_at']) <= time(row['checked_at']), 'Core observation must follow rendering')
            answers = row['answers']
            require(isinstance(answers, dict) and set(answers) == questions
                    and all(type(a.get('answer')) is bool and text(a.get('observation')) for a in answers.values()),
                    'Answer every core question individually with actual pixel observations')
            if independent:
                require(row.get('assessment_method') == 'independent-review',
                        'Independent review required; author-inspection cannot support a pass')
                claim = row['core_action']
                require(len(claim) <= 160 and '\n' not in claim and '\r' not in claim
                        and sum(claim.count(c) for c in '。！？!?') <= 1,
                        'Core action must be one short sentence, not author explanation')
                record_path = bound_file(root, row['independent_check'])
                require(record_path not in independent_records, 'Each complete draft requires a new independent check record')
                independent_records.add(record_path)
                record = load_json(record_path)
                if blind_first:
                    lock = locks.get(row.get('direction_id')) if locked_claims else None
                    if locked_claims:
                        require(lock is not None, 'Every draft must bind an adopted direction claim lock')
                        require(time(lock['adopted_at']) <= time(render['created_at']), 'Claim must be locked at adoption before rendering')
                        if row['direction_id'] != adoption['direction_id']:
                            require(time(row['checked_at']) < adopted, 'Historical draft must precede replacement adoption')
                    validate_blind_core(root, row, render, record, invocation_keys, lock)
                else:
                    fields = {'rubric_version','checker_context','author_session_id','checker_session_id','invocation_id',
                              'unavailable_metadata','started_at','completed_at','inputs','request','raw_return'}
                    require(set(record) == fields and record['rubric_version'] == 'print-core-v2'
                            and record['checker_context'] == 'fresh-isolated',
                            'Independent check must record a fresh isolated context with no extra author inputs')
                    require(text(record['author_session_id']), 'Record the author session identifier')
                    unavailable = record['unavailable_metadata']
                    require(isinstance(unavailable, dict) and set(unavailable) <= {'checker_session_id','invocation_id'},
                            'Explain only genuinely unavailable checker identifiers')
                    for field in ['checker_session_id', 'invocation_id']:
                        value = record[field]
                        require(text(value) or (value is None and text(unavailable.get(field))),
                                'Record real '+field+' or an explicit host-unavailable explanation')
                    require(record['checker_session_id'] != record['author_session_id']
                            and record['invocation_id'] != record['author_session_id'],
                            'The author cannot be the independent checker')
                    identity = (record['checker_session_id'], record['invocation_id'])
                    if any(text(v) for v in identity):
                        require(identity not in invocation_keys, 'A new complete draft needs a new checker invocation')
                        invocation_keys.add(identity)
                    require(time(render['created_at']) <= time(record['started_at']) <= time(record['completed_at']) <= time(row['checked_at']),
                            'Independent check must follow rendering and finish before checked_at')
                    inputs = record['inputs']
                    roles = {'artwork', 'official-product-asset', 'core-action'}
                    require(isinstance(inputs, list) and len(inputs) == 3
                            and all(isinstance(v, dict) and set(v) == {'role','file'} for v in inputs)
                            and {v['role'] for v in inputs} == roles,
                            'Independent inputs must contain only artwork, official product asset and one core action; author notes/direction cards are invalid')
                    supplied = {v['role']: v['file'] for v in inputs}
                    require(all(isinstance(ref, dict) and set(ref) <= {'path','relative_path','sha256'} for ref in supplied.values()),
                            'Independent input descriptors cannot contain author notes or explanations')
                    for role, expected_ref in [('artwork', row['observed_image']), ('official-product-asset', row['official_product_asset'])]:
                        require(bound_file(root, supplied[role]) == bound_file(root, expected_ref)
                                and supplied[role]['sha256'] == expected_ref['sha256'],
                                'Independent input hash differs from actual '+role)
                        image_file(root, supplied[role])
                    require(bound_file(root, supplied['core-action']).read_text(encoding='utf-8') == claim,
                            'Independent checker core-action input differs from the one-sentence claim')
                    request = bound_file(root, record['request']).read_text(encoding='utf-8')
                    require(request == INDEPENDENT_CORE_RUBRIC + '\n核心动作/关系：' + claim,
                            'Independent request contains author explanation or differs from the fixed rubric and claim')
                    raw = load_json(bound_file(root, record['raw_return']))
                    require(set(raw) == {'answers'} and raw['answers'] == answers,
                            'Assessment must exactly preserve the independent raw return answers and pixel observations')
            else:
                require(row.get('assessment_method') in {'author-inspection', 'audience-test'}, 'Declare author inspection or a real audience test; do not invent a viewer')
                if row['assessment_method'] == 'audience-test':
                    bound_file(root, row['audience_test'])
            by_id[row['id']] = (row, keys)
        if independent:
            completed = review['completed_draft_render_records']
            require(isinstance(completed, list) and completed, 'Register every complete draft render, including first and rebuilt drafts')
            declared = [bound_file(root, ref) for ref in completed]
            observed = [bound_file(root, row['render_record']) for row, _ in by_id.values()]
            require(len(set(declared)) == len(declared) and sorted(declared) == sorted(observed),
                    'Every registered complete draft must have exactly one independent assessment')
            if manifest.get('run_scope') == 'delivery-candidate':
                delivery = document(manifest['artifacts']['delivery_manifest'])
                delivered_at = time(delivery['delivered_at'])
                require(all(time(row['checked_at']) <= delivered_at for row, _ in by_id.values()),
                        'Independent core check cannot be later than delivery')
        current = review['current_assessment_ids']
        require(isinstance(current, list) and current and len(current) == len(set(current)) and set(current) <= set(by_id),
                'Current core assessment scope must be explicit')
        pixels = document(manifest['artifacts']['visual_review'])
        expected = set()
        actual = set()
        for unit in pixels['units']:
            expected |= artifact(root, unit['artifact'])
            matching = [by_id[i][0] for i in current if by_id[i][1] == artifact(root, unit['artifact'])]
            require(len(matching) == 1 and bound_file(root, matching[0]['render_record']) == bound_file(root, unit['render_record']),
                    'Core checks must cover the same current render as final pixel review')
        for ident in current:
            row, keys = by_id[ident]
            require(not locked_claims or row['direction_id'] == adoption['direction_id'], 'Current draft must use current adopted direction lock')
            require(not actual & keys, 'Duplicate current core scope')
            actual |= keys
            require(all(a['answer'] for a in row['answers'].values()), 'Current core failure: rebuild the main relation, not local edits')
            require(not any(keys == other_keys and time(other['checked_at']) > time(row['checked_at']) for other, other_keys in by_id.values()),
                    'A later core assessment cannot be hidden by selecting an older pass')
        require(actual == expected and expected, 'Core check coverage must match all current pixel units')
        for row, keys in by_id.values():
            if all(a['answer'] for a in row['answers'].values()):
                continue
            rework = row.get('rework', {})
            require(rework.get('kind') == 'full-rebuild' and rework.get('return_to_stage') in {'direction', 'main-visual-generation'},
                    'Core failure requires full-rebuild; layout, masks, crop, footer and font edits cannot resolve it')
            require(time(row['checked_at']) < time(rework['started_at']) <= time(rework['completed_at']), 'Full rebuild must follow the failed observation')
            require(text(rework.get('relation_before')) and text(rework.get('relation_after')) and rework['relation_before'] != rework['relation_after'],
                    'Full rebuild must describe the changed main relation')
            bound_file(root, rework['production_input'])
            rebuilt = image_file(root, rework['rebuilt_main_visual'])
            require(rework['rebuilt_main_visual']['sha256'] != row['observed_image']['sha256'] and rebuilt.width > 0,
                    'Full rebuild needs changed main visual bytes')
            successor = by_id.get(rework.get('rechecked_assessment_id'))
            require(successor is not None, 'Rebuild requires a new core recheck')
            new, new_keys = successor
            require({k[-1] for k in keys} == {k[-1] for k in new_keys} and keys != new_keys
                    and time(rework['completed_at']) < time(new['checked_at']), 'Recheck must follow full rebuild and bind a new version')
            require(bound_file(root, rework['rebuilt_main_visual']) == bound_file(root, new['observed_image']),
                    'Recheck must inspect the rebuilt main visual')
            # A failed rebuilt image may itself need a second full rebuild.
            # Strictly increasing times and the checks on every failed row
            # prevent cycles; terminal current assessments must all pass.
            cursor = new
            while not all(a['answer'] for a in cursor['answers'].values()):
                following = by_id.get(cursor.get('rework', {}).get('rechecked_assessment_id'))
                require(following is not None and time(following[0]['checked_at']) > time(cursor['checked_at']),
                        'Unresolved core failure in rebuild chain')
                cursor = following[0]
        checks.append(check('core-creative-pixel-review', True,
                            'Independent five answers, allowed inputs/raw return and full rebuild history bound to current pixels; identity and artistic judgment are not authenticated by machine'
                            if independent else 'Historical three answers and full rebuild history bound to current pixels'))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, IndexError) as exc:
        checks.append(check('core-creative-pixel-review', False, str(exc)))
    return checks


def validate(run_dir: Path, manifest_path: Path) -> dict:
    run_dir = run_dir.resolve()
    checks: list[dict] = []
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError) as exc:
        reason = f"{manifest_path}: {exc}"
        return {"schema_version": "0.1.0", "status": "failed",
                "checks": [check("manifest-readable", False, reason)],
                "checks_total": 1, "checks_passed": 0,
                "failure_names": ["manifest-readable"], "errors": [reason]}

    checks.append(check("manifest-schema", manifest.get("schema_version") in {"0.1.0", "0.2.0", "0.3.0", "0.4.0"}, manifest.get("schema_version")))
    checks.append(check("category-print-ad", manifest.get("category") == "print-ad", manifest.get("category")))
    run_scope = manifest.get("run_scope")
    checks.append(check("run-scope", run_scope in RUN_SCOPE_ARTIFACTS, run_scope))
    checks.extend(validate_visual_generation_capability(manifest, run_scope, run_dir))
    checks.append(check("identity-fields", all(isinstance(manifest.get(key), str) and manifest[key] for key in ("run_id", "competition", "brief_id", "selected_direction", "series_mode")), {key: manifest.get(key) for key in ("run_id", "competition", "brief_id", "selected_direction")}))
    checks.append(check('series-mode-valid', manifest.get('series_mode') in {'single', 'series'}, manifest.get('series_mode')))
    plan = manifest.get('series_plan')
    valid = False
    if plan is not None:
        valid = isinstance(plan, dict) and plan.get('mode') == manifest.get('series_mode') and isinstance(plan.get('reason'), str) and bool(plan['reason'].strip())
        units = plan.get('units') if isinstance(plan, dict) else None
        valid = valid and isinstance(units, list) and all(isinstance(u, str) and u for u in units) and len(units) == len(set(units))
        valid = valid and (len(units) >= 2 if manifest.get('series_mode') == 'series' else len(units) == 1)
        valid = valid and type(plan.get('user_requested_series')) is bool and (not plan.get('user_requested_series') or plan['mode'] == 'series')
        if valid and plan['mode'] == 'series':valid = isinstance(plan.get('shared_mechanism'), str) and bool(plan['shared_mechanism'].strip())
        checks.append(check('series-plan-scope', valid, plan))
    method_status = manifest.get("method_validation_status", "not-claimed")
    checks.append(check("method-validation-status", method_status in {"not-claimed", "method-validated"}, method_status))

    artifacts = manifest.get("artifacts")
    checks.append(check("artifact-map", isinstance(artifacts, dict), type(artifacts).__name__))
    resolved: dict[str, Path] = {}
    if isinstance(artifacts, dict):
        for key in RUN_SCOPE_ARTIFACTS.get(run_scope, BASE_ARTIFACTS):
            path, error = safe_path(run_dir, artifacts.get(key))
            present = path is not None and path.is_file()
            checks.append(check(f"artifact:{key}", present and error is None, error or str(path)))
            if present and error is None:
                resolved[key] = path

        if run_scope in {"production-candidate", "delivery-candidate"}:
            aigc_used = manifest.get("aigc_used")
            checks.append(check("aigc-use-declaration", aigc_used in {"yes", "no", "unknown"}, aigc_used))
            if run_scope == "delivery-candidate":
                checks.append(check("aigc-use-resolved", aigc_used in {"yes", "no"}, aigc_used))
            if aigc_used == "yes":
                path, error = safe_path(run_dir, artifacts.get("aigc_record"))
                present = path is not None and path.is_file()
                checks.append(check("artifact:aigc_record", present and error is None, error or str(path)))
                if present and error is None:
                    resolved["aigc_record"] = path

    if manifest.get('direction_contract') == 'print-direction-v6' and run_scope in {'production-candidate', 'delivery-candidate'}:
        checks.append(validate_main_visual_provenance_v6(run_dir, manifest))

    if "quality_gate_results" in resolved:
        checks.extend(validate_quality_gate_results(
            run_dir, resolved["quality_gate_results"], "print-ad", manifest.get("run_id"),
            RUN_SCOPE_GATES.get(run_scope, set()),
        ))

    if method_status == "method-validated":
        used = manifest.get("method_cards_used")
        rejected = manifest.get("method_cards_rejected", [])
        checks.append(check("method-cards-used", isinstance(used, list) and bool(used) and len(used) == len(set(used)), used))
        checks.append(check("method-cards-rejected", isinstance(rejected, list) and len(rejected) == len(set(rejected)), rejected))
        method_path, method_error = safe_path(run_dir, artifacts.get("method_application") if isinstance(artifacts, dict) else None)
        present = method_path is not None and method_path.is_file() and method_error is None
        checks.append(check("artifact:method_application", present, method_error or str(method_path)))
        if present and isinstance(used, list):
            method_text = method_path.read_text(encoding="utf-8-sig")
            checks.append(check("used-methods-documented", all(item in method_text for item in used), used))

    from review_contract import concept_evidence_checks
    checks.extend(concept_evidence_checks(run_dir, manifest))
    checks.extend(validate_visual_review(run_dir, manifest))
    checks.extend(validate_creative_contract(run_dir, manifest))
    if manifest.get('schema_version') == '0.4.0' and 'quality_gate_results' in resolved:
        gates = load_json(resolved['quality_gate_results'])
        series = next((r for r in gates.get('results', []) if r.get('gate_id') == 'print-ad.series-increment'), {})
        checks.append(check('series-waiver-scope', not (manifest.get('series_mode') == 'series' and series.get('status') == 'waived'), series.get('status')))
        if plan is not None and run_scope == 'delivery-candidate' and 'delivery_manifest' in resolved:
            delivery = load_json(resolved['delivery_manifest'])
            actual_units = [u for a in delivery.get('final_artifacts', []) for u in a.get('units', [])]
            checks.append(check('series-delivery-coverage', valid and all(isinstance(u, str) for u in actual_units) and len(actual_units) == len(set(actual_units)) and set(actual_units) == set(plan['units']), actual_units))
    review_checks = validate_review_contract(run_dir, manifest)
    # Historical validation stays reproducible, but is never new-contract acceptance.
    if manifest.get("schema_version") == "0.4.0":
        checks.extend(review_checks)
    # Post-delivery administration never blocks the artwork workflow.
    for item in checks:
        if item['name'] in {'aigc-use-declaration', 'aigc-use-resolved', 'artifact:aigc_record', 'submission-status-explicit'}:
            item['severity'] = 'reminder'
    failed = [item["name"] for item in checks if not item["passed"] and item.get('severity') != 'reminder']
    progress = check_summary(checks) if manifest.get("schema_version") == "0.4.0" else {"status": "passed" if not failed else "failed"}
    return {
        "schema_version": "0.1.0", "run_id": manifest.get("run_id"),
        "run_dir": str(run_dir), "manifest": str(manifest_path.resolve()),
        **progress, "checks_total": len(checks),
        "checks_passed": sum(bool(item["passed"]) for item in checks), "post_delivery_reminders": [item for item in checks if item.get("severity") == "reminder" and not item["passed"]], "failure_names": failed, "review_contract_status": "verified" if all(c["passed"] for c in review_checks) else ("failed" if manifest.get("schema_version") == "0.4.0" else "legacy-not-verified"), "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--manifest", type=Path, help="Absolute path or relative to --path-base (default: cwd, for compatibility)")
    parser.add_argument("--output", type=Path, help="New receipt path; same --path-base as --manifest")
    parser.add_argument("--path-base", choices=("cwd", "run-dir"), default="cwd",
                        help="Use run-dir for the unified-entrypoint convention; legacy cwd remains the default")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps({
            "schema_version": "0.1.0", "status": "passed",
            "run_scope_artifacts": {key: list(value) for key, value in RUN_SCOPE_ARTIFACTS.items()},
            "run_scope_gates": {key: sorted(value) for key, value in RUN_SCOPE_GATES.items()},
            "method_validation_statuses": ["not-claimed", "method-validated"],
        }, ensure_ascii=False))
        return 0
    if args.run_dir is None or args.output is None:
        parser.error("--run-dir and --output are required unless --self-check is used")
    run_dir = args.run_dir.resolve()
    base = run_dir if args.path_base == "run-dir" else Path.cwd()
    manifest = (base / args.manifest).resolve() if args.manifest else run_dir / "print-ad-run-manifest.json"
    output = (base / args.output).resolve()
    if output.exists():
        parser.error("Use a new output receipt; do not overwrite historical evidence")
    result = validate(run_dir, manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result.get(key, []) for key in ("status", "checks_total", "checks_passed", "failure_names", "errors")}, ensure_ascii=False))
    return {"passed": 0, "in-progress": 2}.get(result["status"], 1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

"""Purpose evidence and independent hints; no ranking or adoption decisions."""
import json
from review_contract import bound_file

CREATIVE_REQUEST_REVISION = 'creative-comparison-v1'
CREATIVE_COMPARISON_RUBRIC = '''现有创意比较依据补全：对去重后方向按既有规则强制排序，不并列、不用绝对分；依据具体转折、消费者时刻或产品利益的关联、意外感和创意本身强弱，结合可用案例参照比较，ranking.reason写明已提交内容的具体比较。合格方向仍排在被拦方向之前；不新增权重或门槛，产品意义、传播目的与因果提示仍不参与排序、可画、all_weak或采用。
评价证据范围：不得仅凭影子、倒影、剪纸、摄影等通用表现形式的名称或常见程度判套路；须核对本方向实际对象关系及既有套路、反例的具体范围，命中时照旧执行。未命中列举机制也不自动证明创意强。只比较已提交内容，不补造未写出的文字、关系或未来成图效果；决定关系的必要图中文字应在现有方向句内，未提供则明确指出依赖尚待具体化，不提前计为已成立的优点，也不因此新增主观硬拦。完整图文可共同承担关系，不要求移除文字仍成立，不强制产品做机械动作，不使用竞品替换或品牌独占考试。方向句不能认证成图表现质量，表现效果留待既有代表稿看图验证。'''

PURPOSE_RUBRIC = '''命题传播目的检查：只根据随附原文摘录和匿名方向，逐条判断方向让观众/用户做什么、感受什么、记住产品什么，以及是否服务于命题的传播目的。摘录是原文，不是作者解释；source与行号仅用于追溯，不读取其他文件。
返回purpose_check数组，覆盖全部输入（含去重项），各项仅含direction_id、audience_takeaway、judgment（aligned/drift/reversed/unclear）、purpose_quote（摘录中的逐字原文）、observation、opposite_relation（仅reversed为非空文字，其余null）。不要把主题词吻合当成目的吻合，也不要求每个方向同时承载所有传播目标。
读偏、偏弱、未读出或歧义只提示。明确读反须列出目的原文、方向原句和相反关系，沿既有主关系读反分级处理；不能把“没有服务目的”直接说成“与目的相反”。例如治疗/守护被读成少用/回避应核对是否目的错置，不作为品类分支或固定结论。方向文字不代替成图证据；未生图不得虚构像素或新增硬拦。purpose_check不参与原有套路筛、排序、可画、all_weak、eligible、user_override、采用、承接或生产守卫；不得借目的提示改写这些判断。保留原有完整图文阅读标准，字体/文字设计可以承担创意关系，不要求移除文字后仍成立。'''

def parse_purpose(content):
    value=json.loads(content)
    if not isinstance(value,dict) or set(value)!={'source','excerpts'}:
        raise ValueError('Purpose needs a bound original source and verbatim excerpts')
    source=value['source'];rows=value['excerpts']
    if (not isinstance(source,dict) or set(source)!={'path','sha256'}
        or not isinstance(rows,list) or not rows):
        raise ValueError('Purpose source and nonempty excerpts are required')
    for row in rows:
        if (not isinstance(row,dict) or set(row)!={'line_start','line_end','quote'}
            or type(row['line_start']) is not int or type(row['line_end']) is not int
            or not 1<=row['line_start']<=row['line_end']
            or not isinstance(row['quote'],str) or not row['quote'].strip()):
            raise ValueError('Purpose excerpt needs exact quote and one-based source lines')
    if sum(len(x['quote']) for x in rows)>1200:
        raise ValueError('Keep purpose excerpts short (at most 1200 characters)')
    return value

def validate_purpose_excerpt(root,content):
    value=parse_purpose(content)
    lines=bound_file(root,value['source']).read_text(encoding='utf-8').splitlines()
    for row in value['excerpts']:
        if row['line_end']>len(lines) or row['quote']!='\n'.join(lines[row['line_start']-1:row['line_end']]):
            raise ValueError('Purpose excerpt must be verbatim at the traceable source lines')
    return value

def direction_request_with_purpose(content,references,counterexamples,purpose_content):
    from validate_print_ad_run import direction_request_v11
    parse_purpose(purpose_content)
    return (direction_request_v11(content,references,counterexamples)
            +'\n'+PURPOSE_RUBRIC+'\n命题传播目的原文摘录：\n'+purpose_content)


def current_direction_request(content,references,counterexamples,purpose_content):
    """Current request only; historical generators and their exact bytes stay intact."""
    return (CREATIVE_COMPARISON_RUBRIC+'\n'
            +direction_request_with_purpose(content,references,counterexamples,purpose_content))

def validate_purpose_check(result,candidates,purpose_content):
    purpose=parse_purpose(purpose_content);rows=result.get('purpose_check')
    ids=[x['direction_id'] for x in candidates]
    fields={'direction_id','audience_takeaway','judgment','purpose_quote','observation','opposite_relation'}
    if (not isinstance(rows,list) or len(rows)!=len(ids)
        or any(not isinstance(x,dict) or set(x)!=fields for x in rows)
        or {x['direction_id'] for x in rows}!=set(ids)):
        raise ValueError('Every direction must retain the independent purpose judgment')
    for row in rows:
        if (row['judgment'] not in {'aligned','drift','reversed','unclear'}
            or any(not isinstance(row[k],str) or not row[k].strip() for k in ['audience_takeaway','purpose_quote','observation'])
            or not any(row['purpose_quote'] in x['quote'] for x in purpose['excerpts'])):
            raise ValueError('Purpose judgment must cite the verbatim supplied purpose')
        if row['judgment']=='reversed':
            if not isinstance(row['opposite_relation'],str) or not row['opposite_relation'].strip():
                raise ValueError('Reversal needs the concrete opposite relation; ambiguity is only a hint')
        elif row['opposite_relation'] is not None:
            raise ValueError('Only a documented reversal may record an opposite relation')
    return rows

def direction_purpose_text(row):
    return ('目的提示：'+row['judgment']+'；观众读到：'+row['audience_takeaway']
            +'；目的原文：'+row['purpose_quote']+'；观察：'+row['observation']
            +('；相反关系：'+row['opposite_relation'] if row['opposite_relation'] else ''))

def validate_purpose_choice(root,choice,result):
    if choice.get('purpose_advisories')!=result['purpose_check']:
        raise ValueError('Preserve every original independent purpose hint in the choice list')
    from validate_print_ad_run import direction_choice_blocks
    text=bound_file(root,choice['user_facing_copy']).read_text(encoding='utf-8')
    for row in result['purpose_check']:
        if not any(row['direction_id'] in block and direction_purpose_text(row) in block for block in direction_choice_blocks(text)):
            raise ValueError('Show original purpose hints for every direction before selection')

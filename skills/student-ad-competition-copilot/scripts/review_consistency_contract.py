"""Fixed independent instructions and verifiable product-text observations."""
import json
from pathlib import Path

from review_contract import load

SUPPLEMENT = '''
【返回一致性与产品文字核对 v1】
权威判断是八问答案与实际像素观察；不要为了满足结构改变判断。逐项检查：
1. review_issues 的 claim-unfulfilled 等原五问失败码只对应该问 answer=false，observation 必须逐字等于该问观察。true 仍可有局部不足：另写 hint，question=local-detail、reason_code=local-detail，具体说明局部、影响和像素位置；不能把主关系不成立、读反、合规或文字错误藏在局部提示里。例如第3问true、“整体意义成立，接触附近转折偏弱”可登记 local-detail；第3问true + claim-unfulfilled 是矛盾返回，仍无效。false 仍必须登记原失败码，不得用 local-detail 替代。
2. comparison.ambiguities 的 aspect 是权威分类；affects_main_relation 必须等于 (aspect != secondary)。局部歧义填 secondary/false；action-direction、product-role、contact、other-main 均填 true。不得写 other-main/false 或 action-direction/false。逐条保留原盲读，不能删歧义。
3. comparison.product_scene[].triptych 必须逐字复制下面绑定表中的 JSON 元数据路径与SHA256；输入观看的是该 JSON 指向的 PNG，返回不能用 PNG 引用替代 JSON 引用。element_id、role、answer、observation 同样逐项一致。
4. 必须由独立检查者逐项对照产品上的品牌名、产品名、Logo/印字与官方素材，核对镜像、倒置、错字、伪字；必要时放大并旋正字区再比较，不把作者自查当作证据。comparison.product_label 增加 checks，覆盖每个绑定产品（没有场景产品则 element_id=product）。每项字段恰为 element_id、official_text、observed_text、mirrored、inverted、misspelled、pseudo_text、inspection、observation；四个错误字段均为布尔，inspection=原图位置、放大/旋正过程与对照依据。看不清须如实记为第6问false，不能臆补读字。产品可合理倾斜，旋正后文字结构倒置才记 inverted。
5. 任何产品文字镜像/倒置/错字/伪字是可核实硬性问题：第6问必须false，review_issues 必须 hard/question=product_label_consistent_readable/reason_code=label，observation逐字第6问观察；不能作为local-detail或主观不确定通过。无这些错误也不自动推出可读。
'''

JUDGMENT_SUPPLEMENT = '\n6. 第6问或版面可读性为false时，由你结合完整观察判断其属于主观无法确认还是已核实错误，在judgment_basis中以对应问题名记录subjective-uncertainty或verified-error；可以附verified_errors字符串数组保存已核实错误。不能从某个词是否出现推断类别，不把已核实字形错误写成主观存疑。原八问、主观提示分级和可确认范围保持不变。\n'

STRUCTURED_FORMAT = """
【结构化对照 v1】使用准备步骤返回的 response_schema。comparison_evidence 只写 comparison 中的裸键，如 product_role。
comparison.layout 和 layout_review 中的 text_readable 均为布尔，实际观察写入 observation；两个布局对象逐项一致。
judgment_basis 只填写第6问及第8问中回答 false 的项目；两问都通过时返回空对象。verified_errors 无实际已核实错误时返回空数组。
"""


def comparison_response_schema():
    path = Path(__file__).resolve().parents[1]/'references/schemas/print-ad-run-manifest.schema.json'
    definitions = load(path)['$defs']
    schema = definitions['core_comparison_return_product_rc4']
    schema['$defs'] = {'bound_file': definitions['bound_file']}
    basis = {'type':'string','enum':['subjective-uncertainty','verified-error']}
    label, layout = 'product_label_consistent_readable', 'layout_readable'
    schema['properties']['judgment_basis'] = {'anyOf': [
        dict(type='object',properties={key:basis for key in keys},required=list(keys),additionalProperties=False)
        for keys in ((), (label,), (layout,), (label, layout))
    ]}
    schema['properties']['verified_errors'] = dict(type='array',items={'type':'string'})
    schema['required'].extend(['judgment_basis','verified_errors'])

    def for_transport(value):
        if isinstance(value,list):return [for_transport(item) for item in value]
        if not isinstance(value,dict):return value
        result={key:for_transport(item) for key,item in value.items()
                if key not in {'pattern','minItems','minLength','minimum','uniqueItems'}}
        if 'enum' in result and 'type' not in result:
            result['type']='string'
        return result

    return for_transport(schema)


def supplement(row):
    bindings=[dict(element_id=p['element_id'],role=p['role'],triptych=p['triptych']) for p in row.get('product_triptychs',[])]
    return SUPPLEMENT+JUDGMENT_SUPPLEMENT+'三联JSON绑定表：'+json.dumps(bindings,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def asset_scope(row):
    assets=row.get('required_brand_assets')
    if not isinstance(assets,list):
        raise ValueError('field=required_brand_assets current='+repr(assets)+'; legal source=current manifest official brief, including []')
    ids=[a['element_id'] for a in assets]
    if len(ids)!=len(set(ids)):
        raise ValueError('Duplicate required brand asset element_id')
    return ('\n【本稿必需品牌资产精确集合 v1】element_ids='+json.dumps(ids,ensure_ascii=False,separators=(',',':'))
            +'。brand_asset_review 必须且仅覆盖此集合；不把 product_scene 或 product_label 的产品ID加入品牌资产列表。'
            +('本稿无必需品牌资产，必须返回 brand_asset_review=[]。' if not ids else '每项保持实际像素观察，即使资产缺失也如实记录。')
            +'固定路径和哈希由接入层绑定，不改任何判断、理由或原始返回。')

def validate_product_text(raw, row):
    from product_relationship_contract import require, nonempty
    checks=raw.get('comparison',{}).get('product_label',{}).get('checks')
    expected={p['element_id'] for p in row.get('product_triptychs',[])} or {'product'}
    require(isinstance(checks,list) and len(checks)==len(expected) and {c.get('element_id') for c in checks}==expected,
            'Independent product text checks must cover every bound product')
    flags=('mirrored','inverted','misspelled','pseudo_text')
    for c in checks:
        require(set(c)=={'element_id','official_text','observed_text','inspection','observation',*flags}
                and all(nonempty(c.get(k)) for k in ('official_text','observed_text','inspection','observation'))
                and all(type(c.get(k)) is bool for k in flags), 'Record independent official/observed product text and orientation inspection')
        require(not any(c[k] for k in flags) or raw['answers']['product_label_consistent_readable']['answer'] is False,
                'Verified mirrored/inverted/misspelled/pseudo product text must fail question 6')
    return checks

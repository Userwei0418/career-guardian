# -*- coding: utf-8 -*-
from openai import OpenAI
import sys
import json
import os
import time
from volcenginesdkarkruntime import Ark

sys.path.append('../')
from utils import ner_logger
from utils_log import send_email
# model_id="ep-20250219151347-fspmw"
api_key="99458ecf-4a8e-4e2a-ad96-246caf5fd213"
model_id="ep-20250613142735-f4xrw"
base_url = "https://ark.cn-beijing.volces.com/api/v3"
model_name = f"model:deepseek ,model_id:{model_id}"

#调用api
def call_gpt(prompt, content, isjson=False, cache_key="job_test"):
    """
    第一次运行为无缓存，会先创建缓存，返回id，保存到本地为文件名是cache_key的json内容类似
    {"response_id": "resp_02176655555466813689d2b61dbb1fab5189b02745c0907eecd5b", "ts": 1766555554.723705}
    以后运行直接传职位信息即可，保存时间为70小时，到时间之后会执行删除，没有文件时会重新缓存，循环
    """
    tokens = {"input": 0, 'caching': 0, 'output': 0, 'thinking': 0}
    try:


        client = OpenAI(api_key=api_key, base_url=base_url)
        # 读取历史 response_id
        response_id = load_response_id(cache_key)
        extraBody = {}
        extraBody['caching'] = {"type": "enabled","prefix": True}
        if response_id: # 缓存存在
            input_data = [ { "role": "user", "content": content } ]
            ner_logger.info(f"doubao-deepseek:\n {input_data}")
            response = client.responses.create(
                model=model_id,
                input=input_data,
                previous_response_id= response_id,
                top_p=0.01
            )
        else:
            input_data = [ { "role": "system", "content": prompt }, { "role": "user", "content": content } ]
            ner_logger.info(f"doubao-deepseek:\n {input_data}")
            response =  client.responses.create(
                model=model_id,      # 模型id
                input=input_data,    #输入内容
                top_p=0.01,          #温度
                extra_body=extraBody,#开启缓存
            )
        #存id
        if not response_id:
            save_response_id(cache_key, response.id)
        # 用量
        usage = response.usage.to_dict()
        tokens['input'] = usage.get('input_tokens')
        tokens['output'] = usage.get('output_tokens')
        if usage.get('input_tokens_details'):
            tokens['caching'] = usage.get('input_tokens_details').get('cached_tokens')
            tokens['input'] = tokens['input'] - tokens['caching']
        if usage.get('output_tokens_details'):
            tokens['thinking'] = usage.get('output_tokens_details').get('reasoning_tokens')
            tokens['output'] = tokens['output'] - tokens['thinking']
        # 4 返回结果
        rs = response
        res = get_only_text(rs)   #处理返回结果
        if not rs:
            raise RuntimeError("model returned empty output")
        return True, res, tokens
    except Exception as e:
        import traceback
        traceback.print_exc()
        ner_logger.error(f"doubao error:{e}")
        send_email(f"doubao error:{e}<br>{prompt}")
        return False,"大模型处理失败[ark][responses]", tokens
#版本模型
def getVers():
    return model_name
#处理返回
def get_only_text(resp):
    """
    从 Responses API 返回中，只提取最终 text 内容
    """
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    return c.text
    return ""
# 修改缓存目录到 data 目录下
CACHE_DIR = "./data/response_cache"
CACHE_EXPIRE = 3600 * 70  # 70 小时

os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_file(key: str):
    # 直接使用 key 作为文件名
    return os.path.join(CACHE_DIR, f"{key}.json")

#加载缓存
def load_response_id(key: str):
    path = _cache_file(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data["ts"] > CACHE_EXPIRE:
            # 文件已过期，删除它并返回 None
            os.remove(path)
            return None
        return data["response_id"]
    except Exception:
        return None

#创建缓存
def save_response_id(key: str, response_id: str):
    path = _cache_file(key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"response_id": response_id, "ts": time.time()},
            f,
            ensure_ascii=False
        )
#清理缓存
def cleanup_expired_cache():
    """清理超过70小时的缓存文件"""
    if not os.path.exists(CACHE_DIR):
        return 0

    current_time = time.time()
    cleaned_count = 0

    for filename in os.listdir(CACHE_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(CACHE_DIR, filename)
            try:
                # 获取文件修改时间
                file_mtime = os.path.getmtime(filepath)
                if current_time - file_mtime > CACHE_EXPIRE:
                    os.remove(filepath)
                    cleaned_count += 1
            except Exception:
                # 如果无法访问文件，跳过
                continue

    return cleaned_count


prompt_template_cjob = '''
#角色定义
你是一个专业的信息结构化引擎，专门从职位描述中提取标准化字段。
#核心任务
将原始职位信息转化为JSON格式，仅提取以下指定维度数据。
#字段提取规范
#输出布尔类型的字段，输出：只输出"是"的，未提及或“否”的输出“”
1.是否是蓝领（IsBlueCollar）
定义：从事体力劳动或技术操作的工作，如生产线、建筑工地、维修等
2.是否可以远程/居家办公，但是不包括远程面试，远程笔试（RemoteWork）
3.是否流水线工作（PipelineWork）
4.是否站立工作（StandWork）
5.是否穿防护服（ProtectionClothes）
6.是否可当天入职（IsTodayEntry）
7.是否不要求体检（IsNoCheckUp）
8.是否宝妈可以（IsMomCan）
9.是否残疾人可以（IsDisabledCan）
10.是否退休人员可以（IsRetiredCan）
11.是否退伍军人可以（IsVeteransCan）
12.是否要求无纹身（IsNoTattoo）
13.是否要求无犯罪记录（IsNoCrimeRecord）
14.是否要求统招（IsUniversity）
15.是否要求有残疾人证（IsDisabledCertificate）
16.是否学生可投递（IsStudentDeliver）
触发词：学生可投、应届生、实习岗、暑假工等
17.是否有转正机会(RegularEmployee) 
18.是否可暑期实习(SummerInternship)
19.是否是校招工作(CampusRecruitment)
20.是否可实习(Intern)
21.是否可兼职(Parttime)
22.是否可全职工作（Fulltime）

#布尔类型字段，可输出“是”/“否”
1.是否工作出差（WorkingTravel）
规则：仅当明确出现"出差"或"不出差"
2.是否要求加班（IsNeedOverTime）
规则："自愿加班" → "否"

#文本类字段
1.职位名/岗位名称(JobTitle)
2.发布日期/开始日期(PublishTime)，格式为yyyy-mm-dd，如果文本中没有则为“”，不是毕业时间、入职时间，如果没有年，则根据当前时间计算  
3.到期日期/截止日期/结束日期(CutDate)，格式为yyyy-mm-dd，如果文本中没有则为“”，不是毕业时间、入职时间，如果没有年，则根据当前时间计算  
4.学历(Degree)：可能是多个，不要重复，是个数组，可选择：“大专”，“大专及以上”、“本科”、“本科及以上”、“硕士”、“硕士/MBA”、“研究生”、“硕士及以上”、“研究生及以上”、“博士”
5.年龄要求（Age），如：年满16周岁  → 16- 、放宽至35岁  → -35、20岁以上  → 20- ，不要数组
标准化：1.中文数字转阿拉伯数字 2.如有分隔符统一为"-" 3.如果多个范围，值为范围中最大最小值
6.职位薪资(Salary)：只能为职位的薪水范围或面议，如：“面议”、“6000”、“8000元/月”、“200元/天”、“6k-8k”、“8-10k”、"60万/年",美元换算为人民币按月计算，1美元=7人民币,没提到就为面议
标准化：1.中文数字转阿拉伯数字 2.如有分隔符统一为"-" 3.如果有多个范围，取范围中最大最小值组成新范围
7.招聘人数(JobNum)：职位招聘的具体人数，如：“1人”等，如果为”若干“，则空
8.工作年限(WorkYears)：工作经历具体年限要求，如：“1年及以上”、“5-8年”、“10年以下”等，如果是中文数字如一二三等转换成阿拉伯数字，只要年限取大的即可，无明确工作年限不返回
9.专业要求(MajorRequirement)
10.工作地点(WorkPlace)：岗位所在城市、工作地区、公司所在地、工作地点、职场坐标、国外国家及地区，可能是多个，用逗号分隔，不要输出数组
11.详细地址(Address)：岗位所在城市，不要输出数组
12.工作类型(HopeWorkType)：可选择：全职/兼职/实习等，可能是多个，用逗号分隔，不要输出数组，注意职位要求的经验不能当工作类型
13.所属部门/工作部门/公司(JobDept)
14.职位描述/职位职责/工作职责/岗位职责(JobDescribe),保留原文中的换行符号，排除岗位要求
15.职位要求/工作要求/任职要求/任职资格(Jobreq),保留原文中的换行符号
16.职业类别(JobCategory)： 职位为的分类，如 职能 、技术、运营、市场、人事、财务、行政、客服、销售、市场、人事、财务、行政、客服、销售、市场等
17.身高要求（Height），如：身高1米65以上  → 165-
标准化：1.统一为厘米单位 2.中文数字转阿拉伯数字 3.分隔符统一"-" 4.如果多个范围，值为范围中最大最小值
18.语言要求（LanguageRequirement）
19.行业要求（IndustryRequirement）
20.证书要求（CertificateRequirement）
21.院校要求（SchoolRequirement）
22.驻外地区（OverseasWork）
输出：
  仅提及"海外"/未知国家 → "海外"
  明确国家/城市 → "国家+城市"（如"需常驻吉隆坡" → "马来西亚吉隆坡"）
23.每周实习天数(WeeklyInternshipDays)： 如：每周3天、每周4天等
24.实习时长(InternshipDuration)： 返回月数，如：3个月、6个月等

#列表类字段
1.技能标签（Skills）
输出：关键词列表，最多5个
2.工资结算方式（SalaryPayment）
输出：日结/周结/月结/完工结
3.福利（Welfare）
定义：仅提取明确提到的福利（如保险、旅游、体检等）
输出：福利列表
语义映射：
	任何形式的用餐福利（包括但不限于：管吃/免费三餐/工作餐/免费食堂等） → 包吃
	任何形式的住宿安排（包括但不限于：管住/提供住宿/员工宿舍等） → 包住
	任何社保相关描述（包括但不限于：五险/缴纳社保/五险一金/六险一金等） → 上社保
4.工作时间（WorkTime），仅关注与工作时间相关的关键词或短语，输出标准化标签，如：早九晚五、双休、月休4天、8小时工作制、每日8小时、9:00-17:00、三班倒、倒班制、弹性工作、不上夜班、长白班、大白班、法定假日、白班、夜班、暑假、寒假、短期、寒暑假、坐班、不坐班等，但是不包括远程面试，远程笔试
5.工作内容标签（WorkTags）,提取最能代表该岗位日常工作的关键词标签
输出：关键词列表，最多5个
6.教育背景标签（EducationBackgroundTags）
定义：提取中国为推动高等教育发展而实施的重点建设项目标签如、985、211、双一流、C9、华5等
# 映射类提取字段
1. 职位类别和职位层级（TypeAndLevel）
    ## Task
    基于【参考标准 1：职级体系】和【参考标准 2：职位类别表】，输出该职位的职级和对应的职位类别代码

    ## Reference Data 1: 职级体系 (L1-L5)
    请严格根据以下定义判断职级，**重点在于是否“带团队/管人”**：
    - **L1 (基础执行岗)**: 
        - 定义: 以执行、操作为主，不涉及管理。
        - 示例: 专员、助理、实习生、前台、普工。
    - **L2 (高级执行/专业岗)**: 
        - 定义: 需要一定经验，承担独立任务，是个人贡献者(IC)，**不管理下属**。
        - 示例: 高级专员、资深设计师、高级工程师、HRBP(非管理职)。
        - *注意: 某些职位虽有“经理”头衔（如产品经理、客户经理），若不带团队，仍属于L2。*
    - **L3 (基层管理岗)**: 
        - 定义: 管理小团队 (Team Leader) 或全权负责某个具体业务模块。
        - 示例: 主管、组长、班长、课长。
    - **L4 (中层管理岗)**: 
        - 定义: 管理一般到中等规模团队或部门，通常下属有L3级人员。
        - 示例: 部门经理 (Manager)、城市经理。
    - **L5 (高层管理岗)**: 
        - 定义: 负责多个部门或区域，管理团队规模大，制定战略。
        - 示例: 总监 (Director)、VP、区域总经理。

    ## Reference Data 2: 职位类别表 (JSON)
    {"销售人员":"0101","销售管理":"0102","销售行政/商务":"0103","客服人员":"0201","客服管理":"0202","市场营销":"0301","市场调研":"0302","推广投放":"0303","广告":"0304","公关":"0305","媒介":"0306","会展会务":"0307","政府事务":"0308","视觉/交互设计":"0401","环境/展示设计":"0402","工业设计":"0403","美术/3D/动画":"0404","游戏设计":"0405","编辑":"0501","记者/采编":"0502","作者/撰稿人":"0503","出版发行":"0504","校对录入":"0505","印刷":"0506","主播/助播/直播运营":"0601","演艺人员":"0602","配音员":"0603","经纪人":"0604","艺人助理":"0605","主持人/DJ":"0606","模特":"0607","导演/编导":"0608","摄影/摄像":"0609","舞美/灯光/道具":"0610","化妆/造型/服装师":"0611","录音/音效":"0612","编剧":"0613","制片人":"0614","影视策划":"0615","影视发行":"0616","剪辑/后期":"0617","人力资源":"0701","HRBP":"0702","招聘":"0703","培训":"2502","员工关系":"0705","社保专员":"0706","薪酬绩效":"0707","组织发展/企业文化":"0708","人力资源信息系统管理":"0709","猎头/招聘交付人员":"0710","行政":"0801","图书管理":"0802","党务/纪检监察":"0803","后勤":"0804","前台":"0805","助理/文员":"0806","财务":"0901","审计":"0902","税务":"0903","公司法务":"1001","律师":"1002","风控合规":"1003","法医/司法鉴定":"1004","技术项目管理":"1201","非技术项目管理":"1202","前端开发":"1301","后端开发":"1302","移动开发":"1303","数据":"1304","人工智能":"1305","硬件开发":"1306","品管/测试":"1307","运维/网络安全":"1308","售前售后技术支持":"1309","技术管理":"1310","游戏策划/制作":"1311","产品":"1312","运营":"1313","硬件研发":"1401","通信研发":"1402","电气/自动化技术":"1403","电子技术":"1404","半导体/芯片":"1405","银行及金融服务":"1501","投融资":"1502","证券":"1503","基金":"1504","外汇":"1505","期货":"1506","保险":"1507","担保/典当/拍卖":"1508","房地产开发":"1601","房地产销售/中介/招商":"1602","建筑规划与设计":"1603","建筑工程管理":"1604","装修/室内设计":"1605","建筑/装修工人/施工员":"1606","物业管理人员":"1701","物业服务人员":"1702","物业维修维护人员":"1703","生物/医药研发":"1801","临床研究/试验":"1802","医药市场/销售":"1803","医疗器械研发":"1901","医疗器械销售":"1902","医疗器械生产/维护":"1903","医务管理":"2001","医生":"2002","医技":"2003","药剂师/中药师":"2004","营养师":"2005","心理治疗师":"2006","公共卫生/保健":"2007","护理":"2008","医助":"2009","护工":"2010","采购":"2101","供应链":"2102","国内贸易":"2103","外贸/进出口":"2104","电子商务":"2105","物流":"2106","仓储":"2107","配送":"2108","装卸/搬运":"2109","司机":"2110","无人机飞手":"2111","航空服务":"2112","水上运输服务":"2113","铁路服务":"2114","城市轨道交通服务":"2115","道路交通运输服务":"2116","汽车研发/制造":"2201","新能源汽车技术":"2202","汽车销售/服务":"2203","冶金":"2301","机械设计/制造/维护":"2302","服装/纺织/皮革":"2303","化工":"2304","食品/饮料":"2305","生产管理/营运":"2306","生产质量管理":"2307","安全管理":"2308","技工普工":"2309","石油/天然气":"2401","煤炭":"2402","电力":"2403","风能":"2404","太阳能/光伏":"2405","水利水电":"2406","其他新能源":"2407","矿产/地质":"2408","环保":"2409","咨询/顾问/调研":"2501","翻译":"2503","高等教育":"2601","中小学/学前教育/培训":"2602","考研/考公/考证/留学辅导":"2603","职业教育/培训":"2604","科研/学术":"2605","餐饮管理人员/领班":"2701","厨师":"2702","切配/备料":"2703","面点/烘焙/甜品":"2704","茶饮/咖啡制作":"2705","洗碗/清洁":"2706","商场运营管理":"2707","零售店长/督导":"2708","零售店员/导购":"2709","理货/陈列":"2710","安全/防损":"2711","服务员/营业员/收银员":"2712","药店店长/店员":"2713","驻店药师":"2714","酒店管理":"2801","宾客服务":"2802","客房服务":"2803","民宿运营":"2804","领队/导游/讲解员":"2901","旅游策划":"2902","出入境/票务/计调":"2903","旅游景点运营管理":"2904","旅游景点其他工作人员":"2905","美容/美发/美甲/纹绣":"3001","医美":"3002","保健/足疗/按摩/理疗":"3003","体育/运动健身":"3004","剧本杀":"3005","宠物服务":"3006","摄影服务":"3007","婚庆服务":"3008","丧葬服务":"3009","网吧网咖":"3010","家政/保洁":"3011","生活维修":"3012","安保":"3013","农业生产技术人员":"3101","林业生产技术人员":"3102","畜牧业生产技术人员":"3103","渔业生产技术人员":"3104","农林牧渔管理人员":"3105","公务员":"3201","事业单位工作人员":"3202","社工":"3203","管培生/储备干部":"3204","志愿者/义工":"3205"}

    ## Analysis Steps (思考逻辑)
    1. **职级判断**: 先分析 JD 中的“职责描述”和“任职要求”。是否需要带团队？团队规模多大？是独立干活还是管理他人？据此确定 L1-L5。
    2. **类别匹配**: 
        - 如果职级是 **L3, L4, L5**：检查 JSON 中是否有对应的“管理类”Code（如 `0102 销售管理`, `1310 技术管理`）。如果有，优先使用管理类 Code；如果没有专门的管理Code，则使用最核心的业务 Code。
        - 如果职级是 **L1, L2**：必须匹配具体的业务执行类 Code（如 `0101 销售人员`, `1302 后端开发`），严禁使用“XX管理”类的 Code。
    3. **语义精准匹配**：
        - 区分“行业”与“职能”。例如“医疗器械公司的销售”应匹配 `1902 (医疗器械销售)` 优先于 `0101 (普通销售)`。
    4. **数量限制**: 提取最匹配的 1-2 个 Code。

    # Output Format
    请严格按照以下 JSON 格式输出，不要包含 Markdown 代码块标记或其他文字：
    {
        "Level": "L3",
        "Names": "['销售管理']",
        "Codes": ["0102"],
        "Reasoning": "职位名称为销售主管，JD中明确提到需要带领5人团队完成业绩，属于基层管理，因此匹配L3及销售管理。"
    }
#全局处理规则
1. 未提及或为空的字段，则为""
2. 返回JSON的键使用小括号中的英文
3. 完全按照原文输出，不需要加工。
4. 你所需要的全部内容都在[webpage X begin]...[webpage X end]中，不能虚构内容。
5. 如果存在多职位，那么只返回第一个职位信息即可
6. 脱敏后再输出
7. 所有定义过的字段必须全部出现在JSON中，不允许省略任何key。没有信息的字段请赋值为空字符串 ""，不要删除key。
'''
concent = '''
SSC实习生8013广州市-天河区2025-04-22发布大专无经验招聘1人工作职责1、员工档案归档：负责人事档案扫描和录入工作，按要求完成档案扫描及装订归档，并录入系统；协助归档离职员工资料，并按要求打包存库；
2、入职手续办理：协助办理员工入职手续的系统录入；
3、系统信息整理：协助日常人事档案材料收集、建立，完善HRIS系统人事信息；
4、团队协作：其他临时性事项处理、支持。任职要求1、学历：大专以上学历，档案管理、中文、人力资源、文秘或相关专业
2、相关工作经验优先
'''
if __name__ == '__main__':

    re = call_gpt(prompt_template_cjob,concent,isjson=True, cache_key="job_extract")
    print(re)
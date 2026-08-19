import time
import os
import argparse
from typing import Any

from playwright.sync_api import sync_playwright

from spider_sch import SpiderSch
from spider_com import SpiderCom
from spider_data import DEFAULT_WX_SCHOOL, DEFAULT_PCOUNT
from spider_data import SpiderData
from utils import set_logger_debug, ner_logger
from utils_playwright import get_browser

# ==========================================
# 参数解析配置
# ==========================================
parser = argparse.ArgumentParser(description='这是一个爬取学校及公司公告数据的程序')
parser.add_argument('-m', '--method', default="p", type=str, help='启动方式(方法: p, cp, cjob, ann, wx, etc.)')
parser.add_argument('-f', '--file', default="99", type=str, help='启动具体的配置文件')
parser.add_argument('-v', '--version', default="", type=str, help='版本说明')
parser.add_argument('-d', '--dist', default="dev", type=str, help='云API接口环境 (dev/prod)')
parser.add_argument('-s', '--processfile', default="", type=str, help='需要独立处理的单个文件')
parser.add_argument('-c', '--company', default="", type=str, help='需要单独处理的公司名称')
parser.add_argument('-p', '--proxy', default="", type=str, help='是否使用代理')
parser.add_argument('-r', '--retry', default="1", type=str, help='是否重入与重试')
parser.add_argument('-t', '--pagestart', default="2", type=str, help='翻页开始页数')

args = parser.parse_args()


def clawler_main(s: SpiderSch | SpiderCom, _stat: dict[str, Any] | None = None) -> None:
    """
    从目标网站爬取数据的入口函数
    :param s: 爬虫实例 (SpiderSch 或 SpiderCom)
    :param _stat: 状态统计字典
    """
    if _stat is None:
        _stat = {}

    executable_path = s.get_browser_path()
    with sync_playwright() as p:
        # 创建一个浏览器实例 (根据参数判断是否使用代理)
        browser = get_browser(p, executable_path, args.proxy)
        # 保存浏览器实例
        s.browser = browser
        # 创建一个新页面
        page = browser.new_page()

        # 获取爬取节点和进度
        nodes = s.get_nodes()
        process = s.get_progress()

        for _key, _node in nodes.items():
            # 跳过微信特殊学校，留给专门的微信逻辑处理
            if _key == DEFAULT_WX_SCHOOL:
                continue

            # 若指定了单独公司，仅处理该指定公司
            if 'company' in _stat and _stat['company'] != _key:
                continue

            # 正常处理该节点下的学校或公司信息
            for _sch_info in _node:
                if _key in process:
                    print(f"开始爬取: {_key}")
                    s.run(page, _key, _sch_info, _stat)

        # 停顿10s后关闭浏览器
        time.sleep(10)
        browser.close()


def process_main_wx(s: SpiderSch, d: SpiderData, _stat: dict[str, Any] | None = None) -> None:
    """
    处理爬取的微信公众号数据
    """
    if _stat is None:
        _stat = {}

    nodes = s.get_nodes()
    for _key, _node in nodes.items():
        # 不处理微信特定账号
        if _key == DEFAULT_WX_SCHOOL:
            continue
            
        for _sch_info in _node:
            d.process_announcement_data(_key, _sch_info, _stat, "wx")


def process_main_announcement(s: SpiderSch | SpiderCom, d: SpiderData, _stat: dict[str, Any] | None = None, proc_type: str = "ann", _uapi: str = "up_api") -> None:
    """
    处理爬取的公告数据（包含学校和公司职位公告）
    """
    if _stat is None:
        _stat = {}

    nodes = s.get_nodes()
    for _key, _node in nodes.items():
        if _key == DEFAULT_WX_SCHOOL:
            continue
            
        for _sch_info in _node:
            d.process_announcement_data(_key, _sch_info, _stat, proc_type)
            # 当处理条数超过默认限制时清零
            if 'total' in _stat and _stat['total'] >= DEFAULT_PCOUNT:
                ner_logger.info(f"{_stat['total']}条数据已经处理完成")
                # [DEPRECATED] 上云入库逻辑已弃用
                # d.process_announcement_data(_key,_sch_info,_stat,_uapi)
                # ner_logger.info(f"{_stat['total']}条数据已经上传完成")
                _stat['total'] = 0


def process_main_wxhand(s: SpiderSch, d: SpiderData, _stat: dict[str, Any] | None = None) -> None:
    """
    处理微信手工录入/收集的文章数据
    """
    if _stat is None:
        _stat = {}

    # 预处理数据
    d.pre_wx_article()
    nodes = s.get_nodes()
    
    for _key, _node in nodes.items():
        # 仅处理微信特定学校账号
        if _key != DEFAULT_WX_SCHOOL:
            continue
            
        ner_logger.info(f"开始处理特殊学校数据： {_key}")
        for _sch_info in _node:
            d.process_announcement_data(_key, _sch_info, _stat, "wx")


def process_main_upapi(s: SpiderSch | SpiderCom, d: SpiderData, _stat: dict[str, Any] | None = None, _uapi: str = "up_api") -> None:
    """
    处理并上传数据到云端 [该逻辑已停用(DEPRECATED)]
    """
    # ner_logger.info("[DEPRECATED] 数据上传云端逻辑已停用，不需要入库")
    pass


def process_main_wxhand_api(s: SpiderSch, d: SpiderData, _stat: dict[str, Any] | None = None) -> None:
    """
    微信手工数据上传云端逻辑 [该逻辑已停用(DEPRECATED)]
    """
    # ner_logger.info("[DEPRECATED] 微信手工数据上传逻辑已停用，不需要入库")
    pass


def run_periodically(s: SpiderSch, cs: SpiderCom, d: SpiderData) -> None:
    """
    主控制函数：根据命令行参数 (args) 决定执行什么任务，包括单次执行与死循环周期任务。
    """
    _stat: dict[str, Any] = {}

    # 初始化配置信息到 _stat
    if args.processfile:
        _stat['pfile'] = args.processfile
    if args.company:
        _stat['company'] = args.company
        
    _stat['page_start'] = int(args.pagestart) if args.pagestart else 2
    _stat['dist'] = args.dist
    _stat['retry'] = args.retry
    _stat['p_count'] = 0
    _stat['all_proc_list'] = []

    if args.method == "o":
        s.print_all_sch()

    # ==========================================
    # 模块 1: 公司职位数据爬虫与处理
    # ==========================================
    if args.method in ["cp", "cp_full"]:
        _stat['method'] = args.method
        clawler_main(cs, _stat)
        time.sleep(6)
        ner_logger.info("第一步: 爬取大公司的数据完成, 休息后继续再处理数据")

    if args.method == "cjob":
        process_main_announcement(cs, d, _stat, "cjob", "up_api_cjob")
        time.sleep(6)
        ner_logger.info("第二步: 处理职位数据完成, 休息1分钟后继续")

    if args.method == "cjob_api":
        process_main_upapi(cs, d, _stat, "up_api_cjob")
        time.sleep(6)
        ner_logger.info("第四步: 爬取职位数据并上传完成。")

    if args.method == "all_job":
        ner_logger.info("开始启动周期循环的公司公告处理")
        _loop_times = 0
        while True:
            _all_total = 0
            
            _stat['total'] = 0
            process_main_announcement(cs, d, _stat, "cjob", "up_api_cjob")
            _total = _stat['total']
            _all_total += _total
            time.sleep(6)
            ner_logger.info(f"第二步: 处理职位数据完成, 休息1分钟后继续。处理量: {_total}")

            _stat['total'] = 0
            process_main_upapi(cs, d, _stat, "up_api_cjob")
            _total = _stat['total']
            _all_total += _total
            time.sleep(6)
            ner_logger.info(f"第四步: 爬取职位数据上传完成。处理量: {_total}")

            # 若没有任何数据处理且执行了多次，则结束循环
            if _all_total == 0 and _loop_times > 200:
                ner_logger.info("没有处理任何数据，结束循环。干得漂亮！")
                break
            _loop_times += 1

    # ==========================================
    # 模块 2: 学校系统爬虫调度
    # ==========================================
    if args.method == "p":
        clawler_main(s, _stat)
        time.sleep(6)
        ner_logger.info("第一步: 爬取数据完成, 休息10分钟后继续")

    if args.method == "all_p":
        ner_logger.info("开始启动周期循环的学校公告爬虫")
        clawler_main(s, _stat)
        time.sleep(60 * 60 * 8)
        ner_logger.info("第一步: 爬取数据完成, 休息8小时后继续（循环）")

    # ==========================================
    # 模块 3: 校园公告数据解析及上传
    # ==========================================
    if args.method == "ann":
        process_main_announcement(s, d, _stat)
        time.sleep(6)
        ner_logger.info("第二步: 处理数据公告完成, 休息1分钟后继续")

    if args.method == "ann_wx":
        process_main_wx(s, d, _stat)
        time.sleep(6)
        ner_logger.info("第三步: 处理微信数据完成, 休息1分钟后继续")

    if args.method == "ann_api":
        process_main_upapi(s, d, _stat)
        time.sleep(6)
        ner_logger.info("第四步: 数据上传云端完成。")

    if args.method == "all_ann":
        ner_logger.info("开始启动周期循环的学校公告处理")
        _loop_times = 0
        while True:
            _loop_times += 1
            _all_total = 0
            
            _stat['total'] = 0
            process_main_upapi(s, d, _stat)
            time.sleep(6)
            _total = _stat['total']
            _all_total += _total
            ner_logger.info(f"第零步: 上传数据完成(循环)。处理量: {_total}")

            _stat['total'] = 0
            process_main_announcement(s, d, _stat)
            time.sleep(6)
            _total = _stat['total']
            _all_total += _total
            ner_logger.info(f"第二步: 处理数据完成(循环), 休息1分钟后继续。处理量: {_total}")

            _stat['total'] = 0
            process_main_wx(s, d, _stat)
            time.sleep(6)
            _total = _stat['total']
            _all_total += _total
            ner_logger.info(f"第三步: 处理微信数据完成(循环), 休息1分钟后继续。处理量: {_total}")

            if _all_total == 0 and _loop_times > 20:
                ner_logger.info("没有处理任何数据，结束循环，干得漂亮！")
                break

    # ==========================================
    # 模块 4: 微信手工文章处理
    # ==========================================
    if args.method == "wxhand":
        process_main_wxhand(s, d, _stat)
        time.sleep(6)
        ner_logger.info("第一步: 微信手工数据处理完成。")

    if args.method == "wxhand_api":
        process_main_wxhand_api(s, d, _stat)
        time.sleep(6)
        ner_logger.info("第二步: 微信手工数据上传完成。")

    if args.method == "all_wxhand":
        ner_logger.info("开始启动周期循环的微信处理")
        while True:
            _stat['total'] = 0
            process_main_wxhand_api(s, d, _stat)
            time.sleep(6)
            ner_logger.info(f"第零步: 微信手工数据上传(循环)。处理量: {_stat['total']}")

            time.sleep(6)
            _stat['total'] = 0
            process_main_wxhand(s, d, _stat)
            time.sleep(6)
            ner_logger.info(f"第一步: 微信手工数据处理完成(循环)。处理量: {_stat['total']}")

            _stat['total'] = 0
            process_main_wxhand_api(s, d, _stat)
            time.sleep(6)
            ner_logger.info(f"第二步: 微信手工数据上传(循环)。处理量: {_stat['total']}")
            time.sleep(6)


if __name__ == '__main__':
    # 设置 Debug 级别的日志配置
    set_logger_debug(args.file)
    
    # 实例化抓取器与数据处理器
    s = SpiderSch(args.file)
    cs = SpiderCom(args.file)
    d = SpiderData(s)

    if args.version != '':
        print("====== 命令行使用指南 ======")
        print("  -m   : 启动方式，默认为 p")
        print("         > all: 所有功能")
        print("         > p: 爬取数据 (默认)")
        print("         > wx: 处理微信数据")
        print("         > ann: 处理公告数据")
        print("         > api: 上传云数据\n")
        print("  -f   : 指定使用特定的配置文件，默认为 99")
        print("         > 1 : 表示配置文件需要")
        print("============================")

    # 主程序启动，执行调度任务（单次或者循环）
    run_periodically(s, cs, d)

    """
    使用示例:
    python main.py -m ann -f 2
    python main.py -m p -f 10
    python main.py -m wxhand
    支持单文件执行模式, 如: -s detail_957a920de3fd7b77e77e6e47ab3ce647
    """

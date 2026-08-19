import os
import glob
import json
import shutil
import time

from utils import ner_logger, is_wechat_url, getMD5Str
from utils_html import get_weixin_info, get_weixin_hand_url, clean_weixin_html
from utils_date import check_file_modification_time, check_file_modification_time_old
from utils_playwright import get_wx_url_content
from parsegpt.ann_md import html2md_with_fix, md_to_html
from parsegpt.ann_model import parse_announcement
from parsegpt.cjob_model import parse_cjob
from spider_sch import DEFAULT_COMMON

# 默认手工微信的特殊学校代码
DEFAULT_WX_SCHOOL = "sch_88888"
# 默认处理的数据量
DEFAULT_PCOUNT = 3


class SpiderData:
    """数据抓取与处理核心类"""

    def __init__(self, spider_sch):
        """
        初始化 SpiderData 实例，加载黑名单数据并连接监控系统。
        """
        self.spider_sch = spider_sch

        # 使用集合提高查找效率 (O(1))
        self.black_img_urls = set()
        self.black_img_md5 = set()
        self.black_img_md5_content = set()
        self.black_text = set()

        # 读取各类黑名单数据
        self._load_blacklist("data/black_img_urls.txt", self.black_img_urls)
        self._load_blacklist("data/black_img_md5.txt", self.black_img_md5)
        self._load_blacklist("data/black_img_md5_content.txt", self.black_img_md5_content)

        # 读取带完整 URL 的黑名单，并计算 MD5 后加入
        full_urls_file = "data/black_img_urls.full.txt"
        if os.path.exists(full_urls_file):
            with open(full_urls_file, encoding="utf-8") as f:
                for line in f.read().splitlines():
                    line = line.strip()
                    if line:
                        self.black_img_urls.add(getMD5Str(line))

        ner_logger.info(
            f"读取黑名单数量, url: {len(self.black_img_urls)}, "
            f"md5: {len(self.black_img_md5)}, text: {len(self.black_text)}"
        )

        # 使用同一个 monitor 实例
        self.monitor = spider_sch.monitor
        ner_logger.info("SpiderData 已链接到监控系统")

    def _load_blacklist(self, filepath: str, target_set: set):
        """辅助方法：读取文本文件并将每行内容加载到指定集合中"""
        if os.path.exists(filepath):
            with open(filepath, encoding="utf-8") as f:
                for line in f.read().splitlines():
                    line = line.strip()
                    if line:
                        target_set.add(line)

    def check_url_in_blacklist(self, md5_str: str) -> bool:
        """检查给定的 MD5 是否在图片 URL 或图片 MD5 黑名单中"""
        return md5_str in self.black_img_urls or md5_str in self.black_img_md5

    def check_md5_txt_in_blacklist(self, txt_md5: str) -> bool:
        """检查给定的 MD5 是否在图片内容 MD5 黑名单中"""
        return txt_md5 in self.black_img_md5_content

    def get_wx_path(self) -> str:
        """根据操作系统获取手工维护微信文章的本地路径"""
        if os.name == "nt":
            return self.spider_sch.config.get(DEFAULT_COMMON, "wxpath_win")
        elif os.name == "posix":
            return self.spider_sch.config.get(DEFAULT_COMMON, "wxpath_mac")
        return ""

    def get_wx_url(self, data: dict) -> str:
        """从数据字典中提取微信文章的 URL"""
        if data.get("type_url") == "wxwz" and is_wechat_url(data.get("full_url", "")):
            return data["full_url"]
        elif is_wechat_url(data.get("last_url", "")):
            return data["last_url"]
        return ""

    def proc_wechaturl_md(self, url: str, target_dir: str, outfile: str):
        """调用本地程序将微信文章 URL 转换为 Markdown 文件"""
        exe = self.spider_sch.get_md_exe()
        cmd = f'{exe} -image=url --dir {target_dir} --output {outfile} "{url}"'
        ner_logger.info(f"开始执行微信文章转换 MD: {cmd}")
        os.system(cmd)

    def proc_html_md(self, input_file: str, outfile: str):
        """调用本地程序将 HTML 文件转换为 Markdown 文件"""
        exe = self.spider_sch.get_html_md_exe()
        cmd = f'{exe} --output-overwrite --plugin-table --exclude-selector=".ad" --input "{input_file}" --output "{outfile}"'
        ner_logger.info(f"开始执行 HTML 转换 MD: {cmd}")
        os.system(cmd)

    def process_announcement_data(self, key, sch_info, stat, proc_type="ann"):
        """
        处理指定 key 下的爬取数据文件。
        """
        keydir = self.spider_sch.get_key_dir(key)
        ar_dir = self.spider_sch.get_savepath(f"/data/ardata/{key}")
        cache_dir = self.spider_sch.get_savepath("/data/cache")

        # 检查并创建必要的目录
        os.makedirs(ar_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

        ner_logger.info(f"处理目录: {keydir}, 类型: {proc_type}")

        # 初始化统计列表
        if "all_proc_list" not in stat:
            stat["all_proc_list"] = []

        # 遍历目录下所有的 .json 文件
        for file_path in glob.glob(f"{keydir}/*.json"):
            filename = os.path.basename(file_path)

            # 跳过 index 开头的文件以及非 detail_ 开头的文件
            if filename.startswith("index") or not (
                filename.startswith("detail_") and filename.endswith(".json")
            ):
                continue

            # 委托给辅助方法处理单个文件，如果返回 True 表示达到处理上限，需要退出循环
            if self._process_single_file(
                file_path, filename, key, sch_info, stat, proc_type, ar_dir, cache_dir
            ):
                break

    def _process_single_file(
        self, file_path, filename, key, sch_info, stat, proc_type, ar_dir, cache_dir
    ) -> bool:
        """
        处理单个 JSON 文件的数据。
        返回 True 表示达到了处理上限，需要终止后续处理；返回 False 表示继续处理下一个文件。
        """
        # 检查对应的 HTML 文件是否存在（对于 ann 和 cjob 是必须的）
        hfile = file_path.replace(".json", ".html")
        if proc_type in ["ann", "cjob"] and not os.path.exists(hfile):
            return False

        tag_info = f"{filename}_{proc_type}"

        # 跳过 10 秒内生成的文件（避免与爬虫冲突）
        if check_file_modification_time(file_path):
            ner_logger.info(f"文件 10s 内生成，跳过: {file_path}")
            return False

        # 跳过旧文件并记录到处理列表
        if check_file_modification_time_old(file_path):
            if tag_info not in stat["all_proc_list"]:
                stat["all_proc_list"].append(tag_info)
            return False

        # 定义相关的衍生文件路径
        ar_file = os.path.join(ar_dir, filename)
        md_file = ar_file.replace(".json", ".md")
        fix_file = ar_file.replace(".json", ".html")
        model_file = ar_file.replace(".json", ".model.json")
        up_api_file = model_file.replace(".json", f".json.{stat.get('dist', '')}.ok")
        expired_file = ar_file.replace(".json", ".json.expired")

        # 云端上传类型需要 model_file 存在
        if proc_type in ["up_api", "up_api_cjob"] and not os.path.exists(model_file):
            return False

        # 跳过已标记为过期的文件
        if os.path.exists(expired_file):
            return False

        # 加载 JSON 原始数据
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            ner_logger.error(f"JSON 解析失败: {file_path}")
            return False

        title = data.get("announcement_name", "")

        # 关键词过滤
        if proc_type in ["wx", "ann"] and not self.spider_sch.is_title_include(title):
            ner_logger.info(f"标题在关键词排除之列，跳过: {file_path} / {title}")
            return False

        wx_url = self.get_wx_url(data)

        # 调试单个微信文件时的过滤逻辑
        if "pfile" in stat:
            pfile_prefix = stat["pfile"]
            if not filename.startswith(pfile_prefix):
                return False
            # 移除已处理的文件缓存以便重新处理
            if os.path.exists(model_file) and proc_type in ["wx", "ann", "cjob"]:
                os.remove(model_file)
            if os.path.exists(up_api_file) and proc_type in ["up_api", "up_api_cjob"]:
                os.remove(up_api_file)

        # 检查是否已经处理过
        if os.path.exists(model_file) and proc_type in ["wx", "ann", "cjob"]:
            return False
        if os.path.exists(up_api_file) and proc_type in ["up_api", "up_api_cjob"]:
            return False

        if tag_info in stat["all_proc_list"] and "pfile" not in stat:
            ner_logger.info(f"跳过: 本次启动已处理过的文件 {title} - {tag_info}")
            return False
        else:
            if tag_info not in stat["all_proc_list"]:
                stat["all_proc_list"].append(tag_info)

        # 避免处理过快
        time.sleep(0.5)

        # 根据处理类型执行具体逻辑
        if (proc_type == "wx" and wx_url) or (proc_type == "ann" and wx_url):
            # 获取并处理微信文章
            ok, wx_file = self.pre_wx_article_html(data, cache_dir, wx_url)
            if ok:
                ok_wx, hfile_wx, mdfile_wx = self.process_wechat_data(
                    sch_info, file_path, ar_dir, filename, data, cache_dir, wx_url, wx_file
                )
                if ok_wx:
                    ner_logger.info(f"处理微信转 HTML 数据 - {hfile_wx} \n {file_path}")
                    ok_gonggao = self.process_gonggao_data(
                        sch_info, filename, data, cache_dir, md_file, fix_file,
                        model_file, hfile_wx, proc_type, expired_file, stat
                    )
                    if ok_gonggao == "ok":
                        return self._increment_and_check_stat(stat, "wx")

        elif proc_type == "ann" and not wx_url:
            # 处理普通公告
            ok_gonggao = self.process_gonggao_data(
                sch_info, filename, data, cache_dir, md_file, fix_file,
                model_file, hfile, proc_type, expired_file, stat
            )
            if ok_gonggao == "ok":
                return self._increment_and_check_stat(stat, "ann")

        elif proc_type == "cjob":
            # 处理职位数据
            ner_logger.info(f"开始处理公司职位文件: {title} - {hfile}")
            ok_cjob, msg = parse_cjob(
                self, model_file, data, sch_info, expired_file, hfile, stat
            )
            if ok_cjob == "ok":
                is_full = self._increment_and_check_stat(stat, "cjob")
                if not is_full:
                    ner_logger.info(
                        f"共处理 {stat.get('total', 0)} / {stat.get('p_count', 0)} 条 cjob 数据完成，继续"
                    )
                return is_full
            elif ok_cjob == "Err":
                with open(expired_file, "w", encoding="utf-8") as f:
                    f.write(msg)
                ner_logger.info(f"parse_cjob 失败，写入过期文件: {expired_file}")

        # 注意：up_api 和 up_api_cjob 逻辑已被弃用并移除
        return False

    def _increment_and_check_stat(self, stat: dict, data_type: str) -> bool:
        """辅助方法：增加统计计数，并检查是否达到处理上限"""
        if "total" in stat:
            stat["total"] += 1
        else:
            stat["total"] = 1

        stat["p_count"] = stat.get("p_count", 0) + 1

        if stat["total"] >= DEFAULT_PCOUNT:
            ner_logger.info(f"共处理 {stat['p_count']} 条 {data_type} 数据完成，退出")
            return True
        return False

    def process_gonggao_data(
        self, sch_info, filename, data, cache_dir, md_file, fix_file,
        model_file, hfile, proc_type, expired_file, stat
    ) -> str:
        """处理学校公告 HTML 并转换为 Markdown，然后使用大模型进行解析"""
        start_time = time.time()
        title = data.get("announcement_name", "未知标题")
        channel = data.get("channel", "未知渠道")

        ner_logger.info(f"分析文件: {title} - {md_file}")

        try:
            with open(hfile, "r", encoding="utf-8") as f:
                html_content = f.read()
        except Exception as e:
            ner_logger.error(f"读取 HTML 文件失败: {hfile}, 错误: {e}")
            return ""

        # HTML 转换为 Markdown 并修复格式
        ok, info, full_text = html2md_with_fix(
            self, data, fix_file, md_file, html_content, sch_info, cache_dir, hfile
        )

        # 确保解析成功且 info 包含所需的 props 数据
        if ok and len(info) > 2 and "props" in info:
            # 针对微信公告进行复杂性检测
            if proc_type == "wx":
                if not self.check_wx_file(data, hfile, model_file):
                    with open(expired_file, "a", encoding="utf-8") as fw:
                        fw.write("不能处理这个微信公告(复杂性过高)\n")
                    ner_logger.info(f"不能处理这个微信公告(复杂性过高): {title} - {hfile}")

                    self.monitor.log_clean(
                        key=channel,
                        source_file=filename,
                        model_file=os.path.basename(model_file),
                        status="failed",
                        error="微信公告太复杂，不能处理",
                        duration=time.time() - start_time,
                    )
                    return ""

            # 调用大模型解析公告
            ok_parse, msg = parse_announcement(
                md_file, fix_file, model_file, info, full_text,
                proc_type, sch_info, expired_file, stat
            )
            duration = time.time() - start_time

            if ok_parse:
                ner_logger.info(f"大模型处理文件成功: {title} - {md_file}")
                self.monitor.log_clean(
                    key=channel,
                    source_file=filename,
                    model_file=os.path.basename(model_file),
                    status="success",
                    duration=duration,
                )
                return "ok"
            else:
                with open(expired_file, "a", encoding="utf-8") as fw:
                    fw.write(f"{msg}\n")
                ner_logger.info(f"大模型处理失败: {title} - {msg}")
                self.monitor.log_clean(
                    key=channel,
                    source_file=filename,
                    model_file=os.path.basename(model_file),
                    status="failed",
                    error=msg,
                    duration=duration,
                )
        else:
            # html2md_with_fix 失败处理
            with open(expired_file, "a", encoding="utf-8") as fw:
                fw.write("不能处理这个微信公告 (html2md_with_fix 失败)\n")
            ner_logger.info(f"解析失败 (html2md_with_fix): {title} - {hfile}")

            self.monitor.log_clean(
                key=channel,
                source_file=filename,
                model_file=os.path.basename(model_file),
                status="failed",
                error="html2md_with_fix 处理失败",
                duration=time.time() - start_time,
            )

        return ""

    def process_wechat_data(
        self, sch_info, file_path, ar_dir, filename, data, cache_dir, wx_url, wx_file
    ):
        """处理微信文章数据：调用外部程序生成 MD 并转回 HTML"""
        title = data.get("announcement_name", "未知标题")
        ner_logger.info(f"处理微信数据: {title} - {wx_url} \n {file_path}")

        md_filename = filename.replace(".json", ".md")
        md_cache_dir = f"{cache_dir}_md"

        # 确保缓存目录存在
        os.makedirs(md_cache_dir, exist_ok=True)

        md_file = os.path.join(md_cache_dir, md_filename)

        # 清除旧的缓存文件
        if os.path.exists(md_file):
            os.remove(md_file)

        # 调用外部工具进行转换
        self.proc_wechaturl_md(wx_file, md_cache_dir, md_filename)

        if not os.path.exists(md_file):
            return "", "", ""

        # 验证生成的 MD 文件内容长度
        with open(md_file, "r", encoding="utf-8") as f:
            md_text = f.read()
            if len(md_text) < 50:
                ner_logger.info(
                    f"微信 URL {wx_url} 生成的 MD 文件长度小于 50，不做处理: {md_file}"
                )
                return "", "", ""

        html_file = md_file.replace(".md", ".html")
        ok_html = md_to_html(md_file, html_file)

        if ok_html:
            ner_logger.info(f"微信生成的 MD 及 HTML 文件:\n{md_file}\n{html_file}")
            return "ok", html_file, md_file

        return "", "", ""

    def pre_wx_article_html(self, data, cache_dir, wx_url):
        """
        预处理微信文章：通过 Playwright 获取页面内容并保存，
        同时提取页面信息并进行清洗。
        """
        wx_cache_dir = f"{cache_dir}_wx"
        os.makedirs(wx_cache_dir, exist_ok=True)

        md5_url = getMD5Str(wx_url)
        wx_file = os.path.join(wx_cache_dir, f"{md5_url}.html")
        wx_file_0 = os.path.join(wx_cache_dir, f"{md5_url}.html.0")
        wx_file_config = os.path.join(wx_cache_dir, f"{md5_url}.html.config")

        # 如果缓存或配置不存在，则重新获取
        if not os.path.exists(wx_file) or not os.path.exists(wx_file_config):
            executable_path = self.spider_sch.get_browser_path()
            ok, content, image_lists = get_wx_url_content(executable_path, wx_url)

            if ok:
                with open(wx_file, "w", encoding="utf-8") as f:
                    f.write(content)
                with open(wx_file_config, "w", encoding="utf-8") as f:
                    json.dump(image_lists, f, ensure_ascii=False, indent=4)
            else:
                ner_logger.info(f"获取微信文章失败: {wx_url} \n {wx_file}")
                return False, ""

        # 兼容旧逻辑：保留原始文件的一份拷贝
        if not os.path.exists(wx_file_0):
            shutil.copy(wx_file, wx_file_0)

        # 提取并清洗信息
        get_weixin_info(wx_file, data)
        clean_weixin_html(wx_file, wx_file_0)

        data["wx_code_file_config"] = wx_file_config
        return True, wx_file

    def pre_wx_article(self):
        """预处理手工整理的微信文章本地 HTML 文件并生成相应的 JSON 配置"""
        wx_path = self.get_wx_path()
        ner_logger.info(f"手工微信文章路径: {wx_path}")

        keydir = self.spider_sch.get_key_dir(DEFAULT_WX_SCHOOL)
        os.makedirs(keydir, exist_ok=True)

        # 遍历所有本地 HTML 文件
        for file_path in glob.glob(f"{wx_path}/**/*.html", recursive=True):
            file_err_file = file_path.replace(".html", ".html.err")
            filename = os.path.basename(file_path)

            title, link, wxdate = get_weixin_hand_url(file_path)
            file_json = f"detail_{getMD5Str(link)}.json"
            file_dest = os.path.join(keydir, file_json)

            # 如果存在 .err 标记，则跳过并清理
            if os.path.exists(file_err_file):
                ner_logger.info(f"不可处理的文件将被移除: {file_dest}")
                if os.path.exists(file_dest):
                    os.remove(file_dest)
                continue

            # 已处理过的跳过
            if os.path.exists(file_dest):
                continue

            data = {
                "announcement_name": title,
                "publish_time": wxdate,
                "link": link,
                "full_url": link,
                "last_url": "",
                "parent_url": "http://mp.weixin.qq.com",
                "upload": "",
                "contact": "无",
                "type_url": "wxwz",
                "channel": DEFAULT_WX_SCHOOL,
                "wx_name": "",
                "wx_title": title,
                "wx_public_time": wxdate,
                "wx_source_file": file_path,
            }

            with open(file_dest, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    def check_wx_file(self, data, hfile, model_file) -> bool:
        """检查微信文章是否过于复杂（图片过多/过小等），如果太复杂则拒绝处理"""
        count = 0
        props = data.get("props", {})
        img_urls = props.get("img_urls", {})
        wx_source_file = data.get("wx_source_file", hfile)

        ok_file = wx_source_file.replace(".html", ".html.ok")
        err_file = wx_source_file.replace(".html", ".html.err")

        # 根据图片属性评估复杂度
        for url, info in img_urls.items():
            img_ocr = info.get("img_ocr", "")
            img_width = info.get("img_width", 0)
            img_height = info.get("img_height", 0)
            img_count = info.get("img_count", 1)

            # 跳过全尺寸二维码
            if info.get("full_qr") == "Y":
                continue

            area = img_width * img_height
            if area < 10000 and len(img_ocr) < 5:
                count += 2 * img_count
            elif area < 250000 and len(img_ocr) < 5:
                count += 1 * img_count
            elif url.endswith(".gif"):
                count += 2 * img_count

        # 复杂度阈值判定
        if count > 10:
            ner_logger.info(
                f"微信文章图片过于复杂，处理失败: {wx_source_file} \n- {data}"
            )
            with open(err_file, "w", encoding="utf-8") as f:
                f.write("不好处理")
            return False

        with open(ok_file, "w", encoding="utf-8") as f:
            f.write(f"可以处理 {model_file}")

        return True

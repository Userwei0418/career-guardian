# -*- coding: utf-8 -*-
"""
============================================================
爬虫流水线每日校验脚本  check_pipeline.py
============================================================

【用途】
对照 tmp / ardata 两个目录，按指定日期校验整条流水线的健康度，
定位问题卡在哪一步：抓取 → 清洗 → 上传。

【目录约定（来自主项目）】
    {TMP_DIR}/{key}/index_*.html|.json          列表页抓取结果
    {TMP_DIR}/{key}/detail_*.html|.json         明细抓取结果
    {ARDATA_DIR}/{key}/detail_*.model.json      大模型清洗产出
    {ARDATA_DIR}/{key}/detail_*.model.json.{dist}.ok / .err   上传结果
    {ARDATA_DIR}/{key}/detail_*.json.expired    被标记无法处理

【stage 字段含义】
    done            ：tmp 齐全 + model.json + .ok，全流程成功
    expired         ：被标记过期 / 无法处理（通常不用管）
    crawl_broken    ：tmp 下 json 有但 html 缺失，抓取不完整
    model_missing   ：已抓取但没有 model.json，清洗环节卡住
    upload_err      ：有 .err 文件，上传接口返回失败
    upload_missing  ：清洗完成但没有 .ok / .err，上传没跑到

【基本用法】
    # 默认：校验今天 + dist=prod + 只看 com_*，输出到 OUTPUT_REPORT
    python check_pipeline.py

    # 校验指定日期（支持 YYYY-MM-DD 或 YYYYMMDD）
    python check_pipeline.py -d 2026-04-20
    python check_pipeline.py -d 20260420

    # 切换环境后缀（.prod.ok / .dev.ok）
    python check_pipeline.py -d 2026-04-20 --dist dev

    # 切换检查范围
    python check_pipeline.py --scope com   # 只看公司（默认）
    python check_pipeline.py --scope sch   # 只看学校
    python check_pipeline.py --scope all   # 公司+学校全看

    # 只看某一家（忽略 scope）
    python check_pipeline.py --key com_00512

    # 额外导出明细 CSV，方便 Excel 排查
    python check_pipeline.py -d 2026-04-20 --csv issue.csv

    # 临时换目录（不改脚本顶部常量）
    python check_pipeline.py --tmp E:\other\tmp --ardata E:\other\ardata

【输出】
    - 控制台实时打印报告
    - 同步写入 OUTPUT_REPORT 指定的 txt 文件

【配置修改】
    打开脚本顶部 "默认配置" 区块，改 4 个常量即可：
        TMP_DIR / ARDATA_DIR / OUTPUT_REPORT / DEFAULT_DIST / KEY_PREFIXES
============================================================
"""

import os
import sys
import json
import glob
import argparse
from datetime import datetime, date
from collections import defaultdict


# ======================= 默认配置（按需修改） =======================
TMP_DIR = r"E:\chu\clawler_data\data\tmp"
ARDATA_DIR = r"E:\chu\clawler_data\data\ardata"
OUTPUT_REPORT = r"E:\chu\qzclawler\check\sync_error_check_report.txt"
DEFAULT_DIST = "prod"

# 默认只检查这些前缀的 key；空 tuple 表示全部
KEY_PREFIXES = ("com_",)
# ===================================================================


# ---------- 工具函数 ----------

def parse_date(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError("无法解析日期: " + s)


def file_mdate(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).date()


def is_on_date(path, target):
    try:
        return file_mdate(path) == target
    except OSError:
        return False


def safe_read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------- 同时输出到控制台和文件 ----------

class Tee:
    def __init__(self, path):
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d)
        self.f = open(path, "w", encoding="utf-8")

    def write(self, s):
        sys.__stdout__.write(s)
        self.f.write(s)

    def flush(self):
        sys.__stdout__.flush()
        self.f.flush()

    def close(self):
        self.f.close()


# ---------- 核心校验 ----------

class PipelineChecker:
    def __init__(self, tmp_dir, ar_dir, target, dist="prod",
                 key_filter="", prefixes=()):
        self.tmp_dir = tmp_dir
        self.ar_dir = ar_dir
        self.target = target
        self.dist = dist
        self.key_filter = key_filter
        self.prefixes = tuple(prefixes) if prefixes else ()

        self.rows = []
        self.key_stats = defaultdict(lambda: {
            "index_today": 0,
            "detail_today": 0,
            "model_ok": 0,
            "model_missing": 0,
            "expired": 0,
            "upload_ok": 0,
            "upload_err": 0,
            "upload_missing": 0,
        })

    def iter_keys(self):
        if not os.path.isdir(self.tmp_dir):
            print("[ERR] tmp 目录不存在: " + self.tmp_dir)
            return
        for name in sorted(os.listdir(self.tmp_dir)):
            full = os.path.join(self.tmp_dir, name)
            if not os.path.isdir(full):
                continue
            # 指定了单 key 时，只要名字匹配即可，忽略前缀过滤
            if self.key_filter:
                if name != self.key_filter:
                    continue
            else:
                if self.prefixes and not name.startswith(self.prefixes):
                    continue
            yield name

    def run(self):
        for key in self.iter_keys():
            self._check_key(key)

    def _check_key(self, key):
        tmp_key = os.path.join(self.tmp_dir, key)
        ar_key = os.path.join(self.ar_dir, key)
        stat = self.key_stats[key]

        for html in glob.glob(os.path.join(tmp_key, "index_*.html")):
            if is_on_date(html, self.target):
                stat["index_today"] += 1

        for meta_file in glob.glob(os.path.join(tmp_key, "detail_*.json")):
            html_file = meta_file[:-5] + ".html"

            hit_today = is_on_date(meta_file, self.target) or (
                os.path.exists(html_file) and is_on_date(html_file, self.target)
            )
            if not hit_today:
                continue

            stat["detail_today"] += 1
            self._check_detail(key, meta_file, html_file, ar_key, stat)

    def _check_detail(self, key, meta_file, html_file, ar_key, stat):
        base = os.path.basename(meta_file)[:-5]
        model_file = os.path.join(ar_key, base + ".model.json")
        expired_file = os.path.join(ar_key, base + ".json.expired")
        ok_file = model_file + "." + self.dist + ".ok"
        err_file = model_file + "." + self.dist + ".err"

        meta = safe_read_json(meta_file) or {}
        title = meta.get("announcement_name", "")
        full_url = meta.get("full_url") or meta.get("last_url") or meta.get("link", "")

        # 文件是否存在 + 是否"当天"生成（按 mtime 判断）
        model_exists = os.path.exists(model_file)
        model_today = model_exists and is_on_date(model_file, self.target)

        expired_exists = os.path.exists(expired_file)
        expired_today = expired_exists and is_on_date(expired_file, self.target)

        ok_exists = os.path.exists(ok_file)
        ok_today = ok_exists and is_on_date(ok_file, self.target)

        err_exists = os.path.exists(err_file)
        err_today = err_exists and is_on_date(err_file, self.target)

        row = {
            "key": key,
            "file": base,
            "title": title,
            "url": full_url,
            "tmp_html": os.path.exists(html_file),
            "tmp_json": True,
            "model": model_exists,
            "model_today": model_today,
            "expired": expired_exists,
            "expired_today": expired_today,
            "upload_ok": ok_exists,
            "upload_ok_today": ok_today,
            "upload_err": err_exists,
            "upload_err_today": err_today,
            "stage": "",
            "note": "",
        }

        # ---------- 判定所处阶段（均以"当天"为准） ----------
        if expired_today:
            stat["expired"] += 1
            row["stage"] = "expired"
            row["note"] = "当天被标记为过期/无法处理"
        elif not row["tmp_html"]:
            row["stage"] = "crawl_broken"
            row["note"] = "json 有但 html 缺失，抓取不完整"
        elif not model_today:
            # 当天抓到了，但当天没有清洗出 model.json
            stat["model_missing"] += 1
            row["stage"] = "model_missing"
            if model_exists:
                row["note"] = "model.json 存在但不是当天生成（历史遗留）"
            else:
                row["note"] = "已抓取但未生成 model.json，清洗环节卡住"
        else:
            # 当天清洗成功
            stat["model_ok"] += 1
            if ok_today:
                stat["upload_ok"] += 1
                row["stage"] = "done"
            elif err_today:
                stat["upload_err"] += 1
                row["stage"] = "upload_err"
                row["note"] = "当天上传接口返回失败"
            else:
                stat["upload_missing"] += 1
                row["stage"] = "upload_missing"
                if ok_exists:
                    row["note"] = ".prod.ok 存在但不是当天生成（历史遗留）"
                elif err_exists:
                    row["note"] = ".prod.err 存在但不是当天生成"
                else:
                    row["note"] = "当天未生成 ." + self.dist + ".ok/.err 标记"

        self.rows.append(row)


    def print_report(self):
        print("=" * 80)
        print("校验日期: {}    dist: {}".format(self.target, self.dist))
        print("tmp   : " + self.tmp_dir)
        print("ardata: " + self.ar_dir)
        if self.key_filter:
            print("只检查 key: " + self.key_filter)
        elif self.prefixes:
            print("前缀过滤: " + ", ".join(self.prefixes))
        else:
            print("前缀过滤: <全部>")
        print("=" * 80)

        total = defaultdict(int)
        for s in self.key_stats.values():
            for k, v in s.items():
                total[k] += v

        print("")
        print("[总体]")
        print("  今天抓到列表页      : {}".format(total["index_today"]))
        print("  今天新抓明细        : {}".format(total["detail_today"]))
        print("  清洗成功(model.json): {}".format(total["model_ok"]))
        print("  清洗缺失            : {}".format(total["model_missing"]))
        print("  标记过期            : {}".format(total["expired"]))
        print("  上传成功            : {}".format(total["upload_ok"]))
        print("  上传失败(.err)      : {}".format(total["upload_err"]))
        print("  上传缺失            : {}".format(total["upload_missing"]))

        print("")
        print("[按 key 明细]  (只显示今天有活动或有异常的)")
        header = "{:<14} {:>4} {:>4} {:>4} {:>5} {:>4} {:>5} {:>5} {:>5}".format(
            "key", "idx", "det", "ok", "missM", "exp", "upOK", "upErr", "upMis"
        )
        print(header)
        print("-" * len(header))
        for key in sorted(self.key_stats.keys()):
            s = self.key_stats[key]
            if sum(s.values()) == 0:
                continue
            print("{:<14} {:>4} {:>4} {:>4} {:>5} {:>4} {:>5} {:>5} {:>5}".format(
                key,
                s["index_today"], s["detail_today"],
                s["model_ok"], s["model_missing"], s["expired"],
                s["upload_ok"], s["upload_err"], s["upload_missing"]
            ))

        problems = [r for r in self.rows if r["stage"] not in ("done", "expired")]
        if problems:
            print("")
            print("[问题清单]  共 {} 条".format(len(problems)))
            for r in problems:
                title_short = (r["title"] or "")[:30]
                print("  [{:<16}] {}/{}  {}  -> {}".format(
                    r["stage"], r["key"], r["file"], title_short, r["note"]
                ))

        silent_keys = [k for k in self.iter_keys()
                       if self.key_stats[k]["detail_today"] == 0
                       and self.key_stats[k]["index_today"] == 0]
        if silent_keys:
            print("")
            print("[今天零活动的 key]  共 {} 个（可能抓取失败）".format(len(silent_keys)))
            for k in silent_keys:
                last = self._last_activity(k)
                print("  {}   最近活动: {}".format(k, last or "无任何文件"))

    def _last_activity(self, key):
        tmp_key = os.path.join(self.tmp_dir, key)
        latest = 0
        for p in glob.glob(os.path.join(tmp_key, "*")):
            try:
                latest = max(latest, os.path.getmtime(p))
            except OSError:
                pass
        if latest == 0:
            return None
        return datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M:%S")

    def export_csv(self, path):
        import csv
        fields = ["key", "file", "stage", "note", "title", "url",
                  "tmp_html", "tmp_json",
                  "model", "model_today",
                  "expired", "expired_today",
                  "upload_ok", "upload_ok_today",
                  "upload_err", "upload_err_today"]
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in self.rows:
                w.writerow({k: r.get(k, "") for k in fields})
        print("")
        print("已导出 CSV: " + path)



# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="爬虫流水线按日期校验")
    ap.add_argument("-d", "--date", default="",
                    help="校验日期, 格式 YYYY-MM-DD 或 YYYYMMDD，默认今天")
    ap.add_argument("--tmp", default=TMP_DIR, help="tmp 目录，默认 " + TMP_DIR)
    ap.add_argument("--ardata", default=ARDATA_DIR, help="ardata 目录，默认 " + ARDATA_DIR)
    ap.add_argument("--report", default=OUTPUT_REPORT,
                    help="报告输出 txt 路径，默认 " + OUTPUT_REPORT)
    ap.add_argument("--dist", default=DEFAULT_DIST, choices=["prod", "dev"],
                    help="上传环境后缀，对应 .prod.ok / .dev.ok")
    ap.add_argument("--key", default="", help="只检查指定 key，例如 com_00498")
    ap.add_argument("--scope", default="com", choices=["com", "sch", "all"],
                    help="检查范围：com 只查公司(默认) / sch 只查学校 / all 全部")
    ap.add_argument("--csv", default="", help="把明细清单额外导出到 CSV")
    args = ap.parse_args()

    target = parse_date(args.date) if args.date else date.today()

    if args.scope == "com":
        prefixes = ("com_",)
    elif args.scope == "sch":
        prefixes = ("sch_",)
    else:
        prefixes = ()

    tee = Tee(args.report)
    sys.stdout = tee
    try:
        checker = PipelineChecker(
            args.tmp, args.ardata, target,
            args.dist, args.key, prefixes
        )
        checker.run()
        checker.print_report()
        if args.csv:
            checker.export_csv(args.csv)
    finally:
        sys.stdout = sys.__stdout__
        tee.close()
    print("报告已写入: " + args.report)


if __name__ == "__main__":
    main()

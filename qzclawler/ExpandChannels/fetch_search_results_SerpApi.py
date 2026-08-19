import os
import re
import json
import time
import configparser
from urllib.parse import urlparse, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- 配置区 ----------------
SERPAPI_KEY = "e5b1c45598605deda27209c4e41dc4659f6417adf2230552fdee2ccb0b2d206e"
DATA_DIR = r"D:\code\python\chu\qzclawler\data"

ENGINE = "baidu"
RN = 50
MAX_PAGES = 10
REQUEST_TIMEOUT = 60
SLEEP_SECONDS = 1.2

# 自动代理：先直连，失败再走代理（不需要你手工判断）
AUTO_PROXY_FALLBACK = True
PROXIES = {
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897"
}

TARGETS = {
    # "zhiye": [
    #     "site:zhiye.com inurl:jobs",
    #     "site:zhiye.com inurl:campus",
    #     "site:zhiye.com 校园招聘",
    #     "site:zhiye.com 社会招聘",
    #     "site:zhiye.com 招聘",
    # ],
    # "hotjob": [
    #     "site:hotjob.cn inurl:jobs",
    #     "site:hotjob.cn 招聘",
    #     "site:hotjob.cn 校园招聘",
    #     "site:hotjob.cn 社会招聘",
    # ],
    # "moka": [
    #     "site:app.mokahr.com/apply",
    #     "site:app.mokahr.com/campus_apply",
    #     "site:app.mokahr.com inurl:m",
    #     "site:app.mokahr.com 加入我们",
    #     "site:app.mokahr.com 招聘",
    # ],
    "jobs.feishu": [
        "site:jobs.feishu.cn/apply",
        "site:jobs.feishu.cn/campus_apply",
        "site:jobs.feishu.cn inurl:m",
        "site:jobs.feishu.cn 加入我们",
        "site:jobs.feishu.cn 招聘",
    ]
}
# ----------------------------------------

# ========= 提取规则 =========
RE_ZHIYE = re.compile(r"([a-z0-9][a-z0-9\-_.]*)\.zhiye\.com", re.I)
RE_HOTJOB = re.compile(r"([a-z0-9][a-z0-9\-_.]*)\.hotjob\.cn", re.I)

RE_MOKA_PATH = re.compile(r"app\.mokahr\.com/(?:apply|campus_apply|m|su)/([a-z0-9\-_]+)", re.I)
RE_MOKA_QS = re.compile(r"(?:companyid|orgid)=([a-z0-9\-_]+)", re.I)  # 兼容 companyId=xxx

# 新增：飞书提取规则（提取类似 lilithgames.jobs.feishu.cn 中的 lilithgames 作为唯一标识）
RE_FEISHU = re.compile(r"([a-z0-9][a-z0-9\-_.]*)\.jobs\.feishu\.cn", re.I)


def create_session_with_retry():
    s = requests.Session()
    s.trust_env = True  # 允许使用系统环境变量代理（可选）
    retry = Retry(
        total=3, connect=3, read=3,
        backoff_factor=1.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def serpapi_get(session: requests.Session, url: str, params: dict):
    """
    先直连 serpapi.com；若失败且 AUTO_PROXY_FALLBACK=True，则自动用 PROXIES 再试一次。
    """
    try:
        return session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except Exception as e1:
        if not AUTO_PROXY_FALLBACK:
            raise
        # 代理兜底
        try:
            return session.get(url, params=params, timeout=REQUEST_TIMEOUT, proxies=PROXIES)
        except Exception as e2:
            # 抛出更完整信息，便于定位
            raise RuntimeError(f"Direct failed: {repr(e1)} ; Proxy failed: {repr(e2)}")


def normalize_text(s: str) -> str:
    if not s:
        return ""
    # 处理常见转义与编码
    s = s.replace("\\/", "/")
    s = unquote(s)
    return s


def iter_strings(obj):
    """递归提取所有字符串字段，避免 str(dict) 漏信息"""
    if obj is None:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, (list, tuple, set)):
        for it in obj:
            yield from iter_strings(it)


def extract_ids_from_text(system_name: str, text: str) -> set[str]:
    if not text:
        return set()
    t = normalize_text(text).lower()

    if system_name == "zhiye":
        return set(x for x in RE_ZHIYE.findall(t) if x != "www")
    if system_name == "hotjob":
        return set(x for x in RE_HOTJOB.findall(t) if x != "www")
    if system_name == "moka":
        out = set(RE_MOKA_PATH.findall(t))
        out.update(RE_MOKA_QS.findall(t))
        return out
    if system_name == "jobs.feishu":
        return set(x for x in RE_FEISHU.findall(t) if x != "www")
    return set()


def make_company_key(company_info: dict, fallback_uid: str) -> str:
    """
    你说“只想别重复统计别漏掉、用于判重”：
    - 最稳的唯一标识：系统自己的客户标识（subdomain/company_id）
    - 但很多记录提取不到，只能用退化指纹去尽量合并重复
    这里采用：pre_open_url host + com_name 作为优先指纹；都没有再用 fallback_uid 保证不漏
    """
    com_name = (company_info.get("com_name") or "").strip().lower()

    pre_open = (company_info.get("pre_open_url") or "").strip()
    json_domain = (company_info.get("json_domain") or "").strip()

    host = ""
    for u in (pre_open, json_domain):
        if not u:
            continue
        u2 = u if u.startswith("http") else "http://" + u
        try:
            host = (urlparse(u2).netloc or "").lower()
        except Exception:
            continue
        if host:
            break

    if host and com_name:
        return f"{host}::{com_name}"
    if host:
        return host
    if com_name:
        return com_name
    return fallback_uid  # 保证不漏


def load_existing_from_ini():
    """
    输出两套集合：
    - companies: 去重后的“使用该系统的公司”集合（用于你说的：别重复统计别漏掉）
    - dedup_ids: 可与搜索结果直接对比的“系统客户标识集合”（用于判重）
    同时导出 unresolved：命中系统但提取不到 dedup_id 的记录，便于补规则
    """
    existing = {
        "zhiye": {"companies": set(), "dedup_ids": set(), "unresolved": []},
        "hotjob": {"companies": set(), "dedup_ids": set(), "unresolved": []},
        "moka": {"companies": set(), "dedup_ids": set(), "unresolved": []},
        "jobs.feishu": {"companies": set(), "dedup_ids": set(), "unresolved": []}, # 新增飞书数据槽
    }

    if not os.path.exists(DATA_DIR):
        print(f"⚠️ 未找到数据目录: {DATA_DIR}")
        return existing

    ini_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".ini")]
    print(f"📂 正在扫描已有数据，共 {len(ini_files)} 个配置文件...")

    for file_name in ini_files:
        file_path = os.path.join(DATA_DIR, file_name)
        config = configparser.ConfigParser(interpolation=None)

        try:
            try:
                config.read(file_path, encoding="utf-8")
            except:
                config.read(file_path, encoding="gbk")

            if "Company" not in config.sections():
                continue

            for key in config["Company"]:
                uid = f"{file_name}::{key}"
                raw_json = config["Company"][key]

                try:
                    company_data_list = json.loads(raw_json)
                    if not company_data_list:
                        continue
                    company_info = company_data_list[0]

                    # 收集所有字符串字段
                    texts = []
                    texts.append(company_info.get("pre_open_url", "") or "")
                    texts.append(company_info.get("json_domain", "") or "")
                    texts.append(company_info.get("com_webname", "") or "")
                    urls_dict = company_info.get("urls", {})
                    texts.extend(list(iter_strings(urls_dict)))
                    blob = " ".join(normalize_text(x) for x in texts if x)

                    blob_l = blob.lower()

                    # company 去重 key（尽量去重，但保证不漏）
                    company_key = make_company_key(company_info, uid)

                    # 命中系统：加入 companies；并尝试提取 dedup_ids
                    if "zhiye.com" in blob_l:
                        existing["zhiye"]["companies"].add(company_key)
                        ids = extract_ids_from_text("zhiye", blob)
                        if ids:
                            existing["zhiye"]["dedup_ids"].update(ids)
                        else:
                            existing["zhiye"]["unresolved"].append((uid, company_info.get("com_name", ""), company_info.get("pre_open_url", ""), company_info.get("json_domain", "")))

                    if "hotjob.cn" in blob_l:
                        existing["hotjob"]["companies"].add(company_key)
                        ids = extract_ids_from_text("hotjob", blob)
                        if ids:
                            existing["hotjob"]["dedup_ids"].update(ids)
                        else:
                            existing["hotjob"]["unresolved"].append((uid, company_info.get("com_name", ""), company_info.get("pre_open_url", ""), company_info.get("json_domain", "")))

                    if "app.mokahr.com" in blob_l or "mokahr.com" in blob_l:
                        # 命中 moka 以 app.mokahr.com 为主；提取 id 允许从 mokahr.com 扩展
                        if "app.mokahr.com" in blob_l:
                            existing["moka"]["companies"].add(company_key)
                        ids = extract_ids_from_text("moka", blob)
                        if ids:
                            existing["moka"]["dedup_ids"].update(ids)
                        else:
                            # 只要命中了 app.mokahr.com 但没有id，就记录 unresolved
                            if "app.mokahr.com" in blob_l:
                                existing["moka"]["unresolved"].append((uid, company_info.get("com_name", ""), company_info.get("pre_open_url", ""), company_info.get("json_domain", "")))

                    # 新增飞书命中提取逻辑
                    if "jobs.feishu.cn" in blob_l:
                        existing["jobs.feishu"]["companies"].add(company_key)
                        ids = extract_ids_from_text("jobs.feishu", blob)
                        if ids:
                            existing["jobs.feishu"]["dedup_ids"].update(ids)
                        else:
                            existing["jobs.feishu"]["unresolved"].append((uid, company_info.get("com_name", ""), company_info.get("pre_open_url", ""), company_info.get("json_domain", "")))


                except Exception:
                    continue

        except Exception:
            continue

    # unresolved 导出（方便你补规则）
    for sys in ["zhiye", "hotjob", "moka", "jobs.feishu"]:
        out = f"{sys}_unresolved.tsv"
        with open(out, "w", encoding="utf-8") as f:
            f.write("uid\tcom_name\tpre_open_url\tjson_domain\n")
            for row in existing[sys]["unresolved"]:
                f.write("\t".join(str(x).replace("\t", " ") for x in row) + "\n")

    print("✅ 扫描完成！\n")
    print("📊 ini侧“去重后公司数”(companies) + “可对比判重ID数”(dedup_ids):")
    for sys in ["zhiye", "hotjob", "moka", "jobs.feishu"]:
        print(f"   {sys.upper():12} companies={len(existing[sys]['companies']):4} | dedup_ids={len(existing[sys]['dedup_ids']):4} | unresolved导出={sys}_unresolved.tsv")
    print()
    return existing


def extract_ids_from_serp_item(system_name, item: dict) -> set[str]:
    displayed_link = item.get("displayed_link", "") or ""
    link = item.get("link", "") or ""
    title = item.get("title", "") or ""
    snippet = item.get("snippet", "") or ""
    text = f"{displayed_link} {link} {title} {snippet}"
    return extract_ids_from_text(system_name, text)


def fetch_new_ids_serpapi(system_name, queries, existing_dedup_ids: set[str]):
    session = create_session_with_retry()
    url = "https://serpapi.com/search.json"
    new_ids = set()

    print(f"{'='*70}")
    print(f"【{system_name.upper()}】SerpApi({ENGINE}) 增量挖掘开始")
    print(f"{'='*70}")

    for query in queries:
        print(f"\n[+] 查询词: {query}")

        consecutive_errors = 0

        for page in range(MAX_PAGES):
            pn = page * RN
            params = {"engine": ENGINE, "q": query, "api_key": SERPAPI_KEY, "rn": RN, "pn": pn}

            try:
                resp = serpapi_get(session, url, params)

                if resp.status_code != 200:
                    consecutive_errors += 1
                    print(f"   [!] HTTP {resp.status_code}（连续错误 {consecutive_errors}）")
                    if consecutive_errors >= 3:
                        break
                    time.sleep(2)
                    continue

                data = resp.json()
                if "error" in data:
                    msg = data["error"]
                    if "No results" in msg or "hasn't returned any results" in msg:
                        print("   [-] 无更多结果/无结果")
                        break
                    consecutive_errors += 1
                    print(f"   [!] API错误: {msg}")
                    if consecutive_errors >= 3:
                        break
                    time.sleep(2)
                    continue

                organic = data.get("organic_results", [])
                if not organic:
                    print("   [-] 本页无 organic_results")
                    break

                consecutive_errors = 0

                add_new = 0
                hit_existing = 0
                for item in organic:
                    ids = extract_ids_from_serp_item(system_name, item)
                    for cid in ids:
                        if cid in existing_dedup_ids:
                            hit_existing += 1
                        elif cid not in new_ids:
                            new_ids.add(cid)
                            add_new += 1

                print(f"   第{page+1}页(pn={pn}): 新增{add_new} | 命中已有{hit_existing} | 累计增量{len(new_ids)}")
                time.sleep(SLEEP_SECONDS)

            except Exception as e:
                consecutive_errors += 1
                print(f"   [!] 请求异常(完整): {repr(e)}")
                if consecutive_errors >= 3:
                    print("   [!] 连续异常过多，跳过该查询词")
                    break
                time.sleep(2)

    return new_ids


def save_new_ids(system_name, new_ids):
    out = f"{system_name}_new_clients.txt"
    with open(out, "w", encoding="utf-8") as f:
        for cid in sorted(new_ids):
            f.write(cid + "\n")
    print(f"\n📄 {system_name} 增量ID保存: {out} ({len(new_ids)}条)")


def main():
    print("=" * 70)
    print("🚀 招聘系统客户增量挖掘工具（ini去重公司数 + SerpApi增量判重）")
    print("=" * 70)
    print()

    existing = load_existing_from_ini()

    for sys, queries in TARGETS.items():
        new_ids = fetch_new_ids_serpapi(sys, queries, existing[sys]["dedup_ids"])
        save_new_ids(sys, new_ids)

    print("\n完成。若 SerpApi 仍持续连不上：请确认你的代理端口是否正确（7897/7890）。")


if __name__ == "__main__":
    main()
# 当 requests 不够用时 —— 进入动态网页与浏览器自动化
前面我们的爬虫跑得很顺,因为目标站点是"服务端渲染"——HTML 直接把数据吐给你。

但**真实的招聘网站几乎没有这么友好**。

猎聘、BOSS 直聘、前程无忧、鱼泡——用 `requests.get()` 打开它们,拿回来的 HTML 里**几乎是空的**,只有一堆 `<div id="app"></div>` 和一坨 JS 代码。

这一讲就要回答一个核心问题:**为什么** `**requests**` **抓不到数据?当它失效时,我们该怎么办?​**

学完这一讲,会真正理解:**项目里为什么要上 Playwright、为什么要监听** `**page.on("response")**`**、为什么要加代理和反自动化伪装**——这些不是炫技,而是**被网站一步步逼出来的**。

## **一、先看一个失败案例:用** `**requests**` **抓动态网站**

我们换一个目标站点:[https://quotes.toscrape.com/js/](https://quotes.toscrape.com/js/)。这是 ToScrape 专门做的"JS 渲染版",和上一讲那个静态版长得一模一样,但**数据是 JS 动态生成的**。

![](1_当%20requests%20不够用时%20——%20进入动态网页与.png)

```python
import requests
from bs4 import BeautifulSoup

resp = requests.get("https://quotes.toscrape.com/js/", headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(resp.text, "lxml")

quotes = soup.select("div.quote")
print(f"找到 {len(quotes)} 条数据")
print("--- HTML 原文 ---")
print(resp.text)
```

运行结果大吃一惊:​

找到 0 条数据

![](2_当%20requests%20不够用时%20——%20进入动态网页与.png)

但用浏览器打开同一个网址,能清清楚楚看到 10 条名言。差别在哪?

## **二、关键原理:浏览器和** `**requests**` **看到的不是同一个东西**

这是初学者最容易卡住的地方,必须把它讲透。

**​**`**requests**` **拿到的:​** 服务器**最初**返回的 HTML —— 就像菜谱 **浏览器最终显示的:​** JS 执行完毕后的 HTML —— 就像做好的菜

![](当%20requests%20不够用时%20——%20进入动态网页与.png)

**所以** `**requests**` **抓不到数据,不是它"没本事",而是它根本不执行 JS**。它只是"下载 HTML 的工具",**不是浏览器**。

那要怎么办?有两条路。

## **三、思路 A:不用浏览器,自己找接口**

既然 JS 会去请求 API 拿数据,那我们**直接找到那个 API,自己请求它**,不就拿到 JSON 了吗?

打开 `F12` → Network → 刷新页面 → 找到那个返回数据的请求。在某些网站上,这招能用,而且效率最高。**项目里"API 直连通道"(**`**auto_api/**`**)就是这么干的**——百度、京东这些大厂的招聘 API 接口稳定、参数简单、能直接 `requests.get` 拿 JSON。

但这条路在大多数招聘网站上**走不通**,因为:

1.  **接口参数有签名/加密**:猎聘的搜索接口带着一堆 token,自己构造极难
2.  **接口需要登录态**:没登录直接 401
3.  **接口随时改**:今天调通了,明天网站升级你又得重做
4.  **接口返回的数据被前端二次加工**:你拿到的 JSON 不是页面显示的最终版

所以,对绝大多数招聘网站,我们走第二条路。

## **四、思路 B:启动一个真浏览器 —— Playwright 登场**

既然 `requests` 不执行 JS,那我**直接开一个真浏览器,让它替我加载完页面,我再读最终的 HTML** 不就行了?

这就是 **Playwright** 干的事。它本质上是"用代码遥控一个 Chrome"。

### 4.1 安装

```python
pip install playwright
playwright install chromium    # 下载浏览器内核(只用做一次)

```

### 4.2 用 Playwright 抓那个失败的 JS 页面

```python
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)   # False 让你能看到浏览器窗口
    page = browser.new_page()
    page.goto("https://quotes.toscrape.com/js/")
    page.wait_for_load_state("networkidle")        # 等所有网络请求完成
    
    html = page.content()                           # 拿到 JS 执行后的最终 HTML
    soup = BeautifulSoup(html, "lxml")
    quotes = soup.select("div.quote")
    print(f"Playwright 抓到 {len(quotes)} 条")
    
    browser.close()

```

![](3_当%20requests%20不够用时%20——%20进入动态网页与.png)

成功!会看到一个真的 Chrome 窗口弹出,自动打开网页,等几秒,然后关闭。

**为什么这次成功了?​** 因为 Playwright **是个真浏览器**,它会执行 JS、发起 API 请求、把数据渲染到 DOM 里。我们读的是"成品菜",不是"菜谱"。

### **4.3 Playwright 的核心 API**

```python
page.goto(url)                          # 打开网页
page.wait_for_load_state("networkidle")  # 等到网络空闲(数据加载完了)
page.wait_for_selector("div.quote")     # 等某个元素出现(更精确)
page.click("button.next")               # 点击
page.fill("input.search", "Python")     # 输入
page.select_option("select.city", "北京") # 下拉选择
page.mouse.wheel(0, 3000)               # 滚动 3000 像素
page.content()                          # 拿到当前 HTML
page.query_selector("h1").inner_text()  # 直接读元素文本

```

## **五、用 Playwright 升级我们的职位爬虫**

把前面那个静态爬虫,改成 Playwright 版,顺便加上"翻页"和"等待数据加载":

```python
"""
生产级别的 Playwright 爬虫模板
功能：支持动态渲染页面、翻页、等待数据加载、去重、断点续跑、异常处理、节奏控制
"""
import os
import json
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

# ==================== 配置区 ====================
# 数据保存目录
DATA_DIR = "data/jobs"
# 进度记录文件路径
PROGRESS_FILE = "data/progress.txt"
# 列表页URL（如果有分页，可以改成带页码的格式）
LIST_URL = "https://realpython.github.io/fake-jobs/"
# 浏览器配置
HEADLESS = False  # True为无头模式（不显示浏览器窗口）
TIMEOUT = 30000  # 超时时间（毫秒）


# ==================== 解析函数 ====================
def parse_list_page(html):
    """
    解析列表页，提取职位基本信息

    Args:
        html (str): 列表页HTML内容

    Returns:
        list: 职位信息字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for card in soup.select("div.card-content"):
        # 查找"Apply"按钮获取正确的详情页链接
        apply_link = card.find("a", string="Apply")
        link = apply_link["href"] if apply_link else None

        jobs.append({
            "title": card.select_one("h2.title").get_text(strip=True),
            "company": card.select_one("h3.company").get_text(strip=True),
            "location": card.select_one("p.location").get_text(strip=True),
            "link": link,
        })
    return jobs


def parse_detail_page(html):
    """
    解析详情页，提取职位描述

    Args:
        html (str): 详情页HTML内容

    Returns:
        str: 职位描述文本
    """
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one("div.content")
    return node.get_text(strip=True) if node else ""


# ==================== 数据存储函数 ====================
def save(job):
    """
    将职位数据保存为JSON文件

    Args:
        job (dict): 职位信息字典

    Returns:
        str: 保存的文件路径
    """
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    path = f"{DATA_DIR}/{job_id}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return path


def already_spider(job):
    """
    检查职位是否已经爬取过

    Args:
        job (dict): 职位信息字典

    Returns:
        bool: True表示已爬取
    """
    if not job["link"]:
        return False
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    return os.path.exists(f"{DATA_DIR}/{job_id}.json")


# ==================== 进度管理函数 ====================
def load_progress():
    """
    加载爬取进度

    Returns:
        int: 已处理的职位索引
    """
    if os.path.exists(PROGRESS_FILE):
        try:
            return int(open(PROGRESS_FILE).read())
        except:
            return 0
    return 0


def save_progress(idx):
    """
    保存爬取进度

    Args:
        idx (int): 当前处理到的索引
    """
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(idx))


# ==================== 主程序入口 ====================
if __name__ == "__main__":
    # 创建数据保存目录
    os.makedirs(DATA_DIR, exist_ok=True)

    all_jobs = []  # 存储所有职位

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            # ---- 第1步：抓取列表页（支持翻页）----
            current_page = 1
            max_pages = 3  # 最大翻页数，根据需要调整

            while current_page <= max_pages:
                print(f"\n===== 正在抓取第 {current_page} 页 =====")

                # 如果是第一页，直接访问；否则点击下一页按钮
                if current_page == 1:
                    page.goto(LIST_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
                else:
                    # 尝试点击下一页按钮（根据实际网站结构调整选择器）
                    next_btn = page.query_selector("a.next-page, button.next, .pagination a:last-child")
                    if not next_btn:
                        print("没有更多页面了")
                        break

                    next_btn.click()
                    # 等待新页面加载完成
                    page.wait_for_load_state("networkidle", timeout=TIMEOUT)

                # 等待职位卡片加载完成
                try:
                    page.wait_for_selector("div.card-content", timeout=TIMEOUT)
                except PlaywrightTimeout:
                    print(f"第 {current_page} 页加载超时")
                    break

                # 额外等待，确保动态内容完全加载
                page.wait_for_timeout(1000)

                # 解析当前页的职位列表
                jobs = parse_list_page(page.content())
                print(f"第 {current_page} 页抓到 {len(jobs)} 条")

                if not jobs:
                    print("没有更多数据了")
                    break

                all_jobs.extend(jobs)
                current_page += 1

                # 翻页间隔
                time.sleep(random.uniform(1, 2))

            print(f"\n列表页总共抓到 {len(all_jobs)} 条职位")

            # ---- 第2步：加载进度，实现断点续跑 ----
            start = load_progress()
            print(f"从第 {start} 条开始抓取详情")

            # ---- 第3步：逐个抓取详情页 ----
            for idx, job in enumerate(all_jobs):
                # 跳过已处理的职位（断点续跑）
                if idx < start:
                    continue

                # 跳过无效链接或已爬取的职位
                if not job["link"]:
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过: 无链接 - {job['title']}")
                    save_progress(idx + 1)
                    continue

                if already_spider(job):
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过已抓: {job['title']}")
                    save_progress(idx + 1)
                    continue

                try:
                    print(f"[{idx + 1}/{len(all_jobs)}] 正在抓取: {job['title']}")

                    # 打开详情页
                    page.goto(job["link"], timeout=TIMEOUT, wait_until="domcontentloaded")

                    # 等待详情内容加载
                    page.wait_for_selector("div.content", timeout=TIMEOUT)

                    # 额外等待，确保动态内容完全加载
                    page.wait_for_timeout(500)

                    # 解析详情内容
                    job["description"] = parse_detail_page(page.content())

                    # 保存数据
                    saved_to = save(job)
                    print(f"  已保存: {saved_to}")

                except Exception as e:
                    print(f"  抓取失败: {e}")

                # 更新进度
                save_progress(idx + 1)

                # 随机休眠，控制请求频率
                time.sleep(random.uniform(1, 2))

            print("\n全部完成！")

        except Exception as e:
            print(f"发生错误: {e}")

        finally:
            # 关闭浏览器
            browser.close()

```

**和前面的** `**requests**` **版相比,变化只有两处:​**

1.  用 `page.goto() + page.content()` 替代 `requests.get().text`
2.  加了 `wait_for_selector` 等数据加载

**其他逻辑(解析、落盘、去重、节奏控制)和第 4 讲一模一样**——这就是所谓的"积木思想":换了发请求的方式,其他积木都能继续用。

## **六、性能优化:屏蔽图片和字体**

Playwright 默认会下载所有资源——图片、字体、视频、广告——这些**对抓数据毫无用处,只会拖慢速度、烧代理流量**。我们直接屏蔽掉:

```python
def block_resources(route):
    if route.request.resource_type in ("image", "font", "media"):
        route.abort()       # 取消这个请求
    else:
        route.continue_()   # 其他正常放行

context.route("**/*", block_resources)
```

```python
"""
生产级别的 Playwright 爬虫模板
功能：支持动态渲染页面、翻页、等待数据加载、去重、断点续跑、异常处理、节奏控制、资源屏蔽优化
"""
import os
import json
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

# ==================== 配置区 ====================
# 数据保存目录
DATA_DIR = "data/jobs"
# 进度记录文件路径
PROGRESS_FILE = "data/progress.txt"
# 列表页URL（如果有分页，可以改成带页码的格式）
LIST_URL = "https://realpython.github.io/fake-jobs/"
# 浏览器配置
HEADLESS = False  # True为无头模式（不显示浏览器窗口）
TIMEOUT = 30000  # 超时时间（毫秒）


# ==================== 解析函数 ====================
def parse_list_page(html):
    """
    解析列表页，提取职位基本信息

    Args:
        html (str): 列表页HTML内容

    Returns:
        list: 职位信息字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for card in soup.select("div.card-content"):
        # 查找"Apply"按钮获取正确的详情页链接
        apply_link = card.find("a", string="Apply")
        link = apply_link["href"] if apply_link else None

        jobs.append({
            "title": card.select_one("h2.title").get_text(strip=True),
            "company": card.select_one("h3.company").get_text(strip=True),
            "location": card.select_one("p.location").get_text(strip=True),
            "link": link,
        })
    return jobs


def parse_detail_page(html):
    """
    解析详情页，提取职位描述

    Args:
        html (str): 详情页HTML内容

    Returns:
        str: 职位描述文本
    """
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one("div.content")
    return node.get_text(strip=True) if node else ""


# ==================== 数据存储函数 ====================
def save(job):
    """
    将职位数据保存为JSON文件

    Args:
        job (dict): 职位信息字典

    Returns:
        str: 保存的文件路径
    """
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    path = f"{DATA_DIR}/{job_id}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return path


def already_spider(job):
    """
    检查职位是否已经爬取过

    Args:
        job (dict): 职位信息字典

    Returns:
        bool: True表示已爬取
    """
    if not job["link"]:
        return False
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    return os.path.exists(f"{DATA_DIR}/{job_id}.json")


# ==================== 进度管理函数 ====================
def load_progress():
    """
    加载爬取进度

    Returns:
        int: 已处理的职位索引
    """
    if os.path.exists(PROGRESS_FILE):
        try:
            return int(open(PROGRESS_FILE).read())
        except:
            return 0
    return 0


def save_progress(idx):
    """
    保存爬取进度

    Args:
        idx (int): 当前处理到的索引
    """
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(idx))


# ==================== 主程序入口 ====================
if __name__ == "__main__":
    # 创建数据保存目录
    os.makedirs(DATA_DIR, exist_ok=True)

    all_jobs = []  # 存储所有职位

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800},
        )

        # 性能优化：屏蔽图片、字体、视频等无关资源
        def block_resources(route):
            """
            拦截并屏蔽不必要的资源请求，提升爬取速度

            屏蔽的资源类型：
            - image: 图片（jpg, png, gif, webp等）
            - font: 字体文件（woff, ttf等）
            - media: 音视频文件
            - stylesheet: CSS样式表（可选，如果不需要渲染样式）
            """
            if route.request.resource_type in ("image", "font", "media"):
                route.abort()       # 取消这个请求，节省带宽和时间
            else:
                route.continue_()   # 其他资源正常放行（HTML、JS、XHR等）

        # 应用路由拦截规则，**/* 匹配所有请求
        context.route("**/*", block_resources)

        page = context.new_page()

        try:
            # ---- 第1步：抓取列表页（支持翻页）----
            current_page = 1
            max_pages = 3  # 最大翻页数，根据需要调整

            while current_page <= max_pages:
                print(f"\n===== 正在抓取第 {current_page} 页 =====")

                # 如果是第一页，直接访问；否则点击下一页按钮
                if current_page == 1:
                    page.goto(LIST_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
                else:
                    # 尝试点击下一页按钮（根据实际网站结构调整选择器）
                    next_btn = page.query_selector("a.next-page, button.next, .pagination a:last-child")
                    if not next_btn:
                        print("没有更多页面了")
                        break

                    next_btn.click()
                    # 等待新页面加载完成
                    page.wait_for_load_state("networkidle", timeout=TIMEOUT)

                # 等待职位卡片加载完成
                try:
                    page.wait_for_selector("div.card-content", timeout=TIMEOUT)
                except PlaywrightTimeout:
                    print(f"第 {current_page} 页加载超时")
                    break

                # 额外等待，确保动态内容完全加载
                page.wait_for_timeout(1000)

                # 解析当前页的职位列表
                jobs = parse_list_page(page.content())
                print(f"第 {current_page} 页抓到 {len(jobs)} 条")

                if not jobs:
                    print("没有更多数据了")
                    break

                all_jobs.extend(jobs)
                current_page += 1

                # 翻页间隔
                time.sleep(random.uniform(1, 2))

            print(f"\n列表页总共抓到 {len(all_jobs)} 条职位")

            # ---- 第2步：加载进度，实现断点续跑 ----
            start = load_progress()
            print(f"从第 {start} 条开始抓取详情")

            # ---- 第3步：逐个抓取详情页 ----
            for idx, job in enumerate(all_jobs):
                # 跳过已处理的职位（断点续跑）
                if idx < start:
                    continue

                # 跳过无效链接或已爬取的职位
                if not job["link"]:
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过: 无链接 - {job['title']}")
                    save_progress(idx + 1)
                    continue

                if already_spider(job):
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过已抓: {job['title']}")
                    save_progress(idx + 1)
                    continue

                try:
                    print(f"[{idx + 1}/{len(all_jobs)}] 正在抓取: {job['title']}")

                    # 打开详情页
                    page.goto(job["link"], timeout=TIMEOUT, wait_until="domcontentloaded")

                    # 等待详情内容加载
                    page.wait_for_selector("div.content", timeout=TIMEOUT)

                    # 额外等待，确保动态内容完全加载
                    page.wait_for_timeout(500)

                    # 解析详情内容
                    job["description"] = parse_detail_page(page.content())

                    # 保存数据
                    saved_to = save(job)
                    print(f"  已保存: {saved_to}")

                except Exception as e:
                    print(f"  抓取失败: {e}")

                # 更新进度
                save_progress(idx + 1)

                # 随机休眠，控制请求频率
                time.sleep(random.uniform(1, 2))

            print("\n全部完成！")

        except Exception as e:
            print(f"发生错误: {e}")

        finally:
            # 关闭浏览器
            browser.close()

```

加上这一招,页面打开速度通常能**提升 2~5 倍**。猎聘和鱼泡爬虫都用了这招。

## **七、反自动化伪装:让网站认不出你是机器人**

网站怎么识别"你是不是真人"?最简单的一个判断点:

```python
navigator.webdriver   // 真人浏览器 = undefined,Playwright = true
```

很多反爬系统会检查这个字段。我们把它伪装掉:

```python
context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
""")
```

**这是猎聘、鱼泡项目里所有爬虫的标配第一行代码**。能挡住 80% 的初级反爬。

更高级的伪装(伪造 plugins、languages、WebGL 指纹)有专门的库 `playwright-stealth`,但对中等强度的反爬,上面这一行往往就够了。

```python
"""
生产级别的 Playwright 爬虫模板
功能：支持动态渲染页面、翻页、等待数据加载、去重、断点续跑、异常处理、节奏控制、资源屏蔽优化、反自动化伪装
"""
import os
import json
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

# ==================== 配置区 ====================
# 数据保存目录
DATA_DIR = "data/jobs"
# 进度记录文件路径
PROGRESS_FILE = "data/progress.txt"
# 列表页URL（如果有分页，可以改成带页码的格式）
LIST_URL = "https://realpython.github.io/fake-jobs/"
# 浏览器配置
HEADLESS = False  # True为无头模式（不显示浏览器窗口）
TIMEOUT = 30000  # 超时时间（毫秒）


# ==================== 解析函数 ====================
def parse_list_page(html):
    """
    解析列表页，提取职位基本信息

    Args:
        html (str): 列表页HTML内容

    Returns:
        list: 职位信息字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for card in soup.select("div.card-content"):
        # 查找"Apply"按钮获取正确的详情页链接
        apply_link = card.find("a", string="Apply")
        link = apply_link["href"] if apply_link else None

        jobs.append({
            "title": card.select_one("h2.title").get_text(strip=True),
            "company": card.select_one("h3.company").get_text(strip=True),
            "location": card.select_one("p.location").get_text(strip=True),
            "link": link,
        })
    return jobs


def parse_detail_page(html):
    """
    解析详情页，提取职位描述

    Args:
        html (str): 详情页HTML内容

    Returns:
        str: 职位描述文本
    """
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one("div.content")
    return node.get_text(strip=True) if node else ""


# ==================== 数据存储函数 ====================
def save(job):
    """
    将职位数据保存为JSON文件

    Args:
        job (dict): 职位信息字典

    Returns:
        str: 保存的文件路径
    """
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    path = f"{DATA_DIR}/{job_id}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return path


def already_spider(job):
    """
    检查职位是否已经爬取过

    Args:
        job (dict): 职位信息字典

    Returns:
        bool: True表示已爬取
    """
    if not job["link"]:
        return False
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    return os.path.exists(f"{DATA_DIR}/{job_id}.json")


# ==================== 进度管理函数 ====================
def load_progress():
    """
    加载爬取进度

    Returns:
        int: 已处理的职位索引
    """
    if os.path.exists(PROGRESS_FILE):
        try:
            return int(open(PROGRESS_FILE).read())
        except:
            return 0
    return 0


def save_progress(idx):
    """
    保存爬取进度

    Args:
        idx (int): 当前处理到的索引
    """
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(idx))


# ==================== 主程序入口 ====================
if __name__ == "__main__":
    # 创建数据保存目录
    os.makedirs(DATA_DIR, exist_ok=True)

    all_jobs = []  # 存储所有职位

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800},
        )
        
        # 反自动化伪装：注入JavaScript脚本，隐藏Playwright特征
        context.add_init_script("""
            // 伪装 navigator.webdriver 字段
            // 真人浏览器返回 undefined，Playwright默认返回 true
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 伪装 Chrome 对象（某些网站会检查 window.chrome）
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 伪装 plugins（插件列表）
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ]
            });
            
            // 伪装 languages（语言设置）
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 移除 automation 相关的特征
            delete navigator.__proto__.webdriver;
        """)

        # 性能优化：屏蔽图片、字体、视频等无关资源
        def block_resources(route):
            """
            拦截并屏蔽不必要的资源请求，提升爬取速度

            屏蔽的资源类型：
            - image: 图片（jpg, png, gif, webp等）
            - font: 字体文件（woff, ttf等）
            - media: 音视频文件
            - stylesheet: CSS样式表（可选，如果不需要渲染样式）
            """
            if route.request.resource_type in ("image", "font", "media"):
                route.abort()       # 取消这个请求，节省带宽和时间
            else:
                route.continue_()   # 其他资源正常放行（HTML、JS、XHR等）

        # 应用路由拦截规则，**/* 匹配所有请求
        context.route("**/*", block_resources)

        page = context.new_page()

        try:
            # ---- 第1步：抓取列表页（支持翻页）----
            current_page = 1
            max_pages = 3  # 最大翻页数，根据需要调整

            while current_page <= max_pages:
                print(f"\n===== 正在抓取第 {current_page} 页 =====")

                # 如果是第一页，直接访问；否则点击下一页按钮
                if current_page == 1:
                    page.goto(LIST_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
                else:
                    # 尝试点击下一页按钮（根据实际网站结构调整选择器）
                    next_btn = page.query_selector("a.next-page, button.next, .pagination a:last-child")
                    if not next_btn:
                        print("没有更多页面了")
                        break

                    next_btn.click()
                    # 等待新页面加载完成
                    page.wait_for_load_state("networkidle", timeout=TIMEOUT)

                # 等待职位卡片加载完成
                try:
                    page.wait_for_selector("div.card-content", timeout=TIMEOUT)
                except PlaywrightTimeout:
                    print(f"第 {current_page} 页加载超时")
                    break

                # 额外等待，确保动态内容完全加载
                page.wait_for_timeout(1000)

                # 解析当前页的职位列表
                jobs = parse_list_page(page.content())
                print(f"第 {current_page} 页抓到 {len(jobs)} 条")

                if not jobs:
                    print("没有更多数据了")
                    break

                all_jobs.extend(jobs)
                current_page += 1

                # 翻页间隔
                time.sleep(random.uniform(1, 2))

            print(f"\n列表页总共抓到 {len(all_jobs)} 条职位")

            # ---- 第2步：加载进度，实现断点续跑 ----
            start = load_progress()
            print(f"从第 {start} 条开始抓取详情")

            # ---- 第3步：逐个抓取详情页 ----
            for idx, job in enumerate(all_jobs):
                # 跳过已处理的职位（断点续跑）
                if idx < start:
                    continue

                # 跳过无效链接或已爬取的职位
                if not job["link"]:
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过: 无链接 - {job['title']}")
                    save_progress(idx + 1)
                    continue

                if already_spider(job):
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过已抓: {job['title']}")
                    save_progress(idx + 1)
                    continue

                try:
                    print(f"[{idx + 1}/{len(all_jobs)}] 正在抓取: {job['title']}")

                    # 打开详情页
                    page.goto(job["link"], timeout=TIMEOUT, wait_until="domcontentloaded")

                    # 等待详情内容加载
                    page.wait_for_selector("div.content", timeout=TIMEOUT)

                    # 额外等待，确保动态内容完全加载
                    page.wait_for_timeout(500)

                    # 解析详情内容
                    job["description"] = parse_detail_page(page.content())

                    # 保存数据
                    saved_to = save(job)
                    print(f"  已保存: {saved_to}")

                except Exception as e:
                    print(f"  抓取失败: {e}")

                # 更新进度
                save_progress(idx + 1)

                # 随机休眠，控制请求频率
                time.sleep(random.uniform(1, 2))

            print("\n全部完成！")

        except Exception as e:
            print(f"发生错误: {e}")

        finally:
            # 关闭浏览器
            browser.close()

```

添加 context.add\_init\_script()：

*   在每个页面加载前自动注入JavaScript代码
*   对所有页面生效，无需重复设置

伪装的关键字段：

*   navigator.webdriver：最核心的检测点，改为 undefined
*   window.chrome：模拟Chrome浏览器的特有对象
*   navigator.plugins：伪造插件列表，让浏览器看起来更真实
*   navigator.languages：设置语言偏好
*   删除 webdriver 原型链：彻底清除自动化特征

反检测效果：

*   绕过基于 navigator.webdriver 的简单检测
*   模拟真实浏览器的环境特征
*   降低被识别为机器人的概率

注意事项：

*   这只是基础伪装，高级反爬系统还会检测鼠标轨迹、键盘输入等行为特征
*   如果需要更强的伪装，可以考虑使用 playwright-stealth 库
*   配合合理的请求间隔和User-Agent轮换效果更好

## **八、真正的杀手锏:**`**page.on("response")**` **监听接口**

到这里我们的爬虫已经能抓动态网站了。但现在出现一个新问题:**用 DOM 解析职位数据,字段总是不全、不稳定**。

为什么?因为页面上显示的内容,是前端把接口返回的 JSON **二次加工**后的结果。比如:

*   接口返回的薪资是 `{"min": 15000, "max": 25000, "currency": "CNY"}`
*   页面渲染成 `"15-25k·13薪"`

从 DOM 读到的是后者,要还原成结构化数据还要自己解析字符串,**容易出错**。

**有没有办法直接拿到接口的 JSON?​**

有!Playwright 提供了一个绝杀技:**让浏览器正常加载页面,但我们在旁边"偷听"接口返回**。

```python
captured_data = []

def on_response(response):
    if "search-job" in response.url:        # 匹配目标接口
        try:
            data = response.json()           # 直接拿 JSON
            captured_data.append(data)
            print(f"拦截到: {response.url}")
        except Exception:
            pass

page.on("response", on_response)
page.goto("https://www.liepin.com/zhaopin/")  # 正常打开页面
page.wait_for_load_state("networkidle")

# 现在 captured_data 里就是接口返回的原始 JSON
```

```python
"""
生产级别的 Playwright 爬虫模板
功能：支持动态渲染页面、翻页、等待数据加载、去重、断点续跑、异常处理、节奏控制、资源屏蔽优化、反自动化伪装、API接口监听
"""
import os
import json
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

# ==================== 配置区 ====================
# 数据保存目录
DATA_DIR = "data/jobs"
# 进度记录文件路径
PROGRESS_FILE = "data/progress.txt"
# 列表页URL（如果有分页，可以改成带页码的格式）
LIST_URL = "https://realpython.github.io/fake-jobs/"
# 浏览器配置
HEADLESS = False  # True为无头模式（不显示浏览器窗口）
TIMEOUT = 30000  # 超时时间（毫秒）


# ==================== API接口监听器 ====================
class APICapture:
    """
    API响应拦截器
    用于捕获页面加载过程中的AJAX请求返回的JSON数据
    """
    def __init__(self):
        self.captured_data = []  # 存储捕获到的API数据
        self.target_keywords = []  # 目标接口的关键词列表

    def set_target_keywords(self, keywords):
        """
        设置需要监听的接口关键词

        Args:
            keywords (list): URL中包含的关键词列表，如 ['api/jobs', 'search']
        """
        self.target_keywords = keywords

    def on_response(self, response):
        """
        响应拦截回调函数
        当浏览器收到任何HTTP响应时自动调用

        Args:
            response: Playwright的Response对象
        """
        url = response.url

        # 检查URL是否包含目标关键词
        if any(keyword in url for keyword in self.target_keywords):
            try:
                # 尝试解析JSON数据
                data = response.json()

                # 存储捕获的数据，包含URL和响应内容
                self.captured_data.append({
                    "url": url,
                    "status": response.status,
                    "data": data,
                    "timestamp": time.time()
                })

                print(f"[API拦截] {url} (状态码: {response.status})")

            except Exception as e:
                # 如果响应不是JSON格式，忽略
                pass

    def get_captured_data(self):
        """
        获取所有捕获到的API数据
        
        Returns:
            list: 捕获到的API响应数据列表
        """
        return self.captured_data.copy()

    def clear(self):
        """清空已捕获的数据"""
        self.captured_data.clear()


# ==================== 解析函数 ====================
def parse_list_page(html):
    """
    解析列表页，提取职位基本信息

    Args:
        html (str): 列表页HTML内容

    Returns:
        list: 职位信息字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for card in soup.select("div.card-content"):
        # 查找"Apply"按钮获取正确的详情页链接
        apply_link = card.find("a", string="Apply")
        link = apply_link["href"] if apply_link else None

        jobs.append({
            "title": card.select_one("h2.title").get_text(strip=True),
            "company": card.select_one("h3.company").get_text(strip=True),
            "location": card.select_one("p.location").get_text(strip=True),
            "link": link,
        })
    return jobs


def parse_detail_page(html):
    """
    解析详情页，提取职位描述

    Args:
        html (str): 详情页HTML内容

    Returns:
        str: 职位描述文本
    """
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one("div.content")
    return node.get_text(strip=True) if node else ""


# ==================== 数据存储函数 ====================
def save(job):
    """
    将职位数据保存为JSON文件

    Args:
        job (dict): 职位信息字典

    Returns:
        str: 保存的文件路径
    """
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    path = f"{DATA_DIR}/{job_id}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return path


def already_spider(job):
    """
    检查职位是否已经爬取过

    Args:
        job (dict): 职位信息字典

    Returns:
        bool: True表示已爬取
    """
    if not job["link"]:
        return False
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    return os.path.exists(f"{DATA_DIR}/{job_id}.json")


# ==================== 进度管理函数 ====================
def load_progress():
    """
    加载爬取进度

    Returns:
        int: 已处理的职位索引
    """
    if os.path.exists(PROGRESS_FILE):
        try:
            return int(open(PROGRESS_FILE).read())
        except:
            return 0
    return 0


def save_progress(idx):
    """
    保存爬取进度

    Args:
        idx (int): 当前处理到的索引
    """
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(idx))


# ==================== 主程序入口 ====================
if __name__ == "__main__":
    # 创建数据保存目录
    os.makedirs(DATA_DIR, exist_ok=True)

    all_jobs = []  # 存储所有职位
    api_capture = APICapture()  # 创建API拦截器

    # 设置要监听的API接口关键词（根据实际网站调整）
    # 例如：['api/jobs', 'search', 'recruitment']
    api_capture.set_target_keywords(["fake-jobs"])  # 示例：监听包含fake-jobs的接口

    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800},
        )

        # 反自动化伪装：注入JavaScript脚本，隐藏Playwright特征
        context.add_init_script("""
            // 伪装 navigator.webdriver 字段
            // 真人浏览器返回 undefined，Playwright默认返回 true
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 伪装 Chrome 对象（某些网站会检查 window.chrome）
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 伪装 plugins（插件列表）
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ]
            });
            
            // 伪装 languages（语言设置）
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 移除 automation 相关的特征
            delete navigator.__proto__.webdriver;
        """)

        # 性能优化：屏蔽图片、字体、视频等无关资源
        def block_resources(route):
            """
            拦截并屏蔽不必要的资源请求，提升爬取速度

            屏蔽的资源类型：
            - image: 图片（jpg, png, gif, webp等）
            - font: 字体文件（woff, ttf等）
            - media: 音视频文件
            - stylesheet: CSS样式表（可选，如果不需要渲染样式）
            """
            if route.request.resource_type in ("image", "font", "media"):
                route.abort()       # 取消这个请求，节省带宽和时间
            else:
                route.continue_()   # 其他资源正常放行（HTML、JS、XHR等）

        # 应用路由拦截规则，**/* 匹配所有请求
        context.route("**/*", block_resources)

        page = context.new_page()

        # 注册API响应监听器
        page.on("response", api_capture.on_response)

        try:
            # ---- 第1步：抓取列表页（支持翻页）----
            current_page = 1
            max_pages = 3  # 最大翻页数，根据需要调整

            while current_page <= max_pages:
                print(f"\n===== 正在抓取第 {current_page} 页 =====")

                # 清空之前捕获的API数据
                api_capture.clear()

                # 如果是第一页，直接访问；否则点击下一页按钮
                if current_page == 1:
                    page.goto(LIST_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
                else:
                    # 尝试点击下一页按钮（根据实际网站结构调整选择器）
                    next_btn = page.query_selector("a.next-page, button.next, .pagination a:last-child")
                    if not next_btn:
                        print("没有更多页面了")
                        break

                    next_btn.click()
                    # 等待新页面加载完成
                    page.wait_for_load_state("networkidle", timeout=TIMEOUT)

                # 等待职位卡片加载完成
                try:
                    page.wait_for_selector("div.card-content", timeout=TIMEOUT)
                except PlaywrightTimeout:
                    print(f"第 {current_page} 页加载超时")
                    break

                # 额外等待，确保动态内容和API请求完成
                page.wait_for_timeout(1500)

                # 检查是否捕获到API数据
                captured = api_capture.get_captured_data()
                if captured:
                    print(f"[API数据] 捕获到 {len(captured)} 个API响应")
                    # 这里可以处理API返回的JSON数据
                    # 例如：直接从JSON中提取职位信息，比DOM解析更准确
                    for item in captured:
                        print(f"  - URL: {item['url']}")
                        # print(f"  - 数据: {json.dumps(item['data'], ensure_ascii=False)[:200]}")
                else:
                    print("[API数据] 未捕获到匹配的API响应")

                # 解析当前页的职位列表（备用方案：如果API拦截失败，仍可用DOM解析）
                jobs = parse_list_page(page.content())
                print(f"第 {current_page} 页抓到 {len(jobs)} 条")

                if not jobs:
                    print("没有更多数据了")
                    break

                all_jobs.extend(jobs)
                current_page += 1

                # 翻页间隔
                time.sleep(random.uniform(1, 2))

            print(f"\n列表页总共抓到 {len(all_jobs)} 条职位")

            # ---- 第2步：加载进度，实现断点续跑 ----
            start = load_progress()
            print(f"从第 {start} 条开始抓取详情")

            # ---- 第3步：逐个抓取详情页 ----
            for idx, job in enumerate(all_jobs):
                # 跳过已处理的职位（断点续跑）
                if idx < start:
                    continue

                # 跳过无效链接或已爬取的职位
                if not job["link"]:
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过: 无链接 - {job['title']}")
                    save_progress(idx + 1)
                    continue

                if already_spider(job):
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过已抓: {job['title']}")
                    save_progress(idx + 1)
                    continue

                try:
                    print(f"[{idx + 1}/{len(all_jobs)}] 正在抓取: {job['title']}")

                    # 清空API缓存，准备捕获详情页的接口
                    api_capture.clear()

                    # 打开详情页
                    page.goto(job["link"], timeout=TIMEOUT, wait_until="domcontentloaded")

                    # 等待详情内容加载
                    page.wait_for_selector("div.content", timeout=TIMEOUT)

                    # 额外等待，确保动态内容和API请求完成
                    page.wait_for_timeout(1000)

                    # 检查是否捕获到详情页的API数据
                    detail_api_data = api_capture.get_captured_data()
                    if detail_api_data:
                        print(f"  [API数据] 捕获到 {len(detail_api_data)} 个API响应")
                        # 可以直接从API数据中提取结构化信息
                        # 这比DOM解析更可靠，特别是对于薪资、福利等复杂字段

                    # 解析详情内容（备用方案）
                    job["description"] = parse_detail_page(page.content())

                    # 保存数据
                    saved_to = save(job)
                    print(f"  已保存: {saved_to}")

                except Exception as e:
                    print(f"  抓取失败: {e}")

                # 更新进度
                save_progress(idx + 1)

                # 随机休眠，控制请求频率
                time.sleep(random.uniform(1, 2))

            print("\n全部完成！")

        except Exception as e:
            print(f"发生错误: {e}")

        finally:
            # 关闭浏览器
            browser.close()

```

**这一招的精妙之处:​**

| 方案  | 优点  | 缺点  |
| --- | --- | --- |
| 自己构造 API 请求 | 速度最快 | 签名难破解、参数易变 |
| 解析 DOM | 简单直观 | 字段不全、易受样式变化影响 |
| **​**`**on_response**` **监听** | **拿原始 JSON、不破解签名、稳定** | **要打开浏览器,慢一点** |

这就是猎聘项目里最核心的设计——**​"页面操作触发 + 接口监听获取"混合方案**:

*   让 Playwright 像真人一样点击筛选项 → 触发接口请求
*   我们在旁边监听 → 接住原始 JSON
*   **不需要研究接口签名,也不需要解析复杂 DOM**

#### **猎聘项目里的真实用法**

```python
def onResponse(self, response):
    if "pc-search-job" in response.url:
        ret = response.json()
        self.jsonData = ret['data']['data']['jobCardList']

# 在主流程里:
page.on("response", self.onResponse)
page.goto("https://www.liepin.com/zhaopin/")
# 操作筛选项,触发接口
page.click("...")
# 等接口数据回来
while not self.jsonData:
    time.sleep(0.5)
# 现在可以从 self.jsonData 读结构化职位列表了
```

**这就是为什么项目代码里到处都是** `**self.jsonData**`**、**`**onResponese**`**​** —— 它不是个奇怪的设计,而是一个被验证过的、性价比最高的反爬绕过方案。

## **九、加代理:换 IP 出口**

到目前为止,所有请求都从你家网络出去——**同一个 IP**。一旦抓得勤了,网站会发现"这个 IP 一分钟点了 50 次,肯定不是真人",直接封你。

代理就是"中转站",让你的请求**从别人的 IP 出去**。

```python
browser = p.chromium.launch(
    headless=False,
    proxy={
        "server": "http://proxy.example.com:8080",
        "username": "user",
        "password": "pass",
    },
)
```

加这一个 `proxy` 参数,**所有从这个浏览器出去的流量都走代理**。被封了?换一个代理重启浏览器就行。

#### **代理池的概念**

单个代理也会被封。所以工程化爬虫一定有"代理池":

```python
代理池服务  ←→  爬虫脚本
   │
   ├─ 我有 100 个代理
   ├─ 你领一个去用
   ├─ 你用完了告诉我"被封了 / 还能用"
   └─ 我帮你统一管理、调度、补货

```

这就是 `spider.py` 里 `getProxy()` / `setProxyRecord()` 的全部逻辑。爬虫不直接管代理,只管"领用 + 上报",代理池服务统一调度。

## **十、风控识别:被发现了怎么办?​**

即使做了所有伪装,还是会被发现。那么**怎么知道自己被发现了**?

最简单的方法:**检查页面标题**。

```python
page.goto(url)
title = page.title()

if title in ("猎聘", "405", "Access Denied", ""):
    print("可能被风控了")
    change_proxy()
    return
```

为什么能用标题判断?因为正常职位页的标题是 "Python 工程师 - 猎聘",而被拦截后会变成纯 "猎聘" 或显示 "405"。这是猎聘项目里基于线上观察总结出的经验规则。

**更复杂的判断:​**

*   URL 是否被重定向到验证页
*   页面是否出现滑块验证码 `.verify-slider`
*   HTTP 状态码是不是 405 / 403
*   页面文本里是否出现 "请输入验证码"

```python
if page.query_selector(".slider-verify"):
    print("出现滑块验证")
    # 1. 切代理
    # 2. 或者模拟拖动滑块
    # 3. 或者休眠到第二天
```

鱼泡爬虫甚至做了**模拟滑块拖动**——但这已经是高阶玩法了,通常我们直接换代理。

## 十一、把所有积木拼到一起:Playwright 工程化版本

```python
"""
生产级别的 Playwright 爬虫模板
功能：支持动态渲染页面、翻页、等待数据加载、去重、断点续跑、异常处理、节奏控制、资源屏蔽优化、反自动化伪装、API接口监听、代理切换、风控识别
"""
import os
import json
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

# ==================== 配置区 ====================
# 数据保存目录
DATA_DIR = "data/jobs"
# 进度记录文件路径
PROGRESS_FILE = "data/progress.txt"
# 列表页URL（如果有分页，可以改成带页码的格式）
LIST_URL = "https://realpython.github.io/fake-jobs/"
# 浏览器配置
HEADLESS = False  # True为无头模式（不显示浏览器窗口）
TIMEOUT = 30000  # 超时时间（毫秒）

# 代理池配置（从代理服务获取或手动维护）
PROXY_POOL = [
    "1.92.159.127:8083",
    "121.36.37.160:8083",
    "119.3.219.36:8083",
    "119.3.254.109:8083",
    "1.92.104.120:8083",
    "113.44.168.74:8083",
    "124.70.74.27:8083",
    "121.36.107.179:8083",
    "119.3.218.18:8083",
    "124.70.69.47:8083",
    "121.36.83.164:8083",
    "124.70.78.220:8083",
    "121.36.102.6:8083",
    "120.46.135.31:8083",
    "113.44.236.170:8083",
    "113.44.177.53:8083",
]

# 风控检测关键词
RISK_TITLES = ["安全访问验证", "Access Denied", "405", "403", "验证码"]
RISK_SELECTORS = [".slider-verify", ".verify-slider", "#captcha", "[class*='captcha']"]


# ==================== 代理管理器 ====================
class ProxyManager:
    """
    代理池管理器
    负责代理的分配、轮换、状态记录
    """
    def __init__(self, proxy_pool):
        """
        初始化代理管理器

        Args:
            proxy_pool (list): 代理地址列表，格式如 ["ip:port", ...]
        """
        self.proxy_pool = proxy_pool.copy()
        self.current_index = 0
        self.failed_proxies = set()  # 记录失败的代理
        self.success_proxies = set()  # 记录成功的代理

    def get_next_proxy(self):
        """
        获取下一个可用代理（轮询方式）

        Returns:
            dict or None: 代理配置字典，如果没有可用代理返回None
                格式：{"server": "http://ip:port"}
        """
        if not self.proxy_pool:
            return None

        # 尝试找到未失败的代理
        max_attempts = len(self.proxy_pool)
        attempts = 0

        while attempts < max_attempts:
            proxy_addr = self.proxy_pool[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxy_pool)

            # 跳过已标记为失败的代理
            if proxy_addr not in self.failed_proxies:
                print(f"[代理] 使用: {proxy_addr}")
                return {"server": f"http://{proxy_addr}"}

            attempts += 1

        # 如果所有代理都失败了，重置失败记录，重新尝试
        print("[代理] 所有代理都已失败，重置后重试")
        self.failed_proxies.clear()
        return self.get_next_proxy()

    def report_success(self, proxy_addr):
        """
        报告代理使用成功

        Args:
            proxy_addr (str): 代理地址
        """
        if proxy_addr:
            self.success_proxies.add(proxy_addr)
            self.failed_proxies.discard(proxy_addr)
            print(f"[代理] 报告成功: {proxy_addr}")

    def report_failure(self, proxy_addr):
        """
        报告代理使用失败（被封或不可用）

        Args:
            proxy_addr (str): 代理地址
        """
        if proxy_addr:
            self.failed_proxies.add(proxy_addr)
            print(f"[代理] 报告失败: {proxy_addr}")


# ==================== API接口监听器 ====================
class APICapture:
    """
    API响应拦截器
    用于捕获页面加载过程中的AJAX请求返回的JSON数据
    """
    def __init__(self):
        self.captured_data = []  # 存储捕获到的API数据
        self.target_keywords = []  # 目标接口的关键词列表

    def set_target_keywords(self, keywords):
        """
        设置需要监听的接口关键词

        Args:
            keywords (list): URL中包含的关键词列表，如 ['api/jobs', 'search']
        """
        self.target_keywords = keywords

    def on_response(self, response):
        """
        响应拦截回调函数
        当浏览器收到任何HTTP响应时自动调用

        Args:
            response: Playwright的Response对象
        """
        url = response.url

        # 检查URL是否包含目标关键词
        if any(keyword in url for keyword in self.target_keywords):
            try:
                # 尝试解析JSON数据
                data = response.json()

                # 存储捕获的数据，包含URL和响应内容
                self.captured_data.append({
                    "url": url,
                    "status": response.status,
                    "data": data,
                    "timestamp": time.time()
                })

                print(f"[API拦截] {url} (状态码: {response.status})")

            except Exception as e:
                # 如果响应不是JSON格式，忽略
                pass

    def get_captured_data(self):
        """
        获取所有捕获到的API数据

        Returns:
            list: 捕获到的API响应数据列表
        """
        return self.captured_data.copy()

    def clear(self):
        """清空已捕获的数据"""
        self.captured_data.clear()


# ==================== 风控检测器 ====================
def check_risk(page):
    """
    检测当前页面是否被风控

    Args:
        page: Playwright的Page对象

    Returns:
        bool: True表示检测到风控，False表示正常
    """
    # 方法1：检查页面标题
    title = page.title()
    if any(keyword in title for keyword in RISK_TITLES):
        print(f"[风控] 检测到风险标题: {title}")
        return True

    # 方法2：检查页面是否出现验证码元素
    for selector in RISK_SELECTORS:
        if page.query_selector(selector):
            print(f"[风控] 检测到验证码元素: {selector}")
            return True

    # 方法3：检查页面文本是否包含验证码提示
    page_text = page.text_content("body")
    if page_text and any(keyword in page_text for keyword in ["请输入验证码", "滑块验证", "安全验证"]):
        print("[风控] 检测到验证码文本")
        return True

    # 方法4：检查HTTP状态码（需要在请求时捕获）
    # 这里简化处理，实际可以通过监听response来实现

    return False


def handle_risk(page, proxy_manager, current_proxy):
    """
    处理风控情况

    Args:
        page: Playwright的Page对象
        proxy_manager: 代理管理器实例
        current_proxy: 当前使用的代理地址
    """
    print("[风控] 触发风控处理流程")

    # 1. 报告当前代理失败
    if current_proxy:
        proxy_manager.report_failure(current_proxy)

    # 2. 获取新代理
    new_proxy = proxy_manager.get_next_proxy()
    if new_proxy:
        print(f"[风控] 切换到新代理: {new_proxy['server']}")
    else:
        print("[风控] 没有可用代理，建议稍后重试")

    # 3. 可选：等待一段时间再重试
    wait_time = random.uniform(5, 10)
    print(f"[风控] 等待 {wait_time:.1f} 秒后重试")
    time.sleep(wait_time)


# ==================== 解析函数 ====================
def parse_list_page(html):
    """
    解析列表页，提取职位基本信息

    Args:
        html (str): 列表页HTML内容

    Returns:
        list: 职位信息字典列表
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for card in soup.select("div.card-content"):
        # 查找"Apply"按钮获取正确的详情页链接
        apply_link = card.find("a", string="Apply")
        link = apply_link["href"] if apply_link else None

        jobs.append({
            "title": card.select_one("h2.title").get_text(strip=True),
            "company": card.select_one("h3.company").get_text(strip=True),
            "location": card.select_one("p.location").get_text(strip=True),
            "link": link,
        })
    return jobs


def parse_detail_page(html):
    """
    解析详情页，提取职位描述

    Args:
        html (str): 详情页HTML内容

    Returns:
        str: 职位描述文本
    """
    soup = BeautifulSoup(html, "lxml")
    node = soup.select_one("div.content")
    return node.get_text(strip=True) if node else ""


# ==================== 数据存储函数 ====================
def save(job):
    """
    将职位数据保存为JSON文件

    Args:
        job (dict): 职位信息字典

    Returns:
        str: 保存的文件路径
    """
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    path = f"{DATA_DIR}/{job_id}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return path


def already_spider(job):
    """
    检查职位是否已经爬取过

    Args:
        job (dict): 职位信息字典

    Returns:
        bool: True表示已爬取
    """
    if not job["link"]:
        return False
    job_id = job["link"].rstrip("/").split("/")[-1].replace(".html", "")
    return os.path.exists(f"{DATA_DIR}/{job_id}.json")


# ==================== 进度管理函数 ====================
def load_progress():
    """
    加载爬取进度

    Returns:
        int: 已处理的职位索引
    """
    if os.path.exists(PROGRESS_FILE):
        try:
            return int(open(PROGRESS_FILE).read())
        except:
            return 0
    return 0


def save_progress(idx):
    """
    保存爬取进度

    Args:
        idx (int): 当前处理到的索引
    """
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(idx))


# ==================== 主程序入口 ====================
if __name__ == "__main__":
    # 创建数据保存目录
    os.makedirs(DATA_DIR, exist_ok=True)

    all_jobs = []  # 存储所有职位
    api_capture = APICapture()  # 创建API拦截器
    proxy_manager = ProxyManager(PROXY_POOL)  # 创建代理管理器

    # 设置要监听的API接口关键词（根据实际网站调整）
    # 例如：['api/jobs', 'search', 'recruitment']
    api_capture.set_target_keywords(["fake-jobs"])  # 示例：监听包含fake-jobs的接口

    # 获取初始代理
    current_proxy_config = proxy_manager.get_next_proxy()
    current_proxy_addr = current_proxy_config["server"].replace("http://", "") if current_proxy_config else None

    with sync_playwright() as p:
        # 启动浏览器（带代理）
        browser_kwargs = {"headless": HEADLESS}
        if current_proxy_config:
            browser_kwargs["proxy"] = current_proxy_config

        browser = p.chromium.launch(**browser_kwargs)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800},
        )

        # 反自动化伪装：注入JavaScript脚本，隐藏Playwright特征
        context.add_init_script("""
            // 伪装 navigator.webdriver 字段
            // 真人浏览器返回 undefined，Playwright默认返回 true
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 伪装 Chrome 对象（某些网站会检查 window.chrome）
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 伪装 plugins（插件列表）
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ]
            });
            
            // 伪装 languages（语言设置）
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 移除 automation 相关的特征
            delete navigator.__proto__.webdriver;
        """)

        # 性能优化：屏蔽图片、字体、视频等无关资源
        def block_resources(route):
            """
            拦截并屏蔽不必要的资源请求，提升爬取速度

            屏蔽的资源类型：
            - image: 图片（jpg, png, gif, webp等）
            - font: 字体文件（woff, ttf等）
            - media: 音视频文件
            - stylesheet: CSS样式表（可选，如果不需要渲染样式）
            """
            if route.request.resource_type in ("image", "font", "media"):
                route.abort()       # 取消这个请求，节省带宽和时间
            else:
                route.continue_()   # 其他资源正常放行（HTML、JS、XHR等）

        # 应用路由拦截规则，**/* 匹配所有请求
        context.route("**/*", block_resources)

        page = context.new_page()

        # 注册API响应监听器
        page.on("response", api_capture.on_response)

        try:
            # ---- 第1步：抓取列表页（支持翻页）----
            current_page = 1
            max_pages = 3  # 最大翻页数，根据需要调整

            while current_page <= max_pages:
                print(f"\n===== 正在抓取第 {current_page} 页 =====")

                # 清空之前捕获的API数据
                api_capture.clear()

                # 如果是第一页，直接访问；否则点击下一页按钮
                if current_page == 1:
                    page.goto(LIST_URL, timeout=TIMEOUT, wait_until="domcontentloaded")
                else:
                    # 尝试点击下一页按钮（根据实际网站结构调整选择器）
                    next_btn = page.query_selector("a.next-page, button.next, .pagination a:last-child")
                    if not next_btn:
                        print("没有更多页面了")
                        break

                    next_btn.click()
                    # 等待新页面加载完成
                    page.wait_for_load_state("networkidle", timeout=TIMEOUT)

                # 风控检测
                if check_risk(page):
                    handle_risk(page, proxy_manager, current_proxy_addr)
                    # 重启浏览器使用新代理
                    browser.close()
                    current_proxy_config = proxy_manager.get_next_proxy()
                    current_proxy_addr = current_proxy_config["server"].replace("http://", "") if current_proxy_config else None

                    browser_kwargs = {"headless": HEADLESS}
                    if current_proxy_config:
                        browser_kwargs["proxy"] = current_proxy_config
                    browser = p.chromium.launch(**browser_kwargs)
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        viewport={"width": 1280, "height": 800},
                    )
                    context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                        window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}, app: {}};
                    """)
                    context.route("**/*", block_resources)
                    page = context.new_page()
                    page.on("response", api_capture.on_response)
                    continue

                # 等待职位卡片加载完成
                try:
                    page.wait_for_selector("div.card-content", timeout=TIMEOUT)
                except PlaywrightTimeout:
                    print(f"第 {current_page} 页加载超时")
                    break

                # 额外等待，确保动态内容和API请求完成
                page.wait_for_timeout(1500)

                # 检查是否捕获到API数据
                captured = api_capture.get_captured_data()
                if captured:
                    print(f"[API数据] 捕获到 {len(captured)} 个API响应")
                    # 这里可以处理API返回的JSON数据
                    # 例如：直接从JSON中提取职位信息，比DOM解析更准确
                    for item in captured:
                        print(f"  - URL: {item['url']}")
                        # print(f"  - 数据: {json.dumps(item['data'], ensure_ascii=False)[:200]}")
                else:
                    print("[API数据] 未捕获到匹配的API响应")

                # 解析当前页的职位列表（备用方案：如果API拦截失败，仍可用DOM解析）
                jobs = parse_list_page(page.content())
                print(f"第 {current_page} 页抓到 {len(jobs)} 条")

                if not jobs:
                    print("没有更多数据了")
                    break

                all_jobs.extend(jobs)
                current_page += 1

                # 翻页间隔
                time.sleep(random.uniform(1, 2))

            # 报告代理成功
            if current_proxy_addr:
                proxy_manager.report_success(current_proxy_addr)

            print(f"\n列表页总共抓到 {len(all_jobs)} 条职位")

            # ---- 第2步：加载进度，实现断点续跑 ----
            start = load_progress()
            print(f"从第 {start} 条开始抓取详情")

            # ---- 第3步：逐个抓取详情页 ----
            for idx, job in enumerate(all_jobs):
                # 跳过已处理的职位（断点续跑）
                if idx < start:
                    continue

                # 跳过无效链接或已爬取的职位
                if not job["link"]:
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过: 无链接 - {job['title']}")
                    save_progress(idx + 1)
                    continue

                if already_spider(job):
                    print(f"[{idx + 1}/{len(all_jobs)}] 跳过已抓: {job['title']}")
                    save_progress(idx + 1)
                    continue

                try:
                    print(f"[{idx + 1}/{len(all_jobs)}] 正在抓取: {job['title']}")

                    # 清空API缓存，准备捕获详情页的接口
                    api_capture.clear()

                    # 打开详情页
                    page.goto(job["link"], timeout=TIMEOUT, wait_until="domcontentloaded")

                    # 风控检测
                    if check_risk(page):
                        handle_risk(page, proxy_manager, current_proxy_addr)
                        # 详情页遇到风控，跳过该职位
                        save_progress(idx + 1)
                        continue

                    # 等待详情内容加载
                    page.wait_for_selector("div.content", timeout=TIMEOUT)

                    # 额外等待，确保动态内容和API请求完成
                    page.wait_for_timeout(1000)

                    # 检查是否捕获到详情页的API数据
                    detail_api_data = api_capture.get_captured_data()
                    if detail_api_data:
                        print(f"  [API数据] 捕获到 {len(detail_api_data)} 个API响应")
                        # 可以直接从API数据中提取结构化信息
                        # 这比DOM解析更可靠，特别是对于薪资、福利等复杂字段

                    # 解析详情内容（备用方案）
                    job["description"] = parse_detail_page(page.content())

                    # 保存数据
                    saved_to = save(job)
                    print(f"  已保存: {saved_to}")

                except Exception as e:
                    print(f"  抓取失败: {e}")

                # 更新进度
                save_progress(idx + 1)

                # 随机休眠，控制请求频率
                time.sleep(random.uniform(1, 2))

            print("\n全部完成！")

        except Exception as e:
            print(f"发生错误: {e}")

        finally:
            # 关闭浏览器
            browser.close()

```

**这一版用到的全部积木:​**

| 积木  | 项目里对应 |
| --- | --- |
| Playwright 启动浏览器 | `spider.py::toInstance()` |
| 反自动化注入 | `spider.py::addInitScript()` |
| 屏蔽图片字体 | `spider.py::__handleRequest()` |
| 接口监听 | `spider_liepin.py::onResponese()` |
| 风控识别 | 检查 title == "猎聘" |
| 代理参数 | `spider.py::getProxy()` |
| 文件级去重 | `isSpiderToday()` 雏形 |

这些代码已经具备了**生产级爬虫的完整骨架**。猎聘那 1000 行,本质上就是在这些代码的基础上,把每一项做得更精细。

* * *

## **十二、回头看:四种采集通道现在全打通了**

第 2 讲我们说有四种采集通道,现在应该全部理解了:

| 通道  | 工具  | 适用场景 | 项目位置 |
| --- | --- | --- | --- |
| **静态 HTML** | `requests` + BS4 | 服务端直出 HTML | 部分老旧网站、学校公告 |
| **API 直连** | `requests.get(api)` | 接口简单、无签名 | `auto_api/` 百度京东金蝶 |
| **动态浏览器** | Playwright + DOM 解析 | JS 渲染、需登录 | 鱼泡、猎聘详情页 |
| **接口监听** | `page.on("response")` | 接口有签名但能在浏览器触发 | 猎聘列表、`auto_on_response/` |

**没有"哪种最好",只有"哪种最合适"​**。猎聘项目就是把**通道 3 + 通道 4 混合**:用 Playwright 操作页面触发请求,用 `on_response` 接住 JSON。

这种"半接口、半页面"的混合方案,是目前对抗中高强度反爬最稳的方案。

* * *

## **十三、这一讲的关键认知**

讲到这里,应该已经形成了一个非常重要的判断力:

**面对一个新网站,知道怎么"侦察"它,然后选对工具:​**

```python
打开开发者工具 F12
│
├─ HTML 里直接有数据吗?  → 用 requests
│
├─ 数据是接口加载的,接口好请求吗?  → 用 requests 直接打接口
│
├─ 接口有复杂签名,但能在浏览器触发?  → Playwright + on_response
│
└─ 接口完全无法分析,只能读 DOM?  → Playwright + DOM 解析
```

**这是工程师视角的"工具选型决策"​**——不是"哪个方案酷",而是"哪个方案能用最少的代价拿到数据"。

import time 
import re
import os
import json
import random

from playwright.sync_api import sync_playwright

from utils import ner_logger

#获取浏览器
def get_browser(p,executable_path,isproxy = ""):
    #设置参数
    args=[  # 指定浏览器启动参数
        "--disable-infobars", 
        "--disable-blink-features=PasswordManager,Autofill,AutomationControlled", 
        "--disable-frame-decoration",  
        "--ignore-certificate-errors",  # 绕过HTTPS错误
        "--allow-running-insecure-content"  # 允许不安全内容 
    ]
    proxylist={"server":""}
    if isproxy == 'Y':
        _ps = getProxy()
        proxylist = {"server":_ps}
        ner_logger.info("使用代理："+_ps)
        browser = p.chromium.launch( 
                executable_path=executable_path,  # 指定浏览器路径
                headless=False,  # 设置非无头模式 
                args= args,  #设置参数     
                proxy= proxylist    
            )
        return browser
    #创建浏览器
    browser = p.chromium.launch( 
        executable_path=executable_path,  # 指定浏览器路径
        headless=False,  # 设置非无头模式 
        args= args  #设置参数  
    )
    return browser
#根据文字查找
def click_by_text_and_get_url(page,_url,text_to_click,_type = "pop",area=  None, _max_parent_level='3',_current_url="" ):
    #有时候传入的为空
    if not _type or _type =="":
        _type = "pop" 
    if _type == "pop":
        return click_by_text_and_get_url_pop(page,_url,text_to_click, area, _max_parent_level)
    else:
        return click_by_text_and_get_url_current(page,_url,text_to_click,area,_max_parent_level,_current_url)
#根据文字查找
def click_by_text_and_get_url_pop(page, _url, text_to_click, area=None, _max_parent_level="4"):
    if not _max_parent_level :
        _max_parent_level = "4"
    _max_parent_level = int(_max_parent_level)

    print(f"[入口参数] text_to_click={text_to_click}, area={area}", flush=True)
    try:
        print(f"[调试] 传入参数 text_to_click={text_to_click}, area={area}")
        with page.expect_popup() as popup_info:
            elements = page.locator(f"text={text_to_click}").all()
            if not elements:
                print(f"[警告] 没有找到任何 {text_to_click} 元素")
                return None, None

            target = None

            if not area:  # area 为空，直接选第一个
                target = elements[0]
            else:  # area 不为空，按父节点文本匹配
                for idx, element in enumerate(elements):
                    current = element
                    for level in range(_max_parent_level):
                        full_text = current.inner_text().strip().replace("\n","").replace(" ","").replace("|","").replace("/","").replace(",","").replace("、", "")
                        area_clean = area.replace(" ", "").replace("\n", "").replace(",","").replace("/","").replace("、","")
                        print(f"[调试] 第 {idx} 个元素第 {level} 层父节点文本: {full_text}", flush=True)
                        if area_clean in full_text:
                            target = element
                            break
                        current = current.locator("xpath=..")
                    if target:
                        break

                if not target:
                    print(f"[警告] 没有找到包含 {area} 的 {text_to_click}")
                    return None, None

            # 执行点击
            target.hover(timeout=3000)
            target.click()

        # 获取新页面
        new_page = popup_info.value
        new_page.wait_for_load_state("networkidle")
        new_url = new_page.url
        if page != new_page:
            #等待页面加载完成
            new_page.wait_for_load_state("networkidle")
            content = new_page.content()
            new_page.close()

            return new_url, content  # 返回点击的元素

    except Exception as e:
        print(f"[错误] pop: {e}", flush=True)
        return None, None

#根据文字查找
def click_by_text_and_get_url_current(page, _url, text_to_click, area=None, _max_parent_level="3", _current_url=""):
    if not _max_parent_level :
        _max_parent_level = "3"
    max_parent_level = int(_max_parent_level)
    try:
        print(f"[入口参数] text_to_click={text_to_click}, area={area}", flush=True)
        print(f"[调试] 访问 {_url}", flush=True)
        with page.expect_navigation():
            elements = page.locator(f"text={text_to_click}").all()
            print(f"[调试] 找到 {len(elements)} 个元素 text={text_to_click}", flush=True)

            target = None

            if not area:  # 如果 area 为空，直接选第一个元素
                if elements:
                    target = elements[0]
                else:
                    print(f"[警告] 没有找到任何 {text_to_click} 元素", flush=True)
                    return None, None
            else:  # area 不为空，按父节点匹配
                for idx, element in enumerate(elements):
                    current = element
                    for level in range(max_parent_level):
                        full_text = current.inner_text().replace("\n","").replace(" ","").replace("/","").replace(",","").replace("、", "")
                        area_clean = area.replace(" ", "").replace("\n", "").replace(",","").replace("、", "")
                        print(f"[调试]area = {area_clean} 第 {idx} 个元素第 {level} 层父节点文本: {full_text}", flush=True)
                        if area_clean in full_text:
                            target = element
                            break
                        current = current.locator("xpath=..")
                    if target:
                        break

                if not target:
                    print(f"[警告] 没有找到包含 {area} 的 {text_to_click}", flush=True)
                    return None, None

            # 执行点击
            target.hover(timeout=1000)
            target.click()

            new_url = page.url
        if _url != new_url:
            time.sleep(5)
            page.wait_for_load_state("networkidle")
            content = page.content()
            page.goto(_url)
            print(_url)
            # 等待页面加载完
            print(f"[信息] 点击{text_to_click}成功，新链接为{new_url}", flush=True)

            return new_url, content

    except Exception as e:
        print(f"出现错误 get current: {e}", flush=True)
        return None, None



#检查url是否可用
def check_url_available(executable_path,url):
    with sync_playwright() as p:
        # 启动 Chromium 浏览器 
        browser = get_browser(p,executable_path)
        # 创建新页面
        page = browser.new_page()
        try:
            response = page.goto(url, timeout=1000)
            # 等待页面加载完成，这里可以根据实际情况调整等待时间或条件
            if response.ok:
                return True
        except Exception as e:
            ner_logger.info(f"尝试打开url时出错: {e}")
            return False
        finally:
            # 关闭浏览器
            browser.close()    
#获取微信的url内容
def get_wx_url_content(executable_path,url):
    with sync_playwright() as p:
        # 启动 Chromium 浏览器 
        browser = get_browser(p,executable_path)
        # 创建新页面
        page = browser.new_page()
        # 启动时自动全屏
        page.set_viewport_size({"width": 1280, "height": 1080})
        try:
            time.sleep(2)
            # 导航到微信文章链接
            page.goto(url)
            # 等待页面加载完成，这里可以根据实际情况调整等待时间或条件
            page.wait_for_load_state('load',timeout=30000)
            try:
                page.wait_for_load_state('networkidle',timeout=30000)
            except Exception as e:
                ner_logger.info(f"尝试打开url时出错 networkidle: {e}")
            time.sleep(5)
            #查找js_share_content节点
            js_share_content = page.query_selector('#js_share_content')
            if js_share_content:
                ner_logger.info(f"js_share_content节点存在{url}")
                # 获取下面的<span>的内容为阅读全文的data-url
                # 在 js_share_content 元素内部查找内容为“阅读全文”的 span 元素
                read_more_element = js_share_content.query_selector('span:text("阅读全文")')
                if read_more_element:
                    data_url = read_more_element.get_attribute('data-url')
                    #判断url开始为http://mp.weixin.qq.com
                    if data_url and (data_url.startswith("http://mp.weixin") or data_url.startswith("https://mp.weixin")):
                        ner_logger.info(f"再次获取详情的 data_url:{data_url}")
                        # 访问data_url
                        page.goto(data_url)
                        time.sleep(2)
            #获取image的url
            image_lists = get_image_urls(page)
            time.sleep(2)
            # 获取页面内容
            content = page.content()
            #首先查找'text=阅读原文' 的元素，判断是否存在
            # 通过 id 查找元素
            element = page.query_selector("#js_view_source") 
            if element and element.inner_text() == '阅读原文':
                try:
                    # 等待新页面打开
                    with page.expect_navigation():
                        # 点击元素
                        time.sleep(1)
                        element.click()
                        #等待div.weui-dialog__ft
                        page.wait_for_selector('div.weui-dialog__ft')
                        time.sleep(1)
                        #对弹开的div对话框，进行 允许 点击 
                        if page.query_selector('div.weui-dialog__ft'):
                            page.click('div.weui-dialog__ft >> text=允许')  # 假设【允许】按钮在 div.dialog 中
                            time.sleep(1)
                            # 获取新页面的链接
                            image_lists['yqym_url'] =  page.url        
                except Exception as e:
                    ner_logger.info(f"读取阅读原文出现错误:{e}")
            #返回
            return True,content,image_lists
        except Exception as e:
            import traceback
            ner_logger.info(traceback.format_exc())
            ner_logger.info(f"获取微信内容时出错: {e}")
            return False,None,[]
        finally:
            # 关闭浏览器
            browser.close()    
#检查是否有iframe
def get_iframe_urls(page,detailIframe = ""):  
    try:
        iframe_urls = []
        iframes = page.query_selector_all('iframe')
        for iframe in iframes:
            iframe_src = iframe.get_attribute('src')
            if iframe_src:
                iframe_urls.append(iframe_src)
            #如果iframe的id为detailIframe，则返回
            if iframe.get_attribute('id') == detailIframe:
                return [iframe_src]
        return iframe_urls
    except Exception as e:
        print(f"出现错误: {e}")
        return [] 
#获取界面中的所有图片的链接及大小
def get_image_urls(page):
    image_urls = {}
    try:
        #获取所有的图片
        images = page.query_selector_all('img') 
        for image in images:  
                image_src = image.get_attribute('src')
                data_src = image.get_attribute('data-src')
                        # 获取图片的 bounding box，包含 x, y, width, height
                box = image.bounding_box()
                if image_src and image_src.startswith('http'):
                    url = image_src
                elif data_src and data_src.startswith('http'):
                    url = data_src
                    # 获取图片的显示宽度和高度
                if url and box and url.startswith('http'):
                    width = box['width']
                    height = box['height']
                    image_urls[url] = {'rendered_width': width, 'rendered_height': height}
        #获取所有的svn 
        svgs = page.query_selector_all('svg')
        for svg in svgs:
            # 获取 SVG 元素的背景样式
            # 获取 SVG 元素的 style 属性
            style = svg.get_attribute('style')
            if style:
                # 使用正则表达式提取 background-image 的 URL
                match = re.search(r'background-image:\s*url\((["\']?)(.*?)\1\)', style)
                if match and match.group(2):
                    background_image_url = match.group(2)  
                    ner_logger.info(f"获取到背景图片的 URL: {background_image_url}")
                    if background_image_url and background_image_url.startswith('http'):  
                        box = svg.bounding_box()
                        width = box['width']
                        height = box['height']
                        image_urls[url] = {'rendered_width': width, 'rendered_height': height}
    except Exception as e:
        print(f"获取图片大小失败: {e}")
    #返回
    return image_urls

    
def _get_fallback_proxy():
    """仅作为兜底：从本地文件中随机读取代理"""
    file_path = r"D:\code\python\chu\qzclawler\proxy_pool.txt"
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                proxies = [line.strip() for line in f if line.strip()]
            if proxies:
                return random.choice(proxies)
    except:
        pass
    return ''

def getProxy(tryTimes = 0):
    '''获取代理'''
    if tryTimes >= 3:
        # 只在这里做兜底：如果重试3次失败，从文件随机取一个返回
        return _get_fallback_proxy()
        
    params = {"channel":'yupao', "env": 1}
    proxy = ''
    try:
        import requests
        ret = None
        try:
            # 注意：接口偶发 503/超时，需要重试；加 timeout 防止阻塞
            ret = requests.post('http://121.36.63.42:6868/getproxy', params=params, timeout=8)
            if ret.status_code != 200:
                ner_logger.info(f"获取代理失败: http_status={ret.status_code}")
                time.sleep(1)
                return getProxy(tryTimes + 1)

            try:
                rescontent = ret.json()
            except Exception:
                # 有些情况下返回的不是合法 JSON
                ner_logger.info(f"获取代理失败: 非法JSON, text={ret.text[:200]}")
                time.sleep(1)
                return getProxy(tryTimes + 1)

            if rescontent.get("code") == 200:
                proxy = (rescontent.get('data') or {}).get('proxy') or ''
            else:
                ner_logger.info(f"获取代理失败: code={rescontent.get('code')}, msg={rescontent.get('msg','')}")
                proxy = ''

            if not proxy:
                time.sleep(1)
                return getProxy(tryTimes + 1)

            return proxy
        finally:
            try:
                if ret is not None:
                    ret.close()
            except Exception:
                pass
    except Exception as e:
        ner_logger.info(f"获取代理异常: {e}")
        time.sleep(1)
        return getProxy(tryTimes + 1)
    

#获取page里面是否有redirect跳转
#<div class="target-url" id="targetUrl">https://www.fenbi.com/page/zhaokaodetail/0/461706772627456</div>
def get_redirect_url(page):
    try: 
        redirect_url = page.query_selector('div.target-url')
        #ner_logger.info(f"获取跳转链接成功: {redirect_url}",page.content)
        if redirect_url:
            return True,redirect_url.inner_text()
        else:
            return False,''
    except Exception as e:
        ner_logger.info(f"获取跳转链接失败: {e}")
        return False,''

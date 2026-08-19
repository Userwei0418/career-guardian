import time


def crawl_page(page):
    try:
        next_page_button = page.locator("button.btn-next")
        if next_page_button.is_enabled():
            next_page_button.click(timeout=5000)
            time.sleep(1)  # 等待新页面加载
            return True
        else:
            print("已经到最后一页")
            return False
    except Exception as e:
        print(f"翻页时出错: {e}")
        return False

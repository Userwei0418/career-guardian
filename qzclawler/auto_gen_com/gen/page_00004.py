import time

def crawl_page(page):
    try:
        # 定位并点击下一页元素
        # 通过 class 名定位，由于 class 包含连字符，使用 CSS 选择器
        next_page_button = page.locator("span.widget-pager-nextpage")
        print("111 ",next_page_button)
        # 等待元素可点击后再点击（避免元素未加载完成）
        next_page_button.wait_for(state="visible")
        next_page_button.click()

        return True
    except Exception as e:
        print(f"翻页时出错: {e}")

    return False

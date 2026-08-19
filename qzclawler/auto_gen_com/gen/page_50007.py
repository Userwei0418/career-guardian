def crawl_page(page):
    try:
        # 1. 获取所有页码
        page_spans = page.query_selector_all('span.page')
        current_page = -1
        last_page = -1

        for elem in page_spans:
            text = elem.inner_text().strip()
            if text.isdigit():
                num = int(text)
                # 判断是否是当前页
                if 'current' in elem.get_attribute('class') or 'present' in elem.get_attribute('class'):
                    current_page = num
                last_page = max(last_page, num)

        # 如果没获取到当前页
        if current_page == -1:
            print("无法识别当前页，停止翻页")
            return False

        # 判断是否到最后一页
        if current_page >= last_page:
            print("已经是最后一页，停止翻页")
            return False

        # 2. 查找“下一页”按钮
        next_button = page.query_selector('a.next, a[title="下一页"], a:has-text("下一页")')
        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)  # 等待页面加载
            return True
        else:
            print("未找到下一页按钮")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False

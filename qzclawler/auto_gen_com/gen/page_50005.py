def crawl_page(page):
    try:
        # 获取当前页码
        current_span = page.query_selector('a.page.hover')  # 使用 class="hover" 来定位当前页
        current_page = int(current_span.inner_text()) if current_span else -1

        # 获取所有页码，找到最后一页
        page_spans = page.query_selector_all('a.page')
        last_page = -1
        for elem in reversed(page_spans):  # 从最后一页开始查找
            text = elem.inner_text()
            if text.isdigit():
                last_page = int(text)
                break

        # 判断是否已经是最后一页
        if current_page >= last_page:
            print("已经是最后一页，停止翻页")
            return False

        # 点击“下一页”按钮
        next_button = page.query_selector('#next')  # 查找 id="next" 的按钮
        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)  # 等待 1.5 秒，确保页面加载完成
            return True

    except Exception as e:
        print(f"翻页时出错: {e}")

    return False

def crawl_page(page):
    try:
        # 尝试获取当前页号
        current_span = page.query_selector('span.page.present')
        current_page = int(current_span.inner_text()) if current_span else -1

        # 获取所有页号，计算最后一页
        page_spans = page.query_selector_all('span.page')
        last_page = -1
        for elem in reversed(page_spans):
            text = elem.inner_text()
            if text.isdigit():
                last_page = int(text)
                break

        if current_page >= last_page and last_page != -1:
            print("已经是最后一页，停止翻页。")
            return False

        # 定位下一页按钮，这里是 <span id="next">
        next_button = page.query_selector('span#next')

        if not next_button:
            print("未找到下一页按钮。")
            return False

        # 检查按钮是否有禁用样式或不可点击
        style = next_button.get_attribute('style') or ''
        if 'pointer' not in style:  # 如果没有 pointer，可能不可点击
            print("下一页按钮不可点击")
            return False

        # 点击下一页
        next_button.click()
        page.wait_for_load_state("networkidle")
        print(f"已点击下一页（当前第 {current_page + 1} 页）")
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False

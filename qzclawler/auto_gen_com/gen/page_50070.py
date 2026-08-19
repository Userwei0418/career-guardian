def crawl_page(page):
    try:
        # 获取当前页码
        current_span = page.query_selector('span.page.present')
        current_page = int(current_span.inner_text()) if current_span else -1

        # 获取所有页码元素
        page_spans = page.query_selector_all('span.page')
        last_page = -1
        for elem in reversed(page_spans):
            text = elem.inner_text().strip()
            if text.isdigit():
                last_page = int(text)
                break

        # 判断是否为最后一页
        if current_page >= last_page:
            print(f"已经是最后一页（第 {current_page}/{last_page} 页），停止翻页。")
            return False

        # 定位下一页按钮（使用更精确的选择器）
        next_button = page.query_selector('button.btn-next')
        if next_button:
            # 检查是否被禁用
            disabled = next_button.get_attribute('disabled')
            if disabled:
                print("下一页按钮被禁用，结束翻页。")
                return False

            # 点击并等待页面加载
            next_button.click()
            page.wait_for_load_state("networkidle")
            print(f"已翻到下一页：第 {current_page + 1} 页。")
            return True
        else:
            print("未找到下一页按钮。")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False

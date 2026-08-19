def crawl_page(page):
    try:
        # 获取当前页号
        current_span = page.query_selector('span.page.present')
        current_page = int(current_span.inner_text()) if current_span else -1

        # 获取最大页号
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

        # 通过 aria-label 或 data-ph-at-id 定位下一页按钮
        next_button = page.locator('a[aria-label="View next page"], a[data-ph-at-id="pagination-next-link"]')

        if next_button.count() == 0:
            print("未找到下一页按钮。")
            return False

        # 检查按钮是否可点击（有 href 表示可跳转）
        href_value = next_button.first.get_attribute('href')
        if not href_value:
            print("下一页按钮不可点击（无 href）。")
            return False

        # 点击下一页按钮
        next_button.first.click()
        page.wait_for_load_state("networkidle")
        print(f"已点击下一页（当前第 {current_page + 1} 页）。")
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False

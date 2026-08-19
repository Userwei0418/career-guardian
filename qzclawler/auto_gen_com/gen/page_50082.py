def crawl_page(page):
    try:
        # 获取当前页码
        current_span = page.query_selector('span.page.present')
        current_page = int(current_span.inner_text()) if current_span else -1

        # 获取最后一页数字
        page_spans = page.query_selector_all('span.page')
        last_page = max([int(span.inner_text()) for span in page_spans if span.inner_text().isdigit()] + [-1])

        if current_page >= last_page and last_page != -1:
            print("已经是最后一页，停止翻页")
            return False

        # 查找下一页按钮
        next_button = page.query_selector('a.next[rel="next"]')
        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)
            return True
        else:
            print("没有找到下一页按钮，停止翻页")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False

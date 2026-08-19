def crawl_page(page):
    try:
        current_span = page.query_selector('span.page.present')
        current_page = int(current_span.inner_text()) if current_span else -1

        page_spans = page.query_selector_all('span.page')
        last_page = -1
        for elem in reversed(page_spans):
            text = elem.inner_text()
            if text.isdigit():
                last_page = int(text)
                break

        if current_page >= last_page:
            print("已经是最后一页，停止翻页")
            return False

        next_button = page.query_selector('#next')
        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)
            return True

    except Exception as e:
        print(f"翻页时出错: {e}")

    return False
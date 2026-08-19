def crawl_page(page):
    try:
        paging = page.query_selector('div.pagenum')
        if not paging:
            print("未找到分页区域")
            return False

        cur_span = paging.query_selector('span.chosenone')
        if not cur_span:
            print("未找到当前页")
            return False

        cur_page = cur_span.inner_text().strip()

        spans = paging.query_selector_all('span')
        next_btn = spans[-1]

        print(f"当前页 {cur_page} → 尝试翻页")
        next_btn.click()

        # ✅ 注意这里：arg=cur_page
        page.wait_for_function(
            """(oldPage) => {
                const cur = document.querySelector('div.pagenum span.chosenone');
                return cur && cur.innerText.trim() !== oldPage;
            }""",
            arg=cur_page,
            timeout=5000
        )

        new_span = page.query_selector('div.pagenum span.chosenone')
        new_page = new_span.inner_text().strip()

        print(f"翻页成功 → 当前页 {new_page}")
        return True

    except Exception as e:
        print(f"已到最后一页或翻页失败: {e}")
        return False

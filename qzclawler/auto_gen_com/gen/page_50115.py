def crawl_page(page):
    try:
        # 滚动到底部，确保分页加载
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)

        # 定位“下一页”的 li
        next_li = page.locator("li:has(a:has-text('下一页'))")
        next_li.wait_for(state="visible", timeout=5000)

        # 判断是否禁用（li 上的 disabled）
        li_class = next_li.get_attribute("class") or ""
        if "disabled" in li_class:
            print("已到最后一页，停止翻页。")
            return False

        # 点击 a 标签
        next_li.locator("a").click()
        page.wait_for_load_state("domcontentloaded")
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False

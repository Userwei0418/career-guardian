def crawl_page(page):
    try:
        # 精准获取文本为“下一页”的按钮
        next_btn = page.query_selector('a.next:text("下一页")')

        if not next_btn:
            print("没有找到下一页按钮，结束翻页")
            return False

        # 判断是否禁用
        classes = next_btn.get_attribute("class") or ""
        disabled = next_btn.get_attribute("disabled")

        if "disabled" in classes or disabled is not None:
            print("已到最后一页（下一页不可点击）")
            return False

        print("准备翻页 → 下一页")
        next_btn.click()
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False

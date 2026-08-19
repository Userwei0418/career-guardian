def crawl_page(page) -> bool:
    """
    翻页函数，适配 Vuetify v-pagination 组件。
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # ✅ 定位“下一页”按钮
        next_btn = page.query_selector('button[aria-label="Next page"]')
        if not next_btn:
            print("[翻页] 未找到下一页按钮")
            return False

        # ✅ 判断按钮是否被禁用
        btn_class = next_btn.get_attribute("class") or ""
        if "v-pagination__navigation--disabled" in btn_class or next_btn.get_attribute("disabled"):
            print("[翻页] 下一页按钮已禁用，可能是最后一页")
            return False

        # ✅ 点击并等待页面刷新
        next_btn.click()
        page.wait_for_timeout(1500)
        print("[翻页] 成功点击下一页")
        return True

    except Exception as e:
        print(f"[翻页] 出错: {e}")
        return False

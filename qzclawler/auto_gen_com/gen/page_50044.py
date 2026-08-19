def crawl_page(page, action="next", wait_time=5000):
    """
    爬取分页：支持 'next' 和 'prev'
    如果按钮禁用，则终止操作
    """
    if action not in ["next", "prev"]:
        raise ValueError("action 必须是 'next' 或 'prev'")

    # 针对不同页面结构的分页按钮选择器
    button_selector = (
        "span[class*='next-page']:not(.disabled)"
        if action == "next"
        else "span[class*='prev-page']:not(.disabled)"
    )

    print(f"按钮选择器：{button_selector}")
    btn = page.locator(button_selector)

    # 等待按钮出现
    try:
        btn.wait_for(state="visible", timeout=wait_time)
        print("✅ 按钮已可见")
    except Exception as e:
        print(f"⚠️ 按钮不可见: {e}")
        return False

    # 判断按钮是否禁用
    class_attr = btn.get_attribute("class") or ""
    if "disabled" in class_attr or "pagination-item-disabled" in class_attr:
        print("🚫 按钮已禁用，翻页结束")
        return False

    try:
        print("👉 点击分页按钮")
        btn.click()
        page.wait_for_load_state("domcontentloaded", timeout=wait_time)
        page.wait_for_timeout(1000)  # 稍等1秒防止页面未完全渲染
        print("✅ 翻页成功")
        return True
    except Exception as e:
        print(f"❌ 点击失败: {e}")
        return False

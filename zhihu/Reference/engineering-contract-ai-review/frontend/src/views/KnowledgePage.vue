<script setup>
import { computed, ref } from "vue";
import { knowledgeArticles } from "../data/knowledge";
import { useIdentity } from "../composables/useIdentity";

const { identityConfig, isIdentitySet } = useIdentity();
const categories = ["新手必知", "看懂合同", "维权指南"];
const categoryIcons = { "新手必知": "🌱", "看懂合同": "🔍", "维权指南": "🛡️" };

const activeCategory = ref("新手必知");
const selectedArticle = ref(null);

const recommendedArticles = computed(() => {
  if (!identityConfig.value) return [];
  const slugs = identityConfig.value.recommendedSlugs || [];
  return slugs.map(slug => knowledgeArticles.find(a => a.slug === slug)).filter(Boolean);
});

const filteredArticles = computed(() =>
  knowledgeArticles.filter(a => a.category === activeCategory.value)
);

function openArticle(article) {
  selectedArticle.value = article;
}

function closeArticle() {
  selectedArticle.value = null;
}

function renderMarkdown(md) {
  if (!md) return "";
  let html = md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^- \[x\] (.+)$/gm, '<div class="check-item done">✅ $1</div>')
    .replace(/^- \[ \] (.+)$/gm, '<div class="check-item">☐ $1</div>')
    .replace(/^```[\s\S]*?```/gm, (match) => {
      const code = match.replace(/```\w*\n?/g, "").replace(/```/g, "");
      return `<pre class="code-block">${code}</pre>`;
    })
    .replace(/^\| (.+) \|$/gm, (match) => {
      const cells = match.split("|").filter(c => c.trim()).map(c => c.trim());
      return `<tr>${cells.map(c => `<td>${c}</td>`).join("")}</tr>`;
    })
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li class="numbered">$2</li>')
    .replace(/^❌ (.+)$/gm, '<div class="callout danger">❌ $1</div>')
    .replace(/^✅ (.+)$/gm, '<div class="callout success">✅ $1</div>')
    .replace(/^💡 (.+)$/gm, '<div class="callout info">💡 $1</div>')
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br>");
  return `<p>${html}</p>`;
}
</script>

<template>
  <div class="page-stack">
    <div class="page-toolbar">
      <div>
        <h3>📚 知识学堂</h3>
        <p>了解这些，签合同不踩坑。持续更新中…</p>
      </div>
    </div>

    <el-card v-if="!selectedArticle && recommendedArticles.length">
      <template #header>
        <div class="card-header">
          <span>{{ identityConfig?.icon }} {{ identityConfig?.label }}必读</span>
          <el-tag size="small" type="info">为你精选</el-tag>
        </div>
      </template>
      <div class="recommended-row">
        <el-card
          v-for="article in recommendedArticles"
          :key="article.slug"
          class="recommended-card"
          shadow="hover"
          @click="openArticle(article)"
        >
          <el-tag size="small" type="info">{{ article.tag }}</el-tag>
          <h4>{{ article.title }}</h4>
          <p>{{ article.summary }}</p>
        </el-card>
      </div>
    </el-card>

    <el-card v-if="!selectedArticle">
      <div class="knowledge-categories">
        <div
          v-for="cat in categories"
          :key="cat"
          class="knowledge-cat-tab"
          :class="{ active: activeCategory === cat }"
          @click="activeCategory = cat"
        >
          <span class="cat-icon">{{ categoryIcons[cat] }}</span>
          <span class="cat-name">{{ cat }}</span>
          <span class="cat-count">{{ knowledgeArticles.filter(a => a.category === cat).length }}篇</span>
        </div>
      </div>

      <div class="knowledge-grid">
        <el-card
          v-for="item in filteredArticles"
          :key="item.slug"
          class="knowledge-item"
          shadow="hover"
          @click="openArticle(item)"
        >
          <div class="knowledge-item-header">
            <el-tag size="small" type="info">{{ item.tag }}</el-tag>
          </div>
          <h4>{{ item.title }}</h4>
          <p>{{ item.summary }}</p>
          <el-button text type="primary" size="small">阅读全文 →</el-button>
        </el-card>
      </div>
    </el-card>

    <el-card v-else>
      <div class="article-header">
        <el-button text @click="closeArticle">← 返回列表</el-button>
        <el-tag size="small" type="info" style="margin-left: 12px;">{{ selectedArticle.tag }}</el-tag>
      </div>
      <h2 class="article-title">{{ selectedArticle.title }}</h2>
      <p class="article-summary">{{ selectedArticle.summary }}</p>
      <el-divider />
      <div class="article-content" v-html="renderMarkdown(selectedArticle.content)" />
    </el-card>
  </div>
</template>

<style scoped>
.knowledge-categories {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border-color-light);
  padding-bottom: 16px;
}
.knowledge-cat-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-size: var(--font-size-base);
  color: var(--text-secondary);
}
.knowledge-cat-tab:hover { background: var(--bg-hover); }
.knowledge-cat-tab.active {
  background: var(--color-primary-50);
  color: var(--color-primary-600);
  font-weight: 600;
}
.cat-icon { font-size: 18px; }
.cat-count { font-size: var(--font-size-xs); color: var(--text-tertiary); }

.recommended-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin-bottom: 8px; }
.recommended-card { cursor: pointer; transition: all var(--transition-base); }
.recommended-card:hover { transform: translateY(-2px); }
.recommended-card h4 { margin: 8px 0 4px; font-size: 14px; font-weight: 600; }
.recommended-card p { margin: 0; font-size: 13px; color: var(--text-secondary); }

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.knowledge-item {
  cursor: pointer;
  transition: all var(--transition-base);
}
.knowledge-item:hover { transform: translateY(-3px); box-shadow: var(--shadow-lg); }
.knowledge-item h4 {
  margin: 12px 0 8px;
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
}
.knowledge-item p {
  margin: 0 0 12px;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: var(--line-height-relaxed);
}

.article-header { margin-bottom: 16px; }
.article-title {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 8px 0 4px;
}
.article-summary {
  font-size: var(--font-size-base);
  color: var(--text-tertiary);
  margin: 0;
}
.article-content {
  font-size: var(--font-size-base);
  line-height: var(--line-height-relaxed);
  color: var(--text-primary);
}
.article-content :deep(h2) {
  font-size: var(--font-size-xl);
  font-weight: 700;
  margin: 24px 0 12px;
  color: var(--text-primary);
}
.article-content :deep(h3) {
  font-size: var(--font-size-lg);
  font-weight: 600;
  margin: 20px 0 8px;
  color: var(--text-primary);
}
.article-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: var(--font-size-sm);
}
.article-content :deep(tr) { border-bottom: 1px solid var(--border-color-light); }
.article-content :deep(td) { padding: 8px 12px; }
.article-content :deep(li) { margin: 4px 0; padding-left: 4px; }
.article-content :deep(.code-block) {
  background: var(--color-gray-50);
  padding: 12px 16px;
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  overflow-x: auto;
  margin: 12px 0;
}
.article-content :deep(.callout) {
  padding: 10px 16px;
  border-radius: var(--radius-md);
  margin: 8px 0;
  font-size: var(--font-size-sm);
}
.article-content :deep(.callout.danger) { background: var(--color-danger-bg); }
.article-content :deep(.callout.success) { background: var(--color-success-bg); }
.article-content :deep(.callout.info) { background: var(--color-primary-50); }
.article-content :deep(.check-item) { padding: 4px 0; font-size: var(--font-size-sm); }
.article-content :deep(.check-item.done) { color: var(--color-success); }
</style>

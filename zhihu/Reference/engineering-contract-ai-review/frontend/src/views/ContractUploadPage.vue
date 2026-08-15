<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { UploadFilled } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { fetchContractDetail, uploadContract } from "../api/contracts";

const router = useRouter();
const route = useRoute();
const uploading = ref(false);
const fileList = ref([]);
const versionSource = ref(null);

async function handleChange(uploadFile) {
  fileList.value = [uploadFile];
}

async function loadVersionSource() {
  const versionOfContractId = route.query.version_of_contract_id;
  if (!versionOfContractId) {
    versionSource.value = null;
    return;
  }
  try {
    const { data } = await fetchContractDetail(versionOfContractId);
    versionSource.value = data;
  } catch (error) {
    versionSource.value = null;
    ElMessage.error(error.response?.data?.detail || "获取基准合同版本失败");
  }
}

async function submitUpload() {
  const file = fileList.value[0]?.raw;
  if (!file) {
    ElMessage.warning("请先选择 PDF 文件");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  uploading.value = true;
  try {
    const { data } = await uploadContract(formData, route.query.version_of_contract_id || null);
    ElMessage.success(data.parse_status === "processing" ? "上传成功，后台 OCR 识别已开始" : "上传成功");
    router.push(`/contracts/${data.file_id}`);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "上传失败");
  } finally {
    uploading.value = false;
  }
}

onMounted(loadVersionSource);
</script>

<template>
  <div class="page-stack">
    <el-card>
      <template #header>
        <div>
          <h3>📤 上传你的合同</h3>
          <p>
            {{
              versionSource
                ? `将作为合同组 ${versionSource.contract_group_id} 的新版本上传，基于 V${versionSource.upload_version_no} 追加。`
                : "把合同文件传上来，我会帮你仔细看看里面的条款。支持 PDF 等格式，扫描件也没问题。"
            }}
          </p>
        </div>
      </template>

      <el-alert
        v-if="versionSource"
        type="info"
        :closable="false"
        class="page-note"
        :title="`将作为上传版本 V${versionSource.version_count + 1}`"
        :description="`基准文件：${versionSource.original_filename}；当前合同组共 ${versionSource.version_count} 个上传版本。`"
      />

      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".pdf,.docx,.doc,.xlsx,.xls,.md,.markdown,.txt,.csv,.json,.html,.htm"
        :file-list="fileList"
        :on-change="handleChange"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">把文件拖到这里，或者点击选择</div>
        <template #tip>
          <div class="el-upload__tip">📎 支持 PDF、Word、Excel、Markdown、纯文本等格式，不超过 50MB</div>
        </template>
      </el-upload>

      <div class="upload-actions">
        <el-button type="primary" :loading="uploading" @click="submitUpload">
          🚀 开始上传
        </el-button>
      </div>
    </el-card>
  </div>
</template>

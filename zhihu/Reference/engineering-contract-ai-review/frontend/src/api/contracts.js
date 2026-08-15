import http from "./http";

export function fetchContracts(params) {
  return http.get("/contracts", { params });
}

export function fetchContractDetail(contractId) {
  return http.get(`/contracts/${contractId}`);
}

export function uploadContract(formData, versionOfContractId = null) {
  return http.post("/contracts/upload", formData, {
    params: versionOfContractId ? { version_of_contract_id: versionOfContractId } : undefined,
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function updateContractMetadata(contractId, payload) {
  return http.patch(`/contracts/${contractId}`, payload);
}

export function reviewContract(contractId, perspective = "enterprise") {
  return http.post(`/contracts/${contractId}/review`, null, {
    params: { perspective },
  });
}

export function fetchPerspectives() {
  return http.get("/contracts/perspectives/list");
}

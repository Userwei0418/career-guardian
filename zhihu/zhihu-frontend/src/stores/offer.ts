import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "@/lib/api";

export interface OfferFieldData {
  value: string | null;
  confidence: number;
  evidence_text: string | null;
}

export interface OfferData {
  company_name: OfferFieldData;
  job_title: OfferFieldData;
  city: OfferFieldData;
  monthly_salary: OfferFieldData;
  salary_months: OfferFieldData;
  fixed_salary: OfferFieldData;
  variable_salary: OfferFieldData;
  bonus: OfferFieldData;
  allowance: OfferFieldData;
  probation_months: OfferFieldData;
  probation_salary_rate: OfferFieldData;
  work_location: OfferFieldData;
  working_hours: OfferFieldData;
  start_date: OfferFieldData;
}

export interface SavedOfferData {
  id: number;
  case_id: number;
  name: string | null;
  job_target_id: number | null;
  source_attachment_id: number | null;
  offer_kind: "verbal" | "written";
  response_deadline: string | null;
  extraction_confidence: number | null;
  company_name: string | null;
  job_title: string | null;
  city: string | null;
  monthly_salary: number | null;
  salary_months: number | null;
  fixed_salary: number | null;
  variable_salary: number | null;
  bonus: string | null;
  allowance: number | null;
  probation_months: number | null;
  probation_salary_rate: number | null;
  work_location: string | null;
  working_hours: string | null;
  start_date: string | null;
}

const emptyField = (): OfferFieldData => ({ value: null, confidence: 1.0, evidence_text: null });

const emptyOffer = (): OfferData => ({
  company_name: emptyField(),
  job_title: emptyField(),
  city: emptyField(),
  monthly_salary: emptyField(),
  salary_months: emptyField(),
  fixed_salary: emptyField(),
  variable_salary: emptyField(),
  bonus: emptyField(),
  allowance: emptyField(),
  probation_months: emptyField(),
  probation_salary_rate: emptyField(),
  work_location: emptyField(),
  working_hours: emptyField(),
  start_date: emptyField(),
});

interface OfferState {
  currentStep: number;
  offerData: OfferData;
  overallConfidence: number;
  caseId: number | null;
  offerId: number | null;
  offerName: string | null;
  jobTargetId: number | null;
  sourceAttachmentId: number | null;
  offerKind: "verbal" | "written";
  responseDeadline: string | null;
  preferences: {
    priorities: string[];
    current_city: string;
    monthly_budget: number | null;
    savings_goal: number | null;
  };

  setStep: (step: number) => void;
  setOfferData: (data: Partial<OfferData>) => void;
  updateField: (field: keyof OfferData, value: string | null, confidence?: number) => void;
  setExtractionResult: (fields: OfferData, confidence: number) => void;
  setCaseId: (id: number) => void;
  setOfferId: (id: number) => void;
  setOfferName: (name: string | null) => void;
  setJobTargetId: (id: number | null) => void;
  setSourceAttachmentId: (id: number | null) => void;
  setOfferKind: (kind: "verbal" | "written") => void;
  setResponseDeadline: (value: string | null) => void;
  startNewDraft: (targetId?: number | null) => void;
  setPreferences: (prefs: Partial<OfferState["preferences"]>) => void;
  createCaseAndOffer: () => Promise<{ caseId: number; offerId: number }>;
  hydrateSavedOffer: (offer: SavedOfferData) => void;
  updateSavedOffer: (offerId: number) => Promise<void>;
  reset: () => void;
}

function offerPayload(state: Pick<OfferState, "offerData" | "offerName" | "jobTargetId" | "sourceAttachmentId" | "offerKind" | "responseDeadline" | "overallConfidence">) {
  const { offerData, offerName, jobTargetId, sourceAttachmentId, offerKind, responseDeadline, overallConfidence } = state;
  return {
    name: offerName,
    job_target_id: jobTargetId,
    source_attachment_id: sourceAttachmentId,
    offer_kind: offerKind,
    response_deadline: responseDeadline || null,
    extraction_confidence: overallConfidence || null,
    confirm_facts: true,
    company_name: offerData.company_name?.value || null,
    job_title: offerData.job_title?.value || null,
    city: offerData.city?.value || null,
    monthly_salary: offerData.monthly_salary?.value ? parseFloat(offerData.monthly_salary.value) : null,
    salary_months: offerData.salary_months?.value ? parseInt(offerData.salary_months.value) : null,
    fixed_salary: offerData.fixed_salary?.value ? parseFloat(offerData.fixed_salary.value) : null,
    variable_salary: offerData.variable_salary?.value ? parseFloat(offerData.variable_salary.value) : null,
    bonus: offerData.bonus?.value || null,
    allowance: offerData.allowance?.value ? parseFloat(offerData.allowance.value) : null,
    probation_months: offerData.probation_months?.value ? parseInt(offerData.probation_months.value) : null,
    probation_salary_rate: offerData.probation_salary_rate?.value ? parseFloat(offerData.probation_salary_rate.value) : null,
    work_location: offerData.work_location?.value || null,
    working_hours: offerData.working_hours?.value || null,
    start_date: offerData.start_date?.value || null,
  };
}

export const useOfferStore = create<OfferState>()(persist((set, get) => ({
  currentStep: 1,
  offerData: emptyOffer(),
  overallConfidence: 0,
  caseId: null,
  offerId: null,
  offerName: null,
  jobTargetId: null,
  sourceAttachmentId: null,
  offerKind: "written",
  responseDeadline: null,
  preferences: {
    priorities: [],
    current_city: "",
    monthly_budget: null,
    savings_goal: null,
  },

  setStep: (step) => set({ currentStep: step }),
  setOfferData: (data) =>
    set((state) => ({ offerData: { ...state.offerData, ...data } })),
  updateField: (field, value, confidence = 1.0) =>
    set((state) => ({
      offerData: {
        ...state.offerData,
        [field]: { value, confidence, evidence_text: null },
      },
    })),
  setExtractionResult: (fields, confidence) =>
    set({ offerData: fields, overallConfidence: confidence }),
  setCaseId: (id) => set({ caseId: id }),
  setOfferId: (id) => set({ offerId: id }),
  setOfferName: (name) => set({ offerName: name }),
  setJobTargetId: (id) => set({ jobTargetId: id }),
  setSourceAttachmentId: (id) => set({ sourceAttachmentId: id }),
  setOfferKind: (kind) => set({ offerKind: kind }),
  setResponseDeadline: (value) => set({ responseDeadline: value }),
  startNewDraft: (targetId = null) => set({
    currentStep: 1,
    offerData: emptyOffer(),
    overallConfidence: 0,
    caseId: null,
    offerId: null,
    offerName: null,
    jobTargetId: targetId,
    sourceAttachmentId: null,
    offerKind: "written",
    responseDeadline: null,
    preferences: { priorities: [], current_city: "", monthly_budget: null, savings_goal: null },
  }),
  setPreferences: (prefs) =>
    set((state) => ({ preferences: { ...state.preferences, ...prefs } })),
  createCaseAndOffer: async () => {
    const { offerData, offerName } = get();
    const companyName = offerData.company_name?.value || "新";
    const caseRes = await api.post<{ id: number }>("/cases/", {
      type: "offer_analysis",
      title: offerName || `${companyName} Offer 分析`,
    });
    const payload = {
      case_id: caseRes.id,
      ...offerPayload(get()),
    };
    const offerRes = await api.post<{ id: number; case_id: number }>("/offers/", payload);
    set({ caseId: caseRes.id, offerId: offerRes.id });
    return { caseId: caseRes.id, offerId: offerRes.id };
  },
  hydrateSavedOffer: (offer) => {
    const fields = emptyOffer();
    (Object.keys(fields) as (keyof OfferData)[]).forEach((key) => {
      const value = offer[key as keyof SavedOfferData];
      fields[key] = { value: value == null ? null : String(value), confidence: 1, evidence_text: null };
    });
    set({
      currentStep: 2,
      offerData: fields,
      overallConfidence: offer.extraction_confidence ?? 1,
      caseId: offer.case_id,
      offerId: offer.id,
      offerName: offer.name,
      jobTargetId: offer.job_target_id,
      sourceAttachmentId: offer.source_attachment_id,
      offerKind: offer.offer_kind,
      responseDeadline: offer.response_deadline ? offer.response_deadline.slice(0, 16) : null,
    });
  },
  updateSavedOffer: async (offerId) => {
    await api.put(`/offers/${offerId}`, offerPayload(get()));
  },
  reset: () =>
    set({
      currentStep: 1,
      offerData: emptyOffer(),
      overallConfidence: 0,
      caseId: null,
      offerId: null,
      offerName: null,
      jobTargetId: null,
      sourceAttachmentId: null,
      offerKind: "written",
      responseDeadline: null,
      preferences: { priorities: [], current_city: "", monthly_budget: null, savings_goal: null },
    }),
}), {
  name: "zhihu-offer",
  partialize: (state) => ({
    currentStep: state.currentStep,
    offerData: state.offerData,
    overallConfidence: state.overallConfidence,
    caseId: state.caseId,
    offerId: state.offerId,
    offerName: state.offerName,
    jobTargetId: state.jobTargetId,
    sourceAttachmentId: state.sourceAttachmentId,
    offerKind: state.offerKind,
    responseDeadline: state.responseDeadline,
    preferences: state.preferences,
  }),
}));

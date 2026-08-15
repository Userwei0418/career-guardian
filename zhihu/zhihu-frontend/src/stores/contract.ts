import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ContractState {
  contractId: number | null;
  linkedOfferId: number | null;
  setContractId: (id: number) => void;
  setLinkedOfferId: (id: number | null) => void;
  reset: () => void;
}

export const useContractStore = create<ContractState>()(persist((set) => ({
  contractId: null,
  linkedOfferId: null,
  setContractId: (id) => set({ contractId: id }),
  setLinkedOfferId: (id) => set({ linkedOfferId: id }),
  reset: () => set({ contractId: null, linkedOfferId: null }),
}), {
  name: "zhihu-contract",
}));

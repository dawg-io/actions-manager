import React, { createContext, useContext } from 'react';

export interface StepSelection {
  jobId: string;
  stepId: string;
}

interface StepSelectionValue {
  selected: StepSelection | null;
  onSelect: (selection: StepSelection | null) => void;
}

// Defaults to a no-op so StepCard still renders outside a provider - in tests,
// and in any future caller that doesn't want the detail panel.
const StepSelectionContext = createContext<StepSelectionValue>({
  selected: null,
  onSelect: () => {},
});

export const StepSelectionProvider = StepSelectionContext.Provider;

export const useStepSelection = (): StepSelectionValue => useContext(StepSelectionContext);

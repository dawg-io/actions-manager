import { useCallback } from 'react';
import { handleAIChatMessage } from '../utils/aiWorkflowUtils';
import { UnifiedWorkflowItem, AIChatMessage } from '../types/workflow';

export interface UseAIChatLogicProps {
  aiSessionId: string;
  setIsAILoading: (loading: boolean) => void;
  setAIChatMessages: (messages: AIChatMessage[] | ((prev: AIChatMessage[]) => AIChatMessage[])) => void;
}

export const useAIChatLogic = ({
  aiSessionId,
  setIsAILoading,
  setAIChatMessages
}: UseAIChatLogicProps) => {
  
  const handleAIChatMessageWrapper = useCallback(async (
    message: string,
    selectedWorkflow: UnifiedWorkflowItem | undefined,
    handleWorkflowChange: (field: string, value: string) => void
  ) => {
    setIsAILoading(true);
    try {
      await handleAIChatMessage(
        message,
        aiSessionId,
        selectedWorkflow?.content,
        setAIChatMessages,
        handleWorkflowChange
      );
    } catch (error: any) {
      const errorMessage: AIChatMessage = {
        type: "error",
        message: `Error: ${error.message}`,
        timestamp: new Date().toISOString()
      };
      setAIChatMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsAILoading(false);
    }
  }, [aiSessionId, setIsAILoading, setAIChatMessages]);

  return { handleAIChatMessageWrapper };
};
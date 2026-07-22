import {
  generateRegularWorkflowWithAI,
  generateReusableWorkflowWithAI,
  editWithAI,
  handleAIChatMessage
} from './aiWorkflowUtils';
import { 
  generateWorkflowWithAI, 
  generateReusableWorkflowWithAI as generateReusableWorkflowAPI,
  sendChatMessage,
  editWorkflowWithAI,
  checkAIIntegration 
} from '../api/aiWorkflows';
import { Workflow, RXWorkflow, DetectedBuildResult } from '../types/workflow';

// Mock the API modules
vi.mock('../api/aiWorkflows');

// Mock toast to capture notifications
vi.mock('./toast', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
  },
}));

import { toast } from './toast';

describe('aiWorkflowUtils', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('generateRegularWorkflowWithAI', () => {
    const mockSetWorkflows = jest.fn();
    const mockSetAISessionId = jest.fn();
    const mockSetSelectedWorkflowId = jest.fn();
    const mockSetAIChatMessages = jest.fn();
    const mockSetShowAIChat = jest.fn();

    test('should alert if no repositories selected', async () => {
      await generateRegularWorkflowWithAI(
        [], 'TestProject', null, [], [], '', 'testuser',
        mockSetWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Please select repositories first')
      );
      expect(checkAIIntegration).not.toHaveBeenCalled();
    });

    test('should alert if AI integration is not configured', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(false);

      await generateRegularWorkflowWithAI(
        ['owner/repo'], 'TestProject', null, [], [], '', 'testuser',
        mockSetWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(checkAIIntegration).toHaveBeenCalled();
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('AI integration is not configured')
      );
      expect(generateWorkflowWithAI).not.toHaveBeenCalled();
    });

    test('should generate workflow with AI successfully', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(true);
      (generateWorkflowWithAI as jest.Mock).mockResolvedValue({
        session_id: 'session123',
        workflow_yaml: 'name: CI\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest',
        explanation: 'Generated workflow for your project'
      });

      const detectedBuildTypes: DetectedBuildResult[] = [
        {
          repo: 'owner/repo',
          detected_build_types: [
            { name: 'Node.js', technology: 'node', confidence: 0.9 }
          ]
        }
      ];

      await generateRegularWorkflowWithAI(
        ['owner/repo'], 'TestProject', 'PRJ123', detectedBuildTypes, [], 'custom-workflow', 'testuser',
        mockSetWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(generateWorkflowWithAI).toHaveBeenCalledWith(
        expect.objectContaining({
          user: 'testuser',
          project_name: 'TestProject',
          project_code: 'PRJ123',
          repository_info: {
            selected_repos: ['owner/repo'],
            repo_count: 1
          },
          build_types: ['node']
        })
      );

      expect(mockSetAISessionId).toHaveBeenCalledWith('session123');
      expect(mockSetWorkflows).toHaveBeenCalled();
      expect(mockSetSelectedWorkflowId).toHaveBeenCalledWith('regular-0');
      expect(mockSetAIChatMessages).toHaveBeenCalled();
      expect(mockSetShowAIChat).toHaveBeenCalledWith(true);
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('AI workflow')
      );
    });

    test('should handle empty build types', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(true);
      (generateWorkflowWithAI as jest.Mock).mockResolvedValue({
        session_id: 'session123',
        workflow_yaml: 'name: CI\non: push',
        explanation: 'Generated workflow'
      });

      await generateRegularWorkflowWithAI(
        ['owner/repo'], 'TestProject', null, [], [], '', 'testuser',
        mockSetWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(generateWorkflowWithAI).toHaveBeenCalledWith(
        expect.objectContaining({
          build_types: []
        })
      );
    });

    test('should handle API errors', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(true);
      (generateWorkflowWithAI as jest.Mock).mockRejectedValue(
        new Error('API Error')
      );

      await generateRegularWorkflowWithAI(
        ['owner/repo'], 'TestProject', null, [], [], '', 'testuser',
        mockSetWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to generate AI workflow')
      );
    });
  });

  describe('generateReusableWorkflowWithAI', () => {
    const mockSetRXWorkflows = jest.fn();
    const mockSetAISessionId = jest.fn();
    const mockSetSelectedWorkflowId = jest.fn();
    const mockSetAIChatMessages = jest.fn();
    const mockSetShowAIChat = jest.fn();

    test('should alert if no repositories selected', async () => {
      await generateReusableWorkflowWithAI(
        [], 'TestProject', null, [], '', 'testuser',
        mockSetRXWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Please select repositories first')
      );
    });

    test('should generate reusable workflow successfully', async () => {
      (generateReusableWorkflowAPI as jest.Mock).mockResolvedValue({
        session_id: 'session456',
        reusable_workflow_yaml: 'name: Reusable\non:\n  workflow_call:',
        explanation: 'Generated reusable workflow'
      });

      const detectedBuildTypes: DetectedBuildResult[] = [
        {
          repo: 'owner/repo',
          detected_build_types: [
            { name: 'Python', technology: 'python', confidence: 0.85 }
          ]
        }
      ];

      await generateReusableWorkflowWithAI(
        ['owner/repo'], 'TestProject', 'PRJ123', detectedBuildTypes, 'custom-reusable', 'testuser',
        mockSetRXWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(generateReusableWorkflowAPI).toHaveBeenCalledWith(
        expect.objectContaining({
          user: 'testuser',
          project_name: 'TestProject',
          build_types: ['python']
        })
      );

      expect(mockSetAISessionId).toHaveBeenCalledWith('session456');
      expect(mockSetRXWorkflows).toHaveBeenCalled();
      expect(mockSetAIChatMessages).toHaveBeenCalled();
      expect(mockSetShowAIChat).toHaveBeenCalledWith(true);
    });

    test('should handle empty build types for reusable workflow', async () => {
      (generateReusableWorkflowAPI as jest.Mock).mockResolvedValue({
        session_id: 'session456',
        reusable_workflow_yaml: 'name: Reusable\non:\n  workflow_call:',
        explanation: 'Generated reusable workflow'
      });

      await generateReusableWorkflowWithAI(
        ['owner/repo'], 'TestProject', null, [], '', 'testuser',
        mockSetRXWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(generateReusableWorkflowAPI).toHaveBeenCalledWith(
        expect.objectContaining({
          build_types: []
        })
      );
    });

    test('should handle API errors for reusable workflow', async () => {
      (generateReusableWorkflowAPI as jest.Mock).mockRejectedValue(
        new Error('Network Error')
      );

      await generateReusableWorkflowWithAI(
        ['owner/repo'], 'TestProject', null, [], '', 'testuser',
        mockSetRXWorkflows, mockSetAISessionId, mockSetSelectedWorkflowId,
        mockSetAIChatMessages, mockSetShowAIChat
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to generate AI reusable workflow')
      );
    });
  });

  describe('editWithAI', () => {
    const workflows: Workflow[] = [
      { name: 'test-workflow', content: 'name: CI\non: push', isReusable: false }
    ];
    const rxworkflows: RXWorkflow[] = [
      { name: 'rx-workflow', content: 'name: RX\non:\n  workflow_call:', isReusable: true }
    ];

    const mockSetAISessionId = jest.fn();
    const mockSetAIChatMessages = jest.fn();
    const mockSetShowAIChat = jest.fn();
    const mockSetEditingWorkflowIndex = jest.fn();
    const mockSetEditingWorkflowType = jest.fn();

    test('should alert if workflow has no content', async () => {
      const emptyWorkflows: Workflow[] = [
        { name: 'test', content: '', isReusable: false }
      ];

      await editWithAI(
        0, 'regular', 'improve', emptyWorkflows, rxworkflows, 'testuser',
        'TestProject', null, [], [], '',
        mockSetAISessionId, mockSetAIChatMessages, mockSetShowAIChat,
        mockSetEditingWorkflowIndex, mockSetEditingWorkflowType
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Please provide workflow content')
      );
      expect(checkAIIntegration).not.toHaveBeenCalled();
    });

    test('should alert if AI integration is not configured', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(false);

      await editWithAI(
        0, 'regular', 'improve', workflows, rxworkflows, 'testuser',
        'TestProject', null, [], [], '',
        mockSetAISessionId, mockSetAIChatMessages, mockSetShowAIChat,
        mockSetEditingWorkflowIndex, mockSetEditingWorkflowType
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('AI integration is not configured')
      );
    });

    test('should edit regular workflow with AI successfully', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(true);
      (editWorkflowWithAI as jest.Mock).mockResolvedValue({
        session_id: 'edit-session-123',
        workflow_analysis: 'Your workflow looks good but could be improved',
        updated_workflow: 'name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest'
      });

      const response = await editWithAI(
        0, 'regular', 'improve', workflows, rxworkflows, 'testuser',
        'TestProject', 'PRJ123', ['owner/repo'], [], 'Use Node 20',
        mockSetAISessionId, mockSetAIChatMessages, mockSetShowAIChat,
        mockSetEditingWorkflowIndex, mockSetEditingWorkflowType
      );

      expect(mockSetEditingWorkflowIndex).toHaveBeenCalledWith(0);
      expect(mockSetEditingWorkflowType).toHaveBeenCalledWith('regular');
      expect(editWorkflowWithAI).toHaveBeenCalledWith(
        expect.objectContaining({
          user: 'testuser',
          workflow_name: 'test-workflow',
          current_workflow: 'name: CI\non: push',
          action: 'improve',
          optional_instruction: 'Use Node 20'
        })
      );
      expect(mockSetAISessionId).toHaveBeenCalledWith('edit-session-123');
      expect(mockSetAIChatMessages).not.toHaveBeenCalled();
      expect(mockSetShowAIChat).not.toHaveBeenCalled();
      expect(response?.updated_workflow).toContain('jobs:');
    });

    test('should edit reusable workflow with AI successfully', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(true);
      (editWorkflowWithAI as jest.Mock).mockResolvedValue({
        session_id: 'edit-session-456',
        workflow_analysis: 'Reusable workflow analysis',
        updated_workflow: 'name: RX\non:\n  workflow_call:\njobs: {}'
      });

      await editWithAI(
        0, 'reusable', 'make_reusable', workflows, rxworkflows, 'testuser',
        'TestProject', null, [], [], '',
        mockSetAISessionId, mockSetAIChatMessages, mockSetShowAIChat,
        mockSetEditingWorkflowIndex, mockSetEditingWorkflowType
      );

      expect(mockSetEditingWorkflowType).toHaveBeenCalledWith('reusable');
      expect(editWorkflowWithAI).toHaveBeenCalledWith(
        expect.objectContaining({
          workflow_name: 'rx-workflow',
          current_workflow: 'name: RX\non:\n  workflow_call:',
          action: 'make_reusable'
        })
      );
    });

    test('should handle API errors during edit', async () => {
      (checkAIIntegration as jest.Mock).mockResolvedValue(true);
      (editWorkflowWithAI as jest.Mock).mockRejectedValue(
        new Error('Edit failed')
      );

      await editWithAI(
        0, 'regular', 'improve', workflows, rxworkflows, 'testuser',
        'TestProject', null, [], [], '',
        mockSetAISessionId, mockSetAIChatMessages, mockSetShowAIChat,
        mockSetEditingWorkflowIndex, mockSetEditingWorkflowType
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to analyze workflow with AI')
      );
    });
  });

  describe('handleAIChatMessage', () => {
    const mockSetAIChatMessages = jest.fn();
    const mockHandleWorkflowChange = jest.fn();

    test('should send chat message and update messages', async () => {
      (sendChatMessage as jest.Mock).mockResolvedValue({
        response_message: 'AI response message',
        workflow_updates: ['Updated step 1'],
        updated_workflow: null
      });

      await handleAIChatMessage(
        'User message', 'session123', 'workflow content',
        mockSetAIChatMessages, mockHandleWorkflowChange
      );

      expect(mockSetAIChatMessages).toHaveBeenCalledTimes(2);
      expect(sendChatMessage).toHaveBeenCalledWith(
        'session123', 'User message', 'workflow content'
      );

      // Check user message was added
      const firstCall = (mockSetAIChatMessages as jest.Mock).mock.calls[0][0];
      const userMessages = firstCall([]);
      expect(userMessages[0]).toMatchObject({
        type: 'user',
        message: 'User message'
      });

      // Check AI response was added
      const secondCall = (mockSetAIChatMessages as jest.Mock).mock.calls[1][0];
      const aiMessages = secondCall([]);
      expect(aiMessages[0]).toMatchObject({
        type: 'ai',
        message: 'AI response message',
        workflow_updates: ['Updated step 1']
      });
    });

    test('should update workflow if AI provides updates', async () => {
      (sendChatMessage as jest.Mock).mockResolvedValue({
        response_message: 'Updated your workflow',
        workflow_updates: [],
        updated_workflow: 'name: Updated CI\non: push'
      });

      await handleAIChatMessage(
        'Update the workflow', 'session123', 'old content',
        mockSetAIChatMessages, mockHandleWorkflowChange
      );

      expect(mockHandleWorkflowChange).toHaveBeenCalledWith(
        'content', 'name: Updated CI\non: push'
      );
    });

    test('should not call handleWorkflowChange if not provided', async () => {
      (sendChatMessage as jest.Mock).mockResolvedValue({
        response_message: 'Response',
        workflow_updates: [],
        updated_workflow: 'new content'
      });

      await handleAIChatMessage(
        'Message', 'session123', 'content',
        mockSetAIChatMessages, undefined
      );

      // Should not throw error
      expect(mockSetAIChatMessages).toHaveBeenCalled();
    });

    test('should handle undefined workflow content', async () => {
      (sendChatMessage as jest.Mock).mockResolvedValue({
        response_message: 'Response',
        workflow_updates: [],
        updated_workflow: null
      });

      await handleAIChatMessage(
        'Message', 'session123', undefined,
        mockSetAIChatMessages, mockHandleWorkflowChange
      );

      expect(sendChatMessage).toHaveBeenCalledWith(
        'session123', 'Message', undefined
      );
    });
  });
});

import { 
  detectBuildTypesForRepos, 
  addWorkflowFromDetection, 
  generateTemplates,
  selectTemplate 
} from './buildDetectionUtils';
import { detectBuildTypes, suggestWorkflow } from '../api/repos';
import { generateWorkflowTemplates } from '../api/workflowTemplates';
import { Workflow, BuildType, DetectedBuildResult, WorkflowTemplate } from '../types/workflow';

// Mock the API modules
vi.mock('../api/repos');
vi.mock('../api/workflowTemplates');

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

describe('buildDetectionUtils', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('detectBuildTypesForRepos', () => {
    test('should alert if no repositories selected', async () => {
      const setDetectedBuildTypes = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();

      await detectBuildTypesForRepos(
        [], 'testuser', setDetectedBuildTypes, 
        setShowDetectionResults, setShowDetectionResultsInModal
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Please select repositories first')
      );
      expect(detectBuildTypes).not.toHaveBeenCalled();
    });

    test('should detect build types for multiple repositories', async () => {
      const setDetectedBuildTypes = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const selectedRepos = ['owner1/repo1', 'owner2/repo2'];

      const mockBuildTypes1 = {
        detected_build_types: [
          { name: 'Node.js', technology: 'node', confidence: 0.9 }
        ]
      };
      const mockBuildTypes2 = {
        detected_build_types: [
          { name: 'Python', technology: 'python', confidence: 0.85 }
        ]
      };

      (detectBuildTypes as jest.Mock)
        .mockResolvedValueOnce(mockBuildTypes1)
        .mockResolvedValueOnce(mockBuildTypes2);

      await detectBuildTypesForRepos(
        selectedRepos, 'testuser', setDetectedBuildTypes,
        setShowDetectionResults, setShowDetectionResultsInModal
      );

      expect(detectBuildTypes).toHaveBeenCalledTimes(2);
      expect(detectBuildTypes).toHaveBeenCalledWith('testuser', 'owner1', 'repo1');
      expect(detectBuildTypes).toHaveBeenCalledWith('testuser', 'owner2', 'repo2');
      
      expect(setDetectedBuildTypes).toHaveBeenCalledWith([
        { repo: 'owner1/repo1', ...mockBuildTypes1 },
        { repo: 'owner2/repo2', ...mockBuildTypes2 }
      ]);
      expect(setShowDetectionResultsInModal).toHaveBeenCalledWith(true);
    });

    test('should handle detection errors', async () => {
      const setDetectedBuildTypes = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const selectedRepos = ['owner/repo'];

      (detectBuildTypes as jest.Mock).mockRejectedValue(new Error('API Error'));

      await detectBuildTypesForRepos(
        selectedRepos, 'testuser', setDetectedBuildTypes,
        setShowDetectionResults, setShowDetectionResultsInModal
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Error detecting build types')
      );
    });

    test('should filter out invalid repository names', async () => {
      const setDetectedBuildTypes = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const selectedRepos = ['valid/repo', 'invalid', '', null as any];

      (detectBuildTypes as jest.Mock).mockResolvedValue({
        detected_build_types: []
      });

      await detectBuildTypesForRepos(
        selectedRepos, 'testuser', setDetectedBuildTypes,
        setShowDetectionResults, setShowDetectionResultsInModal
      );

      expect(detectBuildTypes).toHaveBeenCalledTimes(1);
      expect(detectBuildTypes).toHaveBeenCalledWith('testuser', 'valid', 'repo');
    });

    test('should clear previous detection results', async () => {
      const setDetectedBuildTypes = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const selectedRepos = ['owner/repo'];

      (detectBuildTypes as jest.Mock).mockResolvedValue({
        detected_build_types: []
      });

      await detectBuildTypesForRepos(
        selectedRepos, 'testuser', setDetectedBuildTypes,
        setShowDetectionResults, setShowDetectionResultsInModal
      );

      expect(setDetectedBuildTypes).toHaveBeenCalledWith([]);
    });
  });

  describe('addWorkflowFromDetection', () => {
    const mockBuildType: BuildType = {
      name: 'Node.js',
      technology: 'node',
      confidence: 0.9
    };

    test('should create workflow from build type detection', async () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowWorkflowCreationDialog = jest.fn();
      const setWorkflowCreationType = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setDetectedBuildTypes = jest.fn();

      const mockWorkflowYaml = 'name: CI\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest';
      (suggestWorkflow as jest.Mock).mockResolvedValue(mockWorkflowYaml);

      await addWorkflowFromDetection(
        'owner/repo', mockBuildType, 'custom-workflow', workflows, 'PROJECT123', 'testuser',
        setWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog,
        setWorkflowCreationType, setShowDetectionResultsInModal,
        setShowDetectionResults, setDetectedBuildTypes
      );

      expect(suggestWorkflow).toHaveBeenCalledWith('testuser', 'owner', 'repo', 'Node.js');
      expect(setWorkflows).toHaveBeenCalledWith([
        {
          name: 'custom-workflow',
          content: 'name: custom-workflow\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest',
          isReusable: false,
          isModified: true
        }
      ]);
      expect(setSelectedWorkflowId).toHaveBeenCalledWith('regular-0');
      expect(setShowWorkflowCreationDialog).toHaveBeenCalledWith(false);
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('added to the project')
      );
    });

    test('should handle invalid repository name', async () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowWorkflowCreationDialog = jest.fn();
      const setWorkflowCreationType = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setDetectedBuildTypes = jest.fn();

      await addWorkflowFromDetection(
        'invalidrepo', mockBuildType, 'custom-workflow', workflows, null, 'testuser',
        setWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog,
        setWorkflowCreationType, setShowDetectionResultsInModal,
        setShowDetectionResults, setDetectedBuildTypes
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Repository name must be in format "owner/repo"')
      );
      expect(suggestWorkflow).not.toHaveBeenCalled();
    });

    test('should handle null build type', async () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowWorkflowCreationDialog = jest.fn();
      const setWorkflowCreationType = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setDetectedBuildTypes = jest.fn();

      await addWorkflowFromDetection(
        'owner/repo', null as any, 'custom-workflow', workflows, null, 'testuser',
        setWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog,
        setWorkflowCreationType, setShowDetectionResultsInModal,
        setShowDetectionResults, setDetectedBuildTypes
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Invalid build type')
      );
    });

    test('should handle API error response', async () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowWorkflowCreationDialog = jest.fn();
      const setWorkflowCreationType = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setDetectedBuildTypes = jest.fn();

      (suggestWorkflow as jest.Mock).mockResolvedValue({
        error: 'Failed to generate'
      });

      await addWorkflowFromDetection(
        'owner/repo', mockBuildType, 'custom-workflow', workflows, null, 'testuser',
        setWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog,
        setWorkflowCreationType, setShowDetectionResultsInModal,
        setShowDetectionResults, setDetectedBuildTypes
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to generate workflow')
      );
    });

    test('should handle empty workflow response', async () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowWorkflowCreationDialog = jest.fn();
      const setWorkflowCreationType = jest.fn();
      const setShowDetectionResultsInModal = jest.fn();
      const setShowDetectionResults = jest.fn();
      const setDetectedBuildTypes = jest.fn();

      (suggestWorkflow as jest.Mock).mockResolvedValue('   ');

      await addWorkflowFromDetection(
        'owner/repo', mockBuildType, 'custom-workflow', workflows, null, 'testuser',
        setWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog,
        setWorkflowCreationType, setShowDetectionResultsInModal,
        setShowDetectionResults, setDetectedBuildTypes
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Empty response from server')
      );
    });
  });

  describe('generateTemplates', () => {
    test('should alert if no repositories selected', async () => {
      const setTemplatesByType = jest.fn();
      const setShowTemplateModal = jest.fn();

      await generateTemplates(
        [], [], null, 'testuser', setTemplatesByType, setShowTemplateModal
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Please select repositories first')
      );
      expect(generateWorkflowTemplates).not.toHaveBeenCalled();
    });

    test('should generate templates based on detected build types', async () => {
      const setTemplatesByType = jest.fn();
      const setShowTemplateModal = jest.fn();
      const selectedRepos = ['owner/repo'];
      const detectedBuildTypes: DetectedBuildResult[] = [
        {
          repo: 'owner/repo',
          detected_build_types: [
            { name: 'Node.js', technology: 'node', confidence: 0.9 }
          ]
        }
      ];

      const mockTemplates = {
        templates: [
          { name: 'build-template', content: 'build yaml' },
          { name: 'reusable-template', content: 'reusable yaml' },
          { name: 'standard-template', content: 'standard yaml' }
        ]
      };

      (generateWorkflowTemplates as jest.Mock).mockResolvedValue(mockTemplates);

      await generateTemplates(
        selectedRepos, detectedBuildTypes, 'PROJECT123', 'testuser',
        setTemplatesByType, setShowTemplateModal
      );

      expect(generateWorkflowTemplates).toHaveBeenCalledWith('testuser', 'node', 'PROJECT123');
      expect(setTemplatesByType).toHaveBeenCalledWith({
        build: { name: 'build-template', content: 'build yaml' },
        reusable: { name: 'reusable-template', content: 'reusable yaml' },
        standard: { name: 'standard-template', content: 'standard yaml' }
      });
      expect(setShowTemplateModal).toHaveBeenCalledWith(true);
    });

    test('should use generic build type when no build types detected', async () => {
      const setTemplatesByType = jest.fn();
      const setShowTemplateModal = jest.fn();
      const selectedRepos = ['owner/repo'];
      const detectedBuildTypes: DetectedBuildResult[] = [];

      (generateWorkflowTemplates as jest.Mock).mockResolvedValue({
        templates: []
      });

      await generateTemplates(
        selectedRepos, detectedBuildTypes, null, 'testuser',
        setTemplatesByType, setShowTemplateModal
      );

      expect(generateWorkflowTemplates).toHaveBeenCalledWith('testuser', 'generic', null);
    });

    test('should handle empty templates response', async () => {
      const setTemplatesByType = jest.fn();
      const setShowTemplateModal = jest.fn();
      const selectedRepos = ['owner/repo'];

      (generateWorkflowTemplates as jest.Mock).mockResolvedValue({
        templates: null
      });

      await generateTemplates(
        selectedRepos, [], null, 'testuser',
        setTemplatesByType, setShowTemplateModal
      );

      expect(setTemplatesByType).toHaveBeenCalledWith({});
    });

    test('should handle template generation errors', async () => {
      const setTemplatesByType = jest.fn();
      const setShowTemplateModal = jest.fn();
      const selectedRepos = ['owner/repo'];

      (generateWorkflowTemplates as jest.Mock).mockRejectedValue(new Error('API Error'));

      await generateTemplates(
        selectedRepos, [], null, 'testuser',
        setTemplatesByType, setShowTemplateModal
      );

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to generate templates')
      );
    });
  });

  describe('selectTemplate', () => {
    const mockTemplate: WorkflowTemplate = {
      name: 'Test Template',
      content: 'name: CI\non: push'
    };

    test('should add regular workflow from template', () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setRXWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowTemplateModal = jest.fn();

      selectTemplate(
        mockTemplate, false, 'TestProject',
        workflows, setWorkflows, setRXWorkflows,
        setSelectedWorkflowId, setShowTemplateModal
      );

      expect(setWorkflows).toHaveBeenCalledWith([
        {
          name: expect.any(String),
          content: expect.stringContaining('on: push'),
          isReusable: false,
          isModified: true
        }
      ]);
      expect(setSelectedWorkflowId).toHaveBeenCalledWith('regular-0');
      expect(setShowTemplateModal).toHaveBeenCalledWith(false);
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('added to the project')
      );
    });

    test('should add reusable workflow from template', () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setRXWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowTemplateModal = jest.fn();

      selectTemplate(
        mockTemplate, true, 'TestProject',
        workflows, setWorkflows, setRXWorkflows,
        setSelectedWorkflowId, setShowTemplateModal
      );

      expect(setRXWorkflows).toHaveBeenCalledTimes(1);
      expect(setShowTemplateModal).toHaveBeenCalledWith(false);
      
      // Extract callback and test it
      const callback = (setRXWorkflows as jest.Mock).mock.calls[0][0];
      const result = callback([]);
      
      expect(result[0]).toMatchObject({
        name: expect.any(String),
        content: expect.stringContaining('on: push'),
        isReusable: true,
        isModified: true
      });
    });

    test('should handle existing workflows when adding regular workflow', () => {
      const workflows: Workflow[] = [
        { name: 'existing', content: 'test', isReusable: false }
      ];
      const setWorkflows = jest.fn();
      const setRXWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowTemplateModal = jest.fn();

      selectTemplate(
        mockTemplate, false, 'TestProject',
        workflows, setWorkflows, setRXWorkflows,
        setSelectedWorkflowId, setShowTemplateModal
      );

      expect(setSelectedWorkflowId).toHaveBeenCalledWith('regular-1');
    });

    test('should handle existing reusable workflows', () => {
      const workflows: Workflow[] = [];
      const setWorkflows = jest.fn();
      const setRXWorkflows = jest.fn();
      const setSelectedWorkflowId = jest.fn();
      const setShowTemplateModal = jest.fn();

      selectTemplate(
        mockTemplate, true, 'TestProject',
        workflows, setWorkflows, setRXWorkflows,
        setSelectedWorkflowId, setShowTemplateModal
      );

      const callback = (setRXWorkflows as jest.Mock).mock.calls[0][0];
      const result = callback([
        { name: 'existing-rx', content: 'test', isReusable: true }
      ]);
      
      expect(result).toHaveLength(2);
    });
  });
});

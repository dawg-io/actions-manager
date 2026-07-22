import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import UnifiedWorkflowList from './UnifiedWorkflowList';
import { UnifiedWorkflowItem } from '../types/workflow';

const regularWorkflow: UnifiedWorkflowItem = {
  id: 'regular-0',
  name: 'my-workflow',
  content: 'name: my-workflow\non: [push]',
  type: 'regular',
  isReusable: false,
  isModified: false,
  originalIndex: 0,
};

const reusableWorkflow: UnifiedWorkflowItem = {
  id: 'reusable-0',
  name: 'my-reusable',
  content: 'name: my-reusable\non: [workflow_call]',
  type: 'reusable',
  isReusable: true,
  isModified: false,
  originalIndex: 0,
};

const linkedWorkflowItem: UnifiedWorkflowItem = {
  id: 'linked-status-0',
  name: 'shared-deploy',
  content: 'name: shared-deploy\non:\n  workflow_call: {}',
  type: 'linked',
  isReusable: true,
  isModified: false,
  originalIndex: 0,
  rwxProjectId: 5,
  rwxProjectName: 'Shared RWX',
};

const baseProps = {
  selectedWorkflowId: null,
  isCollapsed: false,
  projectCode: 'PROJ',
  loadingStatuses: false,
  workflowStatuses: {},
  selectedRepos: [],
  reusableWorkflowsEnabled: true,
  repoExists: true,
  setIsCollapsed: jest.fn(),
  handleSelectWorkflow: jest.fn(),
};

describe('UnifiedWorkflowList', () => {
  describe('Prefix Mode (usePrefix=true)', () => {
    it('renders AM_PROJ_ prefix span for regular workflows', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          usePrefix={true}
          unifiedWorkflows={[regularWorkflow]}
        />
      );
      expect(screen.getByText('AM_PROJ_')).toBeInTheDocument();
      expect(screen.getByText('my-workflow.yml')).toBeInTheDocument();
    });

    it('renders AM_PROJ_ prefix span for reusable workflows', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          usePrefix={true}
          unifiedWorkflows={[reusableWorkflow]}
        />
      );
      expect(screen.getByText('AM_PROJ_')).toBeInTheDocument();
      expect(screen.getByText('my-reusable.yml')).toBeInTheDocument();
    });
  });

  describe('No Prefix Mode (usePrefix=false)', () => {
    it('does not render AM_PROJ_ prefix span for regular workflows', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          usePrefix={false}
          unifiedWorkflows={[regularWorkflow]}
        />
      );
      expect(screen.queryByText('AM_PROJ_')).not.toBeInTheDocument();
      expect(screen.getByText('my-workflow.yml')).toBeInTheDocument();
    });

    it('does not render AM_PROJ_ prefix span for reusable workflows', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          usePrefix={false}
          unifiedWorkflows={[reusableWorkflow]}
        />
      );
      expect(screen.queryByText('AM_PROJ_')).not.toBeInTheDocument();
      expect(screen.getByText('my-reusable.yml')).toBeInTheDocument();
    });
  });

  describe('default (usePrefix omitted — defaults to true)', () => {
    it('renders prefix span when usePrefix prop is not provided', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
        />
      );
      expect(screen.getByText('AM_PROJ_')).toBeInTheDocument();
    });
  });

  describe('Linked workflow display (source-of-truth naming)', () => {
    const linkedPrefixedWorkflow: UnifiedWorkflowItem = {
      id: 'linked-1',
      name: 'AM_RWW1_testrwx.yml',
      content: 'name: testrwx\non:\n  workflow_call: {}',
      type: 'linked',
      isReusable: true,
      isModified: false,
      originalIndex: 0,
      rwxProjectId: 1,
      rwxProjectName: 'My RWX Project',
    };

    const linkedUnprefixedWorkflow: UnifiedWorkflowItem = {
      id: 'linked-2',
      name: 'testrwx.yml',
      content: 'name: testrwx\non:\n  workflow_call: {}',
      type: 'linked',
      isReusable: true,
      isModified: false,
      originalIndex: 0,
      rwxProjectId: 2,
      rwxProjectName: 'My No-Prefix RWX Project',
    };

    it('preserves prefixed source name in No-Prefix consumer (does not strip prefix)', () => {
      // Consumer is No-Prefix Mode (usePrefix=false), source has prefix AM_RWW1_
      render(
        <UnifiedWorkflowList
          {...baseProps}
          usePrefix={false}
          unifiedWorkflows={[linkedPrefixedWorkflow]}
        />
      );
      // Full prefixed filename must appear exactly as delivered by the source project
      expect(screen.getByText('AM_RWW1_testrwx.yml')).toBeInTheDocument();
      // Consumer's prefix span must NOT be rendered for linked workflows
      expect(screen.queryByText('AM_PROJ_')).not.toBeInTheDocument();
    });

    it('preserves unprefixed source name in Prefix consumer (does not add prefix)', () => {
      // Consumer is Prefix Mode (usePrefix=true), source has no prefix
      render(
        <UnifiedWorkflowList
          {...baseProps}
          usePrefix={true}
          unifiedWorkflows={[linkedUnprefixedWorkflow]}
        />
      );
      // Plain filename from source must appear unchanged
      expect(screen.getByText('testrwx.yml')).toBeInTheDocument();
      // Consumer's prefix span must NOT be rendered for linked workflows
      expect(screen.queryByText('AM_PROJ_')).not.toBeInTheDocument();
    });

    it('preserves prefixed source name in Prefix consumer with different code', () => {
      // Both consumer (PROJ) and source (RWW1) are Prefix Mode, but only source code appears
      render(
        <UnifiedWorkflowList
          {...baseProps}
          usePrefix={true}
          unifiedWorkflows={[linkedPrefixedWorkflow]}
        />
      );
      expect(screen.getByText('AM_RWW1_testrwx.yml')).toBeInTheDocument();
      // Consumer prefix span (AM_PROJ_) must NOT be added for linked workflows
      expect(screen.queryByText('AM_PROJ_')).not.toBeInTheDocument();
    });
  });

  describe('Drift detection badge', () => {
    it('renders "Drift detected" badge for regular workflows whose names appear in driftedWorkflowNames', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
          driftedWorkflowNames={new Set(['my-workflow'])}
        />
      );
      expect(screen.getByText('Drift detected')).toBeInTheDocument();
    });

    it('renders "Drift detected" badge for reusable workflows whose names appear in driftedWorkflowNames', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[reusableWorkflow]}
          driftedWorkflowNames={new Set(['my-reusable'])}
        />
      );
      expect(screen.getByText('Drift detected')).toBeInTheDocument();
    });

    it('does not render the badge when the workflow is not in driftedWorkflowNames', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
          driftedWorkflowNames={new Set(['some-other-workflow'])}
        />
      );
      expect(screen.queryByText('Drift detected')).not.toBeInTheDocument();
    });

    it('does not render the badge when driftedWorkflowNames is omitted', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
        />
      );
      expect(screen.queryByText('Drift detected')).not.toBeInTheDocument();
    });
  });

  describe('Collapsed workflow navigation', () => {
    const longWorkflow: UnifiedWorkflowItem = {
      id: 'regular-long',
      name: 'very-long-build-workflow',
      content: 'name: very-long-build-workflow\non: [push]',
      type: 'regular',
      isReusable: false,
      isModified: false,
      originalIndex: 1,
      workflowStatus: 'under_review',
    };

    const linkedWorkflow: UnifiedWorkflowItem = {
      id: 'linked-compact',
      name: 'deploy-production',
      content: 'name: deploy-production\non:\n  workflow_call: {}',
      type: 'linked',
      isReusable: true,
      isModified: false,
      originalIndex: 2,
      rwxProjectId: 3,
      rwxProjectName: 'Reusable Source',
      rwxRepo: 'octo/reusable-source',
    };

    it('renders compact workflow items with abbreviated names, status, and accessible labels', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          isCollapsed
          selectedWorkflowId="regular-long"
          unifiedWorkflows={[regularWorkflow, longWorkflow]}
        />
      );

      expect(screen.getByRole('navigation', { name: 'Compact workflow navigation' })).toBeInTheDocument();
      expect(screen.getByText('my-workflow.yml')).toBeInTheDocument();
      expect(screen.getByText('very…yml')).toBeInTheDocument();
      expect(screen.queryByText('AM_PROJ_')).not.toBeInTheDocument();
      expect(screen.getByTitle('very-long-build-workflow.yml · Under Review')).toBeInTheDocument();

      const selected = screen.getByRole('button', {
        name: 'very-long-build-workflow.yml, Under Review',
      });
      expect(selected).toHaveAttribute('aria-current', 'page');
      expect(selected.querySelector('.workflow-compact-status-dot')).toHaveClass('status-review');
    });

    it('selects collapsed workflow items with the existing selection handler', async () => {
      const user = userEvent.setup();
      const handleSelectWorkflow = jest.fn();

      render(
        <UnifiedWorkflowList
          {...baseProps}
          isCollapsed
          handleSelectWorkflow={handleSelectWorkflow}
          unifiedWorkflows={[regularWorkflow]}
        />
      );

      await user.click(screen.getByRole('button', { name: 'my-workflow.yml, No status' }));
      expect(handleSelectWorkflow).toHaveBeenCalledWith('regular-0');
    });

    it('keeps linked workflows visible in a separate compact section with source details', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          isCollapsed
          unifiedWorkflows={[regularWorkflow, linkedWorkflow]}
        />
      );

      expect(screen.getByRole('region', { name: 'Linked workflows' })).toBeInTheDocument();
      expect(screen.getByTitle('Linked Workflows')).toBeInTheDocument();
      expect(screen.getByText('deploy…yml')).toBeInTheDocument();
      expect(
        screen.getByTitle('deploy-production.yml · Linked workflow · From: Reusable Source · Repo: octo/reusable-source')
      ).toBeInTheDocument();
    });
  });

  describe('Workflow status badge labels', () => {
    const mkWorkflow = (status: string): UnifiedWorkflowItem => ({
      ...regularWorkflow,
      id: `regular-${status}`,
      workflowStatus: status,
    });

    it('shows "New Local" for status new', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[mkWorkflow('new')]}
        />
      );
      expect(screen.getByText('New Local')).toBeInTheDocument();
    });

    it('shows "Committed Locally" for status committed_locally', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[mkWorkflow('committed_locally')]}
        />
      );
      expect(screen.getByText('Committed Locally')).toBeInTheDocument();
    });

    it('shows "Under Review" for status under_review', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[mkWorkflow('under_review')]}
        />
      );
      expect(screen.getByText('Under Review')).toBeInTheDocument();
    });

    it('shows "Synced" (not "Synced with GitHub") for status synced_with_github', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[mkWorkflow('synced_with_github')]}
        />
      );
      expect(screen.getByText('Synced')).toBeInTheDocument();
      expect(screen.queryByText('Synced with GitHub')).not.toBeInTheDocument();
    });

    it('renders no status badge when workflow has no status', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
        />
      );
      // No known status text should appear in the card area
      expect(screen.queryByText('New Local')).not.toBeInTheDocument();
      expect(screen.queryByText('Committed Locally')).not.toBeInTheDocument();
      expect(screen.queryByText('Synced')).not.toBeInTheDocument();
    });

    it('renders "Linked" badge for linked workflows', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[linkedWorkflowItem]}
        />
      );
      expect(screen.getByText('Linked')).toBeInTheDocument();
    });

    describe('linked workflow lifecycle status badges', () => {
      const mkLinkedWorkflow = (status: string): UnifiedWorkflowItem => ({
        ...linkedWorkflowItem,
        id: `linked-${status}`,
        workflowStatus: status,
      });

      it('shows "New Local" and "Linked" for linked workflow with status new', () => {
        render(
          <UnifiedWorkflowList
            {...baseProps}
            unifiedWorkflows={[mkLinkedWorkflow('new')]}
          />
        );
        expect(screen.getByText('New Local')).toBeInTheDocument();
        expect(screen.getByText('Linked')).toBeInTheDocument();
      });

      it('shows "Committed Locally" and "Linked" for linked workflow with status committed_locally', () => {
        render(
          <UnifiedWorkflowList
            {...baseProps}
            unifiedWorkflows={[mkLinkedWorkflow('committed_locally')]}
          />
        );
        expect(screen.getByText('Committed Locally')).toBeInTheDocument();
        expect(screen.getByText('Linked')).toBeInTheDocument();
      });

      it('shows "Under Review" and "Linked" for linked workflow with status under_review', () => {
        render(
          <UnifiedWorkflowList
            {...baseProps}
            unifiedWorkflows={[mkLinkedWorkflow('under_review')]}
          />
        );
        expect(screen.getByText('Under Review')).toBeInTheDocument();
        expect(screen.getByText('Linked')).toBeInTheDocument();
      });

      it('shows "Synced" and "Linked" for linked workflow with status synced_with_github', () => {
        render(
          <UnifiedWorkflowList
            {...baseProps}
            unifiedWorkflows={[mkLinkedWorkflow('synced_with_github')]}
          />
        );
        expect(screen.getByText('Synced')).toBeInTheDocument();
        expect(screen.getByText('Linked')).toBeInTheDocument();
      });

      it('shows only "Linked" badge when linked workflow has no status', () => {
        render(
          <UnifiedWorkflowList
            {...baseProps}
            unifiedWorkflows={[linkedWorkflowItem]}
          />
        );
        expect(screen.getByText('Linked')).toBeInTheDocument();
        expect(screen.queryByText('New Local')).not.toBeInTheDocument();
        expect(screen.queryByText('Committed Locally')).not.toBeInTheDocument();
        expect(screen.queryByText('Under Review')).not.toBeInTheDocument();
        expect(screen.queryByText('Synced')).not.toBeInTheDocument();
      });
    });
  });
});

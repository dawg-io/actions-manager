import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import UnifiedWorkflowList from './UnifiedWorkflowList';
import { UnifiedWorkflowItem } from '../types/workflow';
import { CustomFile } from '../api/customFiles';

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

const customFile: CustomFile = {
  id: 7,
  project_id: 1,
  display_name: 'Dependabot config',
  file_path: '.github/dependabot.yml',
  file_content: 'version: 2',
  git_hash: null,
  file_status: 'committed_locally',
  pending_delete: false,
  last_modified_by: null,
  description: null,
  created_at: null,
  updated_at: null,
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

/** The section's collapse toggle, found via the section's own accessible region. */
const sectionToggle = (name: string) =>
  within(screen.getByRole('region', { name })).getAllByRole('button')[0];

const getHandle = () => screen.getByRole('button', { name: /^Resize Project Files panel/ });

/** The width the panel actually renders at, straight off its custom property. */
const panelWidth = (container: HTMLElement) =>
  (container.querySelector('.unified-workflows-list') as HTMLElement).style.getPropertyValue(
    '--pf-panel-width'
  );

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
});

describe('UnifiedWorkflowList', () => {
  describe('Compact rows', () => {
    it('renders a single-line row with the bare filename and a status dot', () => {
      render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[regularWorkflow]} />);

      const row = screen.getByRole('button', { name: 'my-workflow.yml, No status' });
      expect(within(row).getByText('my-workflow.yml')).toBeInTheDocument();
      expect(row.querySelector('.pf-row-dot')).toHaveClass('status-none');
    });

    it('keeps the prefixed on-GitHub filename in the row tooltip instead of showing it inline', () => {
      render(<UnifiedWorkflowList {...baseProps} usePrefix unifiedWorkflows={[regularWorkflow]} />);

      // The prefix is detail — it belongs in the editor header, not the navigator.
      expect(screen.queryByText('AM_PROJ_')).not.toBeInTheDocument();
      expect(screen.getByTitle('AM_PROJ_my-workflow.yml · No status')).toBeInTheDocument();
    });

    it('omits the prefix from the tooltip in no-prefix mode', () => {
      render(<UnifiedWorkflowList {...baseProps} usePrefix={false} unifiedWorkflows={[regularWorkflow]} />);

      expect(screen.getByTitle('my-workflow.yml · No status')).toBeInTheDocument();
    });

    it('never applies the consumer prefix to linked workflows', () => {
      const linkedPrefixed: UnifiedWorkflowItem = {
        ...linkedWorkflowItem,
        id: 'linked-1',
        name: 'AM_RWW1_testrwx.yml',
        rwxProjectName: 'My RWX Project',
      };

      render(<UnifiedWorkflowList {...baseProps} usePrefix unifiedWorkflows={[linkedPrefixed]} />);

      expect(screen.getByText('AM_RWW1_testrwx.yml')).toBeInTheDocument();
      expect(screen.queryByTitle(/AM_PROJ_/)).not.toBeInTheDocument();
    });

    it('surfaces linked source details in the tooltip', () => {
      const linked: UnifiedWorkflowItem = {
        ...linkedWorkflowItem,
        name: 'deploy-production',
        rwxProjectName: 'Reusable Source',
        rwxRepo: 'octo/reusable-source',
      };

      render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[linked]} />);

      expect(
        screen.getByTitle(
          'deploy-production.yml · Linked workflow · No status · From: Reusable Source · Repo: octo/reusable-source'
        )
      ).toBeInTheDocument();
    });

    it('marks unsaved workflows with a modified indicator', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[{ ...regularWorkflow, isModified: true }]}
        />
      );

      const row = screen.getByRole('button', { name: 'my-workflow.yml, Unsaved changes' });
      expect(row.querySelector('.pf-row-modified')).toBeInTheDocument();
      expect(row.querySelector('.pf-row-dot')).toHaveClass('status-unsaved');
    });
  });

  describe('Compact file selection', () => {
    it('calls handleSelectWorkflow when a workflow row is clicked', async () => {
      const user = userEvent.setup();
      const handleSelectWorkflow = jest.fn();

      render(
        <UnifiedWorkflowList
          {...baseProps}
          handleSelectWorkflow={handleSelectWorkflow}
          unifiedWorkflows={[regularWorkflow]}
        />
      );

      await user.click(screen.getByRole('button', { name: 'my-workflow.yml, No status' }));
      expect(handleSelectWorkflow).toHaveBeenCalledWith('regular-0');
    });

    it('marks the selected workflow row as current', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          selectedWorkflowId="regular-0"
          unifiedWorkflows={[regularWorkflow, reusableWorkflow]}
        />
      );

      expect(screen.getByRole('button', { name: 'my-workflow.yml, No status' })).toHaveAttribute(
        'aria-current',
        'page'
      );
      expect(
        screen.getByRole('button', { name: 'my-reusable.yml, No status' })
      ).not.toHaveAttribute('aria-current');
    });

    it('calls onSelectCustomFile when a custom file row is clicked', async () => {
      const user = userEvent.setup();
      const onSelectCustomFile = jest.fn();

      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[]}
          customFiles={[customFile]}
          onSelectCustomFile={onSelectCustomFile}
        />
      );

      // The row shows only the basename; the full path stays in the label/tooltip.
      expect(screen.getByText('dependabot.yml')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: '.github/dependabot.yml, Committed Locally' }));
      expect(onSelectCustomFile).toHaveBeenCalledWith(7);
    });

    it('calls onSelectCodeowners with the first repo when the CODEOWNERS row is clicked', async () => {
      const user = userEvent.setup();
      const onSelectCodeowners = jest.fn();

      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[]}
          codeownersRepos={['owner/repo', 'owner/other']}
          onSelectCodeowners={onSelectCodeowners}
        />
      );

      await user.click(screen.getByRole('button', { name: '.github/CODEOWNERS, No status' }));
      expect(onSelectCodeowners).toHaveBeenCalledWith('owner/repo');
    });
  });

  describe('Status dots', () => {
    const cases: Array<[string, string, string]> = [
      ['new', 'New Local', 'status-new'],
      ['committed_locally', 'Committed Locally', 'status-committed'],
      ['under_review', 'Under Review', 'status-review'],
      ['synced_with_github', 'Synced', 'status-synced'],
    ];

    it.each(cases)('renders a %s dot titled "%s"', (status, label, className) => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[{ ...regularWorkflow, workflowStatus: status }]}
        />
      );

      const dot = screen.getByTitle(label);
      expect(dot).toHaveClass(className);
      // Status is a dot now, not a text pill.
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    });
  });

  describe('Indicators reach assistive tech', () => {
    it('names the drift state on the row, not only in the tooltip', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[{ ...regularWorkflow, workflowStatus: 'synced_with_github' }]}
          driftedWorkflowNames={new Set(['my-workflow'])}
        />
      );

      // aria-label replaces content, so the aria-hidden ⚠️ glyph would otherwise vanish.
      expect(
        screen.getByRole('button', { name: 'my-workflow.yml, Synced, Drift detected' })
      ).toBeInTheDocument();
    });

    it('names unsaved changes alongside a lifecycle status without repeating it', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[
            { ...regularWorkflow, workflowStatus: 'synced_with_github', isModified: true },
          ]}
        />
      );

      expect(
        screen.getByRole('button', { name: 'my-workflow.yml, Synced, Unsaved changes' })
      ).toBeInTheDocument();
      // A draft with no lifecycle status reports it once, via the status itself.
      expect(
        screen.queryByRole('button', { name: /Unsaved changes, Unsaved changes/ })
      ).not.toBeInTheDocument();
    });

    it('marks a custom file queued for deletion as pending deletion, not unsaved', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[]}
          customFiles={[{ ...customFile, pending_delete: true }]}
        />
      );

      const row = screen.getByRole('button', {
        name: '.github/dependabot.yml, Committed Locally, Pending Deletion',
      });
      expect(within(row).getByTitle('Pending Deletion')).toBeInTheDocument();
      expect(row.querySelector('.pf-row-modified')).not.toBeInTheDocument();
    });

    it('names the linked qualifier on linked rows', () => {
      render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[linkedWorkflowItem]} />);

      expect(
        screen.getByRole('button', { name: 'shared-deploy.yml, Linked workflow, No status' })
      ).toBeInTheDocument();
    });
  });

  describe('Drift indicator', () => {
    it('renders a drift marker for workflows in driftedWorkflowNames', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
          driftedWorkflowNames={new Set(['my-workflow'])}
        />
      );

      expect(screen.getByTestId('drift-badge')).toBeInTheDocument();
      expect(screen.getByTitle('AM_PROJ_my-workflow.yml · No status · Drift detected')).toBeInTheDocument();
    });

    it('renders a drift marker for reusable workflows too', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[reusableWorkflow]}
          driftedWorkflowNames={new Set(['my-reusable'])}
        />
      );

      expect(screen.getByTestId('drift-badge')).toBeInTheDocument();
    });

    it('does not render a drift marker when the workflow is not drifted', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
          driftedWorkflowNames={new Set(['some-other-workflow'])}
        />
      );

      expect(screen.queryByTestId('drift-badge')).not.toBeInTheDocument();
    });

    it('does not render a drift marker when driftedWorkflowNames is omitted', () => {
      render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[regularWorkflow]} />);

      expect(screen.queryByTestId('drift-badge')).not.toBeInTheDocument();
    });
  });

  describe('Section collapse/expand', () => {
    it('renders every section expanded by default', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow, reusableWorkflow, linkedWorkflowItem]}
          customFiles={[customFile]}
          codeownersRepos={['owner/repo']}
        />
      );

      ['Workflows', 'Reusable Workflows', 'Linked Workflows', 'Custom Files', 'CODEOWNERS'].forEach(
        (name) => expect(sectionToggle(name)).toHaveAttribute('aria-expanded', 'true')
      );
    });

    it('hides a section’s rows when its header is clicked, and restores them on a second click', async () => {
      const user = userEvent.setup();

      render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[regularWorkflow]} />);

      const toggle = sectionToggle('Workflows');
      await user.click(toggle);

      expect(toggle).toHaveAttribute('aria-expanded', 'false');
      expect(
        screen.queryByRole('button', { name: 'my-workflow.yml, No status' })
      ).not.toBeInTheDocument();

      await user.click(toggle);

      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('button', { name: 'my-workflow.yml, No status' })).toBeInTheDocument();
    });

    it('collapses sections independently', async () => {
      const user = userEvent.setup();

      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow]}
          customFiles={[customFile]}
        />
      );

      await user.click(sectionToggle('Workflows'));

      expect(sectionToggle('Workflows')).toHaveAttribute('aria-expanded', 'false');
      expect(sectionToggle('Custom Files')).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByText('dependabot.yml')).toBeInTheDocument();
    });

    it('shows a per-section count', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[regularWorkflow, { ...regularWorkflow, id: 'regular-1', name: 'second' }]}
        />
      );

      expect(within(sectionToggle('Workflows')).getByText('2')).toBeInTheDocument();
    });
  });

  describe('Panel collapse/expand', () => {
    it('collapses the panel from the header toggle', async () => {
      const user = userEvent.setup();
      const setIsCollapsed = jest.fn();

      render(
        <UnifiedWorkflowList {...baseProps} setIsCollapsed={setIsCollapsed} unifiedWorkflows={[regularWorkflow]} />
      );

      await user.click(screen.getByRole('button', { name: 'Collapse Project Files' }));
      expect(setIsCollapsed).toHaveBeenCalledWith(true);
    });

    it('renders an icon-only rail with a clear way to reopen when collapsed', () => {
      render(<UnifiedWorkflowList {...baseProps} isCollapsed unifiedWorkflows={[regularWorkflow]} />);

      expect(screen.getByRole('button', { name: 'Expand Project Files' })).toBeInTheDocument();
      expect(screen.getByText('Project Files')).toBeInTheDocument();
      // No file rows compete with the editor for space.
      expect(screen.queryByText('my-workflow.yml')).not.toBeInTheDocument();
    });

    it('reopens the panel when a rail section icon is clicked', async () => {
      const user = userEvent.setup();
      const setIsCollapsed = jest.fn();

      render(
        <UnifiedWorkflowList
          {...baseProps}
          isCollapsed
          setIsCollapsed={setIsCollapsed}
          unifiedWorkflows={[regularWorkflow]}
        />
      );

      await user.click(within(screen.getByRole('navigation', { name: 'Project Files' })).getByRole('button', { name: 'Workflows' }));
      expect(setIsCollapsed).toHaveBeenCalledWith(false);
    });

    it('does not render the resize handle or Add File button while collapsed', () => {
      render(
        <UnifiedWorkflowList {...baseProps} isCollapsed addWorkflowFn={jest.fn()} unifiedWorkflows={[]} />
      );

      expect(
        screen.queryByRole('button', { name: /^Resize Project Files panel/ })
      ).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Add File' })).not.toBeInTheDocument();
    });
  });

  describe('Panel resize', () => {
    it('defaults to 230px', () => {
      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      expect(panelWidth(container)).toBe('230px');
    });

    it('widens the panel as the handle is dragged right', () => {
      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      fireEvent.mouseDown(getHandle(), { clientX: 230 });
      fireEvent.mouseMove(window, { clientX: 310 });
      fireEvent.mouseUp(window);

      expect(panelWidth(container)).toBe('310px');
    });

    it('clamps the width to the allowed range', () => {
      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      fireEvent.mouseDown(getHandle(), { clientX: 230 });
      fireEvent.mouseMove(window, { clientX: 9999 });
      fireEvent.mouseUp(window);
      expect(panelWidth(container)).toBe('400px');

      fireEvent.mouseDown(getHandle(), { clientX: 400 });
      fireEvent.mouseMove(window, { clientX: 0 });
      fireEvent.mouseUp(window);
      expect(panelWidth(container)).toBe('180px');
    });

    it('stops resizing once the drag ends', () => {
      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      fireEvent.mouseDown(getHandle(), { clientX: 230 });
      fireEvent.mouseMove(window, { clientX: 300 });
      fireEvent.mouseUp(window);
      fireEvent.mouseMove(window, { clientX: 380 });

      expect(panelWidth(container)).toBe('300px');
    });

    it('resizes with the keyboard', () => {
      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      fireEvent.keyDown(getHandle(), { key: 'ArrowRight' });
      expect(panelWidth(container)).toBe('246px');

      fireEvent.keyDown(getHandle(), { key: 'ArrowLeft' });
      expect(panelWidth(container)).toBe('230px');

      fireEvent.keyDown(getHandle(), { key: 'End' });
      expect(panelWidth(container)).toBe('400px');

      fireEvent.keyDown(getHandle(), { key: 'Home' });
      expect(panelWidth(container)).toBe('180px');
    });

    it('keeps a stable accessible name and reports the width in the tooltip', () => {
      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      // A name that changed per drag frame would be re-announced continuously.
      expect(getHandle()).toHaveAccessibleName('Resize Project Files panel');
      expect(getHandle()).toHaveAttribute(
        'title',
        'Resize Project Files panel (230px). Drag, or use arrow keys.'
      );

      fireEvent.keyDown(getHandle(), { key: 'End' });
      expect(panelWidth(container)).toBe('400px');
      expect(getHandle()).toHaveAccessibleName('Resize Project Files panel');
    });

    it('resets to the default width on double click and on Enter', () => {
      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      fireEvent.keyDown(getHandle(), { key: 'End' });
      expect(panelWidth(container)).toBe('400px');

      fireEvent.doubleClick(getHandle());
      expect(panelWidth(container)).toBe('230px');

      fireEvent.keyDown(getHandle(), { key: 'Home' });
      fireEvent.keyDown(getHandle(), { key: 'Enter' });
      expect(panelWidth(container)).toBe('230px');
    });

  });

  describe('Preference persistence', () => {
    it('restores the panel width after a remount', () => {
      const { unmount } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      fireEvent.mouseDown(getHandle(), { clientX: 230 });
      fireEvent.mouseMove(window, { clientX: 330 });
      fireEvent.mouseUp(window);
      unmount();

      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);
      expect(panelWidth(container)).toBe('330px');
    });

    it('restores collapsed sections after a remount', async () => {
      const user = userEvent.setup();
      const { unmount } = render(
        <UnifiedWorkflowList {...baseProps} unifiedWorkflows={[regularWorkflow]} customFiles={[customFile]} />
      );

      await user.click(sectionToggle('Workflows'));
      unmount();

      render(
        <UnifiedWorkflowList {...baseProps} unifiedWorkflows={[regularWorkflow]} customFiles={[customFile]} />
      );

      expect(sectionToggle('Workflows')).toHaveAttribute('aria-expanded', 'false');
      expect(sectionToggle('Custom Files')).toHaveAttribute('aria-expanded', 'true');
    });

    it('falls back to the default width when the stored value is unusable', () => {
      localStorage.setItem('projectFiles.width', 'not-a-number');
      localStorage.setItem('projectFiles.closedSections', '{{ broken');

      const { container } = render(
        <UnifiedWorkflowList {...baseProps} unifiedWorkflows={[regularWorkflow]} />
      );

      expect(panelWidth(container)).toBe('230px');
      expect(sectionToggle('Workflows')).toHaveAttribute('aria-expanded', 'true');
    });

    it('clamps an out-of-range stored width', () => {
      localStorage.setItem('projectFiles.width', '5000');

      const { container } = render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      expect(panelWidth(container)).toBe('400px');
    });
  });

  describe('Add File button', () => {
    it('renders and calls addWorkflowFn directly when clicked', async () => {
      const user = userEvent.setup();
      const addWorkflowFn = jest.fn();

      render(<UnifiedWorkflowList {...baseProps} addWorkflowFn={addWorkflowFn} unifiedWorkflows={[]} />);

      await user.click(screen.getByRole('button', { name: 'Add File' }));
      expect(addWorkflowFn).toHaveBeenCalledTimes(1);
    });

    it('does not render when addWorkflowFn is not provided, even if other file actions are available', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          unifiedWorkflows={[]}
          codeownersRepos={['owner/repo']}
          onSelectCodeowners={jest.fn()}
        />
      );

      expect(screen.queryByRole('button', { name: 'Add File' })).not.toBeInTheDocument();
    });
  });

  describe('Section visibility rules', () => {
    it('always renders the Workflows section with an empty hint', () => {
      render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} />);

      expect(screen.getByText('No workflows yet')).toBeInTheDocument();
    });

    it('hides the Reusable Workflows section when reusable workflows are disabled', () => {
      render(
        <UnifiedWorkflowList
          {...baseProps}
          reusableWorkflowsEnabled={false}
          unifiedWorkflows={[regularWorkflow, reusableWorkflow]}
        />
      );

      expect(screen.queryByRole('region', { name: 'Reusable Workflows' })).not.toBeInTheDocument();
    });

    it('does not mark the CODEOWNERS row selected when no selection is supplied', () => {
      render(
        <UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} codeownersRepos={['owner/repo']} />
      );

      expect(
        screen.getByRole('button', { name: '.github/CODEOWNERS, No status' })
      ).not.toHaveAttribute('aria-current');
    });

    it('hides the CODEOWNERS section when no repos are configured', () => {
      render(<UnifiedWorkflowList {...baseProps} unifiedWorkflows={[]} codeownersRepos={[]} />);

      expect(screen.queryByRole('region', { name: 'CODEOWNERS' })).not.toBeInTheDocument();
    });
  });
});

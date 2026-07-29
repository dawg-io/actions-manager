import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import Sidebar from './Sidebar';

// Top-level (always visible) section labels
const topLevelSections = ['Project Files', 'PR Campaigns'];

describe('Sidebar', () => {
  const user = userEvent.setup();

  test('expanded vs collapsed header & project code display', () => {
    const { rerender } = render(
      <Sidebar
        isCollapsed={false}
        projectCode="PRJ"
      />
    );

    // Expanded: full variant renders wordmark span with aria-label (img is decorative/aria-hidden)
    expect(screen.getAllByLabelText('ActionsManager').length).toBeGreaterThan(0);
    expect(screen.getByText(/Project Key: PRJ/)).toBeInTheDocument();

    // Collapse
    rerender(<Sidebar isCollapsed projectCode="PRJ" />);

    // Collapsed: shield icon-only logo still rendered, project code shown but
    // not the long "Project Key:" line
    expect(screen.getAllByAltText('ActionsManager').length).toBeGreaterThan(0);
    // Project code shown, but not the long "Project Key:" line
    expect(screen.getByText('PRJ')).toBeInTheDocument();
    expect(screen.queryByText(/Project Key:/)).not.toBeInTheDocument();
  });

  test('expanded sidebar shows editable project name above project key', async () => {
    const onProjectNameSave = jest.fn();
    render(
      <Sidebar
        isCollapsed={false}
        projectName="ABC"
        onProjectNameSave={onProjectNameSave}
        projectCode="ABC1"
      />
    );

    expect(screen.getByText('Project')).toBeInTheDocument();
    expect(screen.getByLabelText('project name')).toHaveTextContent('ABC');
    expect(screen.getByText(/Project Key: ABC1/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Edit project name/i }));
    const input = screen.getByRole('textbox', { name: /project name/i });
    await user.clear(input);
    await user.type(input, 'Renamed Project{enter}');

    expect(onProjectNameSave).toHaveBeenCalledWith('Renamed Project');
  });

  test('collapse toggle button reflects state (via title) and calls handler', async () => {
    const onToggleCollapse = jest.fn();

    const { rerender, container } = render(
      <Sidebar isCollapsed={false} onToggleCollapse={onToggleCollapse} />
    );

    // Expanded state -> title says "Collapse sidebar"
    const collapseBtnExpanded = screen.getByTitle('Collapse sidebar');
    expect(collapseBtnExpanded).toBeInTheDocument();

    // Lives in the sidebar header, next to the logo — not the old floating
    // middle-edge control.
    expect(container.querySelector('.sidebar-header .sidebar-collapse-button')).toBe(collapseBtnExpanded);
    expect(container.querySelector('.sidebar-toggle')).not.toBeInTheDocument();

    await user.click(collapseBtnExpanded);
    expect(onToggleCollapse).toHaveBeenCalledTimes(1);

    // Collapsed state -> title says "Expand sidebar", toggle remains visible
    rerender(<Sidebar isCollapsed onToggleCollapse={onToggleCollapse} />);
    const expandBtnCollapsed = screen.getByTitle('Expand sidebar');
    expect(expandBtnCollapsed).toBeInTheDocument();
    expect(container.querySelector('.sidebar-header .sidebar-collapse-button')).toBe(expandBtnCollapsed);
  });

  test('in collapsed mode, top-level section buttons expose labels via title and hide text labels', () => {
    render(<Sidebar isCollapsed />);

    for (const label of topLevelSections) {
      expect(screen.getByTitle(label)).toBeInTheDocument();
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  test('clicking Project Files calls onSectionChange with workflows key', async () => {
    const onSectionChange = jest.fn();
    render(<Sidebar projectType="rwx" onSectionChange={onSectionChange} isCollapsed={false} />);

    await user.click(screen.getByRole('button', { name: /Project Files/i }));
    expect(onSectionChange).toHaveBeenCalledWith('workflows');
  });

  test('sidebar shows PR Campaigns and routes to PR campaign view', async () => {
    const onSectionChange = jest.fn();
    render(<Sidebar projectType="rwx" onSectionChange={onSectionChange} isCollapsed={false} />);

    expect(screen.queryByText('PR History')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /PR Campaigns/i }));
    expect(onSectionChange).toHaveBeenCalledWith('pr-history');
  });

  test('standard project does not show Linked Workflows nav item (moved to Add Workflow flow)', async () => {
    render(<Sidebar projectType="standard" isCollapsed={false} />);
    // Project Configs group must be expanded first to reveal sub-items
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.queryByRole('button', { name: /Linked Workflows/i })).not.toBeInTheDocument();
  });

  test('rwx project does not show Linked Workflows nav item', async () => {
    render(<Sidebar projectType="rwx" isCollapsed={false} />);
    // Expand Project Configs to check its children
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.queryByRole('button', { name: /Linked Workflows/i })).not.toBeInTheDocument();
  });

  test('when collapsed, Project Configs group header is accessible via title only', () => {
    render(<Sidebar projectType="standard" isCollapsed />);
    expect(screen.getByTitle('Project Configs')).toBeInTheDocument();
    expect(screen.queryByText('Project Configs')).not.toBeInTheDocument();
  });

  test('standard project shows Project Configs group header', () => {
    render(<Sidebar projectType="standard" isCollapsed={false} />);
    expect(screen.getByRole('button', { name: /Project Configs/i })).toBeInTheDocument();
  });

  test('rwx project shows Project Configs group header', () => {
    render(<Sidebar projectType="rwx" isCollapsed={false} />);
    expect(screen.getByRole('button', { name: /Project Configs/i })).toBeInTheDocument();
  });

  test('Project Configs group expands and collapses on click', async () => {
    render(<Sidebar projectType="standard" isCollapsed={false} />);
    const groupHeader = screen.getByRole('button', { name: /Project Configs/i });

    // Initially collapsed – Project Info not visible
    expect(screen.queryByRole('button', { name: /Project Info/i })).not.toBeInTheDocument();

    // Expand
    await user.click(groupHeader);
    expect(screen.getByRole('button', { name: /Project Info/i })).toBeInTheDocument();

    // Collapse again
    await user.click(groupHeader);
    expect(screen.queryByRole('button', { name: /Project Info/i })).not.toBeInTheDocument();
  });

  test('Project Configs group auto-expands when active section is project-info', () => {
    render(<Sidebar projectType="standard" isCollapsed={false} activeSection="project-info" />);
    expect(screen.getByRole('button', { name: /Project Info/i })).toBeInTheDocument();
  });

  test('rwx project shows Linked Projects nav item', async () => {
    render(<Sidebar projectType="rwx" isCollapsed={false} />);
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.getByRole('button', { name: /Linked Projects/i })).toBeInTheDocument();
  });

  test('standard project does not show Linked Projects nav item', async () => {
    render(<Sidebar projectType="standard" isCollapsed={false} />);
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.queryByRole('button', { name: /Linked Projects/i })).not.toBeInTheDocument();
  });

  test('clicking Linked Projects calls onSectionChange with linked-projects', async () => {
    const onSectionChange = jest.fn();
    render(
      <Sidebar
        projectType="rwx"
        onSectionChange={onSectionChange}
        isCollapsed={false}
      />
    );

    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    await user.click(screen.getByRole('button', { name: /Linked Projects/i }));
    expect(onSectionChange).toHaveBeenCalledWith('linked-projects');
  });

  test('Project Configs group auto-expands when active section is linked-projects', () => {
    render(<Sidebar projectType="rwx" isCollapsed={false} activeSection="linked-projects" />);
    expect(screen.getByRole('button', { name: /Linked Projects/i })).toBeInTheDocument();
  });

  test('when collapsed, Linked Projects is accessible via title only', () => {
    render(<Sidebar projectType="rwx" isCollapsed activeSection="linked-projects" />);
    expect(screen.getByTitle('Linked Projects')).toBeInTheDocument();
    expect(screen.queryByText('Linked Projects')).not.toBeInTheDocument();
  });

  test('standard project shows Danger Zone nav item', async () => {
    render(<Sidebar projectType="standard" isCollapsed={false} />);
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.getByRole('button', { name: /Danger Zone/i })).toBeInTheDocument();
  });

  test('rwx project shows Danger Zone nav item', async () => {
    render(<Sidebar projectType="rwx" isCollapsed={false} />);
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.getByRole('button', { name: /Danger Zone/i })).toBeInTheDocument();
  });

  test('clicking Danger Zone calls onSectionChange with danger-zone', async () => {
    const onSectionChange = jest.fn();
    render(
      <Sidebar
        projectType="standard"
        onSectionChange={onSectionChange}
        isCollapsed={false}
      />
    );
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    await user.click(screen.getByRole('button', { name: /Danger Zone/i }));
    expect(onSectionChange).toHaveBeenCalledWith('danger-zone');
  });

  test('Project Configs group auto-expands when active section is danger-zone', () => {
    render(<Sidebar projectType="standard" isCollapsed={false} activeSection="danger-zone" />);
    expect(screen.getByRole('button', { name: /Danger Zone/i })).toBeInTheDocument();
  });

  test('when collapsed, Danger Zone is accessible via title only', () => {
    render(<Sidebar projectType="standard" isCollapsed activeSection="danger-zone" />);
    expect(screen.getByTitle('Danger Zone')).toBeInTheDocument();
    expect(screen.queryByText('Danger Zone')).not.toBeInTheDocument();
  });

  // --- Mode badge (usePrefix) ---

  test('expanded sidebar shows prefix mode badge when usePrefix=true', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" usePrefix={true} />);
    expect(screen.getByRole('generic', { name: /Resource naming mode: Prefix Mode/i })).toBeInTheDocument();
  });

  test('expanded sidebar shows no-prefix mode badge when usePrefix=false', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" usePrefix={false} />);
    expect(screen.getByRole('generic', { name: /Resource naming mode: No Prefix Mode/i })).toBeInTheDocument();
  });

  test('expanded sidebar omits mode badge when usePrefix is not provided', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" />);
    expect(screen.queryByRole('generic', { name: /Resource naming mode:/i })).not.toBeInTheDocument();
  });

  test('collapsed sidebar title includes mode when usePrefix=true', () => {
    render(<Sidebar isCollapsed projectCode="PRJ" usePrefix={true} />);
    const el = screen.getByTitle(/Project Key: PRJ.*Prefix Mode/);
    expect(el).toBeInTheDocument();
  });

  test('collapsed sidebar title includes mode when usePrefix=false', () => {
    render(<Sidebar isCollapsed projectCode="PRJ" usePrefix={false} />);
    const el = screen.getByTitle(/Project Key: PRJ.*No Prefix Mode/);
    expect(el).toBeInTheDocument();
  });

  test('collapsed sidebar title omits mode when usePrefix is not provided', () => {
    render(<Sidebar isCollapsed projectCode="PRJ" />);
    const el = screen.getByTitle(/Project Key: PRJ/);
    expect(el).toBeInTheDocument();
  });

  // --- Project Type badge ---

  test('expanded sidebar shows project type badge for standard type', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" projectType="standard" />);
    expect(screen.getByRole('generic', { name: /Project type: Caller Workflow Project/i })).toBeInTheDocument();
  });

  test('expanded sidebar shows project type badge for rwx type', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" projectType="rwx" />);
    expect(screen.getByRole('generic', { name: /Project type: Reusable Workflow Project/i })).toBeInTheDocument();
  });

  test('expanded sidebar defaults to standard project type badge when projectType is not provided', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" />);
    expect(screen.getByRole('generic', { name: /Project type: Caller Workflow Project/i })).toBeInTheDocument();
  });

  test('collapsed sidebar title includes project type for standard', () => {
    render(<Sidebar isCollapsed projectCode="PRJ" projectType="standard" />);
    const el = screen.getByTitle(/Caller Workflow Project/);
    expect(el).toBeInTheDocument();
  });

  test('collapsed sidebar title includes project type for rwx', () => {
    render(<Sidebar isCollapsed projectCode="PRJ" projectType="rwx" />);
    const el = screen.getByTitle(/Reusable Workflow Project/);
    expect(el).toBeInTheDocument();
  });

  // --- Project Info nav item ---

  test('standard project shows Project Info nav item inside Project Configs', async () => {
    render(<Sidebar projectType="standard" isCollapsed={false} />);
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.getByRole('button', { name: /Project Info/i })).toBeInTheDocument();
  });

  test('rwx project shows Project Info nav item inside Project Configs', async () => {
    render(<Sidebar projectType="rwx" isCollapsed={false} />);
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    expect(screen.getByRole('button', { name: /Project Info/i })).toBeInTheDocument();
  });

  test('clicking Project Info calls onSectionChange with project-info', async () => {
    const onSectionChange = jest.fn();
    render(
      <Sidebar
        projectType="standard"
        onSectionChange={onSectionChange}
        isCollapsed={false}
      />
    );
    await user.click(screen.getByRole('button', { name: /Project Configs/i }));
    await user.click(screen.getByRole('button', { name: /Project Info/i }));
    expect(onSectionChange).toHaveBeenCalledWith('project-info');
  });

  test('Project Configs group auto-expands when activeSection is project-info (standard)', () => {
    render(<Sidebar projectType="standard" isCollapsed={false} activeSection="project-info" />);
    expect(screen.getByRole('button', { name: /Project Info/i })).toBeInTheDocument();
  });

  test('Project Configs group auto-expands when activeSection is project-info (rwx)', () => {
    render(<Sidebar projectType="rwx" isCollapsed={false} activeSection="project-info" />);
    expect(screen.getByRole('button', { name: /Project Info/i })).toBeInTheDocument();
  });

  test('when collapsed, Project Info is accessible via title only', () => {
    render(<Sidebar projectType="standard" isCollapsed activeSection="project-info" />);
    expect(screen.getByTitle('Project Info')).toBeInTheDocument();
    expect(screen.queryByText('Project Info')).not.toBeInTheDocument();
  });

  // --- Read Only badge ---

  test('expanded sidebar shows read-only badge when isReadOnly=true', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" isReadOnly={true} />);
    expect(screen.getByRole('generic', { name: /Access level: Read Only/i })).toBeInTheDocument();
  });

  test('expanded sidebar does not show read-only badge when isReadOnly is false', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" isReadOnly={false} />);
    expect(screen.queryByRole('generic', { name: /Access level: Read Only/i })).not.toBeInTheDocument();
  });

  test('expanded sidebar does not show read-only badge when isReadOnly is not provided', () => {
    render(<Sidebar isCollapsed={false} projectCode="PRJ" />);
    expect(screen.queryByRole('generic', { name: /Access level: Read Only/i })).not.toBeInTheDocument();
  });

  test('collapsed sidebar title includes read-only when isReadOnly=true', () => {
    render(<Sidebar isCollapsed projectCode="PRJ" isReadOnly={true} />);
    const el = screen.getByTitle(/Read Only/);
    expect(el).toBeInTheDocument();
  });

  test('collapsed sidebar title does not include read-only when isReadOnly is false', () => {
    render(<Sidebar isCollapsed projectCode="PRJ" isReadOnly={false} />);
    const el = screen.getByTitle(/Project Key: PRJ/);
    expect(el.title).not.toContain('Read Only');
  });

  // --- Sidebar layout: Project Configs pinned to bottom ---

  test('Project Configs wrapper has mt-auto class (pinned to bottom)', () => {
    const { container } = render(<Sidebar projectType="standard" isCollapsed={false} />);
    const nav = container.querySelector('nav.sidebar-nav');
    expect(nav).not.toBeNull();
    // The bottom section containing Project Configs should have mt-auto
    const bottomSection = nav!.querySelector('.mt-auto');
    expect(bottomSection).not.toBeNull();
  });

  test('Project Configs renders after Repository Configs items in DOM order', () => {
    const { container } = render(<Sidebar projectType="standard" isCollapsed={false} />);
    const nav = container.querySelector('nav.sidebar-nav')!;
    const buttons = Array.from(nav.querySelectorAll('button'));
    const reposAndBranchesIdx = buttons.findIndex(b => b.textContent?.includes('Repositories & Branches'));
    const rulesetsIdx = buttons.findIndex(b => b.textContent?.includes('Environment Rulesets'));
    const projectConfigsIdx = buttons.findIndex(b => b.textContent?.includes('Project Configs'));
    expect(reposAndBranchesIdx).toBeGreaterThanOrEqual(0);
    expect(rulesetsIdx).toBeGreaterThan(reposAndBranchesIdx);
    expect(projectConfigsIdx).toBeGreaterThan(rulesetsIdx);
  });

  // --- Repository Configs: flat first-class sidebar items ---

  test('Repository Configs are rendered as flat first-class sidebar items (no parent group)', () => {
    render(<Sidebar projectType="standard" isCollapsed={false} />);
    // The collapsible parent must be gone
    expect(screen.queryByRole('button', { name: /^Repository Configs$/i })).not.toBeInTheDocument();
    // Five repo config items (CODEOWNERS moved to Project Files editor)
    expect(screen.getByRole('button', { name: /Repositories & Branches/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Deploy Environments/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Environment Variables/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Environment Secrets/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Environment Rulesets/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^CODEOWNERS$/i })).not.toBeInTheDocument();
  });

  test.each([
    ['Repositories & Branches', 'repos-and-branches'],
    ['Deploy Environments', 'environments'],
    ['Environment Variables', 'envvars'],
    ['Environment Secrets', 'secrets'],
    ['Environment Rulesets', 'rulesets'],
  ])('clicking %s calls onSectionChange with %s key', async (label, key) => {
    const onSectionChange = jest.fn();
    render(
      <Sidebar
        projectType="standard"
        onSectionChange={onSectionChange}
        isCollapsed={false}
      />
    );
    await user.click(screen.getByRole('button', { name: new RegExp(label, 'i') }));
    expect(onSectionChange).toHaveBeenCalledWith(key);
  });

  test('active repository-config item gets the active class', () => {
    render(
      <Sidebar projectType="standard" isCollapsed={false} activeSection="environments" />
    );
    const activeBtn = screen.getByRole('button', { name: /Deploy Environments/i });
    expect(activeBtn).toHaveClass('active');
  });

  test('when collapsed, repo config items remain reachable by accessible name (aria-label)', () => {
    render(<Sidebar projectType="standard" isCollapsed />);
    expect(
      screen.getByRole('button', { name: /Repositories & Branches/i })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Environment Rulesets/i })).toBeInTheDocument();
    expect(screen.queryByText('Repositories & Branches')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^CODEOWNERS$/i })).not.toBeInTheDocument();
  });
});

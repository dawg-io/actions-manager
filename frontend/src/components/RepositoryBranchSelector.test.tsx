import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

import RepositoryBranchSelector, {
  RepositoryBranchSelectorRepo,
} from './RepositoryBranchSelector';

const REPOS: RepositoryBranchSelectorRepo[] = [
  {
    id: 1,
    name: 'test1',
    full_name: 'whatsupdawg/test1',
    private: false,
    owner: 'whatsupdawg',
    owner_type: 'Organization',
  },
  {
    id: 2,
    name: 'test2',
    full_name: 'whatsupdawg/test2',
    private: true,
    owner: 'whatsupdawg',
    owner_type: 'Organization',
  },
  {
    id: 3,
    name: 'personal-tools',
    full_name: 'octocat/personal-tools',
    private: false,
    owner: 'octocat',
    owner_type: 'User',
  },
];

describe('RepositoryBranchSelector', () => {
  const u = userEvent.setup();

  it('renders the selected and available panels with correct counts and headings', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        visibilityScope="public"
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    expect(
      screen.getByText(/Selected Repositories \(1\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Available Repositories/)).toBeInTheDocument();
    expect(screen.getByTestId('available-helper-text')).toHaveTextContent(
      'Showing public repositories only.',
    );
  });

  it('marks the available row as selected when its full_name is in the selection', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    const row = screen.getByTestId('available-repo-whatsupdawg/test1');
    expect(row).toHaveAttribute('data-selected', 'true');
    const checkbox = within(row).getByRole('checkbox') as HTMLInputElement;
    expect(checkbox).toBeChecked();

    const unselected = screen.getByTestId('available-repo-whatsupdawg/test2');
    expect(unselected).toHaveAttribute('data-selected', 'false');
  });

  it('calls onSelectRepository when an unchecked available row is clicked', async () => {
    const onSelect = jest.fn();
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={[]}
        onSelectRepository={onSelect}
        onRemoveRepository={jest.fn()}
      />,
    );
    await u.click(screen.getByTestId('available-checkbox-whatsupdawg/test1'));
    expect(onSelect).toHaveBeenCalledWith('whatsupdawg/test1');
  });

  it('calls onRemoveRepository when a checked available row is clicked again', async () => {
    const onRemove = jest.fn();
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        onSelectRepository={jest.fn()}
        onRemoveRepository={onRemove}
      />,
    );
    await u.click(screen.getByTestId('available-checkbox-whatsupdawg/test1'));
    expect(onRemove).toHaveBeenCalledWith('whatsupdawg/test1');
  });

  it('calls onRemoveRepository when the selected card X button is pressed', async () => {
    const onRemove = jest.fn();
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        onSelectRepository={jest.fn()}
        onRemoveRepository={onRemove}
      />,
    );
    await u.click(screen.getByTestId('remove-selected-whatsupdawg/test1'));
    expect(onRemove).toHaveBeenCalledWith('whatsupdawg/test1');
  });

  it('filters the available list by the search input (name / owner / full_name)', async () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={[]}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    const search = screen.getByTestId('available-search-input');
    await u.type(search, 'octocat');
    expect(
      screen.getByTestId('available-repo-octocat/personal-tools'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('available-repo-whatsupdawg/test1'),
    ).not.toBeInTheDocument();
  });

  it('shows an empty state when no repositories are selected', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={[]}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    expect(screen.getByTestId('selected-empty-state')).toBeInTheDocument();
  });

  it('shows the loading state when loading=true', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={[]}
        selectedRepositoryNames={[]}
        loading
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    expect(screen.getByTestId('available-loading')).toHaveTextContent(
      /Loading/i,
    );
  });

  it('shows the error state when error is set', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={[]}
        selectedRepositoryNames={[]}
        error="boom"
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    expect(screen.getByTestId('available-error')).toHaveTextContent('boom');
  });

  it('renders the Branch Configuration card with the selected count when a slot is provided', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1', 'whatsupdawg/test2']}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
        branchConfigSlot={<div data-testid="custom-branch-slot">slot-content</div>}
      />,
    );
    const panel = screen.getByTestId('branch-configuration-panel');
    expect(within(panel).getByText(/Branch Configuration \(2\)/)).toBeInTheDocument();
    expect(screen.getByTestId('custom-branch-slot')).toBeInTheDocument();
  });

  it('hides the Branch Configuration card when no slot is provided', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    expect(
      screen.queryByTestId('branch-configuration-panel'),
    ).not.toBeInTheDocument();
  });

  it('uses onReplaceSelection (and skips onRemove/onSelect) in singleSelect mode when provided', async () => {
    const onReplace = jest.fn();
    const onRemove = jest.fn();
    const onSelect = jest.fn();
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        singleSelect
        onSelectRepository={onSelect}
        onRemoveRepository={onRemove}
        onReplaceSelection={onReplace}
      />,
    );
    await u.click(screen.getByTestId('available-checkbox-whatsupdawg/test2'));
    // Single, atomic state replacement — no remove-then-add dance.
    expect(onReplace).toHaveBeenCalledTimes(1);
    expect(onReplace).toHaveBeenCalledWith(['whatsupdawg/test2']);
    expect(onRemove).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('falls back to remove+select in singleSelect mode when onReplaceSelection is not provided', async () => {
    const onRemove = jest.fn();
    const onSelect = jest.fn();
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        singleSelect
        onSelectRepository={onSelect}
        onRemoveRepository={onRemove}
      />,
    );
    // Click a different available row — the previous selection should be
    // removed and the new one added (legacy fallback path).
    await u.click(screen.getByTestId('available-checkbox-whatsupdawg/test2'));
    expect(onRemove).toHaveBeenCalledWith('whatsupdawg/test1');
    expect(onSelect).toHaveBeenCalledWith('whatsupdawg/test2');
  });

  it('renders selected repos that are missing from availableRepositories without misleading badges', () => {
    render(
      <RepositoryBranchSelector
        availableRepositories={[]}
        selectedRepositoryNames={['ghost-org/ghost-repo']}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
      />,
    );
    const card = screen.getByTestId('selected-repo-ghost-org/ghost-repo');
    expect(card).toHaveAttribute('data-has-metadata', 'false');
    // Both badges must be suppressed so we don't mis-label an unknown repo
    // as Public + Personal.
    expect(within(card).queryByText('Public')).not.toBeInTheDocument();
    expect(within(card).queryByText('Private')).not.toBeInTheDocument();
    expect(within(card).queryByText('Personal')).not.toBeInTheDocument();
    expect(within(card).queryByText('Organization')).not.toBeInTheDocument();
    expect(
      screen.getByTestId('selected-repo-unknown-ghost-org/ghost-repo'),
    ).toHaveTextContent(/Metadata unavailable/i);
  });

  it('resets the internal search input when resetSearchKey changes', async () => {
    const { rerender } = render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={[]}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
        resetSearchKey="standard"
      />,
    );
    const search = screen.getByTestId(
      'available-search-input',
    ) as HTMLInputElement;
    await u.type(search, 'octocat');
    expect(search.value).toBe('octocat');

    // Parent toggles the project type — the picker's stale query must be
    // cleared so the freshly-supplied list isn't filtered to nothing.
    rerender(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={[]}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
        resetSearchKey="rwx"
      />,
    );
    expect(
      (screen.getByTestId('available-search-input') as HTMLInputElement).value,
    ).toBe('');
  });

  it('triggers onClearSelectedRepositories when "Clear all" is pressed', async () => {
    const onClear = jest.fn();
    render(
      <RepositoryBranchSelector
        availableRepositories={REPOS}
        selectedRepositoryNames={['whatsupdawg/test1']}
        onSelectRepository={jest.fn()}
        onRemoveRepository={jest.fn()}
        onClearSelectedRepositories={onClear}
      />,
    );
    await u.click(screen.getByTestId('selected-clear-all'));
    expect(onClear).toHaveBeenCalled();
  });
});

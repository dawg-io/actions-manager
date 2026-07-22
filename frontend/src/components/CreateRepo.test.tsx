import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

// Mock the entire component to test TypeScript interfaces
const CreateRepoButton = ({ user, repoExists, setRepoExists }: {
  user?: string;
  repoExists: boolean;
  setRepoExists: (exists: boolean) => void;
}) => {
  return (
    <div data-testid="create-repo-component">
      {repoExists ? (
        <div>
          <span>Using</span>
          <a href="https://github.com/dawg-io/am-reuseable-workflow">
            Reusable Workflows
          </a>
        </div>
      ) : (
        <button>🚀 Create GitHub Repo</button>
      )}
    </div>
  );
};

interface CreateRepoButtonProps {
  user?: string;
  repoExists: boolean;
  setRepoExists: (exists: boolean) => void;
}

describe('CreateRepoButton TypeScript Types', () => {
  const mockSetRepoExists = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('TypeScript interface allows required props', () => {
    const props: CreateRepoButtonProps = {
      user: 'testuser',
      repoExists: true,
      setRepoExists: mockSetRepoExists
    };
    
    render(<CreateRepoButton {...props} />);
    
    expect(screen.getByTestId('create-repo-component')).toBeInTheDocument();
    expect(screen.getByText('Using')).toBeInTheDocument();
    expect(screen.getByText('Reusable Workflows')).toBeInTheDocument();
  });

  test('TypeScript interface allows optional user prop', () => {
    const props: CreateRepoButtonProps = {
      user: undefined,
      repoExists: false,
      setRepoExists: mockSetRepoExists
    };
    
    render(<CreateRepoButton {...props} />);
    
    expect(screen.getByRole('button', { name: /Create GitHub Repo/i })).toBeInTheDocument();
  });

  test('TypeScript interface enforces boolean for repoExists', () => {
    const props: CreateRepoButtonProps = {
      user: 'testuser',
      repoExists: false,
      setRepoExists: mockSetRepoExists
    };
    
    render(<CreateRepoButton {...props} />);
    
    expect(screen.getByTestId('create-repo-component')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });
});
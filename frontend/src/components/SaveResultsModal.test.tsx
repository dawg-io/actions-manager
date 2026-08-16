import React from 'react';
import { render, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import SaveResultsModal from './SaveResultsModal';

describe('SaveResultsModal Component', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onStayOnProject: vi.fn(),
    onGoToMain: vi.fn(),
    projectName: 'Test Project',
    results: [],
    isSuccess: true,
    githubUpdatePerformed: false
  };

  test('should not render when isOpen is false', () => {
    render(<SaveResultsModal {...defaultProps} isOpen={false} />);
    // Dialog with open=false should not render content
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('should render when isOpen is true', () => {
    render(<SaveResultsModal {...defaultProps} />);
    // Dialog should be in the document when open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  test('should display project name', () => {
    render(<SaveResultsModal {...defaultProps} />);
    expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
  });

  test('should show success title when isSuccess is true and no errors', () => {
    render(<SaveResultsModal {...defaultProps} />);
    expect(screen.getByText('✅ Project Saved Successfully!')).toBeInTheDocument();
  });

  test('should show GitHub updated title when githubUpdatePerformed is true', () => {
    render(
      <SaveResultsModal {...defaultProps} githubUpdatePerformed={true} />
    );
    expect(screen.getByText('✅ Project Saved & PRs Created!')).toBeInTheDocument();
  });

  test('should display success results', () => {
    const results = ['✅ Workflow deployed', '✅ Secrets updated'];
    render(
      <SaveResultsModal {...defaultProps} results={results} />
    );
    expect(screen.getByText('Workflow deployed')).toBeInTheDocument();
    expect(screen.getByText('Secrets updated')).toBeInTheDocument();
  });

  test('should display error results', () => {
    const results = ['❌ Failed to deploy', '❌ Invalid configuration'];
    render(
      <SaveResultsModal {...defaultProps} results={results} isSuccess={false} />
    );
    expect(screen.getByText('Failed to deploy')).toBeInTheDocument();
    expect(screen.getByText('Invalid configuration')).toBeInTheDocument();
  });

  test('should show mixed status when both success and error results exist', () => {
    const results = ['✅ Success item', '❌ Error item'];
    render(
      <SaveResultsModal {...defaultProps} results={results} />
    );
    expect(screen.getByText('⚠️ Save Completed with Issues')).toBeInTheDocument();
  });

  test('should call onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <SaveResultsModal {...defaultProps} onClose={onClose} />
    );
    // Click the X button in the dialog
    const closeButton = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeButton);
    
    expect(onClose).toHaveBeenCalled();
  });

  test('should call onGoToMain when Go to Main Screen button is clicked', () => {
    const onGoToMain = vi.fn();
    render(
      <SaveResultsModal {...defaultProps} onGoToMain={onGoToMain} />
    );
    const button = screen.getByRole('button', { name: /Go to Main Screen/i });
    fireEvent.click(button);
    expect(onGoToMain).toHaveBeenCalledTimes(1);
  });

  test('should call onStayOnProject when Stay on Project button is clicked', () => {
    const onStayOnProject = vi.fn();
    render(
      <SaveResultsModal {...defaultProps} onStayOnProject={onStayOnProject} />
    );
    const button = screen.getByRole('button', { name: /Stay on Project/i });
    fireEvent.click(button);
    expect(onStayOnProject).toHaveBeenCalledTimes(1);
  });

  test('should not render results section when results array is empty', () => {
    render(<SaveResultsModal {...defaultProps} results={[]} />);
    // Check that success/error section headings don't exist
    expect(screen.queryByText('✅ Successful Operations')).not.toBeInTheDocument();
    expect(screen.queryByText('❌ Failed Operations')).not.toBeInTheDocument();
  });

  test('should display GitHub update indicator when githubUpdatePerformed is true', () => {
    render(
      <SaveResultsModal {...defaultProps} githubUpdatePerformed={true} />
    );
    expect(screen.getByText('Pull requests have been created/updated for workflow changes')).toBeInTheDocument();
  });

  test('should handle optional props with default values', () => {
    const minimalProps = {
      isOpen: true,
      onClose: vi.fn(),
      onStayOnProject: vi.fn(),
      onGoToMain: vi.fn(),
      projectName: 'Minimal Project'
    };
    render(<SaveResultsModal {...minimalProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  test('should have proper accessibility attributes', () => {
    render(<SaveResultsModal {...defaultProps} />);
    
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    
    // Dialog should have a title
    const title = screen.getByRole('heading', { name: /Project Saved Successfully/i });
    expect(title).toBeInTheDocument();
  });
});

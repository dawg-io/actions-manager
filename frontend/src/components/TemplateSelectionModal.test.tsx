import React from 'react';
import { render, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import TemplateSelectionModal from './TemplateSelectionModal';
import { TemplatesByType } from '../types/workflow';

describe('TemplateSelectionModal Component', () => {
  const mockSetShowTemplateModal = jest.fn();
  const mockSelectTemplate = jest.fn();

  const mockTemplatesByType: TemplatesByType = {
    standard: {
      name: 'Standard Workflow',
      content: 'name: CI\non: [push]'
    },
    reusable: {
      name: 'Reusable Workflow',
      content: 'name: Reusable\non: workflow_call'
    },
    build: {
      name: 'Build Workflow',
      content: 'name: Build\non: [push]'
    }
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('should render dialog when showTemplateModal is true', () => {
    render(
      <TemplateSelectionModal
        showTemplateModal={true}
        templatesByType={mockTemplatesByType}
        setShowTemplateModal={mockSetShowTemplateModal}
        selectTemplate={mockSelectTemplate}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  test('should not render dialog when showTemplateModal is false', () => {
    render(
      <TemplateSelectionModal
        showTemplateModal={false}
        templatesByType={mockTemplatesByType}
        setShowTemplateModal={mockSetShowTemplateModal}
        selectTemplate={mockSelectTemplate}
      />
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('should render template options', () => {
    render(
      <TemplateSelectionModal
        showTemplateModal={true}
        templatesByType={mockTemplatesByType}
        setShowTemplateModal={mockSetShowTemplateModal}
        selectTemplate={mockSelectTemplate}
      />
    );

    expect(screen.getByText('Standard Workflow')).toBeInTheDocument();
    expect(screen.getByText('Reusable Workflow')).toBeInTheDocument();
    expect(screen.getByText('Build Workflow')).toBeInTheDocument();
  });

  test('should call selectTemplate when Use Template button is clicked', () => {
    render(
      <TemplateSelectionModal
        showTemplateModal={true}
        templatesByType={mockTemplatesByType}
        setShowTemplateModal={mockSetShowTemplateModal}
        selectTemplate={mockSelectTemplate}
      />
    );

    const useTemplateButtons = screen.getAllByText('Use Template');
    fireEvent.click(useTemplateButtons[0]);
    
    expect(mockSelectTemplate).toHaveBeenCalledWith(mockTemplatesByType.standard, false);
  });

  test('should have proper dialog title', () => {
    render(
      <TemplateSelectionModal
        showTemplateModal={true}
        templatesByType={mockTemplatesByType}
        setShowTemplateModal={mockSetShowTemplateModal}
        selectTemplate={mockSelectTemplate}
      />
    );

    expect(screen.getByRole('heading', { name: /Select Workflow Template/i })).toBeInTheDocument();
  });

  test('should show loading message when templates are empty', () => {
    render(
      <TemplateSelectionModal
        showTemplateModal={true}
        templatesByType={{}}
        setShowTemplateModal={mockSetShowTemplateModal}
        selectTemplate={mockSelectTemplate}
      />
    );

    expect(screen.getByText('Generating templates...')).toBeInTheDocument();
  });

  test('should call selectTemplate with correct parameters for reusable workflow', () => {
    render(
      <TemplateSelectionModal
        showTemplateModal={true}
        templatesByType={mockTemplatesByType}
        setShowTemplateModal={mockSetShowTemplateModal}
        selectTemplate={mockSelectTemplate}
      />
    );

    const useTemplateButtons = screen.getAllByText('Use Template');
    // Second button is for reusable workflow
    fireEvent.click(useTemplateButtons[1]);
    
    expect(mockSelectTemplate).toHaveBeenCalledWith(mockTemplatesByType.reusable, true);
  });
});

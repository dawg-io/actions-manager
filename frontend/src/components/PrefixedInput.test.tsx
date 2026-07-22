import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import PrefixedInput from './PrefixedInput';

describe('PrefixedInput Component', () => {
  test('should render with prefix and value', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: jest.fn(),
      placeholder: 'Enter value'
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    expect(container.firstChild).toBeTruthy();
  });

  test('should call onChange when input changes', () => {
    const onChange = jest.fn();
    const props = {
      prefix: 'PREFIX_',
      value: '',
      onChange,
      placeholder: 'Enter value'
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    const input = container.querySelector('input');
    
    if (input) {
      fireEvent.change(input, { target: { value: 'newvalue' } });
    }
    
    expect(onChange).toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledWith('newvalue');
  });

  test('should pass only string value to onChange, not event object', () => {
    const onChange = jest.fn();
    const props = {
      prefix: 'TEST_',
      value: 'initial',
      onChange,
      placeholder: 'Enter value'
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    const input = container.querySelector('input');
    
    if (input) {
      fireEvent.change(input, { target: { value: 'updated_value' } });
    }
    
    // Verify that onChange was called with string value, not event object
    expect(onChange).toHaveBeenCalledTimes(1);
    const [firstArg] = onChange.mock.calls[0];
    expect(typeof firstArg).toBe('string');
    expect(firstArg).toBe('updated_value');
    // Ensure it's not an event object
    expect(firstArg).not.toHaveProperty('target');
    expect(firstArg).not.toHaveProperty('nativeEvent');
  });

  test('should render prefix text', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: jest.fn()
    };
    
    const { getByText } = render(<PrefixedInput {...props} />);
    expect(getByText('PREFIX_')).toBeInTheDocument();
  });

  test('should have keyboard accessibility attributes', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: jest.fn()
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    const containerDiv = container.querySelector('.prefixed-input-container');
    
    expect(containerDiv).toHaveAttribute('role', 'button');
    expect(containerDiv).toHaveAttribute('tabIndex', '0');
    expect(containerDiv).toHaveAttribute('aria-label', 'Focus input field');
  });

  test('should focus input when Enter key is pressed on container', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: jest.fn()
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    const containerDiv = container.querySelector('.prefixed-input-container');
    const input = container.querySelector('input');
    
    if (containerDiv && input) {
      fireEvent.keyDown(containerDiv, { key: 'Enter' });
      expect(document.activeElement).toBe(input);
    }
  });

  test('should focus input when Space key is pressed on container', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: jest.fn()
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    const containerDiv = container.querySelector('.prefixed-input-container');
    const input = container.querySelector('input');
    
    if (containerDiv && input) {
      fireEvent.keyDown(containerDiv, { key: ' ' });
      expect(document.activeElement).toBe(input);
    }
  });

  test('should not focus input when other keys are pressed on container', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: jest.fn()
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    const containerDiv = container.querySelector('.prefixed-input-container');
    const input = container.querySelector('input');
    
    if (containerDiv && input) {
      const initialActiveElement = document.activeElement;
      fireEvent.keyDown(containerDiv, { key: 'Tab' });
      expect(document.activeElement).toBe(initialActiveElement);
    }
  });

  test('should not focus input when disabled and keyboard event is triggered', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: jest.fn(),
      disabled: true
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    const containerDiv = container.querySelector('.prefixed-input-container');
    const input = container.querySelector('input');
    
    if (containerDiv && input) {
      const initialActiveElement = document.activeElement;
      fireEvent.keyDown(containerDiv, { key: 'Enter' });
      expect(document.activeElement).not.toBe(input);
      expect(document.activeElement).toBe(initialActiveElement);
    }
  });
});
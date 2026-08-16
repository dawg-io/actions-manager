import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import PrefixedInput from './PrefixedInput';

describe('PrefixedInput Component', () => {
  test('should render with prefix and value', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: vi.fn(),
      placeholder: 'Enter value'
    };
    
    const { container } = render(<PrefixedInput {...props} />);
    expect(container.firstChild).toBeTruthy();
  });

  test('should call onChange when input changes', () => {
    const onChange = vi.fn();
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
    const onChange = vi.fn();
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
      onChange: vi.fn()
    };
    
    const { getByText } = render(<PrefixedInput {...props} />);
    expect(getByText('PREFIX_')).toBeInTheDocument();
  });

  test('container should not have a redundant button role — the input inside is already focusable', () => {
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: vi.fn()
    };

    const { container } = render(<PrefixedInput {...props} />);
    const containerDiv = container.querySelector('.prefixed-input-container');

    expect(containerDiv).not.toHaveAttribute('role');
    expect(containerDiv).not.toHaveAttribute('tabIndex');
    expect(containerDiv).not.toHaveAttribute('aria-label');
  });

  test('should focus input when container is clicked', async () => {
    const user = userEvent.setup();
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: vi.fn()
    };

    const { container } = render(<PrefixedInput {...props} />);
    const containerLabel = container.querySelector('.prefixed-input-container');
    const input = container.querySelector('input');

    // The container is a native <label> wrapping the <input> — clicking it
    // focuses the input via real label-to-control forwarding, no JS needed.
    // Plain fireEvent.click doesn't simulate that browser behavior in jsdom,
    // so this needs userEvent (which does).
    if (containerLabel && input) {
      await user.click(containerLabel);
      expect(document.activeElement).toBe(input);
    }
  });

  test('should not focus input when container is clicked while disabled', async () => {
    const user = userEvent.setup();
    const props = {
      prefix: 'PREFIX_',
      value: 'test',
      onChange: vi.fn(),
      disabled: true
    };

    const { container } = render(<PrefixedInput {...props} />);
    const containerLabel = container.querySelector('.prefixed-input-container');
    const input = container.querySelector('input');

    if (containerLabel && input) {
      const initialActiveElement = document.activeElement;
      await user.click(containerLabel);
      expect(document.activeElement).not.toBe(input);
      expect(document.activeElement).toBe(initialActiveElement);
    }
  });
});
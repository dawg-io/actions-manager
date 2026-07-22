import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { Button } from './button';
import { Card, CardHeader, CardTitle, CardContent } from './card';

describe('shadcn/ui Components', () => {
  describe('Button', () => {
    it('renders with default variant', () => {
      render(<Button>Click me</Button>);
      const button = screen.getByRole('button', { name: /click me/i });
      expect(button).toBeInTheDocument();
      expect(button).toHaveTextContent('Click me');
    });

    it('renders with destructive variant', () => {
      render(<Button variant="destructive">Delete</Button>);
      const button = screen.getByRole('button', { name: /delete/i });
      expect(button).toBeInTheDocument();
    });

    it('renders with outline variant', () => {
      render(<Button variant="outline">Cancel</Button>);
      const button = screen.getByRole('button', { name: /cancel/i });
      expect(button).toBeInTheDocument();
    });

    it('handles disabled state', () => {
      render(<Button disabled>Disabled</Button>);
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
    });

    it('handles click events', () => {
      const handleClick = jest.fn();
      render(<Button onClick={handleClick}>Click</Button>);
      const button = screen.getByRole('button');
      button.click();
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('renders different sizes', () => {
      const { rerender } = render(<Button size="sm">Small</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
      
      rerender(<Button size="lg">Large</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });
  });

  describe('Card', () => {
    it('renders card with title and content', () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>Test Card</CardTitle>
          </CardHeader>
          <CardContent>
            Card content here
          </CardContent>
        </Card>
      );
      
      expect(screen.getByText('Test Card')).toBeInTheDocument();
      expect(screen.getByText('Card content here')).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const { container } = render(
        <Card className="custom-class">Content</Card>
      );
      
      const card = container.firstChild;
      expect(card).toHaveClass('custom-class');
    });
  });
});

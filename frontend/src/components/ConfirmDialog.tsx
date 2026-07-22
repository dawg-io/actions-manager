import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';

export interface ConfirmDialogProps {
  /** Whether the dialog is currently shown. */
  open: boolean;
  /** Dialog title, e.g. "Delete workflow?" */
  title: string;
  /** Descriptive body text explaining what will happen. */
  description: string;
  /** Label for the confirm button. Defaults to "Confirm". */
  confirmLabel?: string;
  /** Label for the cancel button. Defaults to "Cancel". */
  cancelLabel?: string;
  /** When true the confirm button is styled as a destructive action. */
  destructive?: boolean;
  /** Called when the user clicks the confirm button. */
  onConfirm: () => void;
  /** Called when the user clicks cancel or closes the dialog. */
  onCancel: () => void;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onConfirm,
  onCancel,
}) => (
  <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onCancel(); }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button
          variant={destructive ? 'destructive' : 'default'}
          onClick={() => {
            onConfirm();
          }}
        >
          {confirmLabel}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

export default ConfirmDialog;

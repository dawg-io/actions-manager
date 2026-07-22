// Type declarations for utility functions

export interface CopyButtonProps {
  textToCopy: string;
  className?: string;
  title?: string;
}

// copyUtils.d.ts
export declare const copyToClipboard: (
  text: string,
  onSuccess?: () => void,
  onError?: (error: any) => void
) => Promise<void>;


export declare const CopyButton: React.FC<CopyButtonProps>;

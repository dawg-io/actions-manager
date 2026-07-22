import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";

// TypeScript interfaces
interface SaveResultsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStayOnProject: () => void;
  onGoToMain: () => void;
  projectName: string;
  results?: string[];
  isSuccess?: boolean;
  githubUpdatePerformed?: boolean;
}

const SaveResultsModal: React.FC<SaveResultsModalProps> = ({ 
  isOpen, 
  onClose, 
  onStayOnProject,
  onGoToMain,
  projectName,
  results = [],
  isSuccess = true,
  githubUpdatePerformed = false
}) => {
  // Parse results to separate by type and extract PR links
  const successResults = results.filter(result => result.startsWith("✅"));
  const warningResults = results.filter(result => result.startsWith("⚠️"));
  const errorResults = results.filter(result => result.startsWith("❌"));
  const hasResults = results.length > 0;

  // Helper function to format result text with clickable PR links
  const formatResultWithLinks = (result: string): React.ReactNode => {
    // Match PR URLs in the format: https://github.com/...
    const urlRegex = /(https:\/\/github\.com\/[^\s]+)/g;
    const parts = result.split(urlRegex);
    
    return parts.map((part, index) => {
      if (part.match(urlRegex)) {
        return (
          <a 
            key={index}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 underline dark:text-blue-400 dark:hover:text-blue-300"
          >
            {part}
          </a>
        );
      }
      return part;
    });
  };

  const getStatusTitle = (): string => {
    if (isSuccess && errorResults.length === 0) {
      return githubUpdatePerformed ? "✅ Project Saved & PRs Created!" : "✅ Project Saved Successfully!";
    } else if (errorResults.length > 0 && successResults.length > 0) {
      return "⚠️ Save Completed with Issues";
    } else {
      return "❌ Save Failed";
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle id="save-results-title">{getStatusTitle()}</DialogTitle>
          <DialogDescription className="sr-only">
            Project save results and navigation options
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-6">
          <div className="bg-green-50 border border-green-500 rounded-lg p-4 space-y-2 dark:bg-green-950 dark:border-green-700">
            <div className="flex items-center gap-3">
              <span className="text-xl flex-shrink-0">📁</span>
              <span className="text-sm text-green-800 font-medium dark:text-green-200">
                Project "{projectName}" has been saved to the database
              </span>
            </div>
            
            {githubUpdatePerformed && (
              <div className="flex items-center gap-3">
                <span className="text-xl flex-shrink-0">🔀</span>
                <span className="text-sm text-green-800 font-medium dark:text-green-200">
                  Pull requests have been created/updated for workflow changes
                </span>
              </div>
            )}
          </div>

          {hasResults && (
            <div className="space-y-5">
              {successResults.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-base font-semibold text-green-600 dark:text-green-400">
                    ✅ Successful Operations
                  </h4>
                  <ul className="space-y-1">
                    {successResults.map((result, index) => (
                      <li 
                        key={`success-${index}`} 
                        className="bg-green-50 border-l-4 border-green-500 text-green-800 p-2 px-3 rounded text-sm leading-relaxed dark:bg-green-950 dark:text-green-200"
                      >
                        {formatResultWithLinks(result.replace("✅ ", ""))}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              {warningResults.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-base font-semibold text-yellow-600 dark:text-yellow-400">
                    ⚠️ Warnings
                  </h4>
                  <ul className="space-y-1">
                    {warningResults.map((result, index) => (
                      <li 
                        key={`warning-${index}`} 
                        className="bg-yellow-50 border-l-4 border-yellow-500 text-yellow-900 p-2 px-3 rounded text-sm leading-relaxed dark:bg-yellow-950 dark:text-yellow-200"
                      >
                        {formatResultWithLinks(result.replace("⚠️ ", ""))}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              {errorResults.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-base font-semibold text-red-600 dark:text-red-400">
                    ❌ Failed Operations
                  </h4>
                  <ul className="space-y-1">
                    {errorResults.map((result, index) => (
                      <li 
                        key={`error-${index}`} 
                        className="bg-red-50 border-l-4 border-red-600 text-red-900 p-2 px-3 rounded text-sm leading-relaxed dark:bg-red-950 dark:text-red-200"
                      >
                        {formatResultWithLinks(result.replace("❌ ", ""))}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="bg-slate-50 border border-slate-200 rounded-lg p-5 text-center dark:bg-slate-800 dark:border-slate-700">
            <h4 className="text-lg font-semibold text-slate-900 mb-2 dark:text-slate-100">
              What would you like to do next?
            </h4>
            <p className="text-sm text-slate-600 leading-relaxed dark:text-slate-400">
              You can continue working on this project or return to the main project list.
            </p>
          </div>
        </div>
        
        <DialogFooter className="flex justify-center gap-4 sm:justify-center">
          <Button 
            variant="outline"
            onClick={onGoToMain}
            className="min-w-[160px]"
          >
            🏠 Go to Main Screen
          </Button>
          <Button 
            variant="default"
            onClick={onStayOnProject}
            className="min-w-[160px]"
          >
            📝 Stay on Project
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SaveResultsModal;

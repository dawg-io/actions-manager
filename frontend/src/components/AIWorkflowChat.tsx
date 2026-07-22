import React, { useState, useRef, useEffect } from "react";

interface ChatMessage {
  type: "user" | "assistant" | "error";
  message: string;
  timestamp: string;
  workflow_updates?: string[];
}

interface AIWorkflowChatProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId?: string | null;
  currentWorkflow?: string | null;
  onWorkflowUpdate: (workflow: string) => void;
  onSendMessage: (message: string) => Promise<void>;
  chatHistory?: ChatMessage[];
  suggestedQuestions?: string[];
  isLoading?: boolean;
}

const AIWorkflowChat: React.FC<AIWorkflowChatProps> = ({
  isOpen,
  onClose,
  sessionId,
  currentWorkflow,
  onWorkflowUpdate,
  onSendMessage,
  chatHistory = [],
  suggestedQuestions = [],
  isLoading = false
}) => {
  const [userMessage, setUserMessage] = useState("");
  const [localChatHistory, setLocalChatHistory] = useState<ChatMessage[]>(chatHistory);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    setLocalChatHistory(chatHistory);
  }, [chatHistory]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localChatHistory]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen) {
      if (!dialog.open) {
        dialog.showModal();
      }
      chatInputRef.current?.focus();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [isOpen]);

  const handleSendMessage = async () => {
    if (!userMessage.trim() || isLoading) return;

    const messageToSend = userMessage.trim();
    setUserMessage("");

    const newUserMessage: ChatMessage = {
      type: "user",
      message: messageToSend,
      timestamp: new Date().toISOString()
    };

    setLocalChatHistory(prev => [...prev, newUserMessage]);

    try {
      await onSendMessage(messageToSend);
    } catch {
      const errorMessage: ChatMessage = {
        type: "error",
        message: "Sorry, I encountered an error processing your request. Please try again.",
        timestamp: new Date().toISOString()
      };
      setLocalChatHistory(prev => [...prev, errorMessage]);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSendMessage();
    }
  };

  const handleSuggestedQuestion = (question: string) => {
    setUserMessage(question);
    chatInputRef.current?.focus();
  };

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).classList?.contains('ai-chat-overlay')) {
      onClose();
    }
  };

  const handleOverlayKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).classList?.contains('ai-chat-overlay')) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/70 flex justify-center items-center z-50 backdrop-blur-sm"
      onClick={handleOverlayClick}
      onKeyDown={handleOverlayKeyDown}
      role="button"
      tabIndex={0}
      aria-label="Close dialog"
    >
      <dialog
        ref={dialogRef}
        className="bg-gray-900 border border-gray-700 rounded-xl w-[90%] max-w-[800px] h-[80vh] max-h-[600px] flex flex-col shadow-2xl overflow-hidden p-0 m-auto"
        onClose={onClose}
        aria-labelledby="ai-chat-title"
      >
          <div className="bg-gray-800 p-4 border-b border-gray-700 flex justify-between items-center">
          <h3 id="ai-chat-title" className="m-0 text-white text-xl font-semibold">🤖 AI Workflow Assistant</h3>
          <button className="bg-transparent border-none text-gray-400 text-2xl cursor-pointer p-1 leading-none hover:text-white transition-colors" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
            {localChatHistory.length === 0 ? (
              <div className="mb-4">
                <div className="flex flex-col items-start">
                  <div className="max-w-[85%] p-3 rounded-xl bg-gray-800 text-white border border-gray-700">
                    <p>👋 Hello! I've generated an initial workflow for your project. Let me guide you through building a complete CI/CD pipeline step by step.</p>
                    <p>I can help you progressively enhance your workflow with:</p>
                    <ul className="mt-2 pl-6">
                      <li><strong>🔧 Build & Testing:</strong> Comprehensive testing, code quality checks</li>
                      <li><strong>🛡️ Security & Quality:</strong> CodeQL analysis, SonarQube, vulnerability scanning</li>
                      <li><strong>📦 Containerization:</strong> Docker image building and container security</li>
                      <li><strong>🚀 Deployment:</strong> Staging/production environments, automated releases</li>
                      <li><strong>⚙️ Advanced Features:</strong> Secrets management, monitoring, rollback strategies</li>
                    </ul>
                    <p>What would you like to add next?</p>
                  </div>
                </div>
              </div>
            ) : (
              localChatHistory.map((message, index) => (
                <div key={index} className={`flex flex-col ${message.type === 'user' ? 'items-end' : message.type === 'error' ? 'items-center' : 'items-start'}`}>
                  <div className={`max-w-[85%] p-3 rounded-xl break-words ${
                    message.type === 'user' ? 'bg-blue-600 text-white' :
                    message.type === 'error' ? 'bg-red-100 text-red-800 border border-red-400 text-center' :
                    'bg-gray-800 text-white border border-gray-700'
                  }`}>
                    {message.type === "user" ? (
                      <p><strong>You:</strong> {message.message}</p>
                    ) : message.type === "error" ? (
                      <p className="text-red-600">❌ {message.message}</p>
                    ) : (
                      <>
                        <p><strong>AI Assistant:</strong> {message.message}</p>
                        {message.workflow_updates && message.workflow_updates.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-gray-600">
                            <p className="font-semibold text-blue-400"><strong>Changes made:</strong></p>
                            <ul className="mt-2 pl-4">
                              {message.workflow_updates.map((update, i) => (
                                <li key={i} className="text-gray-300 text-sm">{update}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))
            )}

            {isLoading && (
              <div className="flex flex-col items-start">
                <div className="max-w-[85%] p-3 rounded-xl bg-gray-800 text-white border border-gray-700">
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse"></span>
                      <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse delay-200"></span>
                      <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse delay-400"></span>
                    </div>
                    <p>AI is thinking...</p>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {suggestedQuestions.length > 0 && (
            <div className="p-4 border-t border-gray-700 bg-gray-950">
              <p className="m-0 mb-3 text-gray-400 text-sm font-semibold">💡 Suggested questions:</p>
              <div className="flex flex-wrap gap-2">
                {suggestedQuestions.map((question) => (
                  <button
                    key={question}
                    className="bg-gray-800 border border-gray-700 text-white px-3 py-2 rounded-full text-sm cursor-pointer transition-all hover:bg-blue-600 hover:border-blue-600 hover:-translate-y-px disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                    onClick={() => handleSuggestedQuestion(question)}
                    disabled={isLoading}
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="p-4 border-t border-gray-700 bg-gray-800 flex gap-3 items-end">
            <textarea
              ref={chatInputRef}
              className="flex-1 bg-gray-900 border border-gray-700 text-white p-3 rounded-lg text-sm resize-vertical min-h-[20px] max-h-[100px] font-inherit transition-colors focus:outline-none focus:border-blue-600 placeholder-gray-500"
              value={userMessage}
              onChange={(e) => setUserMessage(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Ask me to customize your workflow... (Press Enter to send)"
              disabled={isLoading}
              rows={3}
            />
            <button
              className="bg-blue-600 border-none text-white px-5 py-3 rounded-lg text-sm font-semibold cursor-pointer transition-all hover:bg-blue-500 hover:-translate-y-px disabled:bg-gray-600 disabled:cursor-not-allowed disabled:transform-none whitespace-nowrap"
              onClick={() => void handleSendMessage()}
              disabled={!userMessage.trim() || isLoading}
            >
              {isLoading ? "..." : "Send"}
            </button>
          </div>
        </div>

        <div className="p-3 border-t border-gray-700 bg-gray-950 flex justify-between items-center gap-4">
          <p className="m-0 text-gray-500 text-xs flex-1">
            💡 Tip: Be specific about what you want to add or change in your workflow
          </p>
          <button
            className="bg-green-600 border-none text-white px-4 py-2 rounded-md text-sm font-semibold cursor-pointer transition-all hover:bg-green-500 hover:-translate-y-px hover:shadow-lg hover:shadow-green-600/30 disabled:bg-gray-600 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none whitespace-nowrap min-w-[80px]"
            onClick={onClose}
            disabled={isLoading}
          >
            ✅ Done
          </button>
        </div>
      </dialog>
    </div>
  );
};

export default AIWorkflowChat;

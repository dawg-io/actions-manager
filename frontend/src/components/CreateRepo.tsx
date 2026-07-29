import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { createGitHubRepo, checkRepoStatus } from '../api/repos';
import { Button } from './ui/button';
import { toast } from '../utils/toast';

// TypeScript interfaces
interface CreateRepoButtonProps {
  user?: string;
  repoExists: boolean;
  setRepoExists: (exists: boolean) => void;
}

interface CreateRepoResponse {
  repo_name?: string;
  repo_url?: string;
  error?: string;
}

const CreateRepoButton: React.FC<CreateRepoButtonProps> = ({ user, repoExists, setRepoExists }) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const checkRepo = async () => {
      if (user) {
        const exists = await checkRepoStatus(user, 'am-reuseable-workflow');
        setRepoExists(exists);
      }
    };
    if (user) {
      checkRepo();
    }
  }, [user, setRepoExists]);

  const handleCreateRepo = async () => {
    if (!user) {
      toast.error('User is required to create a repository.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await createGitHubRepo(user, 'private') as CreateRepoResponse;

      if (response?.error) {
        setError(response.error);
      } else if (response?.repo_name) {
        setRepoExists(true);
        console.log('✅ Reusable Repository:', response.repo_url);

        navigate(`/project/${user}/${response.repo_name}`);
      } else {
        setError('Unexpected error: No repository name returned.');
      }
    } catch (err) {
      console.error('❌ Error creating repo:', err);
      setError('Failed to create repository. Please try again.');
    }

    setLoading(false);
  };

  return (
    <div className="create-repo-container">
      {repoExists && user ? (
        <div className="repo-status-badge">
          <span className="status-text">
            Using{' '}
            <a 
              href={`https://github.com/${user}/am-reuseable-workflow`}
              target="_blank" 
              rel="noopener noreferrer" 
              className="repo-link"
            >
              Reusable Workflows
            </a>
          </span>
        </div>
      ) : (
        <Button onClick={handleCreateRepo} disabled={loading}>
          {loading ? 'Creating...' : '🚀 Create GitHub Repo'}
        </Button>
      )}

      {error && <div className="repo-error-message">❌ {error}</div>}
    </div>
  );
};

export default CreateRepoButton;
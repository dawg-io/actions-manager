import React, { useCallback } from 'react';
import JobCard from './JobCard';
import { uniqueId, isFieldUnder } from '../utils/stepSelection';
import { WorkflowJob, ValidationError } from '../utils/workflowGuiConversion';

interface JobListProps {
  jobs: WorkflowJob[];
  onChange: (jobs: WorkflowJob[]) => void;
  validationErrors: ValidationError[];
}

const JobList: React.FC<JobListProps> = ({ jobs, onChange, validationErrors }) => {
  const updateJob = useCallback((index: number, updatedJob: WorkflowJob) => {
    const newJobs = [...jobs];
    newJobs[index] = updatedJob;
    onChange(newJobs);
  }, [onChange, jobs]);

  const removeJob = useCallback((index: number) => {
    onChange(jobs.filter((_, i) => i !== index));
  }, [onChange, jobs]);

  const moveJob = useCallback((fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= jobs.length) return;
    
    const newJobs = [...jobs];
    const [movedJob] = newJobs.splice(fromIndex, 1);
    newJobs.splice(toIndex, 0, movedJob);
    onChange(newJobs);
  }, [onChange, jobs]);

  const duplicateJob = useCallback((index: number) => {
    const job = jobs[index];
    const newJob: WorkflowJob = {
      ...job,
      id: uniqueId(jobs.map(j => j.id), `${job.id}-copy`),
      name: job.name ? `${job.name} (Copy)` : undefined,
      steps: job.steps.map(step => ({
        ...step,
        id: `${step.id}-copy`
      }))
    };
    
    const newJobs = [...jobs];
    newJobs.splice(index + 1, 0, newJob);
    onChange(newJobs);
  }, [onChange, jobs]);

  const getJobErrors = useCallback((jobIndex: number): ValidationError[] => {
    return validationErrors.filter(error => 
      isFieldUnder(error.field, `jobs[${jobIndex}]`)
    );
  }, [validationErrors]);

  return (
    <div className="job-list">
      {jobs.length === 0 ? (
        <div className="no-jobs-notice">
          No jobs defined. Click "Add Job" to create your first job.
        </div>
      ) : (
        jobs.map((job, index) => (
          <JobCard
            key={job.id}
            job={job}
            jobIndex={index}
            onChange={(updatedJob) => updateJob(index, updatedJob)}
            onRemove={() => removeJob(index)}
            onMoveUp={index > 0 ? () => moveJob(index, index - 1) : undefined}
            onMoveDown={index < jobs.length - 1 ? () => moveJob(index, index + 1) : undefined}
            onDuplicate={() => duplicateJob(index)}
            validationErrors={getJobErrors(index)}
            availableJobIds={jobs.map(j => j.id).filter((_, i) => i !== index)}
          />
        ))
      )}
    </div>
  );
};

export default JobList;
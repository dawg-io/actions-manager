import React from "react";
import { Button } from "./ui/button";
// eslint-disable-next-line no-restricted-imports -- Legacy: TODO migrate CSS file to Tailwind CSS classes
import "../styles/projectMgmt.css";

interface DangerZoneProps {
  projectName: string;
  onDeleteProject: () => void;
}

const DangerZone: React.FC<DangerZoneProps> = ({ projectName, onDeleteProject }) => {
  return (
    <div className="danger-zone-page">
      {/* Warning intro */}
      <div className="danger-zone-intro">
        <h2 className="danger-zone-title">⚠️ Danger Zone</h2>
        <p className="danger-zone-description">
          Destructive actions for this project live here. These actions may be permanent and should be used with caution.
        </p>
      </div>

      {/* Delete Project section */}
      <div className="danger-zone-card">
        <div className="danger-zone-card-header">
          <h3 className="danger-zone-card-title">🗑️ Delete Project</h3>
          <p className="danger-zone-card-description">
            Permanently remove <strong>{projectName}</strong> from ActionsManager. You can choose to delete database records only, or also remove all associated GitHub resources (workflows, secrets, environments).
          </p>
        </div>
        <div className="danger-zone-card-action">
          <Button
            variant="destructive"
            onClick={onDeleteProject}
            className="danger-zone-delete-btn"
          >
            ❌ Delete Project
          </Button>
        </div>
      </div>
    </div>
  );
};

export default DangerZone;

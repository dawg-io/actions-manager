import React, { useCallback, useEffect, useState } from "react";
import { Button, Checkbox, Input } from "./ui";
import {
  sendTestEmail,
  fetchSubscriptions,
  createSubscription,
  deleteSubscription,
  fetchDeliveries,
  NOTIFICATION_EVENT_TYPES,
  NotificationSubscription,
  NotificationDelivery,
} from "../api/notifications";
import { fetchProjects, Project } from "../api/projects";

interface WorkspaceNotificationsProps {
  readonly currentUser?: string;
  readonly currentUserRole?: string;
}

type NotificationsTab = "settings" | "history";

const tabButtonClassName = (isActive: boolean): string =>
  `pb-2 -mb-px border-b-2 text-sm font-medium transition-colors ${
    isActive
      ? "border-primary text-primary dark:border-primary-dark dark:text-primary-dark"
      : "border-transparent text-text-secondary dark:text-secondary-dark hover:text-text-primary dark:hover:text-text-primary-dark"
  }`;

const inputSelectClassName =
  "flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-sm transition-colors border-input-border bg-input-background-color text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-input-focus dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100";

const WorkspaceNotifications: React.FC<WorkspaceNotificationsProps> = ({ currentUser, currentUserRole }) => {
  const isAdmin = currentUserRole === "admin";

  const [activeTab, setActiveTab] = useState<NotificationsTab>("settings");

  const [recipientEmail, setRecipientEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [testMessage, setTestMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const [projects, setProjects] = useState<Project[]>([]);
  const [subscriptions, setSubscriptions] = useState<NotificationSubscription[]>([]);
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);

  const [newRecipient, setNewRecipient] = useState("");
  const [newProjectId, setNewProjectId] = useState<string>("");
  const [newEventTypes, setNewEventTypes] = useState<string[]>([]);
  const [newNotifyOnResolved, setNewNotifyOnResolved] = useState(true);
  const [subscriptionMessage, setSubscriptionMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const loadData = useCallback(async () => {
    const [subs, projectList, deliveryList] = await Promise.all([
      fetchSubscriptions(),
      fetchProjects(currentUser),
      fetchDeliveries(),
    ]);
    setSubscriptions(subs);
    setProjects(projectList);
    setDeliveries(deliveryList);
  }, [currentUser]);

  useEffect(() => {
    if (isAdmin) {
      loadData();
    }
  }, [isAdmin, loadData]);

  const handleSendTestEmail = async () => {
    setSending(true);
    setTestMessage(null);
    const result = await sendTestEmail(recipientEmail);
    setTestMessage({ text: result.message, type: result.success ? "success" : "error" });
    setSending(false);
  };

  const toggleEventType = (eventType: string) => {
    setNewEventTypes((current) =>
      current.includes(eventType) ? current.filter((e) => e !== eventType) : [...current, eventType]
    );
  };

  const handleCreateSubscription = async () => {
    setSubscriptionMessage(null);
    const result = await createSubscription({
      recipientEmail: newRecipient,
      projectId: newProjectId ? Number(newProjectId) : null,
      eventTypes: newEventTypes.length > 0 ? newEventTypes : null,
      notifyOnResolved: newNotifyOnResolved,
    });
    if (result.success) {
      setNewRecipient("");
      setNewProjectId("");
      setNewEventTypes([]);
      setNewNotifyOnResolved(true);
      await loadData();
    } else {
      setSubscriptionMessage({ text: result.message || "Failed to add subscription", type: "error" });
    }
  };

  const handleDeleteSubscription = async (subscriptionId: number) => {
    const result = await deleteSubscription(subscriptionId);
    if (result.success) {
      await loadData();
    } else {
      setSubscriptionMessage({ text: result.message || "Failed to remove subscription", type: "error" });
    }
  };

  if (!isAdmin) {
    return (
      <div className="text-sm text-text-secondary dark:text-secondary-dark">
        Only workspace admins can configure notifications.
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto space-y-6">
      <h2 className="text-lg font-semibold text-text-primary dark:text-text-primary-dark">Notifications</h2>

      <div className="flex gap-6 border-b border-border dark:border-border-dark">
        <button className={tabButtonClassName(activeTab === "settings")} onClick={() => setActiveTab("settings")}>
          Settings
        </button>
        <button className={tabButtonClassName(activeTab === "history")} onClick={() => setActiveTab("history")}>
          Delivery History
        </button>
      </div>

      {activeTab === "settings" && (
        <div className="space-y-8">
          <div className="space-y-4">
            <div>
              <p className="text-sm text-text-secondary dark:text-secondary-dark">
                SMTP is configured via <code>SMTP_HOST</code>/<code>SMTP_PORT</code>/<code>SMTP_USERNAME</code>/<code>SMTP_PASSWORD</code>/<code>SMTP_USE_TLS</code>/<code>SMTP_FROM_ADDRESS</code>/<code>SMTP_FROM_NAME</code>{" "}
                environment variables. Send a test email to confirm it's working.
              </p>
            </div>

            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="recipient@example.com"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                disabled={sending}
              />
              <Button onClick={handleSendTestEmail} disabled={sending || !recipientEmail}>
                {sending ? "Sending…" : "Send Test Email"}
              </Button>
            </div>

            {testMessage && (
              <div className={testMessage.type === "success" ? "text-sm text-success" : "text-sm text-red-600 dark:text-red-400"}>
                {testMessage.text}
              </div>
            )}
          </div>

          <div className="space-y-3 border-t border-border dark:border-border-dark pt-6">
            <h3 className="text-base font-semibold text-text-primary dark:text-text-primary-dark">Subscriptions</h3>
            <p className="text-sm text-text-secondary dark:text-secondary-dark">
              Choose who gets notified, for which project, and which events. Leave project unset for all projects, and
              leave events unset for all events.
            </p>

            <div className="space-y-3 rounded-md border border-border dark:border-border-dark p-4">
              <div className="flex gap-2">
                <Input
                  type="email"
                  placeholder="recipient@example.com"
                  value={newRecipient}
                  onChange={(e) => setNewRecipient(e.target.value)}
                />
                <select
                  className={inputSelectClassName}
                  value={newProjectId}
                  onChange={(e) => setNewProjectId(e.target.value)}
                  aria-label="Project scope"
                >
                  <option value="">All projects</option>
                  {projects.map((project) => (
                    <option key={project.project_id} value={project.project_id}>
                      {project.project_name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-wrap gap-3">
                {NOTIFICATION_EVENT_TYPES.map((eventType) => (
                  <label key={eventType} className="flex items-center gap-1.5 text-sm text-text-primary dark:text-text-primary-dark">
                    <Checkbox
                      checked={newEventTypes.includes(eventType)}
                      onCheckedChange={() => toggleEventType(eventType)}
                    />
                    {eventType}
                  </label>
                ))}
              </div>

              <label className="flex items-center gap-1.5 text-sm text-text-primary dark:text-text-primary-dark">
                <Checkbox checked={newNotifyOnResolved} onCheckedChange={(checked) => setNewNotifyOnResolved(checked === true)} />
                Notify on drift resolved
              </label>

              <Button onClick={handleCreateSubscription} disabled={!newRecipient}>
                Add Subscription
              </Button>

              {subscriptionMessage && (
                <div className="text-sm text-red-600 dark:text-red-400">{subscriptionMessage.text}</div>
              )}
            </div>

            {subscriptions.length === 0 ? (
              <p className="text-sm text-text-secondary dark:text-secondary-dark">No subscriptions yet.</p>
            ) : (
              <ul className="space-y-2">
                {subscriptions.map((sub) => (
                  <li
                    key={sub.subscription_id}
                    className="flex items-center justify-between rounded-md border border-border dark:border-border-dark px-3 py-2 text-sm"
                  >
                    <div>
                      <span className="font-medium text-text-primary dark:text-text-primary-dark">{sub.recipient_email}</span>
                      <span className="text-text-secondary dark:text-secondary-dark">
                        {" "}
                        — {sub.project_name || "all projects"} — {sub.event_types ? sub.event_types.join(", ") : "all events"}
                      </span>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => handleDeleteSubscription(sub.subscription_id)}>
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {activeTab === "history" && (
        <div className="space-y-3">
          {deliveries.length === 0 ? (
            <p className="text-sm text-text-secondary dark:text-secondary-dark">No deliveries yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="text-text-secondary dark:text-secondary-dark">
                    <th className="pr-4 py-1">Event</th>
                    <th className="pr-4 py-1">Project</th>
                    <th className="pr-4 py-1">Recipient</th>
                    <th className="pr-4 py-1">Status</th>
                    <th className="pr-4 py-1">Last failure</th>
                  </tr>
                </thead>
                <tbody>
                  {deliveries.map((delivery) => (
                    <tr key={delivery.delivery_id} className="border-t border-border dark:border-border-dark">
                      <td className="pr-4 py-1 text-text-primary dark:text-text-primary-dark">{delivery.event_type}</td>
                      <td className="pr-4 py-1 text-text-primary dark:text-text-primary-dark">{delivery.project_name || "—"}</td>
                      <td className="pr-4 py-1 text-text-primary dark:text-text-primary-dark">{delivery.recipient_email}</td>
                      <td className="pr-4 py-1 text-text-primary dark:text-text-primary-dark">{delivery.status}</td>
                      <td className="pr-4 py-1 text-red-600 dark:text-red-400">{delivery.last_error || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default WorkspaceNotifications;

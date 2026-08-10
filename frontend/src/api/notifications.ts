import apiClient from "./apiClient";

/**
 * Send a test email using the installation's SMTP_* env var configuration.
 * Authentication is handled by apiClient's session cookie.
 */
export const sendTestEmail = async (
  recipientEmail: string
): Promise<{ success: boolean; message: string }> => {
  try {
    const response = await apiClient.post("/api/notifications/test-email", {
      recipient_email: recipientEmail,
    });
    return { success: true, message: response.data.message };
  } catch (error: any) {
    if (error.response?.data?.detail) {
      return { success: false, message: String(error.response.data.detail) };
    }
    return { success: false, message: "Network error" };
  }
};

export const NOTIFICATION_EVENT_TYPES = [
  "drift.detected",
  "drift.resolved",
  "drift.check_failed",
  "campaign.opened",
  "campaign.partially_failed",
  "campaign.completed",
  "campaign_pr.merged",
  "campaign_pr.closed",
  "campaign_pr.failed",
] as const;

export interface NotificationSubscription {
  subscription_id: number;
  recipient_email: string;
  project_id: number | null;
  project_name: string | null;
  event_types: string[] | null;
  notify_on_resolved: boolean;
}

export interface NotificationDelivery {
  delivery_id: number;
  event_type: string;
  project_id: number;
  project_name: string | null;
  recipient_email: string;
  status: string;
  attempt_count: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export const fetchSubscriptions = async (): Promise<NotificationSubscription[]> => {
  try {
    const response = await apiClient.get<NotificationSubscription[]>("/api/notifications/subscriptions");
    return response.data;
  } catch (error) {
    console.error("❌ Error fetching notification subscriptions:", error);
    return [];
  }
};

export const createSubscription = async (params: {
  recipientEmail: string;
  projectId: number | null;
  eventTypes: string[] | null;
  notifyOnResolved: boolean;
}): Promise<{ success: boolean; message?: string }> => {
  try {
    await apiClient.post("/api/notifications/subscriptions", {
      recipient_email: params.recipientEmail,
      project_id: params.projectId,
      event_types: params.eventTypes,
      notify_on_resolved: params.notifyOnResolved,
    });
    return { success: true };
  } catch (error: any) {
    if (error.response?.data?.detail) {
      return { success: false, message: String(error.response.data.detail) };
    }
    return { success: false, message: "Network error" };
  }
};

export const deleteSubscription = async (subscriptionId: number): Promise<{ success: boolean; message?: string }> => {
  try {
    await apiClient.delete(`/api/notifications/subscriptions/${subscriptionId}`);
    return { success: true };
  } catch (error: any) {
    if (error.response?.data?.detail) {
      return { success: false, message: String(error.response.data.detail) };
    }
    return { success: false, message: "Network error" };
  }
};

export const fetchDeliveries = async (): Promise<NotificationDelivery[]> => {
  try {
    const response = await apiClient.get<NotificationDelivery[]>("/api/notifications/deliveries");
    return response.data;
  } catch (error) {
    console.error("❌ Error fetching notification deliveries:", error);
    return [];
  }
};
